//! Offline owner-scoped snapshots. Never overwrite an existing restore target.
use crate::{
    contracts::{CoreError, CoreResult},
    privacy, store,
};
use base64::{Engine, engine::general_purpose::STANDARD};
use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    time::Duration,
};
const MAGIC: &[u8] = b"SYNAPSE-OWNER-BACKUP-1\n";
const MAX: u64 = 256 * 1024 * 1024;
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Entry {
    name: String,
    content: String,
    sha256: String,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Bundle {
    version: u32,
    schema: u32,
    principal: String,
    entries: Vec<Entry>,
}
fn err(code: &str) -> CoreError {
    CoreError::new(
        code,
        "Offline maintenance refused an unsafe, inconsistent or unsupported operation",
    )
}
fn related(left: &Path, right: &Path) -> bool {
    #[cfg(windows)]
    {
        let key = |p: &Path| {
            p.to_string_lossy()
                .replace('\\', "/")
                .trim_start_matches("//?/")
                .trim_end_matches('/')
                .to_lowercase()
        };
        let l = key(left);
        let r = key(right);
        l == r || l.starts_with(&format!("{r}/")) || r.starts_with(&format!("{l}/"))
    }
    #[cfg(not(windows))]
    {
        left.starts_with(right) || right.starts_with(left)
    }
}
fn lock(state: &Path) -> CoreResult<privacy::GuardedFile> {
    let file = privacy::lock_file(&state.join(".synapse-core.lock"))
        .map_err(|_| err("state_lock_unavailable"))?;
    file.try_lock().map_err(|_| err("state_in_use"))?;
    Ok(file)
}
fn open(state: &Path) -> CoreResult<(Connection, Vec<privacy::GuardedFile>)> {
    let db = privacy::absolute(&state.join("core.sqlite3"))?;
    let mut guards = vec![privacy::regular_file(&db)?];
    for suffix in ["core.sqlite3-wal", "core.sqlite3-shm"] {
        let side = state.join(suffix);
        if side.exists() {
            guards.push(privacy::regular_file(&side)?);
        }
    }
    let conn = Connection::open_with_flags(db, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|_| err("backup_integrity"))?;
    conn.busy_timeout(Duration::from_secs(3))?;
    let integrity: String = conn.query_row("PRAGMA quick_check", [], |row| row.get(0))?;
    if integrity != "ok" {
        return Err(err("backup_integrity"));
    }
    Ok((conn, guards))
}
fn schema(conn: &Connection) -> CoreResult<u32> {
    Ok(conn.pragma_query_value(None, "user_version", |row| row.get(0))?)
}
fn supported(version: u32) -> CoreResult<()> {
    if version == 0 || version > store::SCHEMA_VERSION {
        Err(err("unsupported_storage_version"))
    } else {
        Ok(())
    }
}
fn entry(name: String, bytes: Vec<u8>) -> Entry {
    Entry {
        name,
        sha256: crate::tools::sha(&bytes),
        content: STANDARD.encode(bytes),
    }
}
fn regular(path: &Path, limit: u64) -> CoreResult<Vec<u8>> {
    let mut file = privacy::regular_file(path)?;
    let m = file
        .metadata()
        .map_err(|_| err("backup_file_unavailable"))?;
    if !m.is_file() || m.len() > limit {
        return Err(err("backup_size_limit"));
    }
    let mut bytes = Vec::new();
    (&mut file.file)
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| err("backup_file_unavailable"))?;
    if bytes.len() as u64 > limit {
        return Err(err("backup_size_limit"));
    }
    Ok(bytes)
}
fn valid_name(name: &str) -> bool {
    if name == "state/core.sqlite3" {
        return true;
    }
    if let Some(part) = name.strip_prefix("config/") {
        let stem = part.split('.').next().unwrap_or("").to_ascii_lowercase();
        if [
            "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", "com6", "com7",
            "com8", "com9", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
        ]
        .contains(&stem.as_str())
        {
            return false;
        }
        return part.ends_with(".json")
            && part.len() < 100
            && !part.starts_with('.')
            && part
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b));
    }
    if let Some(part) = name.strip_prefix("state/model-ownership/") {
        let hash = part
            .strip_suffix(".json")
            .unwrap_or("")
            .strip_prefix("released-")
            .unwrap_or(part.strip_suffix(".json").unwrap_or(""));
        return hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit());
    }
    false
}
/// No content, credentials or absolute workspace path enters diagnostics.
pub fn inspect(state: &Path) -> CoreResult<Value> {
    let state = privacy::absolute(state)?;
    if !state.is_dir() {
        return Err(err("state_missing"));
    }
    let _state_guard = privacy::pin_directory(&state)?;
    let _lock = lock(&state)?;
    let (c, _db_guards) = open(&state)?;
    let v = schema(&c)?;
    Ok(
        json!({"version":1,"schema":v,"supported":v>0&&v<=store::SCHEMA_VERSION,"integrity":"ok","owner_boundary":"local_os_principal","principal_digest":store::digest(&privacy::principal()?)?,"restore_incomplete":state.join(".restore-incomplete").exists()}),
    )
}
pub fn backup(state: &Path, output: &Path, config: Option<&Path>) -> CoreResult<Value> {
    let state = privacy::absolute(state)?;
    if !state.is_dir() || state.join(".restore-incomplete").exists() {
        return Err(err("state_missing_or_incomplete"));
    }
    let _state_guard = privacy::pin_directory(&state)?;
    let _lock = lock(&state)?;
    privacy::directory(&state)?;
    let (source, _db_guards) = open(&state)?;
    let version = schema(&source)?;
    supported(version)?;
    let stage = tempfile::Builder::new()
        .prefix(".backup-stage-")
        .tempdir_in(&state)
        .map_err(|_| err("backup_stage_unavailable"))?;
    let snapshot = stage.path().join("snapshot.sqlite3");
    // SQLite creates a consistent logical snapshot, including committed WAL pages.
    source.execute("VACUUM main INTO ?1", [snapshot.to_string_lossy().as_ref()])?;
    let mut entries = vec![entry(
        "state/core.sqlite3".into(),
        regular(&snapshot, MAX / 2)?,
    )];
    let leases = state.join("model-ownership");
    if leases.exists() {
        for item in
            fs::read_dir(privacy::absolute(&leases)?).map_err(|_| err("backup_file_unavailable"))?
        {
            let item = item.map_err(|_| err("backup_file_unavailable"))?;
            let name = format!(
                "state/model-ownership/{}",
                item.file_name().to_string_lossy()
            );
            if valid_name(&name) {
                entries.push(entry(name, regular(&item.path(), 4096)?));
            }
        }
    }
    if let Some(config) = config {
        let config = privacy::absolute(config)?;
        for item in fs::read_dir(config).map_err(|_| err("backup_config_unavailable"))? {
            let item = item.map_err(|_| err("backup_config_unavailable"))?;
            let name = format!("config/{}", item.file_name().to_string_lossy());
            if valid_name(&name) {
                entries.push(entry(name, regular(&item.path(), 256 * 1024)?));
            }
        }
    }
    if entries.len() > 1024 {
        return Err(err("backup_size_limit"));
    }
    entries.sort_by(|a, b| a.name.cmp(&b.name));
    let bundle = Bundle {
        version: 1,
        schema: version,
        principal: privacy::principal()?,
        entries,
    };
    let payload = serde_json::to_vec(&bundle)?;
    if payload.len() as u64 > MAX {
        return Err(err("backup_size_limit"));
    }
    let encrypted = privacy::seal(&payload)?;
    if encrypted.len() as u64 + MAGIC.len() as u64 > MAX {
        return Err(err("backup_size_limit"));
    }
    let output = privacy::absolute(output)?;
    let mut file =
        privacy::new_file(&output).map_err(|_| err("backup_output_exists_or_unavailable"))?;
    file.write_all(MAGIC)
        .and_then(|_| file.write_all(&encrypted))
        .and_then(|_| file.sync_all())
        .map_err(|_| err("backup_write_failed"))?;
    Ok(
        json!({"version":1,"schema":version,"entries":bundle.entries.len(),"protection":"windows_dpapi_current_user","sha256":crate::tools::sha(&regular(&output,MAX)?),"consistent_snapshot":true}),
    )
}
pub fn restore(archive: &Path, state: &Path, config: Option<&Path>) -> CoreResult<Value> {
    let bytes = regular(archive, MAX)?;
    if !bytes.starts_with(MAGIC) {
        return Err(err("backup_format"));
    }
    let plain = privacy::unseal(&bytes[MAGIC.len()..])?;
    let bundle: Bundle = serde_json::from_slice(&plain).map_err(|_| err("backup_format"))?;
    supported(bundle.schema)?;
    if bundle.version != 1
        || bundle.principal != privacy::principal()?
        || bundle.entries.len() > 1024
    {
        return Err(err("backup_principal_or_version"));
    }
    let state = privacy::absolute(state)?;
    if state.exists() {
        return Err(err("restore_target_exists"));
    }
    let config = config.map(privacy::absolute).transpose()?;
    if config
        .as_ref()
        .is_some_and(|p| p.exists() || related(p, &state))
    {
        return Err(err("restore_target_exists"));
    }
    let mut files = Vec::new();
    let mut seen = std::collections::BTreeSet::new();
    for item in bundle.entries {
        if !valid_name(&item.name) || !seen.insert(item.name.to_ascii_lowercase()) {
            return Err(err("backup_entry_invalid"));
        }
        if item.name.starts_with("config/") && config.is_none() {
            return Err(err("restore_config_target_required"));
        }
        let bytes = STANDARD
            .decode(item.content)
            .map_err(|_| err("backup_integrity"))?;
        let limit = if item.name == "state/core.sqlite3" {
            MAX / 2
        } else if item.name.starts_with("config/") {
            256 * 1024
        } else {
            4096
        };
        if bytes.len() as u64 > limit {
            return Err(err("backup_size_limit"));
        }
        if crate::tools::sha(&bytes) != item.sha256 {
            return Err(err("backup_integrity"));
        }
        files.push((item.name, bytes));
    }
    if !seen.contains("state/core.sqlite3") {
        return Err(err("backup_integrity"));
    }
    // Verify the decrypted logical database before making either destination
    // visible. Invalid archives cannot leave a seemingly usable restore root.
    {
        let stage = tempfile::Builder::new()
            .prefix(".synapse-restore-validation-")
            .tempdir_in(
                state
                    .parent()
                    .ok_or_else(|| err("restore_target_invalid"))?,
            )
            .map_err(|_| err("restore_stage_unavailable"))?;
        privacy::directory(stage.path())?;
        let _guard = privacy::pin_directory(stage.path())?;
        let db_bytes = &files
            .iter()
            .find(|(name, _)| name == "state/core.sqlite3")
            .ok_or_else(|| err("backup_integrity"))?
            .1;
        {
            let mut file = privacy::new_file(&stage.path().join("core.sqlite3"))?;
            file.write_all(db_bytes)
                .and_then(|_| file.sync_all())
                .map_err(|_| err("restore_write_failed"))?;
        }
        let (db, _db_guards) = open(stage.path())?;
        if schema(&db)? != bundle.schema {
            return Err(err("backup_schema_mismatch"));
        }
    }
    let (state, _state_guard) = privacy::fresh_directory(&state)?;
    let _lock = lock(&state)?;
    let marker = state.join(".restore-incomplete");
    {
        let mut marker_file = privacy::new_file(&marker)?;
        marker_file
            .write_all(b"restore-v1")
            .and_then(|_| marker_file.sync_all())
            .map_err(|_| err("restore_write_failed"))?;
    }
    let _config_guard = if let Some(config) = &config {
        Some(privacy::fresh_directory(config)?.1)
    } else {
        None
    };
    for (name, bytes) in files {
        let path = if let Some(relative) = name.strip_prefix("state/") {
            state.join(relative)
        } else {
            config
                .as_ref()
                .unwrap()
                .join(name.strip_prefix("config/").unwrap())
        };
        if let Some(parent) = path.parent() {
            privacy::directory(parent)?;
        }
        let mut file = privacy::new_file(&path).map_err(|_| err("restore_write_failed"))?;
        file.write_all(&bytes)
            .and_then(|_| file.sync_all())
            .map_err(|_| err("restore_write_failed"))?;
    }
    let (restored, _restored_guards) = open(&state)?;
    if schema(&restored)? != bundle.schema {
        return Err(err("backup_schema_mismatch"));
    }
    drop(restored);
    fs::remove_file(&marker).map_err(|_| err("restore_commit_failed"))?;
    Ok(
        json!({"version":1,"schema":bundle.schema,"restored":true,"configuration_restored":config.is_some(),"state_target_fresh":true,"workspace_files_included":false,"owner_key_required":true}),
    )
}
pub fn run(args: impl Iterator<Item = String>) -> CoreResult<Value> {
    let mut args = args;
    let action = args.next().ok_or_else(|| err("maintenance_usage"))?;
    let mut values = std::collections::BTreeMap::new();
    while let Some(key) = args.next() {
        if !["--state-dir", "--archive", "--output", "--config-root"].contains(&key.as_str())
            || values.contains_key(&key)
        {
            return Err(err("maintenance_usage"));
        }
        values.insert(key, args.next().ok_or_else(|| err("maintenance_usage"))?);
    }
    let state = PathBuf::from(
        values
            .get("--state-dir")
            .ok_or_else(|| err("maintenance_usage"))?,
    );
    let config = values.get("--config-root").map(PathBuf::from);
    let allowed: &[&str] = match action.as_str() {
        "inspect" => &["--state-dir"],
        "backup" => &["--state-dir", "--output", "--config-root"],
        "restore" => &["--state-dir", "--archive", "--config-root"],
        _ => return Err(err("maintenance_usage")),
    };
    if values.keys().any(|key| !allowed.contains(&key.as_str())) {
        return Err(err("maintenance_usage"));
    }
    match action.as_str() {
        "inspect" => inspect(&state),
        "backup" => backup(
            &state,
            Path::new(
                values
                    .get("--output")
                    .ok_or_else(|| err("maintenance_usage"))?,
            ),
            config.as_deref(),
        ),
        "restore" => restore(
            Path::new(
                values
                    .get("--archive")
                    .ok_or_else(|| err("maintenance_usage"))?,
            ),
            &state,
            config.as_deref(),
        ),
        _ => Err(err("maintenance_usage")),
    }
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    fn archive(root: &Path, plain: &[u8]) -> PathBuf {
        let path = root.join("test.backup");
        let mut file = privacy::new_file(&path).unwrap();
        file.write_all(MAGIC).unwrap();
        file.write_all(&privacy::seal(plain).unwrap()).unwrap();
        drop(file);
        path
    }
    #[test]
    fn owner_sealed_malformed_metadata_never_leaks_or_creates_destination() {
        let temp = tempfile::tempdir().unwrap();
        let path = archive(temp.path(), b"{\"SECRET_CANARY_MALFORMED_FIELD\":true}");
        let target = temp.path().join("state");
        let error = restore(&path, &target, None).unwrap_err();
        assert_eq!(error.code, "backup_format");
        assert!(!error.to_string().contains("CANARY"));
        assert!(!target.exists());
    }
    #[test]
    fn sealed_wrong_principal_invalid_database_and_traversal_are_refused_before_creation() {
        for kind in ["principal", "database", "traversal", "case_alias"] {
            let temp = tempfile::tempdir().unwrap();
            let mut bundle = Bundle {
                version: 1,
                schema: store::SCHEMA_VERSION,
                principal: privacy::principal().unwrap(),
                entries: vec![entry(
                    "state/core.sqlite3".into(),
                    b"invalid SQLite fixture".to_vec(),
                )],
            };
            match kind {
                "principal" => bundle.principal = "other-OS-user".into(),
                "traversal" => bundle
                    .entries
                    .push(entry("config/../outside.json".into(), b"secret".to_vec())),
                "case_alias" => {
                    bundle
                        .entries
                        .push(entry("config/A.json".into(), b"one".to_vec()));
                    bundle
                        .entries
                        .push(entry("config/a.json".into(), b"two".to_vec()));
                }
                _ => (),
            }
            let path = archive(temp.path(), &serde_json::to_vec(&bundle).unwrap());
            let target = temp.path().join("restored");
            let config = temp.path().join("config");
            assert!(restore(&path, &target, Some(&config)).is_err(), "{kind}");
            assert!(!target.exists(), "{kind}");
            assert!(!config.exists(), "{kind}");
        }
    }
    #[test]
    fn protected_path_checks_reject_nul_ads_and_case_insensitive_config_overlap() {
        assert!(privacy::absolute(Path::new("C:\\fixture\\name\0hidden")).is_err());
        assert!(privacy::absolute(Path::new("C:\\fixture\\name:stream")).is_err());
        assert!(related(
            Path::new("C:\\FIXTURE\\State"),
            Path::new("c:\\fixture\\state\\config")
        ));
    }
}
