use std::{
    mem::size_of,
    ptr::null_mut,
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering},
        mpsc::{self, Receiver, RecvTimeoutError, Sender, SyncSender},
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

use cpal::{
    Device, FromSample, Sample, SampleFormat, SizedSample, Stream, StreamConfig,
    traits::{DeviceTrait, HostTrait, StreamTrait},
};
use windows_sys::Win32::System::RemoteDesktop::{
    WTS_CURRENT_SESSION, WTS_SESSIONSTATE_UNLOCK, WTSActive, WTSFreeMemory, WTSINFOEXW,
    WTSQuerySessionInformationW, WTSSessionInfoEx,
};

use super::{Devices, Levels, SAMPLE_RATE};

const FRAME_SAMPLES: usize = (SAMPLE_RATE / 50) as usize;
const FRAME_CAPACITY: usize = 16;
const ECHO_TAIL_MS: u64 = 180;
const LOCK_CHECK: Duration = Duration::from_millis(150);
type Frame = [i16; FRAME_SAMPLES];
type Completion = SyncSender<Result<(), String>>;

enum Request {
    Capture(Option<String>, Completion),
    Play(Vec<i16>, u32, Option<String>, Completion),
    StopCapture(Completion),
    StopPlayback(Completion),
    Exit,
}

struct State {
    began: Instant,
    eligible: AtomicBool,
    capturing: AtomicBool,
    speaking: AtomicBool,
    finished: AtomicBool,
    output_fault: AtomicBool,
    input: AtomicU32,
    output: AtomicU32,
    last_input: AtomicU64,
    playback_end: AtomicU64,
    echo_until: AtomicU64,
}

impl State {
    fn new() -> Self {
        Self {
            began: Instant::now(),
            eligible: AtomicBool::new(session_allowed()),
            capturing: AtomicBool::new(false),
            speaking: AtomicBool::new(false),
            finished: AtomicBool::new(false),
            output_fault: AtomicBool::new(false),
            input: AtomicU32::new(0),
            output: AtomicU32::new(0),
            last_input: AtomicU64::new(0),
            playback_end: AtomicU64::new(0),
            echo_until: AtomicU64::new(0),
        }
    }

    fn now(&self) -> u64 {
        self.began.elapsed().as_millis() as u64
    }

    fn accepts_capture(&self) -> bool {
        self.eligible.load(Ordering::Acquire)
            && self.capturing.load(Ordering::Acquire)
            && !self.speaking.load(Ordering::Acquire)
            && self.now() >= self.echo_until.load(Ordering::Acquire)
    }
}

pub struct Audio {
    requests: Sender<Request>,
    frames: Receiver<Frame>,
    errors: Receiver<String>,
    worker: Option<JoinHandle<()>>,
    state: Arc<State>,
}

impl Audio {
    pub fn new() -> Self {
        let state = Arc::new(State::new());
        let (requests, receive) = mpsc::channel();
        let (frames_send, frames) = mpsc::sync_channel(FRAME_CAPACITY);
        let (errors_send, errors) = mpsc::sync_channel(4);
        let worker_state = Arc::clone(&state);
        let worker = thread::spawn(move || {
            Engine {
                input: None,
                output: None,
                frames: frames_send,
                errors: errors_send,
                state: worker_state,
            }
            .run(receive);
        });
        Self {
            requests,
            frames,
            errors,
            worker: Some(worker),
            state,
        }
    }

    pub fn session_allowed() -> bool {
        session_allowed()
    }

    pub fn devices(&self) -> Result<Devices, String> {
        let host = cpal::default_host();
        Ok(Devices {
            inputs: host
                .input_devices()
                .map_err(|e| e.to_string())?
                .filter_map(|device| name(&device))
                .collect(),
            outputs: host
                .output_devices()
                .map_err(|e| e.to_string())?
                .filter_map(|device| name(&device))
                .collect(),
        })
    }

    pub fn start(&mut self, input: Option<&str>) -> Result<(), String> {
        self.stop_capture();
        self.request(|reply| Request::Capture(input.map(str::to_owned), reply))
    }

