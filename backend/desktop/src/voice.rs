//! Voice routing and buffering. Raw samples stay in memory and out of Core requests.
use crate::audio::Audio;
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use std::{
    collections::VecDeque,
    io::{BufRead, BufReader, Read, Write},
    path::Path,
    process::{Child, Command, Stdio},
    sync::mpsc::{self, Receiver, SyncSender},
    time::{Duration, Instant},
};

const RATE: usize = 16_000;
const MAX_TURN: usize = 20 * RATE;
const SILENCE: usize = 8_000;
const MIN_VOICE: usize = 2_400;
const WAKE_BATCH: usize = 1_280;

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Phase {
    Off,
    Starting,
    Wake,
    Listening,
    Processing,
    Speaking,
}

impl Phase {
    pub fn label(self) -> &'static str {
        match self {
            Self::Off => "Desligado",
            Self::Starting => "Iniciando voz local",
            Self::Wake => "Aguardando Artemis",
            Self::Listening => "Ouvindo",
            Self::Processing => "Processando",
            Self::Speaking => "Falando",
        }
    }
}

pub struct Transcript {
    pub text: String,
    pub language: String,
    pub overlap: bool,
}

#[derive(Default)]
struct Turn {
    samples: Vec<i16>,
    voice: usize,
    tail: usize,
}

impl Turn {
    fn push(&mut self, chunk: &[i16]) -> bool {
        let voiced = !chunk.is_empty()
            && chunk
                .iter()
                .map(|sample| {
                    let scaled = f32::from(*sample) / 32768.0;
                    scaled * scaled
                })
                .sum::<f32>()
                / chunk.len() as f32
                >= 0.000144;
        if voiced {
            self.voice += chunk.len();
            self.tail = 0;
        } else if self.voice == 0 {
            return false;
        } else {
            self.tail += chunk.len();
        }
        let space = MAX_TURN.saturating_sub(self.samples.len());
        self.samples
            .extend_from_slice(&chunk[..chunk.len().min(space)]);
        self.samples.len() == MAX_TURN || self.tail >= SILENCE
    }
}

pub struct Voice {
    pub audio: Audio,
    pub phase: Phase,
    pub input: Option<String>,
    pub output: Option<String>,
    pub wake_name: String,
    pub translator: bool,
    pub error: Option<String>,
    pub voice_id: Option<String>,
    worker: Option<Worker>,
    pending: Option<(&'static str, Instant)>,
    armed: bool,
    diagnostic: bool,
    queued: Vec<i16>,
    turn: Turn,
    speech: VecDeque<String>,
    speech_language: String,
    since: Instant,
}

impl Voice {
    pub fn new() -> Self {
        Self {
            audio: Audio::new(),
            phase: Phase::Off,
            input: None,
            output: None,
            wake_name: "Artemis".into(),
            translator: false,
            error: None,
            voice_id: None,
            worker: None,
            pending: None,
            armed: false,
            diagnostic: false,
            queued: Vec::new(),
            turn: Turn::default(),
            speech: VecDeque::new(),
            speech_language: String::new(),
            since: Instant::now(),
        }
    }

    pub fn enable(&mut self, diagnostic: bool) -> Result<(), String> {
        if self.phase != Phase::Off {
            return Err("A voz já está ativa.".into());
        }
        self.error = None;
        self.diagnostic = diagnostic;
        self.worker = Some(Worker::start()?);
        self.armed = true;
        self.phase = Phase::Starting;
        self.request("health", json!({}));
        Ok(())
    }

    pub fn disable(&mut self) {
        self.audio.stop_capture();
        self.audio.stop_playback();
        self.pending = None;
        self.worker = None;
        self.armed = false;
        self.queued.clear();
        self.speech.clear();
        self.turn = Turn::default();
        self.phase = Phase::Off;
    }

    fn fail(&mut self, message: String) {
        self.disable();
        self.error = Some(message);
    }

    pub fn resume(&mut self) {
        self.audio.stop_playback();
        self.speech.clear();
        self.turn = Turn::default();
        self.queued.clear();
        while self.audio.take_frame().is_some() {}
        self.since = Instant::now();
        if !self.armed {
            self.phase = Phase::Off;
        } else if self.translator {
            self.phase = Phase::Listening;
        } else {
            self.phase = Phase::Wake;
            self.request("wake_reset", json!({"name":self.wake_name}));
        }
    }

