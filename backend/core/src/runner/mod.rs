//! Private native project-check implementation. No caller-controlled programs or argv.
#[cfg(windows)]
mod assets;
#[cfg(windows)]
mod python;
#[cfg(windows)]
mod rust;
#[cfg(windows)]
mod windows;

#[cfg(windows)]
use std::{
    sync::{
        Arc, OnceLock,
        atomic::{AtomicBool, AtomicUsize, Ordering},
    },
    time::{Duration, Instant},
};

#[cfg(windows)]
pub(super) struct Control {
    cancelled: AtomicBool,
    began: Instant,
    execution: OnceLock<Instant>,
    output_remaining: Arc<AtomicUsize>,
}
#[cfg(windows)]
impl Control {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            cancelled: AtomicBool::new(false),
            began: Instant::now(),
            execution: OnceLock::new(),
            output_remaining: Arc::new(AtomicUsize::new(32 * 1024)),
        })
    }
    fn preparation(&self) -> Result<(), String> {
        if self.cancelled.load(Ordering::SeqCst) {
            Err("cancelled".into())
        } else if self.began.elapsed() > Duration::from_secs(120) {
            Err("preparation_timeout".into())
        } else {
            Ok(())
        }
    }

    fn before_launch(&self) -> Result<(), String> {
        match self.execution.get() {
            None => self.preparation(),
            Some(_) if self.cancelled.load(Ordering::SeqCst) => Err("cancelled".into()),
            Some(started) if Self::execution_expired(*started) => Err("deadline_exceeded".into()),
            Some(_) => Ok(()),
        }
    }

    fn start_execution(&self) -> Instant {
        *self.execution.get_or_init(Instant::now)
    }

    fn execution_expired(started: Instant) -> bool {
        started.elapsed() >= Duration::from_secs(30)
    }
}
