//! Voice routing and buffering. Raw samples stay in memory and out of Core requests.
use crate::audio::Audio;
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use std::{
    collections::VecDeque,
    ffi::OsStr,
    io::{BufRead, BufReader, Read, Write},
    path::{Path, PathBuf},
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
    pub idle_seconds: u64,
    conversation_open: bool,
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
            idle_seconds: 30,
            conversation_open: false,
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
        self.conversation_open = false;
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
        } else if self.translator || self.conversation_open {
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
        self.conversation_open = false;
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
                            self.conversation_open = !self.translator;
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
                }
                if self.phase == Phase::Listening && self.conversation_idle(self.since.elapsed()) {
                    self.conversation_open = false;
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

    fn conversation_idle(&self, elapsed: Duration) -> bool {
        self.conversation_open
            && !self.translator
            && self.turn.voice == 0
            && elapsed >= Duration::from_secs(self.idle_seconds)
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
            "queued_samples":self.queued.len(),"idle_seconds":self.idle_seconds})
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
    #[cfg(windows)]
    _job: std::os::windows::io::OwnedHandle,
}

#[cfg(windows)]
fn own_worker_process(child: &mut Child) -> Result<std::os::windows::io::OwnedHandle, String> {
    use std::{
        ffi::c_void,
        mem::size_of,
        os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle},
        ptr::null,
    };
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
        SetInformationJobObject,
    };
    let result = (|| {
        let raw = unsafe { CreateJobObjectW(null(), null()) };
        if raw.is_null() {
            return Err("Supervisão do processo de voz indisponível.".into());
        }
        let job = unsafe { OwnedHandle::from_raw_handle(raw) };
        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if unsafe {
            SetInformationJobObject(
                job.as_raw_handle(),
                JobObjectExtendedLimitInformation,
                &limits as *const _ as *const c_void,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        } == 0
            || unsafe { AssignProcessToJobObject(job.as_raw_handle(), child.as_raw_handle()) } == 0
        {
            return Err("Supervisão do processo de voz indisponível.".into());
        }
        Ok(job)
    })();
    if result.is_err() {
        let _ = child.kill();
        let _ = child.wait();
    }
    result
}

struct VoiceRuntime {
    python: PathBuf,
    models: Option<PathBuf>,
}

fn safe_runtime_path(path: &Path, directory: bool) -> Result<(), String> {
    if !path.is_absolute()
        || path
            .components()
            .any(|part| matches!(part, std::path::Component::ParentDir))
        || path.to_string_lossy().contains(['\0', '"'])
    {
        return Err("Configuração de voz local inválida.".into());
    }
    #[cfg(windows)]
    if path.components().any(|part|matches!(part,std::path::Component::Prefix(prefix) if !matches!(prefix.kind(),std::path::Prefix::Disk(_)|std::path::Prefix::VerbatimDisk(_)))) {
        return Err("A voz exige caminhos locais do computador.".into());
    }
    for ancestor in path.ancestors() {
        let metadata = std::fs::symlink_metadata(ancestor)
            .map_err(|_| "Caminho de voz local indisponível.")?;
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            if metadata.file_attributes() & 0x400 != 0 {
                return Err("Links não são permitidos na configuração de voz.".into());
            }
        }
        if metadata.file_type().is_symlink() {
            return Err("Links não são permitidos na configuração de voz.".into());
        }
    }
    let metadata = std::fs::metadata(path).map_err(|_| "Caminho de voz local indisponível.")?;
    if (directory && !metadata.is_dir()) || (!directory && !metadata.is_file()) {
        return Err("Configuração de voz local inválida.".into());
    }
    Ok(())
}

