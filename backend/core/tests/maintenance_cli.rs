#![cfg(windows)]
use rusqlite::Connection;
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};
use synapse_core::{Core, maintenance};
use tempfile::TempDir;

struct Fixture {
    temp: TempDir,
    state: PathBuf,
    workspace: PathBuf,
    config: PathBuf,
    archive: PathBuf,
}
impl Fixture {
    fn new() -> Self {
        let temp = tempfile::tempdir().unwrap();
        let state = temp.path().join("state");
        let workspace = temp.path().join("workspace");
        let config = temp.path().join("config");
        let archive = temp.path().join("sealed.backup");
        fs::create_dir(&workspace).unwrap();
        fs::create_dir(&config).unwrap();
        drop(Core::open(&state, &workspace).unwrap());
        fs::write(
            config.join("preferences.json"),
            b"{\"theme\":\"dark\",\"fixture\":\"CONFIG_SECRET_CANARY\"}",
        )
        .unwrap();
        fs::write(config.join("ignore.txt"), b"not selected").unwrap();
        Self {
            temp,
            state,
            workspace,
            config,
            archive,
        }
    }
    fn backup(&self) {
        maintenance::backup(&self.state, &self.archive, Some(&self.config)).unwrap();
    }
    fn target(&self, name: &str) -> PathBuf {
        self.temp.path().join(name)
    }
}

#[test]
fn dpapi_roundtrip_restores_committed_wal_and_config_without_plaintext_archive() {
    let f = Fixture::new();
    let writer = Connection::open(f.state.join("core.sqlite3")).unwrap();
    writer.execute_batch("PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0; CREATE TABLE readiness_fixture(value TEXT); INSERT INTO readiness_fixture VALUES('COMMITTED_SECRET_CANARY');").unwrap();
    writer
        .execute_batch("BEGIN; INSERT INTO readiness_fixture VALUES('UNCOMMITTED_CANARY');")
        .unwrap();
    assert!(f.state.join("core.sqlite3-wal").metadata().unwrap().len() > 0);
    f.backup();
    writer.execute_batch("ROLLBACK;").unwrap();
    drop(writer);
    let ciphertext = fs::read(&f.archive).unwrap();
    assert!(
        !ciphertext
            .windows(b"SECRET_CANARY".len())
            .any(|w| w == b"SECRET_CANARY")
    );
    let state = f.target("restored");
    let config = f.target("restored-config");
    let report = maintenance::restore(&f.archive, &state, Some(&config)).unwrap();
    assert_eq!(report["restored"], true);
    assert!(!state.join(".restore-incomplete").exists());
    assert_eq!(
        fs::read(config.join("preferences.json")).unwrap(),
        fs::read(f.config.join("preferences.json")).unwrap()
    );
    assert!(!config.join("ignore.txt").exists());
    let restored = Connection::open(state.join("core.sqlite3")).unwrap();
    let values: Vec<String> = restored
        .prepare("SELECT value FROM readiness_fixture")
        .unwrap()
        .query_map([], |row| row.get(0))
        .unwrap()
        .map(Result::unwrap)
        .collect();
    assert_eq!(values, ["COMMITTED_SECRET_CANARY"]);
    drop(restored);
    drop(Core::open(&state, &f.workspace).unwrap());
}
#[test]
fn live_core_lock_blocks_inspection_and_snapshot() {
    let f = Fixture::new();
    let core = Core::open(&f.state, &f.workspace).unwrap();
    assert_eq!(
        maintenance::inspect(&f.state).unwrap_err().code,
        "state_in_use"
    );
    assert_eq!(
        maintenance::backup(&f.state, &f.archive, None)
            .unwrap_err()
            .code,
        "state_in_use"
    );
    assert!(!f.archive.exists());
    drop(core);
    assert_eq!(maintenance::inspect(&f.state).unwrap()["integrity"], "ok");
}
#[test]
fn corrupt_archive_refused_before_any_target_and_no_overwrite() {
    let f = Fixture::new();
    f.backup();
    let original = fs::read(&f.archive).unwrap();
    assert!(maintenance::backup(&f.state, &f.archive, None).is_err());
    assert_eq!(fs::read(&f.archive).unwrap(), original);
    let corrupt = f.target("corrupt.backup");
    let mut bytes = original.clone();
    let last = bytes.len() - 1;
    bytes[last] ^= 0x40;
    fs::write(&corrupt, bytes).unwrap();
    let target = f.target("no-partial-root");
    let config = f.target("no-partial-config");
    assert!(maintenance::restore(&corrupt, &target, Some(&config)).is_err());
    assert!(!target.exists());
    assert!(!config.exists());
    let existing = f.target("existing");
    fs::create_dir(&existing).unwrap();
    fs::write(existing.join("keep"), b"operator-data").unwrap();
    assert_eq!(
        maintenance::restore(&f.archive, &existing, Some(&config))
            .unwrap_err()
            .code,
        "restore_target_exists"
    );
    assert_eq!(fs::read(existing.join("keep")).unwrap(), b"operator-data");
    let fresh = f.target("fresh");
    assert!(maintenance::restore(&f.archive, &fresh, Some(&existing)).is_err());
    assert!(!fresh.exists());
    assert!(maintenance::restore(&f.archive, &fresh, None).is_err());
    assert!(!fresh.exists());
}
#[test]
fn interrupted_restore_marker_blocks_core_and_backup_but_allows_inspection() {
    let f = Fixture::new();
    fs::write(f.state.join(".restore-incomplete"), b"interrupted fixture").unwrap();
    let error = match Core::open(&f.state, &f.workspace) {
        Ok(_) => panic!("incomplete restore accepted"),
        Err(e) => e,
    };
    assert_eq!(error.code, "state_restore_incomplete");
    assert!(maintenance::backup(&f.state, &f.archive, None).is_err());
    assert!(!f.archive.exists());
    assert_eq!(
        maintenance::inspect(&f.state).unwrap()["restore_incomplete"],
        true
    );
}
#[test]
fn archive_and_source_hardlink_aliases_are_refused() {
    let f = Fixture::new();
    f.backup();
    let alias = f.target("archive-alias");
    fs::hard_link(&f.archive, &alias).unwrap();
    assert!(maintenance::restore(&alias, &f.target("restored"), Some(&f.target("rc"))).is_err());
    fs::remove_file(&alias).unwrap();
    let db_alias = f.target("database-alias");
    fs::hard_link(f.state.join("core.sqlite3"), &db_alias).unwrap();
    assert!(maintenance::backup(&f.state, &f.target("second.backup"), None).is_err());
    assert!(!f.target("second.backup").exists());
}
#[test]
fn concurrent_restore_can_claim_fresh_target_only_once() {
    let f = Fixture::new();
    f.backup();
    let target = f.target("once");
    let config = f.target("once-config");
    let results = std::thread::scope(|scope| {
        let first = scope.spawn(|| maintenance::restore(&f.archive, &target, Some(&config)));
        let second = scope.spawn(|| maintenance::restore(&f.archive, &target, Some(&config)));
        [first.join().unwrap(), second.join().unwrap()]
    });
    assert_eq!(
        results.iter().filter(|r| r.is_ok()).count(),
        1,
        "{results:?}"
    );
    assert!(!target.join(".restore-incomplete").exists());
    assert_eq!(maintenance::inspect(&target).unwrap()["integrity"], "ok");
}
#[test]
fn native_maintenance_cli_rejects_irrelevant_duplicate_and_missing_options() {
    let f = Fixture::new();
    for args in [
        vec!["inspect", "--output", "bad"],
        vec!["backup", "--archive", "bad"],
        vec!["restore", "--output", "bad"],
        vec!["inspect", "--config-root", "bad"],
        vec!["inspect", "--state-dir", "duplicate"],
        vec!["backup", "--output"],
    ] {
        let output = Command::new(env!("CARGO_BIN_EXE_synapse-maintenance"))
            .arg(args[0])
            .arg("--state-dir")
            .arg(&f.state)
            .args(&args[1..])
            .output()
            .unwrap();
        assert!(!output.status.success());
        let json: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
        assert_eq!(json["error"]["code"], "maintenance_usage");
    }
}