    pub fn stop_capture(&mut self) {
        let _ = self.request(Request::StopCapture);
        while self.frames.try_recv().is_ok() {}
    }

    pub fn play(
        &mut self,
        samples: Vec<i16>,
        sample_rate: u32,
        output: Option<&str>,
    ) -> Result<(), String> {
        if !(8_000..=192_000).contains(&sample_rate)
            || samples.is_empty()
            || samples.len() > (sample_rate as usize * 120).min(5_760_000)
        {
            return Err("Áudio de resposta inválido ou acima do limite local.".into());
        }
        let result = self
            .request(|reply| Request::Play(samples, sample_rate, output.map(str::to_owned), reply));
        while self.frames.try_recv().is_ok() {}
        result
    }

    pub fn stop_playback(&mut self) {
        let _ = self.request(Request::StopPlayback);
        while self.frames.try_recv().is_ok() {}
    }

    pub fn take_frame(&mut self) -> Option<Vec<i16>> {
        if !self.state.accepts_capture() {
            while self.frames.try_recv().is_ok() {}
            return None;
        }
        let frame = self.frames.try_recv().ok()?;
        if !self.state.accepts_capture() {
            return None;
        }
        if !session_allowed() {
            self.state.eligible.store(false, Ordering::Release);
            self.stop_capture();
            self.stop_playback();
            return None;
        }
        Some(Vec::from(frame))
    }

    pub fn levels(&self) -> Levels {
        let eligible = self.state.eligible.load(Ordering::Acquire);
        let capturing = eligible && self.state.capturing.load(Ordering::Acquire);
        let speaking = eligible && self.state.speaking.load(Ordering::Acquire);
        let input_fresh = self
            .state
            .now()
            .saturating_sub(self.state.last_input.load(Ordering::Relaxed))
            < 180;
        Levels {
            input: if capturing && input_fresh {
                f32::from_bits(self.state.input.load(Ordering::Relaxed))
            } else {
                0.0
            },
            output: if speaking {
                f32::from_bits(self.state.output.load(Ordering::Relaxed))
            } else {
                0.0
            },
            capturing,
            speaking,
            eligible,
        }
    }

    pub fn take_error(&mut self) -> Option<String> {
        self.errors.try_recv().ok()
    }

    fn request(&self, make: impl FnOnce(Completion) -> Request) -> Result<(), String> {
        let (reply, receive) = mpsc::sync_channel(1);
        self.requests
            .send(make(reply))
            .map_err(|_| "O serviço local de áudio foi encerrado.".to_owned())?;
        receive
            .recv()
            .map_err(|_| "O serviço local de áudio foi encerrado.".to_owned())?
    }
}