fn voice_runtime(
    path: Option<&Path>,
    python_override: Option<&OsStr>,
    models_override: Option<&OsStr>,
) -> Result<VoiceRuntime, String> {
    let mut python = None;
    let mut models = None;
    if let Some(path) = path {
        match std::fs::symlink_metadata(path) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
            Err(_) => return Err("Configuração de voz local indisponível.".into()),
            Ok(metadata) => {
                safe_runtime_path(path, false)?;
                if metadata.len() > 16_384 {
                    return Err("Configuração de voz local inválida.".into());
                }
                let value: Value = serde_json::from_slice(
                    &std::fs::read(path).map_err(|_| "Configuração de voz local indisponível.")?,
                )
                .map_err(|_| "Configuração de voz local inválida.")?;
                let values = value
                    .as_object()
                    .ok_or("Configuração de voz local inválida.")?;
                if values.len() != 2
                    || !values.contains_key("python")
                    || !values.contains_key("models")
                {
                    return Err("Configuração de voz local inválida.".into());
                }
                python = Some(PathBuf::from(
                    values["python"]
                        .as_str()
                        .ok_or("Configuração de voz local inválida.")?,
                ));
                models = Some(PathBuf::from(
                    values["models"]
                        .as_str()
                        .ok_or("Configuração de voz local inválida.")?,
                ));
                safe_runtime_path(python.as_ref().unwrap(), false)?;
                safe_runtime_path(models.as_ref().unwrap(), true)?;
            }
        }
    }
    if let Some(value) = python_override {
        python = Some(PathBuf::from(value));
    }
    if let Some(value) = models_override {
        models = Some(PathBuf::from(value));
    }
    let python = python.ok_or("Configure o ambiente de voz em voice-runtime.json.")?;
    safe_runtime_path(&python, false)?;
    #[cfg(windows)]
    if !python
        .file_name()
        .is_some_and(|name| name.to_string_lossy().eq_ignore_ascii_case("python.exe"))
    {
        return Err("A voz exige o executável Python local.".into());
    }
    if let Some(models) = &models {
        safe_runtime_path(models, true)?;
    }
    Ok(VoiceRuntime { python, models })
}

fn configured_voice_runtime() -> Result<VoiceRuntime, String> {
    let root = std::env::var_os("SYNAPSE_CONFIG_ROOT")
        .map(PathBuf::from)
        .or_else(|| {
            std::env::var_os("LOCALAPPDATA").map(|root| PathBuf::from(root).join("Synapse"))
        });
    let config = root.map(|root| root.join("voice-runtime.json"));
    voice_runtime(
        config.as_deref(),
        std::env::var_os("SYNAPSE_VOICE_PYTHON").as_deref(),
        std::env::var_os("SYNAPSE_VOICE_MODELS").as_deref(),
    )
}

