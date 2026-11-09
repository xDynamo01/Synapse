//! Windows-only experiment: kernel-owned lifetime, not a capability/security sandbox.
//! Requires Windows 10+ JOB_LIST; unsupported/restricted hosts fail closed.
use std::ffi::{OsStr, OsString};
use std::fs::File;
use std::io::{self, Read};
use std::mem::{size_of, zeroed};
use std::os::windows::ffi::OsStrExt;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
use std::path::Path;
use std::ptr::{null, null_mut};
use windows_sys::Win32::Foundation::*;
use windows_sys::Win32::Security::SECURITY_ATTRIBUTES;
use windows_sys::Win32::Storage::FileSystem::*;
use windows_sys::Win32::System::JobObjects::*;
use windows_sys::Win32::System::Pipes::CreatePipe;
use windows_sys::Win32::System::Threading::*;

fn checked(result: i32, operation: &str) -> io::Result<()> {
    if result == 0 {
        Err(io::Error::other(format!(
            "containment {operation}: {}",
            io::Error::last_os_error()
        )))
    } else {
        Ok(())
    }
}

fn handle(raw: HANDLE, operation: &str) -> io::Result<OwnedHandle> {
    if raw.is_null() || raw == INVALID_HANDLE_VALUE {
        return Err(io::Error::other(format!(
            "containment {operation}: {}",
            io::Error::last_os_error()
        )));
    }
    // SAFETY: successful Win32 creation transfers exactly one close obligation.
    Ok(unsafe { OwnedHandle::from_raw_handle(raw) })
}

struct Attributes {
    // usize storage supplies pointer alignment; memory is stable through deletion.
    storage: Vec<usize>,
}
impl Attributes {
    fn new() -> io::Result<Self> {
        let mut bytes = 0;
        // SAFETY: documented sizing call intentionally fails with insufficient buffer.
        let result = unsafe { InitializeProcThreadAttributeList(null_mut(), 2, 0, &mut bytes) };
        if result != 0 || unsafe { GetLastError() } != ERROR_INSUFFICIENT_BUFFER || bytes == 0 {
            return Err(io::Error::other("containment attribute sizing failed"));
        }
        let mut storage = vec![0; bytes.div_ceil(size_of::<usize>())];
        checked(
            unsafe {
                InitializeProcThreadAttributeList(storage.as_mut_ptr().cast(), 2, 0, &mut bytes)
            },
            "attribute initialization",
        )?;
        Ok(Self { storage })
    }
    fn raw(&mut self) -> LPPROC_THREAD_ATTRIBUTE_LIST {
        self.storage.as_mut_ptr().cast()
    }
    fn handles(&mut self, attribute: u32, values: &[HANDLE]) -> io::Result<()> {
        // SAFETY: caller keeps values and their handles live until this list is deleted.
        checked(
            unsafe {
                UpdateProcThreadAttribute(
                    self.raw(),
                    0,
                    attribute as usize,
                    values.as_ptr().cast(),
                    size_of_val(values),
                    null_mut(),
                    null(),
                )
            },
            "attribute update",
        )
    }
}
impl Drop for Attributes {
    fn drop(&mut self) {
        // SAFETY: only successfully initialized lists become Attributes.
        unsafe { DeleteProcThreadAttributeList(self.raw()) };
    }
}

fn pipe(parent_reads: bool) -> io::Result<(OwnedHandle, OwnedHandle)> {
    let security = SECURITY_ATTRIBUTES {
        nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
        lpSecurityDescriptor: null_mut(),
        bInheritHandle: 1,
    };
    let (mut read, mut write) = (null_mut(), null_mut());
    checked(
        unsafe { CreatePipe(&mut read, &mut write, &security, 0) },
        "pipe creation",
    )?;
    let read = handle(read, "read pipe")?;
    let write = handle(write, "write pipe")?;
    let (parent, child) = if parent_reads {
        (read, write)
    } else {
        (write, read)
    };
    checked(
        unsafe { SetHandleInformation(parent.as_raw_handle(), HANDLE_FLAG_INHERIT, 0) },
        "parent pipe inheritance",
    )?;
    Ok((parent, child))
}

