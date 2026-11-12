const MAXIMUM_ALLOWED: u32 = 0x02000000;
// Windows LPAC setup is separate from mission authorization and persistence.
use super::Control;
use std::{
    ffi::c_void,
    fs::File,
    io::Read,
    mem::{size_of, size_of_val},
    os::windows::{
        ffi::OsStrExt,
        io::{AsRawHandle, FromRawHandle, OwnedHandle},
    },
    path::Path,
    ptr::{null, null_mut},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};
use windows_sys::Win32::{
    Foundation::{HANDLE, HANDLE_FLAG_INHERIT, LocalFree, SetHandleInformation, WAIT_OBJECT_0},
    Security::{Authorization::*, Isolation::*, *},
    Storage::FileSystem::CreateDirectoryW,
    System::{JobObjects::*, Pipes::CreatePipe, Threading::*},
};

fn wide(s: &str) -> Vec<u16> {
    std::ffi::OsStr::new(s)
        .encode_wide()
        .chain(Some(0))
        .collect()
}
fn raw(h: &OwnedHandle) -> HANDLE {
    h.as_raw_handle()
}
fn own(h: HANDLE) -> OwnedHandle {
    unsafe { OwnedHandle::from_raw_handle(h) }
}
fn error(stage: &str) -> String {
    format!("{stage}:{}", std::io::Error::last_os_error())
}
pub(crate) fn sid_text(sid: PSID) -> Result<String, String> {
    let mut output = null_mut();
    if unsafe { ConvertSidToStringSidW(sid, &mut output) } == 0 {
        return Err(error("sid_text"));
    }
    let mut len = 0;
    unsafe {
        while *output.add(len) != 0 {
            len += 1;
        }
    }
    let result = String::from_utf16_lossy(unsafe { std::slice::from_raw_parts(output, len) });
    unsafe {
        LocalFree(output.cast());
    }
    Ok(result)
}
fn token_info(token: HANDLE, class: TOKEN_INFORMATION_CLASS) -> Result<Vec<usize>, String> {
    let mut bytes = 0;
    unsafe {
        GetTokenInformation(token, class, null_mut(), 0, &mut bytes);
    }
    if bytes == 0 || bytes > 65536 {
        return Err(error(&format!("token_size_class_{class}")));
    }
    let mut buffer = vec![0usize; (bytes as usize).div_ceil(size_of::<usize>())];
    if unsafe { GetTokenInformation(token, class, buffer.as_mut_ptr().cast(), bytes, &mut bytes) }
        == 0
    {
        return Err(error("token_information"));
    }
    Ok(buffer)
}
fn process_token(process: HANDLE) -> Result<OwnedHandle, String> {
    let mut handle = null_mut();
    if unsafe { OpenProcessToken(process, TOKEN_QUERY | TOKEN_DUPLICATE, &mut handle) } == 0 {
        return Err(error("open_token"));
    }
    Ok(own(handle))
}

pub(crate) fn owner_sid() -> Result<String, String> {
    let owner = process_token(unsafe { GetCurrentProcess() })?;
    let info = token_info(raw(&owner), TokenUser)?;
    let user = unsafe { &*(info.as_ptr().cast::<TOKEN_USER>()) };
    sid_text(user.User.Sid)
}

pub(super) fn create_private_directory(path: &Path) -> Result<(), String> {
    let owner = owner_sid()?;
    let descriptor = wide(&format!("D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{owner})"));
    let mut sd = null_mut();
    if unsafe {
        ConvertStringSecurityDescriptorToSecurityDescriptorW(
            descriptor.as_ptr(),
            1,
            &mut sd,
            null_mut(),
        )
    } == 0
    {
        return Err(error("run_security_descriptor"));
    }
    let attributes = SECURITY_ATTRIBUTES {
        nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
        lpSecurityDescriptor: sd,
        bInheritHandle: 0,
    };
    let name: Vec<_> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    let result = unsafe { CreateDirectoryW(name.as_ptr(), &attributes) };
    let failure = (result == 0).then(|| error("run_create_failed"));
    unsafe {
        LocalFree(sd);
    }
    failure.map_or(Ok(()), Err)
}