    pub fn interrupt(&mut self) {
        if self.phase == Phase::Off {
            return;
        }
        // A synchronous worker operation cannot be revoked in Python. Drop it
        // so an old synthesis result cannot play after the user interrupts.
        if self
            .pending
            .is_some_and(|(action, _)| matches!(action, "synthesize" | "transcribe"))
        {
            let diagnostic = self.diagnostic;
            self.disable();
            if let Err(error) = self.enable(diagnostic) {
                self.error = Some(error);
            }
        } else if self.pending.is_none() {
            self.resume();
        } else {
            self.audio.stop_playback();
        }
    }

    pub fn switch(&mut self, input: Option<String>, output: Option<String>) -> Result<(), String> {
        let enabled = self.armed;
        let diagnostic = self.diagnostic;
        self.disable();
        self.input = input;
        self.output = output;
        if enabled {
            self.enable(diagnostic)?;
        }
        Ok(())
    }

    pub fn set_translator(&mut self, active: bool) {
        if self.translator == active {
            return;
        }
        self.translator = active;
        if self.armed
            && self.pending.is_none()
            && matches!(self.phase, Phase::Wake | Phase::Listening)
        {
            self.resume();
        }
    }

    pub fn speak(&mut self, text: &str, language: &str) {
        if self.phase != Phase::Processing || self.pending.is_some() {
            return;
        }
        self.speech = speech_chunks(text);
        self.speech_language = language.into();
        self.speak_next();
    }

    fn speak_next(&mut self) {
        if let Some(text) = self.speech.pop_front() {
            self.phase = Phase::Processing;
            self.request(
                "synthesize",
                json!({"text":text,"language":self.speech_language}),
            );
        } else {
            self.resume();
        }
    }

    fn request(&mut self, action: &'static str, mut value: Value) {
        value["action"] = json!(action);
        let sent = self
            .worker
            .as_ref()
            .is_some_and(|worker| worker.input.try_send(value).is_ok());
        if sent {
            self.pending = Some((action, Instant::now()));
        } else {
            self.fail("O adaptador local de voz ficou indisponível.".into());
        }
    }

    pub fn diagnostic_pcm(&mut self, pcm: &str) -> Result<(), String> {
        if !self.diagnostic || !matches!(self.phase, Phase::Wake | Phase::Listening) {
            return Err("A entrada de diagnóstico não está ativa.".into());
        }
        let samples = decode(pcm)?;
        if samples.len() > RATE / 2 || self.queued.len() + samples.len() > RATE {
            return Err("Envie quadros de até meio segundo e aguarde o consumo.".into());
        }
        self.queued.extend(samples);
        Ok(())
    }