impl Worker {
    fn start() -> Result<Self, String> {
        let runtime = configured_voice_runtime()?;
        let package = synapse_core::python_package_root(
            &Path::new(env!("CARGO_MANIFEST_DIR")).join("../python"),
        )
        .map_err(|_| "Pacote Python do Synapse indisponível.")?;
        let mut command = Command::new(runtime.python);
        if let Some(models) = runtime.models {
            command.env("SYNAPSE_VOICE_MODELS", models);
        }
        command.args(["-I","-B","-u","-c","import runpy,sys;sys.path.insert(0,sys.argv[1]);runpy.run_module('synapse_ai.voice_worker',run_name='__main__')"])
            .arg(package).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command.spawn().map_err(|error| error.to_string())?;
        // No worker request is sent until the process belongs to our private job.
        #[cfg(windows)]
        let job = own_worker_process(&mut child)?;
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
            #[cfg(windows)]
            _job: job,
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

    #[cfg(windows)]
    #[test]
    #[ignore = "private subprocess fixture; does nothing without its explicit test flag"]
    fn synthetic_voice_job_child() {
        if std::env::var_os("SYNAPSE_TEST_VOICE_JOB_CHILD").is_some() {
            std::thread::sleep(Duration::from_secs(60));
        }
    }

    #[cfg(windows)]
    #[test]
    #[ignore = "private subprocess fixture; does nothing without its explicit test flag"]
    fn synthetic_voice_job_owner() {
        use std::os::windows::process::CommandExt;
        let Some(marker) = std::env::var_os("SYNAPSE_TEST_VOICE_JOB_PID") else {
            return;
        };
        let mut child = Command::new(std::env::current_exe().unwrap())
            .creation_flags(0x08000000)
            .args([
                "--exact",
                "voice::tests::synthetic_voice_job_child",
                "--ignored",
            ])
            .env("SYNAPSE_TEST_VOICE_JOB_CHILD", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let _job = own_worker_process(&mut child).unwrap();
        std::fs::write(marker, child.id().to_string()).unwrap();
        std::thread::sleep(Duration::from_secs(60));
        let _ = child.kill();
        let _ = child.wait();
    }

    #[cfg(windows)]
    #[test]
    fn abrupt_voice_owner_death_kills_its_owned_child() {
        use std::os::windows::{
            io::{AsRawHandle, FromRawHandle, OwnedHandle},
            process::CommandExt,
        };
        use windows_sys::Win32::System::Threading::{
            OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_SYNCHRONIZE, PROCESS_TERMINATE,
            TerminateProcess, WaitForSingleObject,
        };
        struct TestHost(Child);
        impl Drop for TestHost {
            fn drop(&mut self) {
                let _ = self.0.kill();
                let _ = self.0.wait();
            }
        }
        let fixture = RuntimeFixture::new();
        let marker = fixture.0.join("pid");
        let mut host = TestHost(
            Command::new(std::env::current_exe().unwrap())
                .creation_flags(0x08000000)
                .args([
                    "--exact",
                    "voice::tests::synthetic_voice_job_owner",
                    "--ignored",
                ])
                .env("SYNAPSE_TEST_VOICE_JOB_PID", &marker)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap(),
        );
        let deadline = Instant::now() + Duration::from_secs(20);
        while !marker.is_file() && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(20));
        }
        let pid: u32 = std::fs::read_to_string(&marker)
            .expect("Owned fixture process must publish its child")
            .parse()
            .unwrap();
        let raw = unsafe {
            OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE | PROCESS_SYNCHRONIZE,
                0,
                pid,
            )
        };
        assert!(
            !raw.is_null(),
            "Open only the child created by our synthetic owner"
        );
        let child = unsafe { OwnedHandle::from_raw_handle(raw) };
        host.0.kill().unwrap();
        host.0.wait().unwrap();
        let status = unsafe { WaitForSingleObject(child.as_raw_handle(), 5000) };
        if status != 0 {
            unsafe {
                TerminateProcess(child.as_raw_handle(), 1);
            };
        }
        assert_eq!(
            status, 0,
            "Closing the killed owner's job must kill its child"
        );
    }

    #[test]
    #[ignore = "requires an existing trusted persisted voice-runtime.json and local voice assets; no audio I/O"]
    fn persisted_voice_runtime_starts_real_worker_health() {
        let root = std::env::var_os("SYNAPSE_CONFIG_ROOT")
            .map(PathBuf::from)
            .or_else(|| {
                std::env::var_os("LOCALAPPDATA").map(|root| PathBuf::from(root).join("Synapse"))
            })
            .expect("Local configuration root is required");
        let configuration = root.join("voice-runtime.json");
        assert!(
            configuration.is_file(),
            "A persisted trusted voice runtime is required"
        );
        let selected = voice_runtime(Some(&configuration), None, None)
            .expect("Persisted voice configuration must validate without terminal overrides");
        assert!(selected.models.is_some());
        let worker = Worker::start().expect("Start only the configured trusted voice worker");
        worker.input.send(json!({"action":"health"})).unwrap();
        let health = worker
            .output
            .recv_timeout(Duration::from_secs(15))
            .expect("Voice health deadline")
            .expect("Voice worker health response");
        for component in ["wake", "stt", "tts"] {
            assert_eq!(
                health[component], true,
                "{component} dependency/assets unavailable"
            );
        }
        assert_eq!(health["voice"], "supertonic-3:F1");
        // Worker Drop kills and waits only for its owned process. Audio is never initialized.
        drop(worker);
    }

    struct RuntimeFixture(PathBuf);
    impl RuntimeFixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "synapse-voice-config-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
            std::fs::create_dir(&root).unwrap();
            std::fs::create_dir(root.join("models")).unwrap();
            std::fs::write(root.join("python.exe"), b"synthetic only").unwrap();
            Self(root)
        }
        fn config(&self, value: Value) -> PathBuf {
            let path = self.0.join("voice-runtime.json");
            std::fs::write(&path, serde_json::to_vec(&value).unwrap()).unwrap();
            path
        }
        fn valid(&self) -> Value {
            json!({"python":self.0.join("python.exe"),"models":self.0.join("models")})
        }
    }
    impl Drop for RuntimeFixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn persisted_voice_runtime_and_explicit_overrides_are_bounded() {
        let fixture = RuntimeFixture::new();
        let path = fixture.config(fixture.valid());
        let runtime = voice_runtime(Some(&path), None, None).unwrap();
        assert_eq!(runtime.python, fixture.0.join("python.exe"));
        assert_eq!(runtime.models, Some(fixture.0.join("models")));
        let other = RuntimeFixture::new();
        let runtime = voice_runtime(
            Some(&path),
            Some(other.0.join("python.exe").as_os_str()),
            Some(other.0.join("models").as_os_str()),
        )
        .unwrap();
        assert_eq!(runtime.python, other.0.join("python.exe"));
        assert_eq!(runtime.models, Some(other.0.join("models")));
        let missing = fixture.0.join("missing.json");
        assert!(voice_runtime(Some(&missing), None, None).is_err());
        let runtime = voice_runtime(
            Some(&missing),
            Some(fixture.0.join("python.exe").as_os_str()),
            None,
        )
        .unwrap();
        assert!(runtime.models.is_none());
    }

    #[test]
    fn malformed_unknown_and_unsafe_voice_configuration_is_rejected() {
        let fixture = RuntimeFixture::new();
        for value in [
            json!({}),
            json!({"python":"relative.exe","models":fixture.0.join("models")}),
            json!({"python":fixture.0.join("python.exe"),"models":fixture.0.join("models"),"command":"execute"}),
            json!({"python":fixture.0.join("missing.exe"),"models":fixture.0.join("models")}),
        ] {
            let path = fixture.config(value);
            assert!(voice_runtime(Some(&path), None, None).is_err());
        }
        let path = fixture.0.join("voice-runtime.json");
        std::fs::write(&path, b"{bad").unwrap();
        assert!(voice_runtime(Some(&path), None, None).is_err());
        std::fs::write(&path, vec![b' '; 16_385]).unwrap();
        assert!(voice_runtime(Some(&path), None, None).is_err());
        #[cfg(windows)]
        {
            std::fs::write(fixture.0.join("cmd.exe"), b"synthetic").unwrap();
            assert!(
                voice_runtime(None, Some(fixture.0.join("cmd.exe").as_os_str()), None).is_err()
            );
        }
    }

    #[cfg(windows)]
    #[test]
    fn voice_runtime_refuses_reparse_ancestors() {
        use std::os::windows::process::CommandExt;
        let fixture = RuntimeFixture::new();
        let target = RuntimeFixture::new();
        let link = fixture.0.join("link");
        let status = Command::new("cmd")
            .creation_flags(0x08000000)
            .args(["/c", "mklink", "/J"])
            .arg(&link)
            .arg(&target.0)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .unwrap();
        assert!(status.success(), "Fixture junction creation failed");
        let path = fixture
            .config(json!({"python":link.join("python.exe"),"models":target.0.join("models")}));
        assert!(voice_runtime(Some(&path), None, None).is_err());
    }

    #[test]
    fn conversation_window_survives_reply_and_expires_only_while_idle() {
        let mut voice = Voice::new();
        voice.armed = true;
        voice.conversation_open = true;
        voice.phase = Phase::Speaking;
        voice.resume();
        assert!(voice.phase == Phase::Listening);
        assert!(!voice.conversation_idle(Duration::from_secs(29)));
        assert!(voice.conversation_idle(Duration::from_secs(30)));
        voice.turn.voice = MIN_VOICE;
        assert!(!voice.conversation_idle(Duration::from_secs(60)));
        voice.turn.voice = 0;
        voice.translator = true;
        assert!(!voice.conversation_idle(Duration::from_secs(60)));
    }

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