pub(super) struct Profile {
    name: String,
    sid: PSID,
    text: String,
}
impl Profile {
    pub fn create(name: &str) -> Result<Self, String> {
        let wide = wide(name);
        let mut sid = null_mut();
        let hr = unsafe {
            CreateAppContainerProfile(
                wide.as_ptr(),
                wide.as_ptr(),
                wide.as_ptr(),
                null(),
                0,
                &mut sid,
            )
        };
        if hr < 0 {
            return Err(format!("profile_create:{hr:#x}"));
        }
        // Never adopt an existing profile. A failed creation leaves no deletion authority.
        match sid_text(sid) {
            Ok(text) => Ok(Self {
                name: name.into(),
                sid,
                text,
            }),
            Err(e) => {
                unsafe {
                    DeleteAppContainerProfile(wide.as_ptr());
                    FreeSid(sid);
                }
                Err(e)
            }
        }
    }
    pub fn protect(&self, path: &Path, writable: bool) -> Result<(), String> {
        let owner_sid = owner_sid()?;
        let access = if writable { "0x1301bf" } else { "GRGX" };
        let level = if writable { "LW" } else { "ME" };
        let descriptor = wide(&format!(
            "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{owner_sid})(A;OICI;{access};;;{})S:(ML;OICI;NW;;;{level})",
            self.text
        ));
        let mut sd = null_mut();
        if unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                descriptor.as_ptr(),
                1,
                &mut sd,
                null_mut(),
            )
        } == 0
        {
            return Err(error("security_descriptor"));
        }
        let (mut dacl, mut sacl) = (null_mut(), null_mut());
        let (mut present, mut defaulted) = (0, 0);
        let ok = unsafe {
            GetSecurityDescriptorDacl(sd, &mut present, &mut dacl, &mut defaulted) != 0
                && GetSecurityDescriptorSacl(sd, &mut present, &mut sacl, &mut defaulted) != 0
        };
        let mut result = if ok {
            unsafe {
                SetNamedSecurityInfoW(
                    wide(&path.to_string_lossy()).as_ptr(),
                    SE_FILE_OBJECT,
                    DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                    null_mut(),
                    null_mut(),
                    dacl,
                    null(),
                )
            }
        } else {
            1
        };
        if result == 0 {
            result = unsafe {
                SetNamedSecurityInfoW(
                    wide(&path.to_string_lossy()).as_ptr(),
                    SE_FILE_OBJECT,
                    LABEL_SECURITY_INFORMATION,
                    null_mut(),
                    null_mut(),
                    null(),
                    sacl,
                )
            };
        }
        unsafe {
            LocalFree(sd);
        }
        if result != 0 {
            return Err(format!("owned_acl:{result}"));
        }
        Ok(())
    }
    pub(super) fn preserve(mut self) {
        self.name.clear();
    }

    pub fn remove(mut self) -> Result<(), String> {
        let hr = unsafe { DeleteAppContainerProfile(wide(&self.name).as_ptr()) };
        if hr < 0 {
            return Err(format!("profile_cleanup:{hr:#x}"));
        }
        self.name.clear();
        Ok(())
    }
    pub fn launch(
        &self,
        executable: &Path,
        args: &[String],
        cwd: &Path,
        tmp: &Path,
        control: &Control,
    ) -> Result<Receipt, String> {
        self.launch_policy(executable, args, cwd, tmp, control, true)
    }
    pub(super) fn launch_policy(
        &self,
        executable: &Path,
        args: &[String],
        cwd: &Path,
        tmp: &Path,
        control: &Control,
        lpac: bool,
    ) -> Result<Receipt, String> {
        control.before_launch()?;
        let job_handle = unsafe { CreateJobObjectW(null(), null()) };
        if job_handle.is_null() {
            return Err(error("job_create"));
        }
        let job = own(job_handle);
        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | JOB_OBJECT_LIMIT_JOB_MEMORY
            | JOB_OBJECT_LIMIT_PROCESS_MEMORY;
        limits.BasicLimitInformation.ActiveProcessLimit = 8;
        limits.JobMemoryLimit = 512 * 1024 * 1024;
        limits.ProcessMemoryLimit = 512 * 1024 * 1024;
        if unsafe {
            SetInformationJobObject(
                raw(&job),
                JobObjectExtendedLimitInformation,
                (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                size_of_val(&limits) as u32,
            )
        } == 0
        {
            return Err(error("job_limits"));
        }
        let (stdin_read, stdin_write) = pipe()?;
        let (stdout_read, stdout_write) = pipe()?;
        let (stderr_read, stderr_write) = pipe()?;
        for handle in [&stdin_write, &stdout_read, &stderr_read] {
            if unsafe { SetHandleInformation(raw(handle), HANDLE_FLAG_INHERIT, 0) } == 0 {
                return Err(error("pipe_inherit"));
            }
        }
        let inherited = [raw(&stdin_read), raw(&stdout_write), raw(&stderr_write)];
        let jobs = [raw(&job)];
        let caps = SECURITY_CAPABILITIES {
            AppContainerSid: self.sid,
            Capabilities: null_mut(),
            CapabilityCount: 0,
            Reserved: 0,
        };
        let optout = u32::from(lpac);
        let mut attributes = Attributes::new(4)?;
        attributes.add(
            PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
            inherited.as_ptr().cast(),
            size_of_val(&inherited),
        )?;
        attributes.add(
            PROC_THREAD_ATTRIBUTE_JOB_LIST,
            jobs.as_ptr().cast(),
            size_of_val(&jobs),
        )?;
        attributes.add(
            PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            (&caps as *const SECURITY_CAPABILITIES).cast(),
            size_of_val(&caps),
        )?;
        attributes.add(
            PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY,
            (&optout as *const u32).cast(),
            size_of_val(&optout),
        )?;
        let mut startup = STARTUPINFOEXW::default();
        startup.StartupInfo.cb = size_of_val(&startup) as u32;
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
        startup.StartupInfo.hStdInput = raw(&stdin_read);
        startup.StartupInfo.hStdOutput = raw(&stdout_write);
        startup.StartupInfo.hStdError = raw(&stderr_write);
        startup.lpAttributeList = attributes.ptr();
        let app = wide(&executable.to_string_lossy());
        let mut command = wide(
            &std::iter::once(executable.to_string_lossy().into_owned())
                .chain(args.iter().cloned())
                .map(|s| quote(&s))
                .collect::<Vec<_>>()
                .join(" "),
        );
        let system = std::env::var("SystemRoot").map_err(|_| "systemroot_unavailable")?;
        let mut environment = vec![
            format!("SystemRoot={system}"),
            format!("LOCALAPPDATA={}", tmp.display()),
            format!("APPDATA={}", tmp.display()),
            format!("PATH={}", executable.parent().unwrap().display()),
            format!("TEMP={}", tmp.display()),
            format!("TMP={}", tmp.display()),
            format!("HOME={}", tmp.display()),
            format!("USERPROFILE={}", tmp.display()),
        ];
        environment.sort_by_key(|s| s.to_ascii_lowercase());
        let mut block: Vec<u16> = environment.iter().flat_map(|s| wide(s)).collect();
        block.push(0);
        let mut process = PROCESS_INFORMATION::default();
        if unsafe {
            CreateProcessW(
                app.as_ptr(),
                command.as_mut_ptr(),
                null(),
                null(),
                1,
                CREATE_SUSPENDED
                    | CREATE_NO_WINDOW
                    | CREATE_UNICODE_ENVIRONMENT
                    | EXTENDED_STARTUPINFO_PRESENT,
                block.as_ptr().cast(),
                wide(&cwd.to_string_lossy()).as_ptr(),
                &startup.StartupInfo,
                &mut process,
            )
        } == 0
        {
            return Err(error("lpac_create_process"));
        }
        let process_handle = own(process.hProcess);
        let thread_handle = own(process.hThread);
        let suspended = (|| {
            let verified = verify(raw(&process_handle), raw(&job), self.sid)?;
            let _resume = control.lock_resume();
            control.before_launch()?;
            let started = control.start_execution();
            if unsafe { ResumeThread(raw(&thread_handle)) } == u32::MAX {
                return Err(error("resume"));
            }
            Ok((verified, started))
        })();
        let (verified, started) = match suspended {
            Ok(result) => result,
            Err(error) => {
                unsafe {
                    TerminateJobObject(raw(&job), 1);
                }
                if unsafe { WaitForSingleObject(raw(&process_handle), 5000) } != WAIT_OBJECT_0 {
                    return Err("descendant_cleanup_failed".into());
                }
                if error.starts_with("lpac_") {
                    return Err(format!(
                        "{error}; suspended_child_reaped=true; resumed=false"
                    ));
                }
                return Err(error);
            }
        };
        drop(thread_handle);
        drop(stdin_read);
        drop(stdin_write);
        drop(stdout_write);
        drop(stderr_write);
        let bytes = Arc::new(Mutex::new(Vec::new()));
        let overflow = Arc::new(AtomicBool::new(false));
        let readers = [stdout_read, stderr_read]
            .into_iter()
            .map(|handle| {
                let bytes = bytes.clone();
                let overflow = overflow.clone();
                let output_remaining = control.output_remaining.clone();
                std::thread::spawn(move || {
                    let mut file = File::from(handle);
                    let mut buf = [0u8; 4096];
                    loop {
                        match file.read(&mut buf) {
                            Ok(0) | Err(_) => break,
                            Ok(n) => {
                                let previous = output_remaining
                                    .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |remaining| {
                                        Some(remaining.saturating_sub(n))
                                    })
                                    .expect("output budget update always succeeds");
                                let mut bytes = bytes.lock().unwrap();
                                bytes.extend_from_slice(&buf[..n.min(previous)]);
                                if n > previous {
                                    overflow.store(true, Ordering::SeqCst);
                                }
                            }
                        }
                    }
                })
            })
            .collect::<Vec<_>>();
        let mut stop = None;
        loop {
            if control.cancelled.load(Ordering::SeqCst) {
                stop = Some("cancelled");
                break;
            }
            if overflow.load(Ordering::SeqCst) {
                stop = Some("output_limit");
                break;
            }
            if Control::execution_expired(started) {
                stop = Some("deadline_exceeded");
                break;
            }
            if unsafe { WaitForSingleObject(raw(&process_handle), 20) } == WAIT_OBJECT_0 {
                break;
            }
        }
        let mut exit_code = 0;
        let exit_error = (unsafe { GetExitCodeProcess(raw(&process_handle), &mut exit_code) } == 0)
            .then(|| error("process_exit_code"));
        unsafe {
            TerminateJobObject(raw(&job), 1);
        }
        // Kill root-exited descendants before joining inherited-pipe readers.
        let mut accounting = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION::default();
        let reap = Instant::now();
        loop {
            if unsafe {
                QueryInformationJobObject(
                    raw(&job),
                    JobObjectBasicAccountingInformation,
                    (&mut accounting as *mut JOBOBJECT_BASIC_ACCOUNTING_INFORMATION).cast(),
                    size_of_val(&accounting) as u32,
                    null_mut(),
                )
            } == 0
            {
                return Err("descendant_cleanup_failed".into());
            }
            if accounting.ActiveProcesses == 0 {
                break;
            }
            if reap.elapsed() > Duration::from_secs(5) {
                return Err("descendant_cleanup_failed".into());
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        for reader in readers {
            reader.join().map_err(|_| "pipe_reader_failed")?;
        }
        if let Some(code) = stop {
            return Err(code.into());
        }
        if overflow.load(Ordering::SeqCst) {
            return Err("output_limit".into());
        }
        if let Some(error) = exit_error {
            return Err(error);
        }
        let output = String::from_utf8_lossy(&bytes.lock().unwrap()).into_owned();
        Ok(Receipt {
            exit_code,
            token: verified,
            output,
        })
    }
}
impl Drop for Profile {
    fn drop(&mut self) {
        if !self.name.is_empty() {
            unsafe {
                DeleteAppContainerProfile(wide(&self.name).as_ptr());
            }
        }
        unsafe {
            FreeSid(self.sid);
        }
    }
}
#[derive(Debug)]
pub(super) struct Receipt {
    pub exit_code: u32,
    pub token: Token,
    pub output: String,
}
#[derive(Debug)]
pub(super) struct Token {
    pub lpac: bool,
    pub verification_method: String,
    pub class46_query: String,
    pub sid: String,
    pub integrity: u32,
    pub capabilities: u32,
    pub job: bool,
}
fn verify(process: HANDLE, job: HANDLE, sid: PSID) -> Result<Token, String> {
    let token = process_token(process)?;
    let app = token_info(raw(&token), TokenIsAppContainer)?;
    let identity = token_info(raw(&token), TokenAppContainerSid)?;
    let actual_sid = unsafe {
        (*(identity.as_ptr().cast::<TOKEN_APPCONTAINER_INFORMATION>())).TokenAppContainer
    };
    let caps = token_info(raw(&token), TokenCapabilities)?;
    let count = unsafe { (*(caps.as_ptr().cast::<TOKEN_GROUPS>())).GroupCount };
    let integrity = token_info(raw(&token), TokenIntegrityLevel)?;
    let label = unsafe {
        (*(integrity.as_ptr().cast::<TOKEN_MANDATORY_LABEL>()))
            .Label
            .Sid
    };
    let level = unsafe { *GetSidSubAuthority(label, (*GetSidSubAuthorityCount(label) - 1) as u32) };
    let mut in_job = 0;
    // Class 46 is diagnostic only on builds that reject this query. Actual
    // enforcement is checked with the kernel's AppContainer access algorithm.
    let mut lpac_value = 0xdeadbeefu32;
    let mut returned = 0u32;
    let class46_query = if unsafe {
        GetTokenInformation(
            raw(&token),
            TokenIsLessPrivilegedAppContainer,
            (&mut lpac_value as *mut u32).cast(),
            4,
            &mut returned,
        )
    } == 0
    {
        format!(
            "unsupported:{}",
            std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
        )
    } else {
        format!("observed:{lpac_value}")
    };
    if app[0] as u32 != 1
        || count != 0
        || level != 0x1000
        || unsafe { EqualSid(actual_sid, sid) } == 0
        || unsafe { IsProcessInJob(process, job, &mut in_job) } == 0
        || in_job == 0
    {
        return Err(format!(
            "containment_verification_failed:app={} caps={count} integrity={level:x} job={in_job}",
            app[0]
        ));
    }
    let mut duplicated = null_mut();
    if unsafe { DuplicateToken(raw(&token), SecurityImpersonation, &mut duplicated) } == 0 {
        return Err(error("duplicate_token"));
    }
    let duplicate = own(duplicated);
    let text = sid_text(actual_sid)?;
    let package = access(raw(&duplicate), Some(&text))?;
    let restricted = access(raw(&duplicate), Some("S-1-15-2-2"))?;
    let ordinary = access(raw(&duplicate), Some("S-1-15-2-1"))?;
    let everyone = access(raw(&duplicate), None)?;
    let combined = access_descriptor(
        raw(&duplicate),
        "O:SYG:SYD:(A;;0x3;;;WD)(A;;0x1;;;S-1-15-2-1)(A;;0x2;;;S-1-15-2-2)",
        MAXIMUM_ALLOWED,
    )?;
    if !package || !restricted || ordinary || everyone || combined != (1, 2) {
        return Err(format!(
            "lpac_kernel_policy_failed:package={package} arap={restricted} aap={ordinary} everyone={everyone} combined={combined:?}"
        ));
    }
    Ok(Token {
        lpac: true,
        verification_method: "kernel_accesscheck_package_policy".into(),
        class46_query,
        sid: sid_text(actual_sid)?,
        integrity: level,
        capabilities: count,
        job: true,
    })
}
fn access(token: HANDLE, package: Option<&str>) -> Result<bool, String> {
    // SYSTEM owner prevents an implicit owner grant; no generic rights or MIC
    // influence the single custom bit. Everyone satisfies the user-side pass.
    let mut sddl = String::from("O:SYG:SYD:(A;;0x1;;;WD)");
    if let Some(package) = package {
        sddl.push_str(&format!("(A;;0x1;;;{package})"));
    }
    match access_descriptor(token, &sddl, 1)? {
        (0, 0) => Ok(false),
        (1, 1) => Ok(true),
        (status, granted) => Err(format!("ambiguous_accesscheck:{status}:{granted}")),
    }
}
fn access_descriptor(token: HANDLE, sddl: &str, desired: u32) -> Result<(i32, u32), String> {
    let mut sd = null_mut();
    if unsafe {
        ConvertStringSecurityDescriptorToSecurityDescriptorW(
            wide(&sddl).as_ptr(),
            1,
            &mut sd,
            null_mut(),
        )
    } == 0
    {
        return Err(error("access_descriptor"));
    }
    let mut mapping = GENERIC_MAPPING::default();
    let mut privileges = [0usize; 128];
    let mut privilege_bytes = size_of_val(&privileges) as u32;
    let mut granted = 0;
    let mut status = 0;
    let ok = unsafe {
        AccessCheck(
            sd,
            token,
            desired,
            &mut mapping,
            privileges.as_mut_ptr().cast(),
            &mut privilege_bytes,
            &mut granted,
            &mut status,
        )
    };
    let failure = error("kernel_accesscheck");
    unsafe {
        LocalFree(sd);
    }
    if ok == 0 {
        return Err(failure);
    }
    Ok((status, granted))
}
fn pipe() -> Result<(OwnedHandle, OwnedHandle), String> {
    let attrs = SECURITY_ATTRIBUTES {
        nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
        lpSecurityDescriptor: null_mut(),
        bInheritHandle: 1,
    };
    let (mut read, mut write) = (null_mut(), null_mut());
    if unsafe { CreatePipe(&mut read, &mut write, &attrs, 0) } == 0 {
        return Err(error("pipe_create"));
    }
    Ok((own(read), own(write)))
}
struct Attributes {
    storage: Vec<usize>,
}
impl Attributes {
    fn new(count: u32) -> Result<Self, String> {
        let mut bytes = 0;
        unsafe {
            InitializeProcThreadAttributeList(null_mut(), count, 0, &mut bytes);
        }
        let mut storage = vec![0usize; bytes.div_ceil(size_of::<usize>())];
        if unsafe {
            InitializeProcThreadAttributeList(storage.as_mut_ptr().cast(), count, 0, &mut bytes)
        } == 0
        {
            return Err(error("attribute_init"));
        }
        Ok(Self { storage })
    }
    fn ptr(&mut self) -> *mut c_void {
        self.storage.as_mut_ptr().cast()
    }
    fn add(&mut self, kind: u32, value: *const c_void, len: usize) -> Result<(), String> {
        if unsafe {
            UpdateProcThreadAttribute(self.ptr(), 0, kind as usize, value, len, null_mut(), null())
        } == 0
        {
            return Err(error("attribute_set"));
        }
        Ok(())
    }
}
impl Drop for Attributes {
    fn drop(&mut self) {
        unsafe {
            DeleteProcThreadAttributeList(self.ptr());
        }
    }
}
fn quote(s: &str) -> String {
    let mut out = String::from("\"");
    let mut slashes = 0;
    for ch in s.chars() {
        if ch == '\\' {
            slashes += 1;
        } else {
            out.extend(std::iter::repeat_n(
                '\\',
                if ch == '"' { slashes * 2 + 1 } else { slashes },
            ));
            slashes = 0;
            out.push(ch);
        }
    }
    out.extend(std::iter::repeat_n('\\', slashes * 2));
    out.push('"');
    out
}