impl Drop for Audio {
    fn drop(&mut self) {
        let _ = self.requests.send(Request::Exit);
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

struct Engine {
    input: Option<Stream>,
    output: Option<Stream>,
    frames: SyncSender<Frame>,
    errors: SyncSender<String>,
    state: Arc<State>,
}

impl Engine {
    fn run(mut self, requests: Receiver<Request>) {
        let mut next_session_check = Instant::now();
        loop {
            if Instant::now() >= next_session_check {
                let eligible = session_allowed();
                let was_eligible = self.state.eligible.swap(eligible, Ordering::AcqRel);
                if !eligible && (self.input.is_some() || self.output.is_some()) {
                    self.stop_capture();
                    self.stop_playback();
                    if was_eligible {
                        let _ = self.errors.try_send("Áudio suspenso. A sessão do Windows precisa estar ativa e desbloqueada.".into());
                    }
                }
                next_session_check = Instant::now() + LOCK_CHECK;
            }
            if self.input.is_some() && !self.state.capturing.load(Ordering::Acquire) {
                self.stop_capture();
            }
            if self.output.is_some()
                && (self.state.output_fault.load(Ordering::Acquire)
                    || self.state.finished.load(Ordering::Acquire)
                        && self.state.now() >= self.state.playback_end.load(Ordering::Acquire))
            {
                self.stop_playback();
            }
            match requests.recv_timeout(Duration::from_millis(20)) {
                Ok(Request::Capture(device, reply)) => {
                    let _ = reply.send(self.capture(device.as_deref()));
                }
                Ok(Request::Play(samples, rate, device, reply)) => {
                    let _ = reply.send(self.playback(samples, rate, device.as_deref()));
                }
                Ok(Request::StopCapture(reply)) => {
                    self.stop_capture();
                    let _ = reply.send(Ok(()));
                }
                Ok(Request::StopPlayback(reply)) => {
                    self.stop_playback();
                    let _ = reply.send(Ok(()));
                }
                Ok(Request::Exit) | Err(RecvTimeoutError::Disconnected) => break,
                Err(RecvTimeoutError::Timeout) => (),
            }
        }
        self.stop_capture();
        self.stop_playback();
    }

    fn verify_session(&self) -> Result<(), String> {
        let allowed = session_allowed();
        self.state.eligible.store(allowed, Ordering::Release);
        if allowed {
            Ok(())
        } else {
            Err("A sessão do Windows precisa estar ativa e desbloqueada.".into())
        }
    }

    fn capture(&mut self, selection: Option<&str>) -> Result<(), String> {
        self.verify_session()?;
        let device = device(selection, true)?;
        let supported = device.default_input_config().map_err(|e| e.to_string())?;
        let config = supported.config();
        verify_config(&config)?;
        let input = Capture::new(
            config.sample_rate,
            self.frames.clone(),
            Arc::clone(&self.state),
        );
        let state = Arc::clone(&self.state);
        let errors = self.errors.clone();
        let failure = move |error| {
            state.capturing.store(false, Ordering::Release);
            let _ = errors.try_send(format!("Entrada de áudio interrompida: {error}"));
        };
        let stream = match supported.sample_format() {
            SampleFormat::F32 => input.stream::<f32>(&device, &config, failure),
            SampleFormat::F64 => input.stream::<f64>(&device, &config, failure),
            SampleFormat::I16 => input.stream::<i16>(&device, &config, failure),
            SampleFormat::U16 => input.stream::<u16>(&device, &config, failure),
            SampleFormat::I24 => input.stream::<cpal::I24>(&device, &config, failure),
            SampleFormat::I32 => input.stream::<i32>(&device, &config, failure),
            _ => return Err("O formato nativo de entrada não é compatível.".into()),
        }
        .map_err(|e| e.to_string())?;
        self.verify_session()?;
        self.state.capturing.store(true, Ordering::Release);
        if let Err(error) = stream.play() {
            self.state.capturing.store(false, Ordering::Release);
            return Err(error.to_string());
        }
        self.input = Some(stream);
        Ok(())
    }

    fn playback(
        &mut self,
        samples: Vec<i16>,
        sample_rate: u32,
        selection: Option<&str>,
    ) -> Result<(), String> {
        self.verify_session()?;
        self.stop_playback();
        let device = device(selection, false)?;
        let supported = device.default_output_config().map_err(|e| e.to_string())?;
        let config = supported.config();
        verify_config(&config)?;
        let output = Playback {
            samples,
            source_rate: u64::from(sample_rate),
            cursor: 0,
            state: Arc::clone(&self.state),
        };
        let state = Arc::clone(&self.state);
        let errors = self.errors.clone();
        let failure = move |error| {
            state.output_fault.store(true, Ordering::Release);
            let _ = errors.try_send(format!("Saída de áudio interrompida: {error}"));
        };
        let stream = match supported.sample_format() {
            SampleFormat::F32 => output.stream::<f32>(&device, &config, failure),
            SampleFormat::F64 => output.stream::<f64>(&device, &config, failure),
            SampleFormat::I16 => output.stream::<i16>(&device, &config, failure),
            SampleFormat::U16 => output.stream::<u16>(&device, &config, failure),
            SampleFormat::I24 => output.stream::<cpal::I24>(&device, &config, failure),
            SampleFormat::I32 => output.stream::<i32>(&device, &config, failure),
            _ => return Err("O formato nativo de saída não é compatível.".into()),
        }
        .map_err(|e| e.to_string())?;
        self.verify_session()?;
        self.state.finished.store(false, Ordering::Release);
        self.state.output_fault.store(false, Ordering::Release);
        self.state.playback_end.store(0, Ordering::Release);
        self.state.speaking.store(true, Ordering::Release);
        if let Err(error) = stream.play() {
            self.state.speaking.store(false, Ordering::Release);
            return Err(error.to_string());
        }
        self.output = Some(stream);
        Ok(())
    }

    fn stop_capture(&mut self) {
        self.state.capturing.store(false, Ordering::Release);
        self.input.take();
        self.state.input.store(0, Ordering::Relaxed);
    }

    fn stop_playback(&mut self) {
        if self.output.take().is_some() {
            self.state
                .echo_until
                .store(self.state.now() + ECHO_TAIL_MS, Ordering::Release);
        }
        self.state.speaking.store(false, Ordering::Release);
        self.state.output.store(0, Ordering::Relaxed);
    }
}

fn session_allowed() -> bool {
    let mut raw = null_mut();
    let mut bytes = 0;
    let ok = unsafe {
        WTSQuerySessionInformationW(
            null_mut(),
            WTS_CURRENT_SESSION,
            WTSSessionInfoEx,
            &mut raw,
            &mut bytes,
        )
    } != 0;
    let allowed = if ok && !raw.is_null() && bytes as usize >= size_of::<WTSINFOEXW>() {
        // The API allocates and aligns this buffer for WTSINFOEXW.
        let info = unsafe { &*raw.cast::<WTSINFOEXW>() };
        session_info_allowed(info)
    } else {
        false
    };
    if !raw.is_null() {
        unsafe { WTSFreeMemory(raw.cast()) };
    }
    allowed
}

fn session_info_allowed(info: &WTSINFOEXW) -> bool {
    if info.Level != 1 {
        return false;
    }
    let session = unsafe { &info.Data.WTSInfoExLevel1 };
    session.SessionId != 0
        && session.SessionState == WTSActive
        && session.SessionFlags as u32 == WTS_SESSIONSTATE_UNLOCK
        && session.UserName[0] != 0
}

fn name(device: &Device) -> Option<String> {
    device
        .description()
        .ok()
        .map(|description| description.name().to_owned())
}

fn device(selection: Option<&str>, input: bool) -> Result<Device, String> {
    let host = cpal::default_host();
    if let Some(selected) = selection {
        let devices: Vec<_> = if input {
            host.input_devices().map_err(|e| e.to_string())?.collect()
        } else {
            host.output_devices().map_err(|e| e.to_string())?.collect()
        };
        let mut matches = devices
            .into_iter()
            .filter(|device| name(device).as_deref() == Some(selected));
        let device = matches
            .next()
            .ok_or_else(|| "Dispositivo de áudio selecionado indisponível.".to_owned())?;
        if matches.next().is_some() {
            return Err("Há mais de um dispositivo com esse nome.".into());
        }
        Ok(device)
    } else {
        (if input {
            host.default_input_device()
        } else {
            host.default_output_device()
        })
        .ok_or_else(|| "Dispositivo de áudio padrão indisponível.".to_owned())
    }
}

fn verify_config(config: &StreamConfig) -> Result<(), String> {
    if !(8_000..=192_000).contains(&config.sample_rate) || !(1..=32).contains(&config.channels) {
        return Err("A configuração nativa de áudio está fora dos limites compatíveis.".into());
    }
    Ok(())
}

struct Capture {
    rate: u32,
    phase: u32,
    sum: f32,
    frame: Frame,
    filled: usize,
    frames: SyncSender<Frame>,
    state: Arc<State>,
}

impl Capture {
    fn new(rate: u32, frames: SyncSender<Frame>, state: Arc<State>) -> Self {
        Self {
            rate,
            phase: 0,
            sum: 0.0,
            frame: [0; FRAME_SAMPLES],
            filled: 0,
            frames,
            state,
        }
    }

    fn reset(&mut self) {
        self.phase = 0;
        self.sum = 0.0;
        self.frame.fill(0);
        self.filled = 0;
    }

    fn add_sample(&mut self, sample: f32) {
        let mut duration = SAMPLE_RATE;
        // Integrate fractional source intervals in each 16 kHz sample bin.
        while duration > 0 {
            let overlap = duration.min(self.rate - self.phase);
            self.sum += sample * overlap as f32;
            self.phase += overlap;
            duration -= overlap;
            if self.phase == self.rate {
                self.frame[self.filled] = i16::from_sample(self.sum / self.rate as f32);
                self.filled += 1;
                self.phase = 0;
                self.sum = 0.0;
                if self.filled == FRAME_SAMPLES {
                    if self.state.accepts_capture() {
                        let _ = self.frames.try_send(self.frame);
                    }
                    self.filled = 0;
                }
            }
        }
    }

    fn stream<T>(
        mut self,
        device: &Device,
        config: &StreamConfig,
        failure: impl FnMut(cpal::StreamError) + Send + 'static,
    ) -> Result<Stream, cpal::BuildStreamError>
    where
        T: SizedSample,
        f32: FromSample<T>,
    {
        let channels = usize::from(config.channels);
        device.build_input_stream(
            config,
            move |samples: &[T], _| {
                if !self.state.accepts_capture() {
                    self.reset();
                    self.state.input.store(0, Ordering::Relaxed);
                    return;
                }
                let mut square = 0.0;
                let mut count = 0u32;
                for frame in samples.chunks_exact(channels) {
                    let mixed = frame
                        .iter()
                        .copied()
                        .map(|value| f32::from_sample(value))
                        .sum::<f32>()
                        / channels as f32;
                    let mixed = if mixed.is_finite() {
                        mixed.clamp(-1.0, 1.0)
                    } else {
                        0.0
                    };
                    square += mixed * mixed;
                    count += 1;
                    self.add_sample(mixed);
                }
                self.state
                    .input
                    .store(rms(square, count).to_bits(), Ordering::Relaxed);
                self.state
                    .last_input
                    .store(self.state.now(), Ordering::Relaxed);
            },
            failure,
            None,
        )
    }
}

struct Playback {
    samples: Vec<i16>,
    source_rate: u64,
    cursor: u64,
    state: Arc<State>,
}

impl Playback {
    fn stream<T>(
        mut self,
        device: &Device,
        config: &StreamConfig,
        failure: impl FnMut(cpal::StreamError) + Send + 'static,
    ) -> Result<Stream, cpal::BuildStreamError>
    where
        T: SizedSample + FromSample<f32>,
    {
        let channels = usize::from(config.channels);
        let rate = u64::from(config.sample_rate);
        device.build_output_stream(
            config,
            move |samples: &mut [T], info| {
                if !self.state.eligible.load(Ordering::Acquire)
                    || self.state.finished.load(Ordering::Acquire)
                {
                    samples.fill(T::from_sample(0.0));
                    return;
                }
                let mut square = 0.0;
                let mut count = 0;
                for frame in samples.chunks_exact_mut(channels) {
                    let index = (self.cursor / rate) as usize;
                    let sample = if let Some(&left) = self.samples.get(index) {
                        let right = self.samples.get(index + 1).copied().unwrap_or(left);
                        let fraction = (self.cursor % rate) as f32 / rate as f32;
                        let mixed = f32::from_sample(left) * (1.0 - fraction)
                            + f32::from_sample(right) * fraction;
                        square += mixed * mixed;
                        count += 1;
                        self.cursor += self.source_rate;
                        mixed
                    } else {
                        0.0
                    };
                    frame.fill(T::from_sample(sample));
                }
                self.state
                    .output
                    .store(rms(square, count).to_bits(), Ordering::Relaxed);
                if (self.cursor / rate) as usize >= self.samples.len() {
                    let stamp = info.timestamp();
                    let latency = stamp
                        .playback
                        .duration_since(&stamp.callback)
                        .unwrap_or_default()
                        .as_millis() as u64;
                    let samples_ms = (u64::from(count) * 1000).div_ceil(rate);
                    self.state.playback_end.store(
                        self.state.now() + latency.min(1000) + samples_ms,
                        Ordering::Release,
                    );
                    self.state.finished.store(true, Ordering::Release);
                }
            },
            failure,
            None,
        )
    }
}

fn rms(square: f32, count: u32) -> f32 {
    (square / count.max(1) as f32).sqrt().clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capture_resamples_fractional_rates_and_gates_output() {
        let state = Arc::new(State::new());
        state.eligible.store(true, Ordering::Release);
        state.capturing.store(true, Ordering::Release);
        let (send, receive) = mpsc::sync_channel(FRAME_CAPACITY);
        let mut capture = Capture::new(44_100, send, Arc::clone(&state));
        for _ in 0..882 {
            capture.add_sample(0.25);
        }
        assert!(
            receive
                .try_recv()
                .unwrap()
                .iter()
                .all(|&value| value == 8192)
        );
        assert!(receive.try_recv().is_err());
        state.speaking.store(true, Ordering::Release);
        for _ in 0..882 {
            capture.add_sample(0.25);
        }
        assert!(receive.try_recv().is_err());
    }

    #[test]
    fn locked_disconnected_unknown_and_service_sessions_are_ineligible() {
        use windows_sys::Win32::System::RemoteDesktop::{
            WTSDisconnected, WTSINFOEX_LEVEL_W, WTSINFOEX_LEVEL1_W,
        };
        let mut session = WTSINFOEX_LEVEL1_W {
            SessionId: 1,
            SessionState: WTSActive,
            SessionFlags: WTS_SESSIONSTATE_UNLOCK as i32,
            ..Default::default()
        };
        session.UserName[0] = u16::from(b'u');
        let info = |session| WTSINFOEXW {
            Level: 1,
            Data: WTSINFOEX_LEVEL_W {
                WTSInfoExLevel1: session,
            },
        };
        assert!(session_info_allowed(&info(session)));
        assert!(!session_info_allowed(&info(WTSINFOEX_LEVEL1_W {
            SessionFlags: 0,
            ..session
        })));
        assert!(!session_info_allowed(&info(WTSINFOEX_LEVEL1_W {
            SessionFlags: -1,
            ..session
        })));
        assert!(!session_info_allowed(&info(WTSINFOEX_LEVEL1_W {
            SessionState: WTSDisconnected,
            ..session
        })));
        assert!(!session_info_allowed(&info(WTSINFOEX_LEVEL1_W {
            SessionId: 0,
            ..session
        })));
        assert!(!session_info_allowed(&info(WTSINFOEX_LEVEL1_W {
            UserName: [0; 21],
            ..session
        })));
        assert!(!session_info_allowed(&WTSINFOEXW::default()));
    }

    #[test]
    #[ignore = "requires an unlocked Windows session and real local microphone and speakers"]
    fn native_devices_capture_stop_and_drain_playback() {
        assert!(
            Audio::session_allowed(),
            "Windows session is not eligible for audio"
        );
        let mut audio = Audio::new();
        let devices = audio.devices().unwrap();
        assert!(!devices.inputs.is_empty());
        assert!(!devices.outputs.is_empty());
        let selected = cpal::default_host()
            .default_input_device()
            .as_ref()
            .and_then(name)
            .unwrap();
        audio.start(Some(&selected)).unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            if let Some(frame) = audio.take_frame() {
                assert_eq!(frame.len(), FRAME_SAMPLES);
                break;
            }
            assert!(
                Instant::now() < deadline,
                "Audio frame did not arrive: {:?}",
                audio.take_error()
            );
            thread::sleep(Duration::from_millis(15));
        }
        assert!(audio.levels().capturing);
        audio.stop_capture();
        assert!(!audio.levels().capturing);
        assert!(audio.take_frame().is_none());

        // A silent fixture exercises the physical output endpoint without a tone.
        audio.play(vec![0; 4400], 44_100, None).unwrap();
        assert!(audio.levels().speaking);
        let deadline = Instant::now() + Duration::from_secs(5);
        while audio.levels().speaking {
            assert!(
                Instant::now() < deadline,
                "Playback did not finish: {:?}",
                audio.take_error()
            );
            thread::sleep(Duration::from_millis(15));
        }
        audio.play(vec![0; 44_100], 44_100, None).unwrap();
        assert!(audio.levels().speaking);
        audio.stop_playback();
        assert!(!audio.levels().speaking);
        assert!(audio.take_error().is_none());
    }
}
