//! Bounded real copies of explicitly configured owner tool assets.
use super::Control;
use sha2::{Digest, Sha256};
use std::{
    fs::{File, OpenOptions},
    io::{Read, Write},
    os::windows::{fs::OpenOptionsExt, io::AsRawHandle},
    path::{Path, PathBuf},
};
use windows_sys::Win32::Storage::FileSystem::{
    BY_HANDLE_FILE_INFORMATION, FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_REPARSE_POINT,
    FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT, FILE_SHARE_READ, FILE_SHARE_WRITE,
    FILE_STREAM_INFO, FileStreamInfo, GetFileInformationByHandle, GetFileInformationByHandleEx,
};

fn verified(path: &Path, directory: bool) -> Result<File, String> {
    verified_with_share(path, directory, FILE_SHARE_READ)
}

fn verified_with_share(path: &Path, directory: bool, share: u32) -> Result<File, String> {
    let file = OpenOptions::new()
        .read(true)
        .share_mode(share)
        .custom_flags(
            FILE_FLAG_OPEN_REPARSE_POINT
                | if directory {
                    FILE_FLAG_BACKUP_SEMANTICS
                } else {
                    0
                },
        )
        .open(path)
        .map_err(|e| format!("asset_open:{e}"))?;
    let mut info = BY_HANDLE_FILE_INFORMATION::default();
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut info) } == 0
        || info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT != 0
        || (info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY != 0) != directory
        || (!directory && info.nNumberOfLinks != 1)
    {
        return Err("unsafe_asset_identity".into());
    }
    Ok(file)
}

pub(super) fn sealed_directory(path: &Path) -> Result<File, String> {
    // LLD atomically renames a temporary output within this directory. Share
    // write access for that operation while denying deletion/replacement.
    verified_with_share(path, true, FILE_SHARE_READ | FILE_SHARE_WRITE)
}

/// Hold a checked output file across the next contained phase. The same handle
/// checks the identity and stream table, and disallows replacement and writes.
pub(super) fn sealed_output(path: &Path) -> Result<File, String> {
    let file = verified(path, false)?;
    if file.metadata().map_err(|_| "output_metadata")?.len() == 0 {
        return Err("empty_phase_output".into());
    }
    let mut buffer = [0u64; 32];
    if unsafe {
        GetFileInformationByHandleEx(
            file.as_raw_handle(),
            FileStreamInfo,
            buffer.as_mut_ptr().cast(),
            std::mem::size_of_val(&buffer) as u32,
        )
    } == 0
    {
        return Err("output_stream_query".into());
    }
    let stream = unsafe { &*buffer.as_ptr().cast::<FILE_STREAM_INFO>() };
    const DEFAULT_STREAM: &str = "::$DATA";
    if stream.NextEntryOffset != 0
        || stream.StreamNameLength as usize != DEFAULT_STREAM.len() * size_of::<u16>()
    {
        return Err("unexpected_output_stream".into());
    }
    let name = unsafe {
        std::slice::from_raw_parts(
            buffer
                .as_ptr()
                .cast::<u8>()
                .add(std::mem::offset_of!(FILE_STREAM_INFO, StreamName))
                .cast::<u16>(),
            DEFAULT_STREAM.len(),
        )
    };
    if !name.iter().copied().eq(DEFAULT_STREAM.encode_utf16()) {
        return Err("unexpected_output_stream".into());
    }
    Ok(file)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn phase_output_rejects_hardlinks_and_alternate_streams() {
        let root = tempfile::TempDir::new().unwrap();
        let output = root.path().join("check.obj");
        std::fs::write(&output, b"fixture").unwrap();
        assert!(sealed_output(&output).is_ok());
        let alias = root.path().join("alias.obj");
        std::fs::hard_link(&output, &alias).unwrap();
        assert_eq!(sealed_output(&output).unwrap_err(), "unsafe_asset_identity");
        std::fs::remove_file(alias).unwrap();
        let mut stream = output.as_os_str().to_os_string();
        stream.push(":unexpected");
        std::fs::write(stream, b"stream").unwrap();
        assert_eq!(
            sealed_output(&output).unwrap_err(),
            "unexpected_output_stream"
        );
    }
}
fn ancestors(path: &Path) -> Result<(), String> {
    for ancestor in path.ancestors().skip(1) {
        if !ancestor.as_os_str().is_empty() {
            verified(ancestor, true)?;
        }
    }
    Ok(())
}
struct Copy<'a> {
    bytes: u64,
    control: &'a Control,
    root: &'a Path,
    files: Vec<(String, u64, String)>,
}

