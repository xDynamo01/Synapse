use crate::{contracts::CoreResult, conversation::Launch};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    io::{BufRead, BufReader, Write},
    sync::{
        Arc, Mutex,
        atomic::{AtomicU8, Ordering},
    },
    time::{Duration, Instant},
};

#[derive(Default)]
pub(crate) struct Stop {
    state: AtomicU8, // 0 active, 1 user cancellation, 2 deadline
    #[cfg(windows)]
    job: Mutex<Option<std::os::windows::io::OwnedHandle>>,
}
impl Stop {
    pub(crate) fn cancel(&self) {
        self.stop(1);
    }
    fn stop(&self, reason: u8) {
        let _ = self
            .state
            .compare_exchange(0, reason, Ordering::SeqCst, Ordering::SeqCst);
        #[cfg(windows)]
        {
            self.job.lock().unwrap().take();
        }
    }
}

fn digest(request: &Value) -> CoreResult<String> {
    let bytes = serde_json::to_vec(request)?;
    Ok(Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect())
}

pub(crate) fn run(launch: Launch, stop: Arc<Stop>) -> Result<String, String> {
    let timeout_ms = launch.generation.timeout_ms + 5000;
    let bare = json!({"version":2,"request_id":launch.id,"model_id":launch.model_id,"endpoint":launch.endpoint,"messages":launch.messages,"generation":launch.generation});
    let digest = digest(&bare).map_err(|_| "worker_protocol".to_string())?;
    let mut request = bare.clone();
    request["digest"] = json!(digest);
    let finished = Arc::new(AtomicU8::new(0));
    let watcher_done = finished.clone();
    let watcher_stop = stop.clone();
    let watcher = std::thread::spawn(move || {
        let start = Instant::now();
        while watcher_done.load(Ordering::SeqCst) == 0
            && watcher_stop.state.load(Ordering::SeqCst) == 0
        {
            if start.elapsed() >= Duration::from_millis(timeout_ms) {
                watcher_stop.stop(2);
                break;
            }
            std::thread::sleep(Duration::from_millis(25));
        }
    });
    #[cfg(windows)]
    let outcome = windows::run(&request, &bare, &digest, &stop);
    #[cfg(not(windows))]
    let outcome: Result<String, String> = Err("worker_unavailable".into());
    finished.store(1, Ordering::SeqCst);
    let _ = watcher.join();
    match stop.state.load(Ordering::SeqCst) {
        1 => Err("cancelled".into()),
        2 => Err("provider_timeout".into()),
        _ => outcome,
    }
}

#[cfg(windows)]
mod windows {
    use super::*;
    use std::{
        ffi::c_void,
        fs::File,
        mem::size_of,
        os::windows::{
            ffi::OsStrExt,
            io::{FromRawHandle, OwnedHandle},
        },
        path::PathBuf,
        ptr::{null, null_mut},
    };
    use windows_sys::Win32::{
        Foundation::{HANDLE, HANDLE_FLAG_INHERIT, INVALID_HANDLE_VALUE, SetHandleInformation},
        Security::SECURITY_ATTRIBUTES,
        Storage::FileSystem::{
            CreateFileW, FILE_ATTRIBUTE_NORMAL, FILE_GENERIC_WRITE, OPEN_EXISTING,
        },
        System::{
            JobObjects::{
                CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
                JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
                SetInformationJobObject,
            },
            Pipes::CreatePipe,
            Threading::{
                CREATE_NO_WINDOW, CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT, CreateProcessW,
                DeleteProcThreadAttributeList, EXTENDED_STARTUPINFO_PRESENT,
                InitializeProcThreadAttributeList, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                PROC_THREAD_ATTRIBUTE_JOB_LIST, PROCESS_INFORMATION, ResumeThread,
                STARTF_USESTDHANDLES, STARTUPINFOEXW, UpdateProcThreadAttribute,
                WaitForSingleObject,
            },
        },
    };

