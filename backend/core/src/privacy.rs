//! Owner-only state/temporary storage. DPAPI seals offline backup payloads.
use crate::{CoreError, CoreResult};
use std::{
    fs::File,
    ops::{Deref, DerefMut},
    path::{Path, PathBuf},
};
/// Retain no-delete ancestor handles for the duration of each sensitive effect.
pub(crate) struct GuardedFile {
    pub(crate) file: File,
    _pins: Vec<File>,
}
impl Deref for GuardedFile {
    type Target = File;
    fn deref(&self) -> &File {
        &self.file
    }
}
impl DerefMut for GuardedFile {
    fn deref_mut(&mut self) -> &mut File {
        &mut self.file
    }
}
pub(crate) struct DirectoryGuard {
    _pins: Vec<File>,
}
fn failure() -> CoreError {
    CoreError::new(
        "private_storage_unavailable",
        "Owner-scoped storage protection failed",
    )
}
pub(crate) fn absolute(path: &Path) -> CoreResult<PathBuf> {
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        if path.as_os_str().encode_wide().any(|c| c == 0) {
            return Err(failure());
        }
    }
    let p = if path.is_absolute() {
        path.to_owned()
    } else {
        std::env::current_dir().map_err(|_| failure())?.join(path)
    };
    if p.components()
        .any(|c| matches!(c, std::path::Component::ParentDir))
    {
        return Err(failure());
    }
    let p: PathBuf = p.components().collect();
    #[cfg(windows)]
    if p.components()
        .any(|c| matches!(c,std::path::Component::Normal(n) if n.to_string_lossy().contains(':')))
    {
        return Err(failure());
    }
    for ancestor in p.ancestors() {
        if let Ok(m) = std::fs::symlink_metadata(ancestor) {
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if m.file_attributes() & 0x400 != 0 {
                    return Err(failure());
                }
            }
            if m.file_type().is_symlink() {
                return Err(failure());
            }
        }
    }
    Ok(p)
}
pub(crate) fn principal() -> CoreResult<String> {
    #[cfg(windows)]
    {
        crate::runner::owner_sid().map_err(|_| failure())
    }
    #[cfg(unix)]
    {
        unsafe extern "C" {
            fn geteuid() -> u32;
        }
        Ok(format!("uid:{}", unsafe { geteuid() }))
    }
    #[cfg(not(any(windows, unix)))]
    {
        Err(failure())
    }
}
pub(crate) fn directory(path: &Path) -> CoreResult<PathBuf> {
    let p = absolute(path)?;
    if !p.exists() {
        if let Some(parent) = p.parent() {
            if !parent.is_dir() {
                directory(parent)?;
            }
        }
        #[cfg(windows)]
        {
            let _pins = windows::parents(&p)?;
            windows::mkdir(&p)?;
        }
        #[cfg(not(windows))]
        {
            std::fs::create_dir(&p).map_err(|_| failure())?;
        }
    }
    protect(&p, true)?;
    Ok(p)
}
pub(crate) fn pin_directory(path: &Path) -> CoreResult<DirectoryGuard> {
    let p = absolute(path)?;
    #[cfg(windows)]
    {
        let mut pins = windows::parents(&p)?;
        pins.push(windows::open(&p, true, false)?);
        Ok(DirectoryGuard { _pins: pins })
    }
    #[cfg(not(windows))]
    {
        let _ = p;
        Ok(DirectoryGuard { _pins: Vec::new() })
    }
}
/// Atomically refuse an existing restore target; never adopt a concurrently
/// created directory after an earlier `exists` check.
pub(crate) fn fresh_directory(path: &Path) -> CoreResult<(PathBuf, DirectoryGuard)> {
    let p = absolute(path)?;
    #[cfg(windows)]
    {
        let _pins = windows::parents(&p)?;
        windows::mkdir(&p)?;
    }
    #[cfg(not(windows))]
    {
        std::fs::create_dir(&p).map_err(|_| failure())?;
    }
    protect(&p, true)?;
    let guard = pin_directory(&p)?;
    Ok((p, guard))
}
pub(crate) fn new_file(path: &Path) -> CoreResult<GuardedFile> {
    let p = absolute(path)?;
    #[cfg(windows)]
    {
        let pins = windows::parents(&p)?;
        let file = windows::create(&p)?;
        Ok(GuardedFile { file, _pins: pins })
    }
    #[cfg(not(windows))]
    {
        use std::os::unix::fs::OpenOptionsExt;
        let file = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(p)
            .map_err(|_| failure())?;
        Ok(GuardedFile {
            file,
            _pins: Vec::new(),
        })
    }
}
pub(crate) fn regular_file(path: &Path) -> CoreResult<GuardedFile> {
    let p = absolute(path)?;
    #[cfg(windows)]
    {
        let pins = windows::parents(&p)?;
        let file = windows::open(&p, false, false)?;
        windows::owner(&file)?;
        Ok(GuardedFile { file, _pins: pins })
    }
    #[cfg(not(windows))]
    {
        use std::os::unix::fs::MetadataExt;
        let file = File::open(p).map_err(|_| failure())?;
        let meta = file.metadata().map_err(|_| failure())?;
        if !meta.is_file() || meta.nlink() != 1 {
            return Err(failure());
        }
        Ok(GuardedFile {
            file,
            _pins: Vec::new(),
        })
    }
}
pub(crate) fn lock_file(path: &Path) -> CoreResult<GuardedFile> {
    let p = absolute(path)?;
    if !p.exists() {
        match new_file(&p) {
            Ok(file) => return Ok(file),
            Err(_) if p.exists() => (),
            Err(error) => return Err(error),
        }
    }
    #[cfg(windows)]
    {
        let pins = windows::parents(&p)?;
        let file = windows::open(&p, false, true)?;
        windows::owner(&file)?;
        Ok(GuardedFile { file, _pins: pins })
    }
    #[cfg(not(windows))]
    {
        let file = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(&p)
            .map_err(|_| failure())?;
        Ok(GuardedFile {
            file,
            _pins: Vec::new(),
        })
    }
}
pub(crate) fn protect(path: &Path, directory: bool) -> CoreResult<()> {
    let p = absolute(path)?;
    #[cfg(windows)]
    {
        windows::protect(&p, directory)
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::{MetadataExt, PermissionsExt};
        let m = std::fs::symlink_metadata(&p).map_err(|_| failure())?;
        unsafe extern "C" {
            fn geteuid() -> u32;
        }
        if m.uid() != unsafe { geteuid() } {
            return Err(failure());
        }
        std::fs::set_permissions(
            p,
            std::fs::Permissions::from_mode(if directory { 0o700 } else { 0o600 }),
        )
        .map_err(|_| failure())
    }
    #[cfg(not(any(windows, unix)))]
    {
        Err(failure())
    }
}
pub(crate) fn seal(bytes: &[u8]) -> CoreResult<Vec<u8>> {
    #[cfg(windows)]
    {
        windows::crypt(bytes, false)
    }
    #[cfg(not(windows))]
    {
        let _ = bytes;
        Err(CoreError::new(
            "backup_protection_unavailable",
            "Protected backups require a supported owner key provider",
        ))
    }
}
pub(crate) fn unseal(bytes: &[u8]) -> CoreResult<Vec<u8>> {
    #[cfg(windows)]
    {
        windows::crypt(bytes, true)
    }
    #[cfg(not(windows))]
    {
        let _ = bytes;
        Err(failure())
    }
}
#[cfg(windows)]
mod windows {
    use super::*;
    use std::{
        ffi::c_void,
        os::windows::{
            ffi::OsStrExt,
            fs::OpenOptionsExt,
            io::{AsRawHandle, FromRawHandle},
        },
        ptr::{null, null_mut},
    };
    use windows_sys::Win32::{
        Foundation::{INVALID_HANDLE_VALUE, LocalFree},
        Security::{
            Authorization::{
                ConvertStringSecurityDescriptorToSecurityDescriptorW, GetSecurityInfo,
                SE_FILE_OBJECT, SetSecurityInfo,
            },
            GetSecurityDescriptorDacl, OWNER_SECURITY_INFORMATION, SECURITY_ATTRIBUTES,
        },
        Storage::FileSystem::{
            BY_HANDLE_FILE_INFORMATION, CreateDirectoryW, CreateFileW, GetFileInformationByHandle,
        },
    };
    #[repr(C)]
    struct Blob {
        len: u32,
        data: *mut u8,
    }
    #[link(name = "crypt32")]
    unsafe extern "system" {
        fn CryptProtectData(
            input: *const Blob,
            description: *const u16,
            entropy: *const Blob,
            reserved: *mut c_void,
            prompt: *mut c_void,
            flags: u32,
            out: *mut Blob,
        ) -> i32;
        fn CryptUnprotectData(
            input: *const Blob,
            description: *mut *mut u16,
            entropy: *const Blob,
            reserved: *mut c_void,
            prompt: *mut c_void,
            flags: u32,
            out: *mut Blob,
        ) -> i32;
    }
    pub(super) fn open(path: &Path, directory: bool, write: bool) -> CoreResult<File> {
        let file = std::fs::OpenOptions::new()
            .read(true)
            .access_mode(if write { 0xc0060000 } else { 0x80000000 })
            .share_mode(3)
            .custom_flags(0x00200000 | if directory { 0x02000000 } else { 0 })
            .open(path)
            .map_err(|_| failure())?;
        let mut info: BY_HANDLE_FILE_INFORMATION = unsafe { std::mem::zeroed() };
        if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut info) } == 0
            || info.dwFileAttributes & 0x400 != 0
            || (info.dwFileAttributes & 0x10 != 0) != directory
            || (!directory && info.nNumberOfLinks != 1)
        {
            return Err(failure());
        }
        Ok(file)
    }
    pub(super) fn parents(path: &Path) -> CoreResult<Vec<File>> {
        let mut paths: Vec<_> = path
            .parent()
            .ok_or_else(failure)?
            .ancestors()
            .filter(|p| p.has_root())
            .collect();
        paths.reverse();
        paths.into_iter().map(|p| open(p, true, false)).collect()
    }
    pub(super) fn owner(file: &File) -> CoreResult<()> {
        let principal = principal()?;
        let mut owner = null_mut();
        let mut original = null_mut();
        let result = unsafe {
            GetSecurityInfo(
                file.as_raw_handle(),
                SE_FILE_OBJECT,
                OWNER_SECURITY_INFORMATION,
                &mut owner,
                null_mut(),
                null_mut(),
                null_mut(),
                &mut original,
            )
        };
        if result != 0 {
            return Err(failure());
        }
        let actual = crate::runner::sid_text(owner);
        unsafe {
            LocalFree(original);
        }
        if actual.ok().as_deref() != Some(principal.as_str()) {
            return Err(failure());
        }
        Ok(())
    }
    struct Descriptor(*mut c_void);
    impl Drop for Descriptor {
        fn drop(&mut self) {
            unsafe {
                LocalFree(self.0);
            }
        }
    }
    fn descriptor(directory: bool) -> CoreResult<Descriptor> {
        let principal = principal()?;
        let inherit = if directory { "OICI" } else { "" };
        let sddl: Vec<u16> =
            format!("O:{principal}D:P(A;{inherit};FA;;;SY)(A;{inherit};FA;;;{principal})")
                .encode_utf16()
                .chain(Some(0))
                .collect();
        let mut descriptor = null_mut();
        if unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl.as_ptr(),
                1,
                &mut descriptor,
                null_mut(),
            )
        } == 0
        {
            return Err(failure());
        }
        Ok(Descriptor(descriptor))
    }
    fn attrs(descriptor: &Descriptor) -> SECURITY_ATTRIBUTES {
        SECURITY_ATTRIBUTES {
            nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: descriptor.0,
            bInheritHandle: 0,
        }
    }
    pub(super) fn mkdir(path: &Path) -> CoreResult<()> {
        let sd = descriptor(true)?;
        let name: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
        if unsafe { CreateDirectoryW(name.as_ptr(), &attrs(&sd)) } == 0 {
            Err(failure())
        } else {
            Ok(())
        }
    }
    pub(super) fn create(path: &Path) -> CoreResult<File> {
        let sd = descriptor(false)?;
        let name: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
        let handle = unsafe {
            CreateFileW(
                name.as_ptr(),
                0xc0060000,
                3,
                &attrs(&sd),
                1,
                0x00200080,
                null_mut(),
            )
        };
        if handle == INVALID_HANDLE_VALUE {
            return Err(failure());
        }
        Ok(unsafe { File::from_raw_handle(handle) })
    }
    pub(super) fn protect(path: &Path, directory: bool) -> CoreResult<()> {
        let _pins = parents(path)?;
        let file = open(path, directory, true)?;
        owner(&file)?;
        let sd = descriptor(directory)?;
        let mut dacl = null_mut();
        let mut present = 0;
        let mut defaulted = 0;
        if unsafe { GetSecurityDescriptorDacl(sd.0, &mut present, &mut dacl, &mut defaulted) } == 0
            || present == 0
        {
            return Err(failure());
        }
        let status = unsafe {
            SetSecurityInfo(
                file.as_raw_handle(),
                SE_FILE_OBJECT,
                0x80000004,
                null_mut(),
                null_mut(),
                dacl,
                null_mut(),
            )
        };
        if status == 0 { Ok(()) } else { Err(failure()) }
    }
    pub(super) fn crypt(bytes: &[u8], decrypt: bool) -> CoreResult<Vec<u8>> {
        if bytes.len() > 256 * 1024 * 1024 {
            return Err(failure());
        }
        let input = Blob {
            len: bytes.len() as u32,
            data: bytes.as_ptr() as *mut u8,
        };
        let label = b"Synapse.OwnerBackup.v1";
        let entropy = Blob {
            len: label.len() as u32,
            data: label.as_ptr() as *mut u8,
        };
        let mut output = Blob {
            len: 0,
            data: null_mut(),
        };
        let ok = unsafe {
            if decrypt {
                CryptUnprotectData(
                    &input,
                    null_mut(),
                    &entropy,
                    null_mut(),
                    null_mut(),
                    1,
                    &mut output,
                )
            } else {
                CryptProtectData(
                    &input,
                    null(),
                    &entropy,
                    null_mut(),
                    null_mut(),
                    1,
                    &mut output,
                )
            }
        };
        if ok == 0 {
            return Err(CoreError::new(
                "backup_key_or_integrity",
                "Backup owner key is unavailable or archive was modified",
            ));
        }
        let result =
            unsafe { std::slice::from_raw_parts(output.data, output.len as usize).to_vec() };
        unsafe {
            for index in 0..output.len as usize {
                std::ptr::write_volatile(output.data.add(index), 0);
            }
            LocalFree(output.data.cast());
        }
        Ok(result)
    }
}
