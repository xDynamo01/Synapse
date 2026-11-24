//! Local single-owner self-change gate. Human authority is obtained at the native
//! desktop, never from a model, actor label, mission grant or request boolean.
//! A prepared journal MUST commit in an earlier request than publication.
use crate::{CoreError, CoreResult, contracts::ToolOperation, store, tools};
use rusqlite::{OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;

pub(crate) const SCHEMA: &str = "
CREATE TABLE IF NOT EXISTS self_changes(
 id TEXT PRIMARY KEY, principal TEXT NOT NULL, context TEXT NOT NULL,
 proposal TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL,
 root_identity TEXT NOT NULL, file_identity TEXT NOT NULL,
 reviewer TEXT, review_digest TEXT, review_evidence TEXT, approver TEXT, executor TEXT);
CREATE TABLE IF NOT EXISTS self_change_journal(
 change_id TEXT PRIMARY KEY REFERENCES self_changes(id), root_identity TEXT NOT NULL,
 file_identity TEXT NOT NULL, before_bytes BLOB NOT NULL, after_bytes BLOB NOT NULL,
 phase TEXT NOT NULL);
";

pub(crate) fn acknowledge(tx: &Transaction<'_>) -> CoreResult<()> {
    tx.execute_batch(SCHEMA)?;
    Ok(())
}

fn denied() -> CoreError {
    CoreError::new(
        "self_change_denied",
        "Dedicated self-change authority or exact state is required",
    )
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Context {
    conversation: String,
    project: String,
    mission: String,
    swarm: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Proposal {
    id: String,
    context: Context,
    proposer_agent: String,
    root: String,
    path: String,
    base_version: String,
    base_digest: String,
    content: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Reference {
    id: String,
    context: Context,
    change_digest: String,
    #[serde(default)]
    review: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct Record {
    proposal: Proposal,
    digest: String,
    state: String,
    reviewer: Option<String>,
    review_digest: Option<String>,
    approver: Option<String>,
    executor: Option<String>,
    root_identity: String,
    file_identity: String,
}

#[cfg(windows)]
fn principal() -> CoreResult<String> {
    crate::runner::owner_sid().map_err(|_| denied())
}
#[cfg(not(windows))]
fn principal() -> CoreResult<String> {
    Err(CoreError::new(
        "capability_unavailable",
        "Local authenticated Windows desktop required",
    ))
}

fn normalized(path: &Path) -> CoreResult<String> {
    let path = path.canonicalize().map_err(|_| denied())?;
    Ok(path_key(&path))
}
fn path_key(path: &Path) -> String {
    path.to_string_lossy()
        .trim_start_matches(r"\\?\")
        .trim_end_matches(['\\', '/'])
        .replace('\\', "/")
        .to_lowercase()
}
fn overlaps(a: &str, b: &str) -> bool {
    a == b || a.starts_with(&format!("{b}/")) || b.starts_with(&format!("{a}/"))
}

/// Deny generic project registration/execution over source and installed binaries,
/// including ancestor roots. No user-controlled exemption or mission can bypass it.
pub(crate) fn guard_project_root(root: &Path) -> CoreResult<()> {
    let source = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .ok_or_else(denied)?;
    let exe = std::env::current_exe().map_err(|_| denied())?;
    let distribution = exe.parent().ok_or_else(denied)?;
    let mut protected=vec![source.to_path_buf(),distribution.to_path_buf()];
    #[cfg(windows)]
    if let Some(config)=std::env::var_os("SYNAPSE_CONFIG_ROOT")
        .map(std::path::PathBuf::from)
        .or_else(||std::env::var_os("LOCALAPPDATA").map(|base|std::path::PathBuf::from(base).join("Synapse"))) {
        if !config.is_absolute() {return Err(denied());}
        // Configuration files can select local executables. Protect their
        // authority without denying a separate workspace below the same base.
        protected.push(config.join("native-toolchain.json"));
        protected.push(config.join("voice-runtime.json"));
    }
    guard_roots(root, &protected.iter().map(|path|path.as_path()).collect::<Vec<_>>())
}
pub(crate) fn guard_effect(root: &Path) -> CoreResult<()> {
    guard_project_root(root)
}
fn guard_roots(root: &Path, protected: &[&Path]) -> CoreResult<()> {
    let actual = normalized(root)?;
    for item in protected {
        // An installed package can run without the compiler's source checkout.
        // Keep its absolute source protection lexical when it is not present.
        let protected = item.canonicalize().unwrap_or_else(|_| item.to_path_buf());
        if !protected.is_absolute() || overlaps(&actual, &path_key(&protected)) {
            return Err(denied());
        }
    }
    Ok(())
}

fn load(tx: &Transaction<'_>, reference: &Reference) -> CoreResult<Record> {
    let row: Option<(String,String,String,String,Option<String>,Option<String>,Option<String>,Option<String>)> = tx.query_row(
        "SELECT principal,context,proposal,digest,reviewer,review_digest,approver,executor FROM self_changes WHERE id=?1",
        [&reference.id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?,r.get(6)?,r.get(7)?))).optional()?;
    let (owner, context, proposal, digest, reviewer, review_digest, approver, executor) =
        row.ok_or_else(denied)?;
    if owner != principal()?
        || context != serde_json::to_string(&reference.context)?
        || digest != reference.change_digest
    {
        return Err(denied());
    }
    if let (Some(reviewer), Some(review_digest)) = (&reviewer, &review_digest) {
        let evidence: Option<String> = tx.query_row(
            "SELECT review_evidence FROM self_changes WHERE id=?1",
            [&reference.id],
            |row| row.get(0),
        )?;
        let evidence = evidence.ok_or_else(denied)?;
        if store::digest(&(digest.as_str(), reviewer.as_str(), evidence.as_str()))?
            != *review_digest
        {
            return Err(denied());
        }
    }
    let state = tx.query_row(
        "SELECT state FROM self_changes WHERE id=?1",
        [&reference.id],
        |r| r.get(0),
    )?;
    let (root_identity, file_identity) = tx.query_row(
        "SELECT root_identity,file_identity FROM self_changes WHERE id=?1",
        [&reference.id],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    let proposal: Proposal = serde_json::from_str(&proposal)?;
    if store::digest(&proposal)? != digest {
        return Err(denied());
    }
    Ok(Record {
        proposal,
        digest,
        state,
        reviewer,
        review_digest,
        approver,
        executor,
        root_identity,
        file_identity,
    })
}

fn broker(p: &Proposal, state: &Path) -> CoreResult<tools::Broker> {
    tools::prepare(
        Path::new(&p.root),
        state,
        &ToolOperation::Replace {
            path: p.path.clone(),
            content: p.content.clone(),
        },
    )
}
fn event(tx: &Transaction<'_>, id: &str, phase: &str, digest: &str) -> CoreResult<()> {
    // No contents, diff, review text, paths or external diagnostic strings.
    store::event(
        tx,
        "self_change",
        json!({"id":id,"phase":phase,"digest":digest}),
    )?;
    Ok(())
}

pub(crate) fn dispatch(
    tx: &Transaction<'_>,
    action: &str,
    payload: &Value,
    state: &Path,
) -> CoreResult<Value> {
    dispatch_with_consent(tx, action, payload, state, human_confirmation)
}

fn dispatch_with_consent(
    tx: &Transaction<'_>,
    action: &str,
    payload: &Value,
    state: &Path,
    consent: fn(&str, &str) -> CoreResult<()>,
) -> CoreResult<Value> {
    if action == "propose" {
        let p: Proposal = serde_json::from_value(payload.clone()).map_err(|_| denied())?;
        for value in [
            &p.id,
            &p.proposer_agent,
            &p.context.conversation,
            &p.context.project,
            &p.context.mission,
        ] {
            if value.is_empty()
                || value.len() > 128
                || !value
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_:./".contains(&b))
            {
                return Err(denied());
            }
        }
        if p.content.len() > 32_768
            || p.content.contains('\0')
            || p.base_version != env!("CARGO_PKG_VERSION")
            || !Path::new(&p.root).is_absolute()
        {
            return Err(denied());
        }
        let mut b = broker(&p, state)?;
        let (identity, before) = b.replacement_snapshot()?;
        let root_identity = b.root_identity()?;
        if tools::sha(&before) != p.base_digest
            || before.len() > 32_768
            || before.contains(&0)
            || std::str::from_utf8(&before).is_err()
        {
            return Err(denied());
        }
        let digest = store::digest(&p)?;
        tx.execute("INSERT INTO self_changes(id,principal,context,proposal,digest,state,root_identity,file_identity) VALUES(?1,?2,?3,?4,?5,'proposed',?6,?7)",params![p.id,principal()?,serde_json::to_string(&p.context)?,serde_json::to_string(&p)?,digest,root_identity,identity])?;
        event(tx, &p.id, "proposed", &digest)?;
        return Ok(
            json!({"id":p.id,"change_digest":digest,"base_version":p.base_version,"base_digest":p.base_digest,"state":"proposed"}),
        );
    }
    let reference: Reference = serde_json::from_value(payload.clone()).map_err(|_| denied())?;
    let r = load(tx, &reference)?;
    let p = &r.proposal;
    let owner = principal()?;
    match action {
        "get" => {
            return Ok(
                json!({"id":p.id,"change_digest":r.digest,"state":r.state,"base_version":p.base_version,"base_digest":p.base_digest,"proposer_agent":p.proposer_agent,"proposer_principal":owner,"reviewer_principal":r.reviewer,"review_digest":r.review_digest,"approver_principal":r.approver,"executor_principal":r.executor}),
            );
        }
        "review" => {
            if r.state != "proposed" {
                return Err(denied());
            }
            let review = reference
                .review
                .as_deref()
                .filter(|v| !v.trim().is_empty() && v.len() <= 4096)
                .ok_or_else(denied)?;
            let mut b = broker(p, state)?;
            let (identity, before) = b.replacement_snapshot()?;
            if tools::sha(&before) != p.base_digest
                || identity != r.file_identity
                || b.root_identity()? != r.root_identity
            {
                return Err(denied());
            }
            let before = String::from_utf8(before).map_err(|_| denied())?;
            consent(
                "Synapse: independent code review",
                &format!(
                    "Review this concrete code change before any approval. Tests alone do not constitute code review.\nBase version: {}\nChange SHA256: {}\nBase SHA256: {}\nTarget: {} / {}\nProposer agent (untrusted label): {}\nBEFORE:\n{}\nAFTER:\n{}\nReview findings:\n{}\nConfirm only after independently reviewing this diff.",
                    p.base_version,
                    r.digest,
                    p.base_digest,
                    p.root,
                    p.path,
                    p.proposer_agent,
                    before,
                    p.content,
                    review
                ),
            )?;
            let rd = store::digest(&(r.digest.as_str(), owner.as_str(), review))?;
            tx.execute(
                "UPDATE self_changes SET state='reviewed',reviewer=?2,review_digest=?3,review_evidence=?4 WHERE id=?1",
                params![p.id, owner, rd, review],
            )?;
        }
        "approve" => {
            if r.state != "reviewed" || r.reviewer.is_none() || r.review_digest.is_none() {
                return Err(denied());
            }
            consent(
                "Synapse: explicit self-change approval",
                &format!(
                    "Authorize this exact self-change?\nTarget: {} / {}\nBase version: {}\nBase SHA256: {}\nChange SHA256: {}\nIndependent code review SHA256: {}\nThis is a dedicated self-change approval.\nVerified previous bytes will be retained for rollback.",
                    p.root,
                    p.path,
                    p.base_version,
                    p.base_digest,
                    r.digest,
                    r.review_digest.as_deref().unwrap_or_default()
                ),
            )?;
            tx.execute(
                "UPDATE self_changes SET state='approved',approver=?2 WHERE id=?1",
                params![p.id, owner],
            )?;
        }
        "prepare" => {
            if r.state != "approved" || r.approver.as_deref() != Some(&owner) {
                return Err(denied());
            }
            let mut b = broker(p, state)?;
            let root_identity = b.root_identity()?;
            let (identity, before) = b.replacement_snapshot()?;
            if tools::sha(&before) != p.base_digest
                || identity != r.file_identity
                || root_identity != r.root_identity
            {
                return Err(denied());
            }
            tx.execute("INSERT INTO self_change_journal(change_id,root_identity,file_identity,before_bytes,after_bytes,phase) VALUES(?1,?2,?3,?4,?5,'prepared')",params![p.id,root_identity,identity,before,p.content.as_bytes()])?;
            tx.execute(
                "UPDATE self_changes SET state='prepared' WHERE id=?1",
                [&p.id],
            )?;
        }
        "publish" | "rollback" | "recover" => {
            let allowed = match action {
                "publish" => r.state == "prepared",
                "rollback" => r.state == "published",
                _ => r.state == "prepared" || r.state == "published",
            };
            if !allowed || r.approver.as_deref() != Some(&owner) || r.review_digest.is_none() {
                return Err(denied());
            }
            let (root_identity,identity,before,after):(String,String,Vec<u8>,Vec<u8>)=tx.query_row("SELECT root_identity,file_identity,before_bytes,after_bytes FROM self_change_journal WHERE change_id=?1",[&p.id],|row|Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?)))?;
            let mut b = broker(p, state)?;
            let (actual_identity, current) = b.replacement_snapshot()?;
            if b.root_identity()? != root_identity
                || actual_identity != identity
                || tools::sha(&before) != p.base_digest
                || after != p.content.as_bytes()
            {
                return Err(denied());
            }
            // A complete write followed by SQLite interruption is recognized by
            // digest. Unknown partial bytes need fresh concrete human consent;
            // a prepared journal alone does not prove ownership of those bytes.
            if action != "recover" && current != before && current != after {
                return Err(denied());
            }
            if action == "recover" && current != before && current != after {
                consent(
                    "Synapse: recover partial self-change",
                    &format!(
                        "The target has unknown bytes. Restore only after reviewing the interruption and ruling out an unrelated edit.\nTarget: {} / {}\nChange SHA256: {}\nCurrent SHA256: {}\nRestore SHA256: {}",
                        p.root,
                        p.path,
                        r.digest,
                        tools::sha(&current),
                        tools::sha(&before)
                    ),
                )?;
            }
            let (bytes, next) = if action == "publish" {
                (&after, "published")
            } else {
                (&before, "rolled_back")
            };
            b.replacement_write(bytes)?;
            tx.execute(
                "UPDATE self_change_journal SET phase=?2 WHERE change_id=?1",
                params![p.id, next],
            )?;
            tx.execute(
                "UPDATE self_changes SET state=?2,executor=?3 WHERE id=?1",
                params![p.id, next, owner],
            )?;
        }
        "revoke" => {
            if !["proposed", "reviewed", "approved", "prepared"].contains(&r.state.as_str()) {
                return Err(denied());
            }
            if r.state == "prepared" {
                let mut b = broker(p, state)?;
                let (identity, bytes) = b.replacement_snapshot()?;
                if identity != r.file_identity
                    || b.root_identity()? != r.root_identity
                    || tools::sha(&bytes) != p.base_digest
                {
                    return Err(denied());
                }
            }
            tx.execute(
                "UPDATE self_changes SET state='revoked' WHERE id=?1",
                [&p.id],
            )?;
        }
        _ => return Err(denied()),
    }
    let next: String = tx.query_row(
        "SELECT state FROM self_changes WHERE id=?1",
        [&p.id],
        |row| row.get(0),
    )?;
    event(tx, &p.id, &next, &r.digest)?;
    Ok(json!({"id":p.id,"change_digest":r.digest,"state":next}))
}

#[cfg(windows)]
fn confirmation_pages(text: &str) -> CoreResult<Vec<String>> {
    if text.contains('\0') {
        return Err(denied());
    }
    let mut pages = Vec::new();
    let mut page = String::new();
    let mut lines = 0;
    let mut chars = 0;
    for ch in text.chars() {
        page.push(ch);
        chars += 1;
        if ch == '\n' {
            lines += 1;
        }
        if chars >= 600 || lines >= 12 {
            pages.push(std::mem::take(&mut page));
            lines = 0;
            chars = 0;
        }
    }
    if !page.is_empty() {
        pages.push(page);
    }
    Ok(pages)
}
#[cfg(windows)]
fn human_confirmation(title: &str, text: &str) -> CoreResult<()> {
    #[link(name = "user32")]
    unsafe extern "system" {
        fn MessageBoxW(
            hwnd: *mut std::ffi::c_void,
            text: *const u16,
            title: *const u16,
            style: u32,
        ) -> i32;
    }
    let title: Vec<u16> = title.encode_utf16().chain(Some(0)).collect();
    let pages = confirmation_pages(text)?;
    // YES/NO, warning, NO selected by default, foreground. This is local-owner
    // consent, not a credential prompt or a separate multi-user authenticator.
    for (index, page) in pages.iter().enumerate() {
        let text: Vec<u16> = format!(
            "Page {} / {}. No cancels the whole operation.\n\n{}",
            index + 1,
            pages.len(),
            page
        )
        .encode_utf16()
        .chain(Some(0))
        .collect();
        if unsafe {
            MessageBoxW(
                std::ptr::null_mut(),
                text.as_ptr(),
                title.as_ptr(),
                0x4 | 0x30 | 0x100 | 0x10000,
            )
        } != 6
        {
            return Err(denied());
        }
    }
    Ok(())
}
#[cfg(not(windows))]
fn human_confirmation(_: &str, _: &str) -> CoreResult<()> {
    Err(denied())
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    use rusqlite::Connection;
    use std::fs;

    fn yes(_: &str, _: &str) -> CoreResult<()> {
        Ok(())
    }
    #[test]
    fn review_pages_preserve_complete_unicode_diff_without_truncation() {
        let text = "☃á🦀before\n".repeat(300);
        let pages = confirmation_pages(&text).unwrap();
        assert_eq!(pages.concat(), text);
        assert!(pages.len() > 1);
        assert!(pages.iter().all(|p|p.chars().count()<=600 && p.chars().filter(|c|*c=='\n').count()<=12));
        assert!(confirmation_pages("hidden\0diff").is_err());
    }
    fn no(_: &str, _: &str) -> CoreResult<()> {
        Err(denied())
    }
    struct Fixture {
        _temp: tempfile::TempDir,
        db: Connection,
        root: std::path::PathBuf,
        state: std::path::PathBuf,
        proposal: Value,
        reference: Value,
    }
    impl Fixture {
        fn new() -> Self {
            let temp = tempfile::tempdir().unwrap();
            let root = temp.path().join("fixture-project");
            let state = temp.path().join("state");
            fs::create_dir_all(&root).unwrap();
            fs::create_dir_all(&state).unwrap();
            fs::write(root.join("module.rs"), "// SECRET_CANARY_OLD\n").unwrap();
            let mut db = Connection::open_in_memory().unwrap();
            let tx = db.transaction().unwrap();
            tx.execute_batch("PRAGMA foreign_keys=ON; CREATE TABLE events(cursor INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,payload TEXT);").unwrap();
            acknowledge(&tx).unwrap();
            tx.commit().unwrap();
            let proposal = json!({"id":"change-1","context":{"conversation":"chat-a","project":"project-a","mission":"mission-a","swarm":"swarm-a"},"proposer_agent":"agent-proposer","root":root.to_str().unwrap(),"path":"module.rs","base_version":env!("CARGO_PKG_VERSION"),"base_digest":tools::sha(b"// SECRET_CANARY_OLD\n"),"content":"// SECRET_CANARY_NEW\n"});
            let mut result = Self {
                _temp: temp,
                db,
                root,
                state,
                proposal,
                reference: Value::Null,
            };
            let reply = result.call("propose", result.proposal.clone()).unwrap();
            result.reference = json!({"id":"change-1","context":result.proposal["context"],"change_digest":reply["change_digest"]});
            result
        }
        fn call(&mut self, action: &str, payload: Value) -> CoreResult<Value> {
            let tx = self.db.transaction()?;
            let result = dispatch_with_consent(&tx, action, &payload, &self.state, yes)?;
            tx.commit()?;
            Ok(result)
        }
        fn step(&mut self, action: &str) -> CoreResult<Value> {
            let mut reference = self.reference.clone();
            if action == "review" {
                reference["review"] = json!(
                    "Independently inspected exact before/after; no findings. Tests not used as review."
                );
            }
            self.call(action, reference)
        }
        fn prepare(&mut self) {
            for step in ["review", "approve", "prepare"] {
                self.step(step).unwrap();
            }
        }
    }
    #[test]
    fn exact_review_then_approval_publication_and_verified_rollback() {
        let mut f = Fixture::new();
        assert!(f.step("approve").is_err());
        assert!(f.step("prepare").is_err());
        assert!(f.step("publish").is_err());
        f.prepare();
        f.step("publish").unwrap();
        assert_eq!(
            fs::read(f.root.join("module.rs")).unwrap(),
            b"// SECRET_CANARY_NEW\n"
        );
        let record = f.step("get").unwrap();
        assert_eq!(record["reviewer_principal"], principal().unwrap());
        assert_eq!(record["approver_principal"], record["reviewer_principal"]);
        assert_eq!(record["executor_principal"], record["approver_principal"]);
        f.step("rollback").unwrap();
        assert_eq!(
            fs::read(f.root.join("module.rs")).unwrap(),
            b"// SECRET_CANARY_OLD\n"
        );
    }
    #[test]
    fn every_context_dimension_and_principal_is_exactly_bound() {
        let mut f = Fixture::new();
        for key in ["conversation", "project", "mission", "swarm"] {
            let mut forged = f.reference.clone();
            forged["context"][key] = json!("other");
            for action in [
                "get", "review", "approve", "prepare", "publish", "rollback", "recover", "revoke",
            ] {
                assert!(f.call(action, forged.clone()).is_err(), "{key} / {action}");
            }
        }
        f.db.execute(
            "UPDATE self_changes SET principal='forged-other-OS-principal'",
            [],
        )
        .unwrap();
        assert!(f.step("get").is_err());
    }
    #[test]
    fn authority_cannot_be_forged_by_roles_boolean_or_generic_approval() {
        let mut f = Fixture::new();
        for key in [
            "approved",
            "principal",
            "human",
            "reviewer",
            "actor",
            "mission_approved",
        ] {
            let mut payload = f.reference.clone();
            payload[key] = json!(true);
            assert!(f.call("approve", payload).is_err());
        }
        let mut p = f.proposal.clone();
        p["id"] = json!("change-2");
        p["proposer_agent"] = json!("human:administrator");
        let proposed = f.call("propose", p.clone()).unwrap();
        let reference = json!({"id":"change-2","context":p["context"],"change_digest":proposed["change_digest"]});
        assert!(f.call("approve", reference).is_err());
        let tx = f.db.transaction().unwrap();
        let mut reference = f.reference.clone();
        reference["review"] = json!("reviewed");
        assert!(dispatch_with_consent(&tx, "review", &reference, &f.state, no).is_err());
    }
    #[test]
    fn base_drift_revocation_and_changed_digest_block_publication() {
        let mut f = Fixture::new();
        f.step("review").unwrap();
        f.step("approve").unwrap();
        fs::write(f.root.join("module.rs"), "operator edit").unwrap();
        assert!(f.step("prepare").is_err());
        let mut reference = f.reference.clone();
        reference["change_digest"] = json!("bad");
        assert!(f.call("get", reference).is_err());
        fs::write(f.root.join("module.rs"), "// SECRET_CANARY_OLD\n").unwrap();
        f.step("prepare").unwrap();
        f.step("revoke").unwrap();
        assert!(f.step("publish").is_err());
    }
    #[test]
    fn interrupted_publication_transaction_recovers_from_durable_journal() {
        let mut f = Fixture::new();
        f.prepare();
        {
            let tx = f.db.transaction().unwrap();
            dispatch_with_consent(&tx, "publish", &f.reference, &f.state, yes).unwrap();
            // The file effect is durable, the result transaction is interrupted.
        }
        assert_eq!(f.step("get").unwrap()["state"], "prepared");
        assert!(f.step("revoke").is_err());
        assert_eq!(
            fs::read(f.root.join("module.rs")).unwrap(),
            b"// SECRET_CANARY_NEW\n"
        );
        f.step("recover").unwrap();
        assert_eq!(
            fs::read(f.root.join("module.rs")).unwrap(),
            b"// SECRET_CANARY_OLD\n"
        );
    }
    #[test]
    fn partial_bytes_need_new_human_consent_and_replaced_inode_is_refused() {
        let mut f = Fixture::new();
        f.prepare();
        fs::write(f.root.join("module.rs"), b"partial").unwrap();
        {
            let tx = f.db.transaction().unwrap();
            assert!(dispatch_with_consent(&tx, "recover", &f.reference, &f.state, no).is_err());
        }
        assert_eq!(fs::read(f.root.join("module.rs")).unwrap(), b"partial");
        f.step("recover").unwrap();
        let mut f = Fixture::new();
        f.prepare();
        fs::rename(f.root.join("module.rs"), f.root.join("displaced.rs")).unwrap();
        fs::write(f.root.join("module.rs"), b"// SECRET_CANARY_OLD\n").unwrap();
        assert!(f.step("publish").is_err());
        assert!(f.step("recover").is_err());
    }
    #[test]
    fn diagnostics_exclude_secrets_and_generic_roots_cannot_bypass_gate() {
        let mut f = Fixture::new();
        f.prepare();
        f.step("publish").unwrap();
        let events: String =
            f.db.query_row("SELECT group_concat(payload) FROM events", [], |r| r.get(0))
                .unwrap();
        assert!(!events.contains("SECRET_CANARY"));
        assert!(!f.step("get").unwrap().to_string().contains("SECRET_CANARY"));
        let ancestor = f.root.parent().unwrap();
        assert!(guard_roots(&f.root, &[&f.root]).is_err());
        assert!(guard_roots(ancestor, &[&f.root]).is_err());
        assert!(guard_roots(&f.state, &[&f.root]).is_ok());
        assert!(guard_project_root(Path::new(env!("CARGO_MANIFEST_DIR"))).is_err());
    }
}