fn hex_digest(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

impl Copy<'_> {
    fn file(&mut self, source: &Path, target: &Path) -> Result<String, String> {
        self.control.preparation()?;
        ancestors(source)?;
        let mut input = verified(source, false)?;
        let mut output = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(target)
            .map_err(|e| format!("asset_create:{e}"))?;
        let mut buf = [0u8; 65536];
        let mut hash = Sha256::new();
        let mut file_bytes = 0u64;
        loop {
            self.control.preparation()?;
            let count = input.read(&mut buf).map_err(|_| "asset_read")?;
            if count == 0 {
                break;
            }
            self.bytes = self.bytes.checked_add(count as u64).ok_or("asset_limit")?;
            if self.bytes > 2147483648 {
                return Err("asset_limit".into());
            }
            file_bytes += count as u64;
            hash.update(&buf[..count]);
            output.write_all(&buf[..count]).map_err(|_| "asset_write")?;
        }
        output.sync_all().map_err(|_| "asset_write")?;
        let name = target
            .strip_prefix(self.root)
            .ok()
            .and_then(Path::to_str)
            .ok_or("asset_relative_path")?
            .replace('\\', "/");
        let digest = hex_digest(&hash.finalize());
        self.files.push((name, file_bytes, digest.clone()));
        Ok(digest)
    }

    fn digest(mut self) -> String {
        self.files.sort_unstable();
        let mut hash = Sha256::new();
        for (path, bytes, digest) in self.files {
            hash.update((path.len() as u64).to_be_bytes());
            hash.update(path.as_bytes());
            hash.update(bytes.to_be_bytes());
            hash.update(digest.as_bytes());
        }
        hex_digest(&hash.finalize())
    }
    fn tree(&mut self, source: &Path, target: &Path) -> Result<(), String> {
        self.control.preparation()?;
        ancestors(source)?;
        let _hold = verified(source, true)?;
        std::fs::create_dir(target).map_err(|_| "asset_directory")?;
        for entry in std::fs::read_dir(source).map_err(|_| "asset_directory")? {
            let entry = entry.map_err(|_| "asset_directory")?;
            let name = entry.file_name();
            let name = name.to_string_lossy();
            if ["test", "tests", "site-packages", "__pycache__"].contains(&name.as_ref())
                || [".pth", ".pyc", ".pyo"].iter().any(|e| name.ends_with(e))
                || ["sitecustomize.py", "usercustomize.py"].contains(&name.as_ref())
            {
                continue;
            }
            let from = entry.path();
            let to = target.join(name.as_ref());
            if entry.file_type().map_err(|_| "asset_type")?.is_dir() {
                self.tree(&from, &to)?;
            } else {
                self.file(&from, &to)?;
            }
        }
        Ok(())
    }
}
pub(super) fn python(
    executable: &Path,
    target: &Path,
    control: &Control,
) -> Result<PathBuf, String> {
    if !executable.is_absolute()
        || executable.file_name().and_then(|s| s.to_str()) != Some("python.exe")
    {
        return Err("toolchain_unavailable".into());
    }
    let source = executable.parent().ok_or("toolchain_unavailable")?;
    let mut copy = Copy {
        bytes: 0,
        control,
        root: target,
        files: Vec::new(),
    };
    copy.file(executable, &target.join("python.exe"))?;
    for entry in std::fs::read_dir(source).map_err(|_| "toolchain_unavailable")? {
        let entry = entry.map_err(|_| "toolchain_unavailable")?;
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if name.ends_with(".dll") {
            copy.file(&entry.path(), &target.join(name.as_ref()))?;
        }
    }
    copy.tree(&source.join("Lib"), &target.join("Lib"))?;
    copy.tree(&source.join("DLLs"), &target.join("DLLs"))?;
    Ok(target.join("python.exe"))
}

const RUST_TARGET: &str = "x86_64-pc-windows-msvc";

