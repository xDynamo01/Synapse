use crate::{
    contracts::{CoreError, CoreResult, MissionContract, SkillManifest, ToolOperation},
    store,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::path::Path;

pub(crate) fn sha(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|x| format!("{x:02x}"))
        .collect()
}

pub(crate) fn details(op: &ToolOperation) -> (&str, &str) {
    match op {
        ToolOperation::List { path } => ("workspace_list", path),
        ToolOperation::Read { path } => ("workspace_read", path),
        ToolOperation::Create { path, .. } => ("artifact_create", path),
        ToolOperation::Replace { path, .. } => ("artifact_replace", path),
    }
}

pub(crate) fn authorize(
    tx: &Transaction<'_>,
    mission: &str,
    op: &ToolOperation,
) -> CoreResult<Value> {
    let row: Option<(String, String)> = tx
        .query_row(
            "SELECT contract,state FROM missions WHERE id=?1",
            [mission],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .optional()?;
    let (raw, state) = row.ok_or_else(|| CoreError::new("not_found", "Mission not found"))?;
    if state != "approved" {
        return Err(CoreError::new(
            "mission_not_approved",
            "Mission is not approved",
        ));
    }
    let contract: MissionContract = serde_json::from_str(&raw)?;
    if contract.execution.is_some() {
        return Err(CoreError::new(
            "capability_unavailable",
            "Execution policy requires the integrated coordinator and enforcing runner",
        ));
    }
    let (action, path) = details(op);
    if !contract.actions.iter().any(|a| a == action)
        || !contract.resources.iter().any(|p| p == path)
    {
        return Err(CoreError::new(
            "permission_denied",
            "Action or exact resource is not approved",
        ));
    }
    if matches!(op, ToolOperation::Replace { .. }) && contract.rollback != "verified backup" {
        return Err(CoreError::new(
            "permission_denied",
            "Replacement requires verified backup policy",
        ));
    }
    if matches!(op, ToolOperation::Create { .. }) && contract.rollback != "manual removal" {
        return Err(CoreError::new(
            "permission_denied",
            "Create requires the manual removal rollback policy",
        ));
    }
    if let ToolOperation::Create { content, .. } | ToolOperation::Replace { content, .. } = op {
        if contract.artifact_digests.get(path).map(String::as_str)
            != Some(sha(content.as_bytes()).as_str())
        {
            return Err(CoreError::new(
                "permission_denied",
                "Artifact digest is not approved for this target",
            ));
        }
    }
    if matches!(op, ToolOperation::Replace { .. })
        && !contract.artifact_previous_digests.contains_key(path)
    {
        return Err(CoreError::new(
            "permission_denied",
            "Previous artifact digest is not approved",
        ));
    }
    let mut pin_result = Value::Null;
    if let Some(pin) = contract.skill {
        let row: Option<(String, String)> = tx
            .query_row(
                "SELECT manifest,digest FROM skills WHERE scope=?1 AND id=?2 AND version=?3",
                params![pin.scope, pin.id, pin.version],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()?;
        let (raw, digest) =
            row.ok_or_else(|| CoreError::new("contract_conflict", "Pinned Skill missing"))?;
        let skill: SkillManifest = serde_json::from_str(&raw)?;
        if pin.scope != contract.scope
            || digest != pin.digest
            || store::digest(&skill)? != digest
            || !skill.tools.iter().any(|x| x == action)
            || !skill.permissions.iter().any(|x| x == action)
            || skill
                .permissions
                .iter()
                .any(|x| !contract.actions.contains(x))
            || skill.tools.iter().any(|x| !contract.actions.contains(x))
        {
            return Err(CoreError::new(
                "permission_denied",
                "Pinned Skill does not authorize this tool",
            ));
        }
        pin_result = json!({"scope":pin.scope,"id":pin.id,"version":pin.version,"digest":digest});
    }
    Ok(pin_result)
}

pub(crate) fn previous_digest(
    tx: &Transaction<'_>,
    mission: &str,
    op: &ToolOperation,
) -> CoreResult<String> {
    authorize(tx, mission, op)?;
    let raw: String = tx.query_row(
        "SELECT contract FROM missions WHERE id=?1",
        [mission],
        |r| r.get(0),
    )?;
    let contract: MissionContract = serde_json::from_str(&raw)?;
    contract
        .artifact_previous_digests
        .get(details(op).1)
        .cloned()
        .ok_or_else(|| CoreError::new("permission_denied", "Previous digest missing"))
}

#[cfg(not(windows))]
pub(crate) fn prepare(_root: &Path, _state: &Path, _op: &ToolOperation) -> CoreResult<Broker> {
    Err(CoreError::new(
        "capability_unavailable",
        "Workspace tools currently require Windows",
    ))
}
#[cfg(not(windows))]
pub(crate) struct Broker;
#[cfg(not(windows))]
pub(crate) struct OwnedRead {
    pub identity: String,
    pub bytes: Vec<u8>,
}
#[cfg(not(windows))]
impl Broker {
    pub fn target(&self) -> String {
        String::new()
    }
    pub fn root_identity(&self) -> CoreResult<String> {
        Err(CoreError::new("capability_unavailable", "Windows required"))
    }
    pub fn execute(&self, _: &ToolOperation) -> CoreResult<Value> {
        Err(CoreError::new("capability_unavailable", "Windows required"))
    }
    pub fn replacement_snapshot(&mut self) -> CoreResult<(String, Vec<u8>)> {
        Err(CoreError::new("capability_unavailable", "Windows required"))
    }
    pub fn replacement_write(&mut self, _: &[u8]) -> CoreResult<()> {
        Err(CoreError::new("capability_unavailable", "Windows required"))
    }
    pub fn create_is_absent(&self) -> CoreResult<bool> {
        Err(CoreError::new("capability_unavailable", "Windows required"))
    }
    pub fn create_owned(&self, _: &[u8]) -> CoreResult<(String, Vec<u8>)> {
        Err(CoreError::new("capability_unavailable", "Windows required"))
    }
    pub fn read_owned_guarded(&self) -> CoreResult<OwnedRead> {
        Err(CoreError::new("capability_unavailable", "Windows required"))
    }
    pub fn delete_owned(&self, _: &str, _: &[u8]) -> CoreResult<()> {
        Err(CoreError::new("capability_unavailable", "Windows required"))
    }
}

#[cfg(windows)]
mod win {
    use super::*;
    use std::{
        fs::{File, OpenOptions},
        io::{Read, Seek, SeekFrom, Write},
        os::windows::{ffi::OsStrExt, fs::OpenOptionsExt, io::AsRawHandle},
        path::{Component, PathBuf},
    };
    use windows_sys::Win32::{
        Foundation::{GENERIC_READ, HANDLE},
        Globalization::{CSTR_EQUAL, CompareStringOrdinal},
        Storage::FileSystem::*,
    };

    fn fail(message: &str) -> CoreError {
        CoreError::new("path_denied", message)
    }
    fn same(a: &[u16], b: &[u16]) -> bool {
        unsafe {
            CompareStringOrdinal(a.as_ptr(), a.len() as i32, b.as_ptr(), b.len() as i32, 1)
                == CSTR_EQUAL
        }
    }
    fn within(path: &[u16], dir: &[u16]) -> bool {
        path.len() >= dir.len()
            && same(&path[..dir.len()], dir)
            && (path.len() == dir.len()
                || dir.last() == Some(&(b'\\' as u16))
                || path[dir.len()] == b'\\' as u16)
    }
    fn final_path(file: &File) -> CoreResult<Vec<u16>> {
        let handle = file.as_raw_handle() as HANDLE;
        let needed = unsafe { GetFinalPathNameByHandleW(handle, std::ptr::null_mut(), 0, 0) };
        if needed == 0 || needed > 32767 {
            return Err(fail("Cannot resolve opened handle"));
        }
        let mut buf = vec![0u16; needed as usize + 1];
        let len =
            unsafe { GetFinalPathNameByHandleW(handle, buf.as_mut_ptr(), buf.len() as u32, 0) };
        if len == 0 || len as usize >= buf.len() {
            return Err(fail("Cannot resolve opened handle"));
        }
        buf.truncate(len as usize);
        Ok(buf)
    }
    fn info(file: &File, directory: bool) -> CoreResult<BY_HANDLE_FILE_INFORMATION> {
        let mut i: BY_HANDLE_FILE_INFORMATION = unsafe { std::mem::zeroed() };
        if unsafe { GetFileInformationByHandle(file.as_raw_handle() as HANDLE, &mut i) } == 0 {
            return Err(fail("Cannot inspect file handle"));
        }
        if unsafe { GetFileType(file.as_raw_handle() as HANDLE) } != FILE_TYPE_DISK
            || i.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT != 0
            || (i.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY != 0) != directory
            || (!directory && i.nNumberOfLinks != 1)
        {
            return Err(fail("Reparse point, hard link or unexpected type"));
        }
        Ok(i)
    }
    fn identity(i: BY_HANDLE_FILE_INFORMATION) -> String {
        format!(
            "{:08x}:{:08x}{:08x}",
            i.dwVolumeSerialNumber, i.nFileIndexHigh, i.nFileIndexLow
        )
    }
    fn snapshot(f: &mut File) -> CoreResult<(String, Vec<u8>)> {
        let identity = identity(info(f, false)?);
        f.seek(SeekFrom::Start(0))
            .map_err(|_| fail("Cannot seek file"))?;
        let mut bytes = Vec::new();
        (&mut *f)
            .take(32769)
            .read_to_end(&mut bytes)
            .map_err(|_| fail("Cannot read file"))?;
        if bytes.len() > 32768 || std::str::from_utf8(&bytes).is_err() {
            return Err(fail("Only bounded UTF-8 files are supported"));
        }
        Ok((identity, bytes))
    }
    fn open(path: &Path, directory: bool) -> CoreResult<File> {
        let mut opts = OpenOptions::new();
        opts.read(true)
            .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE)
            .custom_flags(
                FILE_FLAG_OPEN_REPARSE_POINT
                    | if directory {
                        FILE_FLAG_BACKUP_SEMANTICS
                    } else {
                        0
                    },
            );
        let f = opts.open(path).map_err(|_| fail("Cannot open path"))?;
        info(&f, directory)?;
        Ok(f)
    }
    fn pin_ancestors(path: &Path, dirs: &mut Vec<File>) -> CoreResult<Vec<u16>> {
        let mut ancestors: Vec<&Path> = path.ancestors().filter(|p| p.has_root()).collect();
        ancestors.reverse();
        let volume = ancestors
            .first()
            .ok_or_else(|| fail("Absolute directory required"))?;
        let mut wide: Vec<u16> = volume.as_os_str().encode_wide().collect();
        wide.push(0);
        let mut filesystem = [0u16; 64];
        if unsafe { GetDriveTypeW(wide.as_ptr()) } != 3
            || unsafe {
                GetVolumeInformationW(
                    wide.as_ptr(),
                    std::ptr::null_mut(),
                    0,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    filesystem.as_mut_ptr(),
                    filesystem.len() as u32,
                )
            } == 0
            || !same(
                &filesystem[..filesystem
                    .iter()
                    .position(|x| *x == 0)
                    .unwrap_or(filesystem.len())],
                &[b'N' as u16, b'T' as u16, b'F' as u16, b'S' as u16],
            )
        {
            return Err(CoreError::new(
                "capability_unavailable",
                "Workspace tools require local fixed NTFS volumes",
            ));
        }
        let mut prior: Option<Vec<u16>> = None;
        for ancestor in ancestors {
            let f = open(ancestor, true)?;
            let actual = final_path(&f)?;
            if let Some(parent) = &prior {
                if !within(&actual, parent) {
                    return Err(fail("Directory identity changed"));
                }
            }
            prior = Some(actual);
            dirs.push(f);
        }
        prior.ok_or_else(|| fail("Absolute directory required"))
    }
    fn parts(raw: &str) -> CoreResult<Vec<String>> {
        if raw == "." {
            return Ok(vec![]);
        }
        if raw.is_empty() || raw.len() > 512 || raw.contains('\\') || raw.contains(':') {
            return Err(fail("Invalid relative path"));
        }
        let path = Path::new(raw);
        let mut out = Vec::new();
        for c in path.components() {
            let Component::Normal(s) = c else {
                return Err(fail("Invalid path component"));
            };
            let s = s.to_str().ok_or_else(|| fail("Invalid path encoding"))?;
            if s.is_empty()
                || s.ends_with('.')
                || s.ends_with(' ')
                || !s
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._- ".contains(&b))
            {
                return Err(fail("Invalid path component"));
            }
            let stem = s.split('.').next().unwrap().to_ascii_uppercase();
            if [
                "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7",
                "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8",
                "LPT9",
            ]
            .contains(&stem.as_str())
            {
                return Err(fail("Reserved name"));
            }
            out.push(s.to_string());
        }
        if raw
            .split('/')
            .any(|x| x.is_empty() || x == "." || x == "..")
            || out.is_empty()
        {
            return Err(fail("Invalid relative path"));
        }
        Ok(out)
    }
    pub(crate) struct OwnedRead {
        pub identity: String,
        pub bytes: Vec<u8>,
        _file: File,
    }

    pub(crate) struct Broker {
        dirs: Vec<File>,
        root_handle_index: usize,
        parent: PathBuf,
        leaf: Option<String>,
        target: String,
        root: Vec<u16>,
        state: Vec<u16>,
        replacement: Option<File>,
    }
    impl Broker {
        pub fn target(&self) -> String {
            self.target.clone()
        }
        pub fn root_identity(&self) -> CoreResult<String> {
            Ok(identity(info(&self.dirs[self.root_handle_index], true)?))
        }
        pub fn create_is_absent(&self) -> CoreResult<bool> {
            match std::fs::symlink_metadata(self.file_path()?) {
                Ok(_) => Ok(false),
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(true),
                Err(_) => Err(fail("Cannot inspect create target")),
            }
        }
        fn file_path(&self) -> CoreResult<PathBuf> {
            let leaf = self
                .leaf
                .as_ref()
                .ok_or_else(|| fail("File path required"))?;
            Ok(self.parent.join(leaf))
        }
        fn verify_file_path(&self, file: &File) -> CoreResult<()> {
            let actual = final_path(file)?;
            let expected: Vec<u16> = self.target.encode_utf16().collect();
            if !same(&actual, &expected)
                || !within(&actual, &self.root)
                || within(&actual, &self.state)
            {
                return Err(fail("Alias, protected or outside workspace"));
            }
            Ok(())
        }
        pub fn create_owned(&self, bytes: &[u8]) -> CoreResult<(String, Vec<u8>)> {
            if bytes.len() > 32768 || std::str::from_utf8(bytes).is_err() {
                return Err(CoreError::invalid("Only bounded UTF-8 files are supported"));
            }
            let mut file = OpenOptions::new()
                .read(true)
                .write(true)
                .create_new(true)
                .share_mode(0)
                .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
                .open(self.file_path()?)
                .map_err(|error| {
                    if error.kind() == std::io::ErrorKind::AlreadyExists {
                        CoreError::new("artifact_conflict", "Create target already exists")
                    } else {
                        CoreError::new("effect_failed", "Cannot create new file")
                    }
                })?;
            info(&file, false)?;
            self.verify_file_path(&file)?;
            file.write_all(bytes)
                .and_then(|_| file.sync_all())
                .map_err(|_| CoreError::new("effect_failed", "Cannot write and flush artifact"))?;
            let receipt = snapshot(&mut file)?;
            if receipt.1 != bytes {
                return Err(CoreError::new("effect_failed", "Artifact readback differs"));
            }
            Ok(receipt)
        }
        fn open_owned(&self, access: u32) -> CoreResult<File> {
            // Deny concurrent writes and renames during readback and compensation.
            let file = OpenOptions::new()
                .access_mode(access)
                .share_mode(0)
                .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
                .open(self.file_path()?)
                .map_err(|_| fail("Cannot exclusively open artifact"))?;
            self.verify_file_path(&file)?;
            Ok(file)
        }
        #[cfg(test)]
        pub fn read_owned(&self) -> CoreResult<(String, Vec<u8>)> {
            let receipt = self.read_owned_guarded()?;
            Ok((receipt.identity, receipt.bytes))
        }
        pub fn read_owned_guarded(&self) -> CoreResult<OwnedRead> {
            let mut file = self.open_owned(GENERIC_READ)?;
            let (identity, bytes) = snapshot(&mut file)?;
            Ok(OwnedRead {
                identity,
                bytes,
                _file: file,
            })
        }
        pub fn delete_owned(&self, identity: &str, bytes: &[u8]) -> CoreResult<()> {
            let mut file = self.open_owned(GENERIC_READ | DELETE)?;
            let (actual_identity, actual_bytes) = snapshot(&mut file)?;
            if actual_identity != identity || actual_bytes != bytes {
                return Err(CoreError::new(
                    "ownership_conflict",
                    "Artifact identity or bytes changed",
                ));
            }
            info(&file, false)?;
            // Mark the verified handle for deletion and close it before checking absence.
            let disposition = FILE_DISPOSITION_INFO { DeleteFile: true };
            if unsafe {
                SetFileInformationByHandle(
                    file.as_raw_handle() as HANDLE,
                    FileDispositionInfo,
                    (&disposition as *const FILE_DISPOSITION_INFO).cast(),
                    std::mem::size_of_val(&disposition) as u32,
                )
            } == 0
            {
                return Err(CoreError::new("effect_failed", "Artifact deletion refused"));
            }
            drop(file);
            if !self.create_is_absent()? {
                return Err(CoreError::new(
                    "effect_failed",
                    "Artifact absence not verified",
                ));
            }
            Ok(())
        }
        pub fn replacement_snapshot(&mut self) -> CoreResult<(String, Vec<u8>)> {
            let f = self
                .replacement
                .as_mut()
                .ok_or_else(|| fail("Replacement handle missing"))?;
            snapshot(f)
        }
        pub fn replacement_write(&mut self, bytes: &[u8]) -> CoreResult<()> {
            let f = self
                .replacement
                .as_mut()
                .ok_or_else(|| fail("Replacement handle missing"))?;
            info(f, false)?;
            f.seek(SeekFrom::Start(0))
                .and_then(|_| f.write_all(bytes))
                .and_then(|_| f.set_len(bytes.len() as u64))
                .and_then(|_| f.sync_all())
                .map_err(|_| {
                    CoreError::new("effect_failed", "Cannot write and flush replacement")
                })?;
            let (_, actual) = self.replacement_snapshot()?;
            if actual != bytes {
                return Err(CoreError::new(
                    "effect_failed",
                    "Replacement readback differs",
                ));
            }
            Ok(())
        }
        pub fn execute(&self, op: &ToolOperation) -> CoreResult<Value> {
            let path = self
                .leaf
                .as_ref()
                .map_or(self.parent.clone(), |x| self.parent.join(x));
            match op {
                ToolOperation::List { .. } => {
                    let mut entries = Vec::new();
                    let mut scanned = 0;
                    for item in
                        std::fs::read_dir(&path).map_err(|_| fail("Cannot list directory"))?
                    {
                        scanned += 1;
                        if scanned > 128 {
                            return Err(CoreError::new(
                                "response_too_large",
                                "Directory exceeds 128 entries",
                            ));
                        }
                        let item = item.map_err(|_| fail("Cannot list directory"))?;
                        let n = item.file_name().to_string_lossy().into_owned();
                        if entries.len() >= 128 {
                            return Err(CoreError::new(
                                "response_too_large",
                                "Directory exceeds 128 entries",
                            ));
                        }
                        let child = item.path();
                        if let Ok(f) = open(&child, true).or_else(|_| open(&child, false)) {
                            let actual = final_path(&f)?;
                            if within(&actual, &self.root) && !within(&actual, &self.state) {
                                entries.push(n);
                            }
                        }
                    }
                    entries.sort();
                    Ok(json!({"entries":entries}))
                }
                ToolOperation::Read { .. } => {
                    let f = open(&path, false)?;
                    let actual = final_path(&f)?;
                    if !within(&actual, &self.root) || within(&actual, &self.state) {
                        return Err(fail("Protected or outside workspace"));
                    }
                    let mut bytes = Vec::new();
                    f.take(32769)
                        .read_to_end(&mut bytes)
                        .map_err(|_| fail("Cannot read file"))?;
                    if bytes.len() > 32768 {
                        return Err(CoreError::new(
                            "response_too_large",
                            "File exceeds read limit",
                        ));
                    }
                    let content = String::from_utf8(bytes.clone())
                        .map_err(|_| fail("Only UTF-8 files are supported"))?;
                    Ok(json!({"content":content,"sha256":sha(&bytes),"bytes":bytes.len()}))
                }
                ToolOperation::Create { content, .. } => {
                    if content.len() > 32768 {
                        return Err(CoreError::invalid("Content exceeds 32768 bytes"));
                    }
                    let mut opts = OpenOptions::new();
                    opts.read(true)
                        .write(true)
                        .create_new(true)
                        .share_mode(FILE_SHARE_READ)
                        .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT);
                    let mut f = opts
                        .open(&path)
                        .map_err(|_| CoreError::new("effect_failed", "Cannot create new file"))?;
                    info(&f, false)?;
                    let actual = final_path(&f)?;
                    if !within(&actual, &self.root) || within(&actual, &self.state) {
                        return Err(fail("Protected or outside workspace"));
                    }
                    f.write_all(content.as_bytes())
                        .and_then(|_| f.sync_all())
                        .and_then(|_| f.seek(SeekFrom::Start(0)).map(|_| ()))
                        .map_err(|_| {
                            CoreError::new("effect_failed", "Cannot write and flush artifact")
                        })?;
                    let mut readback = Vec::new();
                    f.take(32769)
                        .read_to_end(&mut readback)
                        .map_err(|_| CoreError::new("effect_failed", "Cannot read artifact"))?;
                    if readback != content.as_bytes() {
                        return Err(CoreError::new("effect_failed", "Artifact readback differs"));
                    }
                    Ok(
                        json!({"sha256":sha(&readback),"bytes":readback.len(),"readback_verified":true}),
                    )
                }
                ToolOperation::Replace { .. } => Err(CoreError::new(
                    "capability_unavailable",
                    "Replacement unavailable",
                )),
            }
        }
    }
    pub(crate) fn prepare(root: &Path, state: &Path, op: &ToolOperation) -> CoreResult<Broker> {
        let (_, raw) = details(op);
        let components = parts(raw)?;
        let mut dirs = Vec::new();
        let root_real = pin_ancestors(root, &mut dirs)?;
        let root_handle_index = dirs.len() - 1;
        let state_real = pin_ancestors(state, &mut dirs)?;
        let is_list = matches!(op, ToolOperation::List { .. });
        if components.is_empty() && !is_list {
            return Err(fail("File path required"));
        }
        let parent_count = if is_list {
            components.len()
        } else {
            components.len() - 1
        };
        let mut current = root.to_path_buf();
        for part in &components[..parent_count] {
            current.push(part);
            let f = open(&current, true)?;
            let actual = final_path(&f)?;
            if !within(&actual, &root_real) || within(&actual, &state_real) {
                return Err(fail("Protected or outside workspace"));
            }
            dirs.push(f);
        }
        let parent_real = final_path(dirs.last().unwrap())?;
        // With no components the last retained handle is the state handle, not the root.
        let parent_real = if parent_count == 0 {
            root_real.clone()
        } else {
            parent_real
        };
        if within(&parent_real, &state_real) {
            return Err(fail("Protected state"));
        }
        let leaf = if is_list {
            None
        } else {
            components.last().cloned()
        };
        let mut target = String::from_utf16(&parent_real).map_err(|_| fail("Invalid path"))?;
        if let Some(l) = &leaf {
            if !target.ends_with('\\') {
                target.push('\\');
            }
            target.push_str(l);
        }
        let replacement = if matches!(op, ToolOperation::Replace { .. }) {
            let path = current.join(leaf.as_ref().unwrap());
            let mut opts = OpenOptions::new();
            opts.read(true)
                .write(true)
                .share_mode(0)
                .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT);
            let file = opts
                .open(&path)
                .map_err(|_| fail("Cannot exclusively open replacement target"))?;
            info(&file, false)?;
            let actual = final_path(&file)?;
            let expected: Vec<u16> = target.encode_utf16().collect();
            if !same(&actual, &expected)
                || !within(&actual, &root_real)
                || within(&actual, &state_real)
            {
                return Err(fail("Alias, protected or outside workspace"));
            }
            Some(file)
        } else {
            None
        };
        Ok(Broker {
            dirs,
            root_handle_index,
            parent: current,
            leaf,
            target,
            root: root_real,
            state: state_real,
            replacement,
        })
    }

    #[cfg(test)]
    mod owned_tests {
        use super::*;
        use std::fs;

        const CONTENT: &[u8] = b"verified artifact\n";

        fn fixture() -> (tempfile::TempDir, PathBuf, Broker) {
            let temp = tempfile::tempdir().unwrap();
            let workspace = temp.path().join("workspace");
            let state = temp.path().join("state");
            fs::create_dir(&workspace).unwrap();
            fs::create_dir(&state).unwrap();
            let broker = prepare(
                &workspace,
                &state,
                &ToolOperation::Read {
                    path: "artifact.txt".into(),
                },
            )
            .unwrap();
            (temp, workspace.join("artifact.txt"), broker)
        }

        #[test]
        fn root_identity_changes_when_the_directory_is_exchanged() {
            let (temp, path, broker) = fixture();
            let workspace = path.parent().unwrap();
            let original = temp.path().join("original_workspace");
            let identity = broker.root_identity().unwrap();
            assert!(fs::rename(workspace, &original).is_err());
            drop(broker);
            fs::rename(workspace, &original).unwrap();
            fs::create_dir(workspace).unwrap();
            let current = prepare(
                workspace,
                &temp.path().join("state"),
                &ToolOperation::Read {
                    path: "artifact.txt".into(),
                },
            )
            .unwrap();
            assert_ne!(current.root_identity().unwrap(), identity);
        }

        #[test]
        fn create_read_and_delete_share_the_same_identity_and_bytes() {
            let (_temp, path, broker) = fixture();
            let receipt = broker.create_owned(CONTENT).unwrap();
            assert_eq!(receipt.1, CONTENT);
            assert_eq!(fs::read(&path).unwrap(), CONTENT);
            assert_eq!(broker.read_owned().unwrap(), receipt);
            broker.delete_owned(&receipt.0, CONTENT).unwrap();
            assert!(broker.create_is_absent().unwrap());
        }

        #[test]
        fn guarded_read_holds_exclusive_access_until_dropped() {
            let (_temp, path, broker) = fixture();
            let (identity, _) = broker.create_owned(CONTENT).unwrap();
            let read = broker.read_owned_guarded().unwrap();
            assert_eq!(read.identity, identity);
            assert_eq!(read.bytes, CONTENT);
            assert!(fs::write(&path, b"changed").is_err());
            assert!(fs::rename(&path, path.with_file_name("moved.txt")).is_err());
            drop(read);
            fs::write(&path, b"changed").unwrap();
        }

        #[test]
        fn create_conflict_preserves_occupied_file() {
            let (_temp, path, broker) = fixture();
            fs::write(&path, b"already here").unwrap();
            assert_eq!(
                broker.create_owned(CONTENT).unwrap_err().code,
                "artifact_conflict"
            );
            assert_eq!(fs::read(&path).unwrap(), b"already here");
        }

        #[test]
        fn read_and_delete_refuse_hard_links() {
            let (_temp, path, broker) = fixture();
            let (identity, _) = broker.create_owned(CONTENT).unwrap();
            let link = path.with_file_name("linked.txt");
            fs::hard_link(&path, &link).unwrap();
            assert_eq!(broker.read_owned().unwrap_err().code, "path_denied");
            assert_eq!(
                broker.delete_owned(&identity, CONTENT).unwrap_err().code,
                "path_denied"
            );
            assert_eq!(fs::read(&path).unwrap(), CONTENT);
            assert_eq!(fs::read(&link).unwrap(), CONTENT);
        }

        #[test]
        fn delete_refuses_changed_bytes_and_changed_identity() {
            let (_temp, path, broker) = fixture();
            let (identity, _) = broker.create_owned(CONTENT).unwrap();
            fs::write(&path, b"edited").unwrap();
            assert_eq!(
                broker.delete_owned(&identity, CONTENT).unwrap_err().code,
                "ownership_conflict"
            );
            assert_eq!(fs::read(&path).unwrap(), b"edited");
            let original = path.with_file_name("original.txt");
            fs::rename(&path, &original).unwrap();
            let (new_identity, _) = broker.create_owned(CONTENT).unwrap();
            assert_ne!(new_identity, identity);
            assert_eq!(
                broker.delete_owned(&identity, CONTENT).unwrap_err().code,
                "ownership_conflict"
            );
            assert_eq!(fs::read(&path).unwrap(), CONTENT);
            assert_eq!(fs::read(&original).unwrap(), b"edited");
        }

        #[test]
        fn delete_refusal_preserves_readonly_artifact() {
            let (_temp, path, broker) = fixture();
            let (identity, _) = broker.create_owned(CONTENT).unwrap();
            let mut permissions = fs::metadata(&path).unwrap().permissions();
            permissions.set_readonly(true);
            fs::set_permissions(&path, permissions.clone()).unwrap();
            let result = broker.delete_owned(&identity, CONTENT);
            permissions.set_readonly(false);
            fs::set_permissions(&path, permissions).unwrap();
            assert_eq!(result.unwrap_err().code, "effect_failed");
            assert_eq!(fs::read(&path).unwrap(), CONTENT);
        }

        #[test]
        fn owned_reads_enforce_the_byte_limit() {
            let (_temp, path, broker) = fixture();
            let oversized = vec![b'a'; 32769];
            assert_eq!(
                broker.create_owned(&oversized).unwrap_err().code,
                "invalid_request"
            );
            assert!(broker.create_is_absent().unwrap());
            fs::write(&path, oversized).unwrap();
            assert_eq!(broker.read_owned().unwrap_err().code, "path_denied");
        }
    }
}
#[cfg(windows)]
pub(crate) use win::{Broker, OwnedRead, prepare};