fn wide(value: &OsStr) -> io::Result<Vec<u16>> {
    let mut result: Vec<u16> = value.encode_wide().collect();
    if result.contains(&0) {
        return Err(io::Error::other("containment argument contains NUL"));
    }
    result.push(0);
    Ok(result)
}

fn command_line(arguments: &[OsString]) -> io::Result<Vec<u16>> {
    let mut output = Vec::new();
    // Windows CRT argument quoting; no shell, lossy Unicode or executable search.
    for argument in arguments {
        if !output.is_empty() {
            output.push(32);
        }
        output.push(34);
        let mut slashes = 0;
        for unit in wide(argument)?
            .into_iter()
            .take(argument.encode_wide().count())
        {
            if unit == 92 {
                slashes += 1;
            } else {
                output.extend(std::iter::repeat_n(
                    92,
                    slashes * if unit == 34 { 2 } else { 1 },
                ));
                if unit == 34 {
                    output.push(92);
                }
                output.push(unit);
                slashes = 0;
            }
        }
        output.extend(std::iter::repeat_n(92, slashes * 2));
        output.push(34);
    }
    output.push(0);
    if output.len() > 32767 {
        return Err(io::Error::other(
            "containment command line exceeds Win32 bound",
        ));
    }
    Ok(output)
}