// Stable 1.96.0 (ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96). Keep the
// matching Rust/LLVM binaries and standard-library layout together.
const RUST_EXECUTABLES: [(&str, &str); 4] = [
    (
        "bin/rustc.exe",
        "acb138286bbe20c6cf3ec39a7e0a68c3fab0cd949baa2912cf466514d0d531ab",
    ),
    (
        "bin/rustc_driver-a13b2a09f32f9fcf.dll",
        "3d2ffa6ea9c003669aecaa173f03d479cac1e42eed9cad624dfb1085bde5d6df",
    ),
    (
        "bin/std-f6a1efc0b26a278e.dll",
        "837c9f26736e8bcf8572020f6f95169029bcea4d537e6ee60f410133a75683a2",
    ),
    (
        "lib/rustlib/x86_64-pc-windows-msvc/bin/rust-lld.exe",
        "6c4c105ed5d6d9cc45322c1f7cb149ac8c2d262ce1c393e134f8fc7730335311",
    ),
];
const RUST_LINK_CRATES: &[&str] = &[
    "test-d6d264ee84bd4196",
    "getopts-2856b343c67ec8a5",
    "rustc_std_workspace_std-ffa91dc1d8e99fd5",
    "std-f6a1efc0b26a278e",
    "panic_unwind-90f24475c2dadfb3",
    "cfg_if-2d70a11e4a249f4c",
    "windows_link-a36b0a9019dd5e28",
    "rustc_demangle-20df77ba1ccb827e",
    "std_detect-72562e3bcf55d18a",
    "hashbrown-379c2b5854b7942b",
    "rustc_std_workspace_alloc-0fc8fdb483aa915c",
    "unwind-63d02d00483a3a96",
    "rustc_std_workspace_core-f5fff62847b8386e",
    "alloc-4007f5acb6859617",
    "core-d378bf52e32e9198",
    "compiler_builtins-0cdac2e568b3eee7",
];
const RUST_METADATA_CRATES: &[&str] = &[
    "panic_abort-80cad03f5519e354",
    "proc_macro-95968c7daeee49bc",
    "profiler_builtins-1f34af11b6763157",
    "rustc_literal_escaper-8d617a7e42322ac6",
    "sysroot-c30b5f7161e3bc9f",
];
const WIN_IMPORT_LIBS: &[&str] = &[
    "kernel32.lib",
    "ntdll.lib",
    "userenv.lib",
    "ws2_32.lib",
    "dbghelp.lib",
];

pub(super) struct RustConfig {
    pub sysroot: PathBuf,
    pub vc_x64_lib: PathBuf,
    pub sdk_um_x64_lib: PathBuf,
    pub sdk_ucrt_x64_lib: PathBuf,
}

pub(super) struct RustAssets {
    pub compiler: PathBuf,
    pub linker: PathBuf,
    pub sysroot: PathBuf,
    pub libraries: Vec<PathBuf>,
    pub native_dirs: [PathBuf; 3],
    pub digest: String,
    pub bytes: u64,
}

pub(super) fn rust(
    config: &RustConfig,
    target: &Path,
    control: &Control,
) -> Result<RustAssets, String> {
    for source in [
        &config.sysroot,
        &config.vc_x64_lib,
        &config.sdk_um_x64_lib,
        &config.sdk_ucrt_x64_lib,
    ] {
        if !source.is_absolute() {
            return Err("toolchain_unavailable".into());
        }
    }
    let source_rust = config.sysroot.join("lib").join("rustlib").join(RUST_TARGET);
    let target_rust = target.join("lib").join("rustlib").join(RUST_TARGET);
    let target_lib = target_rust.join("lib");
    let native_dirs = ["vc", "um", "ucrt"].map(|name| target.join(name));
    for dir in [
        &target.join("bin"),
        &target_rust.join("bin"),
        &target_lib,
        &native_dirs[0],
        &native_dirs[1],
        &native_dirs[2],
    ] {
        std::fs::create_dir_all(dir).map_err(|_| "asset_directory")?;
    }
    let mut copy = Copy {
        bytes: 0,
        control,
        root: target,
        files: Vec::new(),
    };
    for (relative, expected) in RUST_EXECUTABLES {
        let relative: PathBuf = relative.split('/').collect();
        let digest = copy.file(&config.sysroot.join(&relative), &target.join(&relative))?;
        if digest != expected {
            return Err("unsupported_rust_toolchain".into());
        }
    }
    let source_lib = source_rust.join("lib");
    for krate in RUST_LINK_CRATES.iter().chain(RUST_METADATA_CRATES) {
        for extension in ["rlib", "rmeta"] {
            let name = format!("lib{krate}.{extension}");
            copy.file(&source_lib.join(&name), &target_lib.join(&name))?;
        }
    }
    for (source, destination, names) in [
        (
            &config.vc_x64_lib,
            &native_dirs[0],
            &["msvcrt.lib", "vcruntime.lib", "oldnames.lib"][..],
        ),
        (&config.sdk_um_x64_lib, &native_dirs[1], WIN_IMPORT_LIBS),
        (&config.sdk_ucrt_x64_lib, &native_dirs[2], &["ucrt.lib"][..]),
    ] {
        for name in names {
            copy.file(&source.join(name), &destination.join(name))?;
        }
    }
    let libraries = RUST_LINK_CRATES
        .iter()
        .map(|krate| target_lib.join(format!("lib{krate}.rlib")))
        .chain(WIN_IMPORT_LIBS.iter().map(|name| native_dirs[1].join(name)))
        .collect();
    Ok(RustAssets {
        compiler: target.join("bin").join("rustc.exe"),
        linker: target_rust.join("bin").join("rust-lld.exe"),
        sysroot: target.to_owned(),
        libraries,
        native_dirs,
        bytes: copy.bytes,
        digest: copy.digest(),
    })
}