fn sddl(path: &Path) -> String {
    use std::{os::windows::ffi::OsStrExt, ptr::null_mut};
    use windows_sys::Win32::{
        Foundation::LocalFree,
        Security::{
            Authorization::{
                ConvertSecurityDescriptorToStringSecurityDescriptorW, GetNamedSecurityInfoW,
                SE_FILE_OBJECT,
            },
            DACL_SECURITY_INFORMATION, OWNER_SECURITY_INFORMATION,
        },
    };
    let path: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    let mut descriptor = null_mut();
    assert_eq!(
        unsafe {
            GetNamedSecurityInfoW(
                path.as_ptr(),
                SE_FILE_OBJECT,
                OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
                null_mut(),
                null_mut(),
                null_mut(),
                null_mut(),
                &mut descriptor,
            )
        },
        0
    );
    let mut text = null_mut();
    assert_ne!(
        unsafe {
            ConvertSecurityDescriptorToStringSecurityDescriptorW(
                descriptor,
                1,
                OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
                &mut text,
                null_mut(),
            )
        },
        0
    );
    let mut len = 0;
    while unsafe { *text.add(len) } != 0 {
        len += 1;
    }
    let result = String::from_utf16(unsafe { std::slice::from_raw_parts(text, len) }).unwrap();
    unsafe {
        LocalFree(text.cast());
        LocalFree(descriptor);
    }
    result
}
#[test]
fn archive_and_restored_state_config_have_protected_owner_system_acls() {
    let f = Fixture::new();
    f.backup();
    let state = f.target("private-state");
    let config = f.target("private-config");
    maintenance::restore(&f.archive, &state, Some(&config)).unwrap();
    for path in [
        &f.archive,
        &state,
        &config,
        &state.join("core.sqlite3"),
        &config.join("preferences.json"),
    ] {
        let acl = sddl(path);
        assert!(acl.contains("D:P"), "{acl}");
        assert_eq!(acl.matches("(A;").count(), 2, "{acl}");
        assert!(acl.contains(";;;SY)"), "{acl}");
        assert!(!acl.contains(";;;WD)"));
        assert!(!acl.contains(";;;AU)"));
        assert!(!acl.contains(";;;BU)"));
    }
}
