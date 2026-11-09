//! Throwaway boundary comparison; not an authoritative Core or product scaffold.
use pyo3::prelude::*;
use pyo3::types::PyModule;
use serde::Deserialize;
use serde_json::{Value, json};
use std::ffi::CString;
use std::io::{self, Read, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{self, Receiver};
use std::time::Duration;

const ENGINE: &str = include_str!("../engine.py");
const LIMIT: usize = 4096;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    v: u32,
    id: u32,
    op: String,
    job: Option<String>,
}

fn request(raw: &[u8]) -> Result<Request, ()> {
    let r: Request = serde_json::from_slice(raw).map_err(|_| ())?;
    let value: Value = serde_json::from_slice(raw).map_err(|_| ())?;
    let job_op = matches!(r.op.as_str(), "start" | "status" | "cancel");
    if r.v != 1
        || !value.as_object().ok_or(())?.contains_key("job")
        || !matches!(
            r.op.as_str(),
            "start" | "status" | "cancel" | "crash" | "hang" | "rust_crash"
        )
        || job_op != r.job.is_some()
        || r.job
            .as_ref()
            .is_some_and(|s| s.is_empty() || s.chars().count() > 64)
    {
        return Err(());
    }
    Ok(r)
}

fn read_frame(input: &mut impl Read) -> io::Result<Option<Vec<u8>>> {
    let mut size = [0_u8; 4];
    // Distinguish clean EOF from an incomplete header, without an unbounded allocation.
    if input.read(&mut size[..1])? == 0 {
        return Ok(None);
    }
    input.read_exact(&mut size[1..])?;
    let n = u32::from_be_bytes(size) as usize;
    if n == 0 || n > LIMIT {
        return Err(io::Error::other("invalid frame size"));
    }
    let mut raw = vec![0; n];
    input.read_exact(&mut raw)?;
    Ok(Some(raw))
}

fn write_frame(output: &mut impl Write, raw: &[u8]) -> io::Result<()> {
    if raw.is_empty() || raw.len() > LIMIT {
        return Err(io::Error::other("invalid frame size"));
    }
    output.write_all(&(raw.len() as u32).to_be_bytes())?;
    output.write_all(raw)?;
    output.flush()
}

fn error(id: u32, state: &str) -> Vec<u8> {
    json!({"v":1,"id":id,"kind":"error","state":state,"value":null})
        .to_string()
        .into_bytes()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Event {
    v: u32,
    id: u32,
    kind: String,
    state: String,
    value: Option<i64>,
}

fn validate_event(raw: Vec<u8>, id: u32) -> io::Result<Vec<u8>> {
    let event: Event = serde_json::from_slice(&raw).map_err(io::Error::other)?;
    if event.v != 1
        || event.id != id
        || !matches!(event.kind.as_str(), "event" | "error")
        || !matches!(
            event.state.as_str(),
            "running" | "succeeded" | "cancelled" | "unknown" | "capacity"
        )
        || event.value
            != if event.state == "succeeded" {
                Some(42)
            } else {
                None
            }
    {
        return Err(io::Error::other("invalid worker event"));
    }
    Ok(raw)
}

struct Worker {
    child: Child,
    stdin: Option<ChildStdin>,
    rx: Receiver<io::Result<Vec<u8>>>,
    dead: bool,
}
impl Worker {
    fn new() -> io::Result<Self> {
        let executable = std::env::var_os("SYNAPSE_SPIKE_PYTHON").ok_or_else(|| {
            io::Error::other("set SYNAPSE_SPIKE_PYTHON to measured absolute interpreter")
        })?;
        let mut command = Command::new(executable);
        command
            .args(["-I", "-S", "-u", "-c", ENGINE])
            .env_clear()
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        // Windows' loader may require SystemRoot; no user Python environment is inherited.
        if let Some(root) = std::env::var_os("SystemRoot") {
            command.env("SystemRoot", root);
        }
        let mut child = command.spawn()?;
        let stdin = child.stdin.take();
        let mut stdout = child.stdout.take().unwrap();
        let (tx, rx) = mpsc::sync_channel(1);
        std::thread::spawn(move || {
            loop {
                let raw = match read_frame(&mut stdout) {
                    Ok(Some(raw)) => Ok(raw),
                    Ok(None) => Err(io::Error::other("worker eof")),
                    Err(e) => Err(e),
                };
                let stop = raw.is_err();
                if tx.send(raw).is_err() || stop {
                    break;
                }
            }
        });
        Ok(Self {
            child,
            stdin,
            rx,
            dead: false,
        })
    }
    fn receive(&self) -> io::Result<Vec<u8>> {
        self.rx
            .recv_timeout(Duration::from_secs(2))
            .map_err(io::Error::other)?
    }
    fn stop(&mut self) {
        self.stdin.take();
        let _ = self.child.kill();
        let _ = self.child.wait();
        self.dead = true;
    }
    fn dispatch(&mut self, raw: &[u8], id: u32) -> Vec<u8> {
        if self.dead {
            return error(id, "worker_lost");
        }
        let result = write_frame(self.stdin.as_mut().unwrap(), raw).and_then(|_| self.receive());
        match result {
            Ok(raw) => match validate_event(raw, id) {
                Ok(raw) => raw,
                Err(_) => {
                    self.stop();
                    error(id, "invalid_worker_event")
                }
            },
            Err(e) => {
                let state = if e.to_string().contains("timed out") {
                    "worker_timeout"
                } else {
                    "worker_lost"
                };
                self.stop();
                error(id, state)
            }
        }
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        self.stop();
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mode = std::env::args().nth(1).ok_or("candidate required")?;
    let mut worker = if mode == "worker" {
        Some(Worker::new()?)
    } else {
        None
    };
    if mode != "worker" && mode != "embedded" {
        return Err("unknown candidate".into());
    }
    let embedded = if mode == "embedded" {
        Some(Python::attach(|py| -> PyResult<Py<PyAny>> {
            let source = CString::new(ENGINE).unwrap();
            let module = PyModule::from_code(py, &source, c"spike_engine.py", c"spike_engine")?;
            Ok(module.getattr("Engine")?.call0()?.unbind())
        })?)
    } else {
        None
    };
    let mut stdout = io::stdout().lock();
    let ready = if let Some(w) = &mut worker {
        w.receive()?
    } else {
        Python::attach(|py| {
            embedded
                .as_ref()
                .unwrap()
                .bind(py)
                .call_method0("hello")?
                .extract::<String>()
        })?
        .into_bytes()
    };
    let hello: Value = serde_json::from_slice(&ready)?;
    if hello["kind"] != "ready"
        || hello["v"] != 1
        || !hello["pid"].is_u64()
        || !hello["runtime"].is_string()
    {
        return Err("bad initialization".into());
    }
    write_frame(&mut stdout, &ready)?;
    let mut stdin = io::stdin().lock();
    while let Some(raw) = read_frame(&mut stdin)? {
        let response = match request(&raw) {
            Err(()) => error(0, "invalid_schema"),
            Ok(r) if r.op == "rust_crash" => std::process::exit(72),
            Ok(r) => {
                if let Some(w) = &mut worker {
                    w.dispatch(&raw, r.id)
                } else {
                    let raw = std::str::from_utf8(&raw)?;
                    let result = Python::attach(|py| {
                        embedded
                            .as_ref()
                            .unwrap()
                            .bind(py)
                            .call_method1("dispatch", (raw,))?
                            .extract::<String>()
                    })?;
                    validate_event(result.into_bytes(), r.id)?
                }
            }
        };
        write_frame(&mut stdout, &response)?;
    }
    Ok(())
}
