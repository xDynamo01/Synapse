//! Private native project-check implementation. No caller-controlled programs or argv.
#[cfg(windows)]
mod assets;
#[cfg(windows)]
mod native;
#[cfg(windows)]
mod python;
#[cfg(windows)]
mod rust;
#[cfg(windows)]
mod windows;
#[cfg(windows)]
pub(crate) use windows::{owner_sid, sid_text};

#[cfg(not(windows))]
use crate::contracts::CheckKind;
use crate::contracts::{CandidateArtifact, PlannedCheck};
use serde_json::Value;
use std::{
    path::PathBuf,
    sync::{
        Arc, Mutex, OnceLock,
        atomic::{AtomicBool, AtomicUsize, Ordering},
        mpsc::{self, Receiver, SyncSender},
    },
    thread::JoinHandle,
    time::{Duration, Instant},
};

pub(crate) struct Control {
    cancelled: AtomicBool,
    began: Instant,
    execution: OnceLock<Instant>,
    output_remaining: Arc<AtomicUsize>,
    resume: Mutex<()>,
}
impl Control {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            cancelled: AtomicBool::new(false),
            began: Instant::now(),
            execution: OnceLock::new(),
            output_remaining: Arc::new(AtomicUsize::new(32 * 1024)),
            resume: Mutex::new(()),
        })
    }
    pub(crate) fn lock_resume(&self) -> std::sync::MutexGuard<'_, ()> {
        self.resume
            .lock()
            .unwrap_or_else(|error| error.into_inner())
    }
    pub(crate) fn signal_cancel(&self) {
        self.cancelled.store(true, Ordering::SeqCst);
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

#[cfg(windows)]
pub(crate) use native::Tools;

#[cfg(not(windows))]
pub(crate) struct Tools;

#[cfg(not(windows))]
impl Tools {
    pub(crate) fn configure(_: &CheckKind) -> Result<Self, &'static str> {
        Err("containment_unavailable")
    }
}

pub(crate) struct Launch {
    pub id: String,
    pub mission_id: String,
    pub root: PathBuf,
    pub profile_name: String,
    pub artifacts: Vec<CandidateArtifact>,
    pub recipe: PlannedCheck,
    pub tools: Tools,
}

pub(crate) struct Outcome {
    pub receipt: Option<Value>,
    pub error: Option<&'static str>,
    pub cleanup_complete: bool,
}

pub(crate) enum Event {
    Prepared(String),
    Finished(Outcome),
}

pub(crate) struct Active {
    pub id: String,
    pub mission_id: String,
    pub events: Receiver<Event>,
    pub permit: SyncSender<()>,
    control: Arc<Control>,
    thread: JoinHandle<()>,
}

impl Active {
    pub(crate) fn start(launch: Launch) -> Self {
        let id = launch.id.clone();
        let mission_id = launch.mission_id.clone();
        let control = Control::new();
        let worker_control = control.clone();
        let (sender, events) = mpsc::sync_channel(2);
        let (permit, authorization) = mpsc::sync_channel(1);
        let thread = std::thread::spawn(move || {
            #[cfg(windows)]
            let result = native::run(launch, &worker_control, &sender, &authorization);
            #[cfg(not(windows))]
            let result = {
                let _ = (launch, worker_control, authorization);
                Outcome {
                    receipt: None,
                    error: Some("containment_unavailable"),
                    cleanup_complete: true,
                }
            };
            let _ = sender.send(Event::Finished(result));
        });
        Self {
            id,
            mission_id,
            events,
            permit,
            control,
            thread,
        }
    }

    pub(crate) fn control(&self) -> Arc<Control> {
        self.control.clone()
    }
    pub(crate) fn cancel(&self) {
        let _resume = self
            .control
            .resume
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        self.control.cancelled.store(true, Ordering::SeqCst);
    }

    pub(crate) fn join(self) -> Option<Outcome> {
        let _ = self.thread.join();
        self.events.try_iter().find_map(|event| match event {
            Event::Finished(outcome) => Some(outcome),
            Event::Prepared(_) => None,
        })
    }
}
