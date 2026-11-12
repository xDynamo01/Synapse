//! Read-only Git base snapshots. Git config, hooks, filters and executables are never invoked.
use std::{
    collections::{BTreeMap, BTreeSet},
    io::ErrorKind,
    path::Path,
};

use rusqlite::{OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha1::{Digest, Sha1};

use crate::{
    contracts::{CandidateArtifact, CoreError, CoreResult, ToolOperation},
    tools,
};

fn unavailable(message: &str) -> CoreError {
    CoreError::new("workspace_unsupported", message)
}
fn conflict() -> CoreError {
    CoreError::new(
        "git_base_changed",
        "Local Git HEAD or index changed after the mission base was pinned",
    )
}

fn metadata_exists(path: &Path) -> CoreResult<bool> {
    match std::fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == ErrorKind::NotFound => Ok(false),
        Err(_) => Err(unavailable("Cannot inspect Git metadata")),
    }
}

pub(crate) fn top_level(root: &Path) -> CoreResult<bool> {
    metadata_exists(&root.join(".git"))
}

fn require_outside_git(root: &Path) -> CoreResult<()> {
    for ancestor in root.ancestors() {
        if top_level(ancestor)? {
            return Err(unavailable(
                "Publication must use a top-level local Git workspace or a non-Git workspace",
            ));
        }
    }
    Ok(())
}

struct Metadata {
    _broker: tools::Broker,
    read: tools::OwnedRead,
}
fn read(root: &Path, state: &Path, path: &str, cap: u64) -> CoreResult<Metadata> {
    let broker = tools::prepare(root, state, &ToolOperation::Read { path: path.into() })
        .map_err(|_| unavailable("Git metadata path is inaccessible or unsupported"))?;
    let read = broker
        .read_binary_guarded(cap)
        .map_err(|_| unavailable("Git metadata is busy, unverified or too large"))?;
    Ok(Metadata {
        _broker: broker,
        read,
    })
}
fn text(bytes: &[u8]) -> CoreResult<&str> {
    std::str::from_utf8(bytes).map_err(|_| unavailable("Invalid Git reference encoding"))
}
fn oid(value: &str) -> CoreResult<&str> {
    if value.len() == 40 && value.bytes().all(|b| b.is_ascii_hexdigit()) {
        Ok(value)
    } else {
        Err(unavailable("A committed SHA-1 Git repository is required"))
    }
}
fn ref_name(reference: &str) -> bool {
    reference.starts_with("refs/")
        && reference.split('/').all(|part| {
            !part.is_empty()
                && !part.starts_with('.')
                && !part.ends_with('.')
                && !part.ends_with(".lock")
                && !part.contains("..")
                && part
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b))
        })
}

pub(crate) struct Base {
    pub head: String,
    pub index_digest: String,
    index: BTreeMap<String, IndexEntry>,
    _pins: Vec<Metadata>,
}

struct IndexEntry {
    path: String,
    mode: u32,
    extended: u16,
    object_id: [u8; 20],
}

fn take<'a>(data: &'a [u8], pos: &mut usize, len: usize) -> Option<&'a [u8]> {
    let end = pos.checked_add(len)?;
    let slice = data.get(*pos..end)?;
    *pos = end;
    Some(slice)
}
fn u32_at(data: &[u8]) -> u32 {
    u32::from_be_bytes(data.try_into().unwrap())
}
fn u16_at(data: &[u8]) -> u16 {
    u16::from_be_bytes(data.try_into().unwrap())
}