    pub fn tick(&mut self) -> Option<Transcript> {
        if let Some(error) = self.audio.take_error() {
            self.fail(error);
        }
        if self.armed && !self.diagnostic && !Audio::session_allowed() {
            self.disable();
            return None;
        }
        if let Some((action, began)) = self.pending {
            let reply = self.worker.as_ref()?.output.try_recv();
            match reply {
                Ok(Ok(value)) => {
                    self.pending = None;
                    match action {
                        "health" => {
                            if ["wake", "stt", "tts"].iter().any(|key| value[*key] != true) {
                                self.fail("O pacote local de voz está incompleto.".into());
                            } else {
                                self.voice_id = value["voice"].as_str().map(str::to_owned);
                                self.request("wake_reset", json!({"name":self.wake_name}));
                            }
                        }
                        "wake_reset" if self.phase == Phase::Wake && self.translator => {
                            self.phase = Phase::Listening;
                            self.queued.clear();
                        }
                        "wake_reset" if self.phase == Phase::Starting => {
                            if !self.diagnostic {
                                if let Err(error) = self.audio.start(self.input.as_deref()) {
                                    self.fail(error);
                                    return None;
                                }
                            }
                            self.phase = if self.translator {
                                Phase::Listening
                            } else {
                                Phase::Wake
                            };
                            self.since = Instant::now();
                        }
                        "wake" if value["detected"] == true || self.translator => {
                            self.queued.clear();
                            while self.audio.take_frame().is_some() {}
                            self.turn = Turn::default();
                            self.phase = Phase::Listening;
                            self.since = Instant::now();
                        }
                        "transcribe" => {
                            let text = value["text"].as_str().unwrap_or_default();
                            let language = value["language"].as_str().unwrap_or_default();
                            let overlap = value["ambiguous"] == true
                                || value["confidence"].as_f64().unwrap_or(0.0) < 0.60;
                            if text.trim().is_empty() || !matches!(language, "pt-BR" | "en-US") {
                                self.resume();
                            } else {
                                return Some(Transcript {
                                    text: text.into(),
                                    language: language.into(),
                                    overlap,
                                });
                            }
                        }
                        "synthesize" => {
                            let rate = value["sample_rate"]
                                .as_u64()
                                .and_then(|rate| u32::try_from(rate).ok());
                            let audio = value["pcm"]
                                .as_str()
                                .ok_or_else(|| "Áudio sintetizado ausente.".into())
                                .and_then(decode);
                            let result = audio.and_then(|audio| {
                                self.audio.play(
                                    audio,
                                    rate.ok_or("Taxa de áudio inválida.")?,
                                    self.output.as_deref(),
                                )
                            });
                            match result {
                                Ok(()) => {
                                    self.phase = Phase::Speaking;
                                    self.since = Instant::now();
                                }
                                Err(error) => self.fail(error),
                            }
                        }
                        _ => {}
                    }
                }
                Ok(Err(error)) => self.fail(error),
                Err(mpsc::TryRecvError::Disconnected) => {
                    self.fail("O adaptador local de voz encerrou.".into())
                }
                Err(mpsc::TryRecvError::Empty) if began.elapsed() > Duration::from_secs(90) => {
                    self.fail("O adaptador local de voz excedeu o tempo de resposta.".into());
                }
                Err(mpsc::TryRecvError::Empty) => {}
            }
        }
        while let Some(chunk) = self.audio.take_frame() {
            if matches!(self.phase, Phase::Wake | Phase::Listening) && self.queued.len() < RATE {
                self.queued.extend(chunk);
            }
        }
        if self.pending.is_some() {
            return None;
        }
        match self.phase {
            Phase::Wake if self.queued.len() >= WAKE_BATCH => {
                let count = self.queued.len().min(RATE / 2);
                let pcm = encode(&self.queued.drain(..count).collect::<Vec<_>>());
                self.request("wake", json!({"pcm":pcm}));
            }
            Phase::Listening => {
                let samples = std::mem::take(&mut self.queued);
                if samples.chunks(RATE / 50).any(|frame| self.turn.push(frame)) {
                    let turn = std::mem::take(&mut self.turn);
                    if turn.voice >= MIN_VOICE {
                        self.phase = Phase::Processing;
                        self.request("transcribe", json!({"pcm":encode(&turn.samples)}));
                    }
                } else if !self.translator
                    && self.turn.voice == 0
                    && self.since.elapsed() > Duration::from_secs(9)
                {
                    self.resume();
                }
            }
            Phase::Speaking
                if self.since.elapsed() > Duration::from_millis(200)
                    && !self.audio.levels().speaking =>
            {
                self.speak_next()
            }
            _ => {}
        }
        None
    }