pub struct Process {
    process: OwnedHandle,
    job: Option<OwnedHandle>,
    stopped: bool,
}
impl Process {
    pub fn launch(executable: OsString, engine: &str) -> io::Result<(Self, File, File)> {
        if !Path::new(&executable).is_absolute() {
            return Err(io::Error::other(
                "containment requires absolute interpreter",
            ));
        }
        let failure = std::env::var("SYNAPSE_SPIKE_CONTAINMENT_FAILURE").unwrap_or_default();
        let job = handle(unsafe { CreateJobObjectW(null(), null()) }, "job creation")?;
        checked(
            unsafe { SetHandleInformation(job.as_raw_handle(), HANDLE_FLAG_INHERIT, 0) },
            "job inheritance",
        )?;
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { zeroed() };
        // No BREAKAWAY_OK or SILENT_BREAKAWAY_OK. Name is null; only host owns this handle.
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        checked(
            unsafe {
                SetInformationJobObject(
                    job.as_raw_handle(),
                    JobObjectExtendedLimitInformation,
                    (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                    size_of_val(&limits) as u32,
                )
            },
            "job limits",
        )?;
        let (stdin, child_stdin) = pipe(false)?;
        let (stdout, child_stdout) = pipe(true)?;
        let security = SECURITY_ATTRIBUTES {
            nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: null_mut(),
            bInheritHandle: 1,
        };
        let null_name = wide(OsStr::new("NUL"))?;
        let child_stderr = handle(
            unsafe {
                CreateFileW(
                    null_name.as_ptr(),
                    GENERIC_WRITE,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    &security,
                    OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL,
                    null_mut(),
                )
            },
            "stderr null handle",
        )?;
        let inherited = [
            child_stdin.as_raw_handle(),
            child_stdout.as_raw_handle(),
            child_stderr.as_raw_handle(),
        ];
        let jobs = [if failure == "invalid-job" {
            null_mut()
        } else {
            job.as_raw_handle()
        }];
        let mut attributes = Attributes::new()?;
        attributes.handles(PROC_THREAD_ATTRIBUTE_HANDLE_LIST, &inherited)?;
        attributes.handles(PROC_THREAD_ATTRIBUTE_JOB_LIST, &jobs)?;
        let mut startup: STARTUPINFOEXW = unsafe { zeroed() };
        startup.StartupInfo.cb = size_of::<STARTUPINFOEXW>() as u32;
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
        startup.StartupInfo.hStdInput = inherited[0];
        startup.StartupInfo.hStdOutput = inherited[1];
        startup.StartupInfo.hStdError = inherited[2];
        startup.lpAttributeList = attributes.raw();
        let application = wide(&executable)?;
        let mut arguments = vec![
            executable,
            "-I".into(),
            "-S".into(),
            "-u".into(),
            "-c".into(),
            engine.into(),
        ];
        if let Some(fixture) = std::env::var_os("SYNAPSE_SPIKE_TREE_FIXTURE") {
            if fixture != "fixture-hang" && fixture != "fixture-busy" {
                return Err(io::Error::other("containment unknown synthetic fixture"));
            }
            arguments.push(fixture);
        }
        let mut command = command_line(&arguments)?;
        let mut environment = Vec::new();
        if let Some(root) = std::env::var_os("SystemRoot") {
            let mut entry = OsString::from("SystemRoot=");
            entry.push(root);
            environment.extend(wide(&entry)?);
        }
        environment.push(0);
        if environment.len() == 1 {
            environment.push(0);
        }
        if failure == "before-create" {
            return Err(io::Error::other(
                "containment injected before-create rejection",
            ));
        }
        let mut info: PROCESS_INFORMATION = unsafe { zeroed() };
        // SAFETY: all pointers refer to live initialized buffers/handles. JOB_LIST assigns
        // during creation, including before return; suspension adds a separate resume gate.
        checked(
            unsafe {
                CreateProcessW(
                    application.as_ptr(),
                    command.as_mut_ptr(),
                    null(),
                    null(),
                    1,
                    CREATE_SUSPENDED
                        | CREATE_UNICODE_ENVIRONMENT
                        | EXTENDED_STARTUPINFO_PRESENT
                        | CREATE_NO_WINDOW,
                    environment.as_ptr().cast(),
                    null(),
                    &startup.StartupInfo,
                    &mut info,
                )
            },
            "CreateProcessW/JOB_LIST",
        )?;
        drop(attributes);
        let process = handle(info.hProcess, "process handle")?;
        let thread = handle(info.hThread, "thread handle")?;
        let mut owned = Self {
            process,
            job: Some(job),
            stopped: false,
        };
        let mut assigned = 0;
        let setup = (|| {
            checked(
                unsafe { IsProcessInJob(owned.process.as_raw_handle(), jobs[0], &mut assigned) },
                "membership query",
            )?;
            if assigned == 0 {
                return Err(io::Error::other("containment membership denied"));
            }
            if failure == "before-resume" {
                return Err(io::Error::other(
                    "containment injected before-resume rejection",
                ));
            }
            if failure == "hold-before-resume" {
                // Test-only rendezvous: observer captures original identity while the
                // main thread is still suspended, then kills this owning Rust host.
                eprintln!("containment suspended pid={}", info.dwProcessId);
                io::stdin().read_exact(&mut [0])?;
                return Err(io::Error::other("containment held launch rejected"));
            }
            if unsafe { ResumeThread(thread.as_raw_handle()) } != 1 {
                return Err(io::Error::other(format!(
                    "containment resume failed: {}",
                    io::Error::last_os_error()
                )));
            }
            Ok(())
        })();
        if let Err(error) = setup {
            owned.stop()?;
            return Err(error);
        }
        // Thread, attribute list and child-side pipe copies close before returning.
        Ok((owned, File::from(stdin), File::from(stdout)))
    }

    pub fn stop(&mut self) -> io::Result<()> {
        if self.stopped {
            return Ok(());
        }
        let termination = if let Some(job) = self.job.as_ref() {
            checked(
                unsafe { TerminateJobObject(job.as_raw_handle(), 74) },
                "terminate job",
            )
        } else {
            Ok(())
        };
        // Last close remains a kernel fallback even when TerminateJobObject failed.
        self.job.take();
        let result = unsafe { WaitForSingleObject(self.process.as_raw_handle(), 2000) };
        if result != WAIT_OBJECT_0 {
            return Err(io::Error::other(format!(
                "containment wait failed ({result}): {}",
                io::Error::last_os_error()
            )));
        }
        self.stopped = true;
        termination
    }
}
impl Drop for Process {
    fn drop(&mut self) {
        if let Err(error) = self.stop() {
            eprintln!("{error}");
        }
    }
}