fn parse_index(bytes: &[u8]) -> Option<BTreeMap<String, IndexEntry>> {
    let data = bytes.get(..bytes.len().checked_sub(20)?)?;
    if data.get(..4)? != b"DIRC" || Sha1::digest(data)[..] != bytes[data.len()..] {
        return None;
    }
    let version = u32_at(data.get(4..8)?);
    if !matches!(version, 2 | 3) {
        return None;
    }
    let count = u32_at(data.get(8..12)?) as usize;
    if count > 100_000 {
        return None;
    }
    let mut index = BTreeMap::new();
    let mut pos = 12;
    for _ in 0..count {
        let start = pos;
        let entry = take(data, &mut pos, 62)?;
        let mode = u32_at(&entry[24..28]);
        let flags = u16_at(&entry[60..62]);
        if flags & 0x3000 != 0 {
            return None;
        }
        let extended = if flags & 0x4000 != 0 {
            if version < 3 {
                return None;
            }
            u16_at(take(data, &mut pos, 2)?)
        } else {
            0
        };
        let name_len = data.get(pos..)?.iter().position(|byte| *byte == 0)?;
        if name_len == 0 || name_len.min(0xfff) != usize::from(flags & 0xfff) {
            return None;
        }
        let path = std::str::from_utf8(take(data, &mut pos, name_len)?)
            .ok()?
            .to_owned();
        let padding = 8 - (pos - start) % 8;
        if take(data, &mut pos, padding)?.iter().any(|byte| *byte != 0) {
            return None;
        }
        if index
            .insert(
                path.to_ascii_lowercase(),
                IndexEntry {
                    path,
                    mode,
                    extended,
                    object_id: entry[40..60].try_into().ok()?,
                },
            )
            .is_some()
        {
            return None;
        }
    }
    while pos < data.len() {
        let name = take(data, &mut pos, 4)?;
        // Lowercase mandatory extensions include split and sparse indexes.
        if !name[0].is_ascii_uppercase() {
            return None;
        }
        let size = u32_at(take(data, &mut pos, 4)?) as usize;
        take(data, &mut pos, size)?;
    }
    Some(index)
}

pub(crate) fn observe(root: &Path, state: &Path) -> CoreResult<Base> {
    let head = read(root, state, ".git/HEAD", 1024)?;
    for name in [
        "commondir",
        "index.lock",
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "rebase-apply",
        "rebase-merge",
    ] {
        if metadata_exists(&root.join(".git").join(name))? {
            return Err(unavailable(
                "Git workspace has linked metadata, an active lock or an unfinished operation",
            ));
        }
    }
    let head_value = text(&head.read.bytes)?.trim();
    let (head_value, head_ref) = if let Some(reference) = head_value.strip_prefix("ref: ") {
        if !ref_name(reference) {
            return Err(unavailable("Invalid or unsupported Git reference"));
        }
        let reference_path = format!(".git/{reference}");
        // A packed-only ref can be shadowed by a loose ref while the packed
        // file is open. Require a ref file whose identity can be held.
        let metadata = read(root, state, &reference_path, 1024)?;
        let commit = oid(text(&metadata.read.bytes)?.trim())?;
        (format!("{reference}@{commit}"), Some(metadata))
    } else {
        (oid(head_value)?.into(), None)
    };
    let index = read(root, state, ".git/index", 8 * 1024 * 1024)?;
    let index_digest = tools::sha(&index.read.bytes);
    let parsed = parse_index(&index.read.bytes).ok_or_else(|| {
        unavailable("Git index must be an ordinary conflict-free SHA-1 v2 or v3 index")
    })?;
    let mut pins = vec![head, index];
    pins.extend(head_ref);
    Ok(Base {
        head: head_value,
        index_digest,
        index: parsed,
        _pins: pins,
    })
}

impl Base {
    pub(crate) fn verify_targets(
        &self,
        contract: &crate::contracts::MissionContract,
    ) -> CoreResult<()> {
        for path in &contract.resources {
            let entry = self.index.get(&path.to_ascii_lowercase());
            if contract.artifact_previous_digests.contains_key(path) {
                if entry.is_none_or(|entry| {
                    entry.path != *path
                        || !matches!(entry.mode, 0o100644 | 0o100755)
                        || entry.extended != 0
                }) {
                    return Err(CoreError::new(
                        "git_target_conflict",
                        "An approved edit target is not a regular tracked file",
                    ));
                }
            } else if entry.is_some() {
                return Err(CoreError::new(
                    "git_target_conflict",
                    "A create target already exists in the Git index",
                ));
            }
        }
        Ok(())
    }
}