    pub fn status(&self) -> Value {
        let levels = self.audio.levels();
        let phase = if self.phase == Phase::Wake {
            format!("Aguardando {}", self.wake_name)
        } else {
            self.phase.label().into()
        };
        json!({"phase":phase,"capturing":levels.capturing,"speaking":levels.speaking,
            "input_level":levels.input,"output_level":levels.output,"eligible":levels.eligible,
            "wake_name":self.wake_name,"voice":self.voice_id,"error":self.error,"diagnostic":self.diagnostic,
            "queued_samples":self.queued.len()})
    }
}

fn speech_chunks(text: &str) -> VecDeque<String> {
    let mut chunks = VecDeque::new();
    let mut remaining = text.trim();
    while let Some((limit, _)) = remaining.char_indices().nth(500) {
        let boundary = remaining[..limit]
            .rfind(char::is_whitespace)
            .filter(|index| *index > 0)
            .unwrap_or(limit);
        chunks.push_back(remaining[..boundary].trim().into());
        remaining = remaining[boundary..].trim_start();
    }
    if !remaining.is_empty() {
        chunks.push_back(remaining.into());
    }
    chunks
}

fn encode(samples: &[i16]) -> String {
    STANDARD.encode(
        samples
            .iter()
            .flat_map(|sample| sample.to_le_bytes())
            .collect::<Vec<_>>(),
    )
}

fn decode(pcm: &str) -> Result<Vec<i16>, String> {
    let bytes = STANDARD.decode(pcm).map_err(|_| "PCM Base64 inválido.")?;
    if bytes.is_empty() || bytes.len() % 2 != 0 {
        return Err("PCM16 inválido.".into());
    }
    Ok(bytes
        .chunks_exact(2)
        .map(|bytes| i16::from_le_bytes([bytes[0], bytes[1]]))
        .collect())
}

struct Worker {
    input: SyncSender<Value>,
    output: Receiver<Result<Value, String>>,
    child: Child,
}

impl Worker {
    fn start() -> Result<Self, String> {
        let python = std::env::var_os("SYNAPSE_VOICE_PYTHON")
            .ok_or("Configure SYNAPSE_VOICE_PYTHON para o ambiente local de voz.")?;
        if !Path::new(&python).is_absolute() {
            return Err("Use um caminho absoluto para SYNAPSE_VOICE_PYTHON.".into());
        }
        let package = Path::new(env!("CARGO_MANIFEST_DIR")).join("../python");
        let mut command = Command::new(python);
        command.args(["-I","-u","-c","import runpy,sys;sys.path.insert(0,sys.argv[1]);runpy.run_module('synapse_ai.voice_worker',run_name='__main__')"])
            .arg(package).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command.spawn().map_err(|error| error.to_string())?;
        let mut stdin = child.stdin.take().expect("piped voice input");
        let mut stdout = BufReader::new(child.stdout.take().expect("piped voice output"));
        let (input, requests) = mpsc::sync_channel::<Value>(1);
        let (replies, output) = mpsc::sync_channel(1);
        std::thread::spawn(move || {
            for (index, mut request) in requests.into_iter().enumerate() {
                let id = index + 1;
                request["id"] = json!(id);
                let result = (|| -> Result<Value, String> {
                    serde_json::to_writer(&mut stdin, &request)
                        .map_err(|error| error.to_string())?;
                    stdin
                        .write_all(b"\n")
                        .and_then(|()| stdin.flush())
                        .map_err(|error| error.to_string())?;
                    let mut line = Vec::new();
                    (&mut stdout)
                        .take(8 * 1024 * 1024)
                        .read_until(b'\n', &mut line)
                        .map_err(|error| error.to_string())?;
                    if line.last() != Some(&b'\n') {
                        return Err("Resposta de voz local incompleta.".into());
                    }
                    let mut reply: Value =
                        serde_json::from_slice(&line).map_err(|error| error.to_string())?;
                    if reply["id"] != id {
                        return Err("Resposta de voz fora de sequência.".into());
                    }
                    if reply["ok"] == true {
                        Ok(reply["result"].take())
                    } else {
                        Err(reply["error"]["message"]
                            .as_str()
                            .unwrap_or("Falha no adaptador de voz.")
                            .into())
                    }
                })();
                if replies.send(result).is_err() {
                    break;
                }
            }
        });
        Ok(Self {
            input,
            output,
            child,
        })
    }
}

impl Drop for Worker {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn segments_speech_and_bounds_pcm() {
        let mut turn = Turn::default();
        assert!(!turn.push(&[0; 320]));
        assert!(turn.samples.is_empty());
        assert!(!turn.push(&[1200; MIN_VOICE]));
        assert!(turn.push(&[0; SILENCE]));
        assert_eq!(turn.voice, MIN_VOICE);
        assert_eq!(
            decode(&encode(&[0, -32768, 32767])).unwrap(),
            [0, -32768, 32767]
        );
    }
}