    fn wide(s: &str) -> Vec<u16> {
        std::ffi::OsStr::new(s)
            .encode_wide()
            .chain(Some(0))
            .collect()
    }
    fn own(handle: HANDLE) -> OwnedHandle {
        unsafe { OwnedHandle::from_raw_handle(handle) }
    }
    fn pipe() -> Result<(OwnedHandle, OwnedHandle), String> {
        let attrs = SECURITY_ATTRIBUTES {
            nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: null_mut(),
            bInheritHandle: 1,
        };
        let (mut read, mut write) = (null_mut(), null_mut());
        if unsafe { CreatePipe(&mut read, &mut write, &attrs, 0) } == 0 {
            return Err("worker_unavailable".into());
        }
        Ok((own(read), own(write)))
    }
    fn raw(h: &OwnedHandle) -> HANDLE {
        use std::os::windows::io::AsRawHandle;
        h.as_raw_handle()
    }
    fn no_inherit(h: &OwnedHandle) -> Result<(), String> {
        if unsafe { SetHandleInformation(raw(h), HANDLE_FLAG_INHERIT, 0) } == 0 {
            Err("worker_unavailable".into())
        } else {
            Ok(())
        }
    }
    struct Attributes {
        storage: Vec<usize>,
    }
    impl Attributes {
        fn new() -> Result<Self, String> {
            let mut bytes = 0;
            unsafe {
                InitializeProcThreadAttributeList(null_mut(), 2, 0, &mut bytes);
            }
            if bytes == 0 {
                return Err("worker_unavailable".into());
            }
            let mut storage = vec![0usize; bytes.div_ceil(size_of::<usize>())];
            if unsafe {
                InitializeProcThreadAttributeList(
                    storage.as_mut_ptr() as *mut c_void,
                    2,
                    0,
                    &mut bytes,
                )
            } == 0
            {
                return Err("worker_unavailable".into());
            }
            Ok(Self { storage })
        }
        fn ptr(&mut self) -> *mut c_void {
            self.storage.as_mut_ptr() as *mut c_void
        }
        fn add(&mut self, kind: usize, handles: &[HANDLE]) -> Result<(), String> {
            if unsafe {
                UpdateProcThreadAttribute(
                    self.ptr(),
                    0,
                    kind,
                    handles.as_ptr() as *const c_void,
                    size_of_val(handles),
                    null_mut(),
                    null(),
                )
            } == 0
            {
                Err("worker_unavailable".into())
            } else {
                Ok(())
            }
        }
    }
    impl Drop for Attributes {
        fn drop(&mut self) {
            unsafe {
                DeleteProcThreadAttributeList(self.ptr());
            }
        }
    }
    fn read_line<R: BufRead>(reader: &mut R) -> Result<Value, String> {
        let mut buf = Vec::new();
        std::io::Read::take(&mut *reader, 65537)
            .read_until(b'\n', &mut buf)
            .map_err(|_| "worker_protocol".to_string())?;
        if buf.is_empty() || buf.len() > 65536 || !buf.ends_with(b"\n") {
            return Err("worker_protocol".into());
        }
        serde_json::from_slice(&buf).map_err(|_| "worker_protocol".into())
    }
    pub(super) fn run(
        request: &Value,
        bare: &Value,
        digest: &str,
        stop: &Arc<Stop>,
    ) -> Result<String, String> {
        if stop.state.load(Ordering::SeqCst) != 0 {
            return Err("cancelled".into());
        }
        let (child_stdin, parent_stdin) = pipe()?;
        let (parent_stdout, child_stdout) = pipe()?;
        no_inherit(&parent_stdin)?;
        no_inherit(&parent_stdout)?;
        let nul_name = wide("NUL");
        let attrs = SECURITY_ATTRIBUTES {
            nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: null_mut(),
            bInheritHandle: 1,
        };
        let nul_raw = unsafe {
            CreateFileW(
                nul_name.as_ptr(),
                FILE_GENERIC_WRITE,
                0,
                &attrs,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                null_mut(),
            )
        };
        if nul_raw == INVALID_HANDLE_VALUE {
            return Err("worker_unavailable".into());
        }
        let nul = own(nul_raw);
        let job_raw = unsafe { CreateJobObjectW(null(), null()) };
        if job_raw.is_null() {
            return Err("worker_unavailable".into());
        }
        let job = own(job_raw);
        let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if unsafe {
            SetInformationJobObject(
                raw(&job),
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const c_void,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        } == 0
        {
            return Err("worker_unavailable".into());
        }
        let python = std::env::var("SYNAPSE_PYTHON_EXECUTABLE")
            .map_err(|_| "worker_unavailable".to_string())?;
        if python.contains('"') || python.contains('\0') || !PathBuf::from(&python).is_file() {
            return Err("worker_unavailable".into());
        }
        let app = wide(&python);
        let mut cmd = wide(&format!("\"{python}\" -m synapse_ai"));
        let package = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../python")
            .canonicalize()
            .map_err(|_| "worker_unavailable".to_string())?;
        let cwd = wide(&package.to_string_lossy());
        let mut env_values = vec![
            format!(
                "SystemRoot={}",
                std::env::var("SystemRoot").unwrap_or_else(|_| "C:\\Windows".into())
            ),
            format!("PATH={}", std::env::var("PATH").unwrap_or_default()),
        ];
        env_values.sort_by_key(|s| s.to_ascii_lowercase());
        let mut env_block: Vec<u16> = env_values.iter().flat_map(|s| wide(s)).collect();
        env_block.push(0);
        let mut attributes = Attributes::new()?;
        let inherited = [raw(&child_stdin), raw(&child_stdout), raw(&nul)];
        let jobs = [raw(&job)];
        attributes.add(PROC_THREAD_ATTRIBUTE_HANDLE_LIST as usize, &inherited)?;
        attributes.add(PROC_THREAD_ATTRIBUTE_JOB_LIST as usize, &jobs)?;
        let mut startup = STARTUPINFOEXW::default();
        startup.StartupInfo.cb = size_of::<STARTUPINFOEXW>() as u32;
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
        startup.StartupInfo.hStdInput = raw(&child_stdin);
        startup.StartupInfo.hStdOutput = raw(&child_stdout);
        startup.StartupInfo.hStdError = raw(&nul);
        startup.lpAttributeList = attributes.ptr();
        let mut process = PROCESS_INFORMATION::default();
        if unsafe {
            CreateProcessW(
                app.as_ptr(),
                cmd.as_mut_ptr(),
                null(),
                null(),
                1,
                CREATE_SUSPENDED
                    | CREATE_NO_WINDOW
                    | CREATE_UNICODE_ENVIRONMENT
                    | EXTENDED_STARTUPINFO_PRESENT,
                env_block.as_ptr() as *const c_void,
                cwd.as_ptr(),
                &startup.StartupInfo,
                &mut process,
            )
        } == 0
        {
            return Err("worker_unavailable".into());
        }
        let process_handle = own(process.hProcess);
        let thread_handle = own(process.hThread);
        {
            let mut held = stop.job.lock().unwrap();
            if stop.state.load(Ordering::SeqCst) != 0 {
                return Err("cancelled".into());
            }
            *held = Some(job);
            if unsafe { ResumeThread(raw(&thread_handle)) } == u32::MAX {
                held.take();
                return Err("worker_unavailable".into());
            }
        }
        drop(thread_handle);
        drop(child_stdin);
        drop(child_stdout);
        drop(nul);
        let mut writer = File::from(parent_stdin);
        let mut reader = BufReader::new(File::from(parent_stdout));
        let result = (|| {
            let hello = read_line(&mut reader)?;
            if hello != json!({"type":"hello","version":2}) {
                return Err("worker_protocol".into());
            }
            serde_json::to_writer(&mut writer, request)
                .map_err(|_| "worker_protocol".to_string())?;
            writer
                .write_all(b"\n")
                .and_then(|_| writer.flush())
                .map_err(|_| "worker_protocol".to_string())?;
            drop(writer);
            let answer = read_line(&mut reader)?;
            if answer.get("version") != Some(&json!(2))
                || answer.get("request_id") != bare.get("request_id")
                || answer.get("digest") != Some(&json!(digest))
                || answer.as_object().map(|o| o.len()) != Some(6)
            {
                return Err("worker_protocol".into());
            }
            let code = answer.get("error");
            match (answer.get("ok"), answer.get("content"), code) {
                (Some(Value::Bool(true)), Some(Value::String(content)), Some(Value::Null))
                    if !content.trim().is_empty() && content.len() <= 32768 =>
                {
                    Ok(content.clone())
                }
                (Some(Value::Bool(false)), Some(Value::Null), Some(Value::String(code)))
                    if [
                        "model_unavailable",
                        "provider_unavailable",
                        "provider_timeout",
                        "provider_malformed",
                        "provider_error",
                        "provider_redirect",
                        "invalid_endpoint",
                    ]
                    .contains(&code.as_str()) =>
                {
                    Err(code.clone())
                }
                _ => Err("worker_protocol".into()),
            }
        })();
        // Closing the last job handle terminates descendants even when the worker
        // wrote a response but kept running.
        stop.job.lock().unwrap().take();
        unsafe {
            WaitForSingleObject(raw(&process_handle), 5000);
        }
        result
    }
}