#[derive(Serialize, Deserialize)]
pub(crate) struct PreviousArtifact {
    pub path: String,
    pub identity: String,
    pub content: String,
}

pub(crate) fn record_edit_plan(
    tx: &Transaction<'_>,
    mission: &str,
    workspace: &Path,
    state: &Path,
    paths: &[String],
) -> CoreResult<()> {
    if !(1..=16).contains(&paths.len()) {
        return Err(CoreError::invalid(
            "Git edit requires one to sixteen exact tracked paths",
        ));
    }
    let base = observe(workspace, state)?;
    let root_broker = tools::prepare(workspace, state, &ToolOperation::List { path: ".".into() })?;
    let mut seen = BTreeSet::new();
    let mut originals = Vec::new();
    let mut size = 0usize;
    for path in paths {
        if path.contains(['/', '\\'])
            || path.starts_with('.')
            || !seen.insert(path.to_ascii_lowercase())
        {
            return Err(CoreError::invalid(
                "Git edit paths must be unique flat filenames",
            ));
        }
        let entry = base
            .index
            .get(&path.to_ascii_lowercase())
            .filter(|entry| {
                entry.path == *path
                    && matches!(entry.mode, 0o100644 | 0o100755)
                    && entry.extended == 0
            })
            .ok_or_else(|| {
                CoreError::new(
                    "git_target_conflict",
                    "Git edit paths must be regular tracked files",
                )
            })?;
        let broker = tools::prepare(
            workspace,
            state,
            &ToolOperation::Read { path: path.clone() },
        )?;
        let source = broker.read_owned_guarded()?;
        size += source.bytes.len();
        if source.bytes.len() > 8192 || size > 16384 {
            return Err(CoreError::invalid(
                "Git edit base text exceeds the supported size",
            ));
        }
        let mut blob = Sha1::new();
        blob.update(format!("blob {}\0", source.bytes.len()).as_bytes());
        blob.update(&source.bytes);
        if blob.finalize()[..] != entry.object_id {
            return Err(CoreError::new(
                "git_target_conflict",
                "Git edit target differs from its indexed bytes",
            ));
        }
        originals.push(PreviousArtifact {
            path: path.clone(),
            identity: source.identity,
            content: String::from_utf8(source.bytes)
                .map_err(|_| CoreError::invalid("Git edit base must be UTF-8"))?,
        });
    }
    tx.execute("INSERT INTO mission_git_edit_plans(mission_id,root,root_identity,head,index_digest,artifacts) VALUES(?1,?2,?3,?4,?5,?6)", params![mission,root_broker.target(),root_broker.root_identity()?,base.head,base.index_digest,serde_json::to_string(&originals)?])?;
    Ok(())
}

pub(crate) fn originals(tx: &Transaction<'_>, mission: &str) -> CoreResult<Vec<PreviousArtifact>> {
    let row: Option<String> = tx
        .query_row(
            "SELECT artifacts FROM mission_git_edit_plans WHERE mission_id=?1",
            [mission],
            |row| row.get(0),
        )
        .optional()?;
    row.map(|data| serde_json::from_str(&data).map_err(Into::into))
        .transpose()
        .map(Option::unwrap_or_default)
}

pub(crate) fn original_for(
    tx: &Transaction<'_>,
    mission: &str,
    contract: &crate::contracts::MissionContract,
    path: &str,
) -> CoreResult<Option<PreviousArtifact>> {
    let Some(expected) = contract.artifact_previous_digests.get(path) else {
        return Ok(None);
    };
    let artifact = originals(tx, mission)?
        .into_iter()
        .find(|item| item.path == path)
        .filter(|item| tools::sha(item.content.as_bytes()) == *expected)
        .ok_or_else(|| {
            CoreError::new(
                "git_target_conflict",
                "Sealed replacement base text is missing or changed",
            )
        })?;
    Ok(Some(artifact))
}

