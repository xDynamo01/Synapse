//! In-memory device audio. Capture is delivered only as bounded 16 kHz mono frames.
#[cfg(windows)]
#[path = "audio/windows.rs"]
mod windows;
#[cfg(windows)]
pub use windows::Audio;

pub const SAMPLE_RATE: u32 = 16_000;

#[derive(Default)]
pub struct Devices {
    pub inputs: Vec<String>,
    pub outputs: Vec<String>,
}

#[derive(Clone, Copy, Default)]
pub struct Levels {
    pub input: f32,
    pub output: f32,
    pub capturing: bool,
    pub speaking: bool,
    pub eligible: bool,
}

#[cfg(not(windows))]
pub struct Audio;

#[cfg(not(windows))]
impl Audio {
    pub fn new() -> Self {
        Self
    }
    pub fn session_allowed() -> bool {
        false
    }
    pub fn devices(&self) -> Result<Devices, String> {
        Ok(Devices::default())
    }
    pub fn start(&mut self, _input: Option<&str>) -> Result<(), String> {
        Err("A captura local ainda não está habilitada nesta plataforma.".into())
    }
    pub fn play(
        &mut self,
        _samples: Vec<i16>,
        _sample_rate: u32,
        _output: Option<&str>,
    ) -> Result<(), String> {
        Err("A reprodução local ainda não está habilitada nesta plataforma.".into())
    }
    pub fn stop_capture(&mut self) {}
    pub fn stop_playback(&mut self) {}
    pub fn take_frame(&mut self) -> Option<Vec<i16>> {
        None
    }
    pub fn levels(&self) -> Levels {
        Levels::default()
    }
    pub fn take_error(&mut self) -> Option<String> {
        None
    }
}