fn verified_plan_base(
    tx: &Transaction<'_>,
    mission: &str,
    root: &Path,
    state: &Path,
) -> CoreResult<Option<Base>> {
    let planned: Option<(String,String,String,String)> = tx.query_row("SELECT root,root_identity,head,index_digest FROM mission_git_edit_plans WHERE mission_id=?1", [mission], |row| Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?))).optional()?;
    let Some((planned_root, identity, head, index)) = planned else {
        return Ok(None);
    };
    let base = observe(root, state).map_err(|_| conflict())?;
    let broker = tools::prepare(root, state, &ToolOperation::List { path: ".".into() })?;
    if broker.target() != planned_root
        || broker.root_identity()? != identity
        || base.head != head
        || base.index_digest != index
    {
        return Err(conflict());
    }
    for prior in originals(tx, mission)? {
        let broker = tools::prepare(root, state, &ToolOperation::Read { path: prior.path })?;
        let observed = broker.read_owned_guarded()?;
        if observed.identity != prior.identity || observed.bytes != prior.content.as_bytes() {
            return Err(conflict());
        }
    }
    Ok(Some(base))
}

pub(crate) fn verify_edit_plan(
    tx: &Transaction<'_>,
    mission: &str,
    root: &Path,
    state: &Path,
) -> CoreResult<()> {
    verified_plan_base(tx, mission, root, state)?;
    Ok(())
}

pub(crate) fn bind(
    tx: &Transaction<'_>,
    mission: &str,
    root: &Path,
    state: &Path,
    contract: &crate::contracts::MissionContract,
) -> CoreResult<()> {
    let base = match verified_plan_base(tx, mission, root, state)? {
        Some(base) => base,
        None if top_level(root)? => observe(root, state)?,
        None => return Ok(()),
    };
    base.verify_targets(contract)?;
    tx.execute(
        "INSERT INTO mission_git_bases(mission_id,head,index_digest) VALUES(?1,?2,?3)",
        params![mission, base.head, base.index_digest],
    )?;
    Ok(())
}

pub(crate) fn guard(
    tx: &Transaction<'_>,
    mission: &str,
    root: &Path,
    state: &Path,
) -> CoreResult<Option<Base>> {
    let expected: Option<(String, String)> = tx
        .query_row(
            "SELECT head,index_digest FROM mission_git_bases WHERE mission_id=?1",
            [mission],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    if let Some((head, index)) = expected {
        let base = observe(root, state).map_err(|_| conflict())?;
        if base.head != head || base.index_digest != index {
            return Err(conflict());
        }
        Ok(Some(base))
    } else {
        require_outside_git(root)?;
        Ok(None)
    }
}

pub(crate) fn receipt(tx: &Transaction<'_>, mission: &str) -> CoreResult<Option<Value>> {
    let row: Option<(String, String)> = tx
        .query_row(
            "SELECT head,index_digest FROM mission_git_bases WHERE mission_id=?1",
            [mission],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    Ok(row.map(|(head, index)| json!({"head":head,"index_digest":index})))
}

pub(crate) fn diff(
    tx: &Transaction<'_>,
    mission: &str,
    artifacts: &[CandidateArtifact],
) -> CoreResult<Value> {
    let originals = originals(tx, mission)?;
    let result: Vec<_> = artifacts.iter().map(|candidate| {
        let before = originals.iter().find(|item| item.path == candidate.path).map(|item| item.content.as_str());
        json!({"path":candidate.path,"before":before,"after":candidate.content,"before_sha256":before.map(|text| tools::sha(text.as_bytes())),"after_sha256":tools::sha(candidate.content.as_bytes())})
    }).collect();
    Ok(json!(result))
}
