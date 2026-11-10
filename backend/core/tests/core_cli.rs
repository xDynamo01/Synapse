use serde_json::{Value, json};
use std::{
    io::{BufRead, BufReader, Write},
    process::{Command, Stdio},
};
use tempfile::TempDir;

fn run(root: &TempDir, lines: &[Value]) -> Vec<Value> {
    raw(
        root,
        &lines.iter().map(|v| format!("{v}\n")).collect::<String>(),
    )
}
fn raw(root: &TempDir, input: &str) -> Vec<Value> {
    let mut child = Command::new(env!("CARGO_BIN_EXE_synapse-backend"))
        .args([
            "--state-dir",
            root.path().join("state").to_str().unwrap(),
            "--workspace",
            root.path().to_str().unwrap(),
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut stdin = child.stdin.take().unwrap();
    let input = input.as_bytes().to_vec();
    let writer = std::thread::spawn(move || stdin.write_all(&input));
    let output = child.wait_with_output().unwrap();
    writer.join().unwrap().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout)
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect()
}
fn req(id: &str, command: Value) -> Value {
    json!({"version":1,"request_id":id,"command":command})
}
fn ok(v: &Value) {
    assert_eq!(v["ok"], true, "{v}");
}
fn error(v: &Value, code: &str) {
    assert_eq!(v["ok"], false, "{v}");
    assert_eq!(v["error"]["code"], code, "{v}");
}

#[test]
fn mission_previous_digests_are_optional_and_validate_resources_and_sha256() {
    let root = TempDir::new().unwrap();
    let base = json!({"version":1,"scope":"project:a","objective":"Replace a file","actions":["artifact_replace"],"resources":["file.txt"],"rollback":"verified backup"});
    let mut valid = base.clone();
    valid["artifact_previous_digests"] = json!({"file.txt":"0".repeat(64)});
    let mut foreign = base.clone();
    foreign["artifact_previous_digests"] = json!({"other.txt":"0".repeat(64)});
    let mut malformed = base.clone();
    malformed["artifact_previous_digests"] = json!({"file.txt":"A".repeat(64)});
    let out = run(
        &root,
        &[
            req(
                "old",
                json!({"type":"mission_propose","mission_id":"old","contract":base}),
            ),
            req(
                "valid",
                json!({"type":"mission_propose","mission_id":"valid","contract":valid}),
            ),
            req(
                "foreign",
                json!({"type":"mission_propose","mission_id":"foreign","contract":foreign}),
            ),
            req(
                "malformed",
                json!({"type":"mission_propose","mission_id":"malformed","contract":malformed}),
            ),
        ],
    );
    ok(&out[0]);
    ok(&out[1]);
    error(&out[2], "invalid_request");
    error(&out[3], "invalid_request");
}

#[cfg(windows)]
fn tool(id: &str, mission: &str, kind: &str, path: &str, content: Option<&str>) -> Value {
    let mut operation = json!({"type":kind,"path":path});
    if let Some(content) = content {
        operation["content"] = json!(content);
    }
    req(
        id,
        json!({"type":"tool_execute","mission_id":mission,"operation":operation}),
    )
}

#[cfg(windows)]
fn approved_tool_mission(root: &TempDir, mission: &str, resources: Value, skill: Option<Value>) {
    use sha2::{Digest, Sha256};
    let mut contract = json!({"version":1,"scope":"project:a","objective":"Work on approved files","actions":["workspace_list","workspace_read","artifact_create","artifact_replace"],"resources":resources,"rollback":"manual removal"});
    let mut digests = serde_json::Map::new();
    for resource in resources.as_array().unwrap() {
        let path = resource.as_str().unwrap();
        let content = match path {
            "report.txt" => "hello",
            "existing.txt" => "changed",
            "file.txt" => "pinned",
            "new.txt" => "no",
            _ => "data",
        };
        let digest = Sha256::digest(content.as_bytes())
            .iter()
            .map(|x| format!("{x:02x}"))
            .collect::<String>();
        digests.insert(path.into(), json!(digest));
    }
    contract["artifact_digests"] = json!(digests);
    if let Some(skill) = skill {
        contract["skill"] = skill;
    }
    let proposal = run(
        root,
        &[req(
            &format!("p-{mission}"),
            json!({"type":"mission_propose","mission_id":mission,"contract":contract}),
        )],
    );
    ok(&proposal[0]);
    let digest = proposal[0]["result"]["contract_digest"].as_str().unwrap();
    let approval = run(
        root,
        &[req(
            &format!("a-{mission}"),
            json!({"type":"mission_approve","mission_id":mission,"contract_digest":digest}),
        )],
    );
    ok(&approval[0]);
}

#[cfg(windows)]
fn approve_replacement(root: &TempDir) {
    use sha2::{Digest, Sha256};
    let hash = |s: &str| {
        Sha256::digest(s.as_bytes())
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>()
    };
    std::fs::write(root.path().join("file.txt"), "old").unwrap();
    let contract = json!({"version":1,"scope":"project:a","objective":"Replace","actions":["artifact_replace"],"resources":["file.txt"],"rollback":"verified backup","artifact_digests":{"file.txt":hash("new")},"artifact_previous_digests":{"file.txt":hash("old")}});
    let proposal = run(
        root,
        &[req(
            "proposal",
            json!({"type":"mission_propose","mission_id":"m","contract":contract}),
        )],
    );
    ok(&proposal[0]);
    let digest = proposal[0]["result"]["contract_digest"].as_str().unwrap();
    ok(&run(
        root,
        &[req(
            "approval",
            json!({"type":"mission_approve","mission_id":"m","contract_digest":digest}),
        )],
    )[0]);
}

#[cfg(windows)]
#[test]
fn approved_replace_is_verified_and_replays_after_restart() {
    let root = TempDir::new().unwrap();
    approve_replacement(&root);
    let request = tool("replace", "m", "replace", "file.txt", Some("new"));
    let result = run(&root, &[request.clone()]);
    ok(&result[0]);
    assert_eq!(
        std::fs::read_to_string(root.path().join("file.txt")).unwrap(),
        "new"
    );
    assert_eq!(result, run(&root, &[request]));
    std::fs::write(root.path().join("file.txt"), "changed by user").unwrap();
    let restore = |id: &str| {
        req(
            id,
            json!({"type":"tool_recovery","intent_id":"replace","mode":"restore"}),
        )
    };
    error(&run(&root, &[restore("conflict")])[0], "recovery_required");
    assert_eq!(
        std::fs::read_to_string(root.path().join("file.txt")).unwrap(),
        "changed by user"
    );
    std::fs::write(root.path().join("file.txt"), "new").unwrap();
    let restored = run(&root, &[restore("restore")]);
    ok(&restored[0]);
    assert_eq!(
        std::fs::read_to_string(root.path().join("file.txt")).unwrap(),
        "old"
    );
    assert_eq!(restored, run(&root, &[restore("restore")]));
    error(
        &run(
            &root,
            &[req(
                "restore",
                json!({"type":"tool_recovery","intent_id":"replace","mode":"inspect"}),
            )],
        )[0],
        "idempotency_conflict",
    );
}

#[cfg(windows)]
#[test]
fn replacement_rejects_wrong_content_revocation_and_corrupt_backup() {
    let root = TempDir::new().unwrap();
    approve_replacement(&root);
    error(
        &run(
            &root,
            &[tool("wrong-new", "m", "replace", "file.txt", Some("wrong"))],
        )[0],
        "permission_denied",
    );
    std::fs::write(root.path().join("file.txt"), "wrong old").unwrap();
    error(
        &run(
            &root,
            &[tool("wrong-old", "m", "replace", "file.txt", Some("new"))],
        )[0],
        "permission_denied",
    );
    std::fs::write(root.path().join("file.txt"), "old").unwrap();
    ok(&run(
        &root,
        &[tool("replace", "m", "replace", "file.txt", Some("new"))],
    )[0]);
    let db = rusqlite::Connection::open(root.path().join("state/core.sqlite3")).unwrap();
    db.execute(
        "UPDATE replacement_backups SET backup=?1 WHERE request_id='replace'",
        [b"corrupted".as_slice()],
    )
    .unwrap();
    drop(db);
    let restore = |id: &str| {
        req(
            id,
            json!({"type":"tool_recovery","intent_id":"replace","mode":"restore"}),
        )
    };
    error(&run(&root, &[restore("corrupt")])[0], "recovery_required");
    assert_eq!(
        std::fs::read_to_string(root.path().join("file.txt")).unwrap(),
        "new"
    );
    let db = rusqlite::Connection::open(root.path().join("state/core.sqlite3")).unwrap();
    db.execute(
        "UPDATE replacement_backups SET backup=?1 WHERE request_id='replace'",
        [b"old".as_slice()],
    )
    .unwrap();
    drop(db);
    ok(&run(
        &root,
        &[req(
            "revoke",
            json!({"type":"mission_revoke","mission_id":"m","reason":"stop"}),
        )],
    )[0]);
    error(
        &run(&root, &[restore("revoked")])[0],
        "mission_not_approved",
    );
}

#[cfg(windows)]
#[test]
fn replacement_rejects_hardlinks_and_exchanged_target_on_restore() {
    let root = TempDir::new().unwrap();
    approve_replacement(&root);
    std::fs::hard_link(root.path().join("file.txt"), root.path().join("alias.txt")).unwrap();
    error(
        &run(
            &root,
            &[tool("linked", "m", "replace", "file.txt", Some("new"))],
        )[0],
        "path_denied",
    );
    std::fs::remove_file(root.path().join("alias.txt")).unwrap();
    ok(&run(
        &root,
        &[tool("replace", "m", "replace", "file.txt", Some("new"))],
    )[0]);
    std::fs::rename(
        root.path().join("file.txt"),
        root.path().join("displaced.txt"),
    )
    .unwrap();
    std::fs::write(root.path().join("file.txt"), "new").unwrap();
    error(
        &run(
            &root,
            &[req(
                "restore",
                json!({"type":"tool_recovery","intent_id":"replace","mode":"restore"}),
            )],
        )[0],
        "recovery_required",
    );
    assert_eq!(
        std::fs::read_to_string(root.path().join("file.txt")).unwrap(),
        "new"
    );
}

#[cfg(windows)]
#[test]
fn tool_create_read_list_and_stop_survive_restart() {
    let root = TempDir::new().unwrap();
    approved_tool_mission(&root, "m", json!([".", "report.txt"]), None);
    let create = tool("create", "m", "create", "report.txt", Some("hello"));
    let wrong = run(
        &root,
        &[tool(
            "wrong-digest",
            "m",
            "create",
            "report.txt",
            Some("different"),
        )],
    );
    error(&wrong[0], "permission_denied");
    assert!(!root.path().join("report.txt").exists());
    let out = run(
        &root,
        &[
            create.clone(),
            tool("read", "m", "read", "report.txt", None),
            tool("list", "m", "list", ".", None),
        ],
    );
    for v in &out {
        ok(v);
    }
    assert_eq!(
        out[0]["result"]["sha256"],
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    );
    assert_eq!(out[1]["result"]["content"], "hello");
    assert_eq!(out[1]["result"]["sha256"], out[0]["result"]["sha256"]);
    assert!(
        out[2]["result"]["entries"]
            .as_array()
            .unwrap()
            .iter()
            .any(|x| x == "report.txt")
    );
    assert!(
        !out[2]["result"]["entries"]
            .as_array()
            .unwrap()
            .iter()
            .any(|x| x == "state")
    );
    let next = run(
        &root,
        &[
            create.clone(),
            tool("create", "m", "create", "report.txt", Some("changed")),
            req(
                "revoke",
                json!({"type":"mission_revoke","mission_id":"m","reason":"stop"}),
            ),
            tool("after", "m", "read", "report.txt", None),
        ],
    );
    assert_eq!(out[0], next[0]);
    error(&next[1], "idempotency_conflict");
    ok(&next[2]);
    error(&next[3], "mission_not_approved");
    let after = run(
        &root,
        &[
            create,
            tool(
                "after-restart",
                "m",
                "create",
                "report.txt",
                Some("overwrite"),
            ),
        ],
    );
    assert_eq!(out[0], after[0]);
    error(&after[1], "mission_not_approved");
    assert_eq!(
        std::fs::read_to_string(root.path().join("report.txt")).unwrap(),
        "hello"
    );
}

#[cfg(windows)]
#[test]
fn tool_denies_unapproved_paths_state_links_overwrite_and_replace() {
    let root = TempDir::new().unwrap();
    std::fs::write(root.path().join("existing.txt"), "original").unwrap();
    let proposed = json!({"version":1,"scope":"project:a","objective":"Pending","actions":["workspace_read"],"resources":["existing.txt"],"rollback":"manual removal"});
    ok(&run(
        &root,
        &[req(
            "pending",
            json!({"type":"mission_propose","mission_id":"pending","contract":proposed}),
        )],
    )[0]);
    error(
        &run(
            &root,
            &[tool("unapproved", "pending", "read", "existing.txt", None)],
        )[0],
        "mission_not_approved",
    );
    approved_tool_mission(
        &root,
        "m",
        json!([
            "existing.txt",
            "state/core.sqlite3",
            "../outside",
            "link.txt",
            "absent.txt",
            "file:stream"
        ]),
        None,
    );
    std::fs::hard_link(
        root.path().join("state/core.sqlite3"),
        root.path().join("link.txt"),
    )
    .unwrap();
    let out = run(
        &root,
        &[
            tool("denied-resource", "m", "read", "other.txt", None),
            tool("traversal", "m", "read", "../outside", None),
            tool("ads", "m", "read", "file:stream", None),
            tool("state", "m", "read", "state/core.sqlite3", None),
            tool("hardlink", "m", "read", "link.txt", None),
            tool("replace", "m", "replace", "existing.txt", Some("changed")),
            tool("overwrite", "m", "create", "existing.txt", Some("changed")),
        ],
    );
    error(&out[0], "permission_denied");
    for i in 1..=4 {
        error(&out[i], "path_denied");
    }
    error(&out[5], "permission_denied");
    error(&out[6], "recovery_required");
    assert_eq!(
        std::fs::read_to_string(root.path().join("existing.txt")).unwrap(),
        "original"
    );
}

#[cfg(windows)]
#[test]
fn tool_rejects_junction_and_cancelled_mission() {
    let root = TempDir::new().unwrap();
    let outside = TempDir::new().unwrap();
    std::fs::write(outside.path().join("secret.txt"), "secret").unwrap();
    let link = root.path().join("junction");
    let status = Command::new("cmd")
        .args(["/c", "mklink", "/J"])
        .arg(&link)
        .arg(outside.path())
        .output()
        .unwrap();
    assert!(
        status.status.success(),
        "{}",
        String::from_utf8_lossy(&status.stderr)
    );
    approved_tool_mission(&root, "m", json!(["junction/secret.txt", "new.txt"]), None);
    let out = run(
        &root,
        &[
            tool("junction", "m", "read", "junction/secret.txt", None),
            req(
                "cancel",
                json!({"type":"mission_cancel","mission_id":"m","reason":"stop"}),
            ),
        ],
    );
    error(&out[0], "path_denied");
    ok(&out[1]);
    let out = run(
        &root,
        &[tool("cancelled", "m", "create", "new.txt", Some("no"))],
    );
    error(&out[0], "mission_not_approved");
    assert!(!root.path().join("new.txt").exists());
}

#[cfg(windows)]
#[test]
fn skill_version_cannot_be_replaced_or_broaden_mission() {
    let root = TempDir::new().unwrap();
    let skill = json!({"id":"helper","version":"1","scope":"project:a","provenance":"local","tools":["artifact_create"],"permissions":["artifact_create"],"instructions":"First"});
    let registered = run(
        &root,
        &[req("one", json!({"type":"skill_register","skill":skill}))],
    );
    ok(&registered[0]);
    let digest = registered[0]["result"]["digest"].clone();
    let mut changed = skill.clone();
    changed["instructions"] = json!("Changed");
    error(
        &run(
            &root,
            &[req(
                "replace-skill",
                json!({"type":"skill_register","skill":changed}),
            )],
        )[0],
        "already_exists",
    );
    changed["version"] = json!("2");
    ok(&run(
        &root,
        &[req(
            "new-skill",
            json!({"type":"skill_register","skill":changed}),
        )],
    )[0]);
    let pin = json!({"scope":"project:a","id":"helper","version":"1","digest":digest});
    approved_tool_mission(&root, "m", json!(["file.txt"]), Some(pin.clone()));
    let out = run(
        &root,
        &[tool(
            "create-pinned",
            "m",
            "create",
            "file.txt",
            Some("pinned"),
        )],
    );
    ok(&out[0]);
    assert_eq!(out[0]["result"]["skill"]["version"], "1");
    let bad = json!({"version":1,"scope":"project:a","objective":"narrow","actions":["workspace_read"],"resources":["file.txt"],"rollback":"manual removal","skill":pin});
    error(
        &run(
            &root,
            &[req(
                "narrow",
                json!({"type":"mission_propose","mission_id":"narrow","contract":bad}),
            )],
        )[0],
        "permission_denied",
    );
}

#[cfg(windows)]
#[test]
fn prepared_intent_is_never_replayed_and_skill_is_pinned() {
    use sha2::{Digest, Sha256};
    let root = TempDir::new().unwrap();
    let skill = json!({"id":"helper","version":"1","scope":"project:a","provenance":"local manifest","tools":["artifact_create"],"permissions":["artifact_create"],"instructions":"Use approved creation."});
    let registered = run(
        &root,
        &[req("s", json!({"type":"skill_register","skill":skill}))],
    );
    ok(&registered[0]);
    let pin = json!({"scope":"project:a","id":"helper","version":"1","digest":registered[0]["result"]["digest"]});
    approved_tool_mission(&root, "m", json!(["owned.txt", "pending.txt"]), Some(pin));
    let out = run(
        &root,
        &[
            tool("read-denied", "m", "read", "owned.txt", None),
            tool("owned", "m", "create", "owned.txt", Some("data")),
        ],
    );
    error(&out[0], "permission_denied");
    ok(&out[1]);
    assert_eq!(out[1]["result"]["skill"]["version"], "1");
    let request = tool("pending-effect", "m", "create", "pending.txt", Some("data"));
    let parsed: synapse_core::Request = serde_json::from_value(request.clone()).unwrap();
    let digest = Sha256::digest(serde_json::to_vec(&parsed).unwrap())
        .iter()
        .map(|x| format!("{x:02x}"))
        .collect::<String>();
    let target = root
        .path()
        .canonicalize()
        .unwrap()
        .join("pending.txt")
        .to_string_lossy()
        .into_owned();
    let db = rusqlite::Connection::open(root.path().join("state/core.sqlite3")).unwrap();
    db.execute("INSERT INTO tool_intents(request_id,request_digest,mission_id,target,content_digest,status) VALUES(?1,?2,'m',?3,'fixture','prepared')",rusqlite::params!["pending-effect",digest,target]).unwrap();
    drop(db);
    let out = run(
        &root,
        &[
            request.clone(),
            tool("another", "m", "create", "pending.txt", Some("data")),
            tool(
                "pending-effect",
                "m",
                "create",
                "pending.txt",
                Some("changed"),
            ),
            req("pending-effect", json!({"type":"health"})),
        ],
    );
    error(&out[0], "recovery_required");
    error(&out[1], "recovery_required");
    error(&out[2], "idempotency_conflict");
    error(&out[3], "idempotency_conflict");
    assert!(!root.path().join("pending.txt").exists());
}

#[cfg(all(windows, feature = "test-fault-injection"))]
#[test]
fn tool_crash_after_durable_prepare_does_not_apply_or_replay() {
    let root = TempDir::new().unwrap();
    approved_tool_mission(&root, "m", json!(["crash.txt"]), None);
    let request = tool("crash-request", "m", "create", "crash.txt", Some("data"));
    let mut child = Command::new(env!("CARGO_BIN_EXE_synapse-backend"))
        .args([
            "--state-dir",
            root.path().join("state").to_str().unwrap(),
            "--workspace",
            root.path().to_str().unwrap(),
        ])
        .env("SYNAPSE_TEST_CRASH_AFTER_TOOL_PREPARE", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    writeln!(child.stdin.take().unwrap(), "{request}").unwrap();
    assert_eq!(child.wait().unwrap().code(), Some(86));
    assert!(!root.path().join("crash.txt").exists());
    let out = run(
        &root,
        &[
            request,
            tool("new-id", "m", "create", "crash.txt", Some("data")),
        ],
    );
    error(&out[0], "recovery_required");
    error(&out[1], "recovery_required");
    assert!(!root.path().join("crash.txt").exists());
    ok(&run(
        &root,
        &[req(
            "abandon",
            json!({"type":"tool_recovery","intent_id":"crash-request","mode":"safe_abandon"}),
        )],
    )[0]);
    ok(&run(
        &root,
        &[tool("released", "m", "create", "crash.txt", Some("data"))],
    )[0]);
}

#[cfg(all(windows, feature = "test-fault-injection"))]
fn crash_on(root: &TempDir, request: &Value, fault: &str) {
    let mut child = Command::new(env!("CARGO_BIN_EXE_synapse-backend"))
        .args([
            "--state-dir",
            root.path().join("state").to_str().unwrap(),
            "--workspace",
            root.path().to_str().unwrap(),
        ])
        .env(fault, "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    writeln!(child.stdin.take().unwrap(), "{request}").unwrap();
    assert_eq!(child.wait().unwrap().code(), Some(86));
}

#[cfg(all(windows, feature = "test-fault-injection"))]
#[test]
fn replacement_crashes_are_not_repeated_and_can_be_verified() {
    for fault in [
        "SYNAPSE_TEST_CRASH_BEFORE_REPLACE",
        "SYNAPSE_TEST_CRASH_AFTER_REPLACE",
        "SYNAPSE_TEST_CRASH_BEFORE_REPLACE_CONFIRM",
    ] {
        let root = TempDir::new().unwrap();
        approve_replacement(&root);
        let request = tool("replace", "m", "replace", "file.txt", Some("new"));
        crash_on(&root, &request, fault);
        let before = fault == "SYNAPSE_TEST_CRASH_BEFORE_REPLACE";
        assert_eq!(
            std::fs::read_to_string(root.path().join("file.txt")).unwrap(),
            if before { "old" } else { "new" }
        );
        error(&run(&root, &[request.clone()])[0], "recovery_required");
        if !before {
            std::fs::write(root.path().join("file.txt"), "partial").unwrap();
            error(
                &run(
                    &root,
                    &[req(
                        "partial-finalize",
                        json!({"type":"tool_recovery","intent_id":"replace","mode":"finalize"}),
                    )],
                )[0],
                "recovery_required",
            );
            error(
                &run(
                    &root,
                    &[req(
                        "partial-restore",
                        json!({"type":"tool_recovery","intent_id":"replace","mode":"restore"}),
                    )],
                )[0],
                "recovery_required",
            );
            assert_eq!(
                std::fs::read_to_string(root.path().join("file.txt")).unwrap(),
                "partial"
            );
            std::fs::write(root.path().join("file.txt"), "new").unwrap();
        }
        let finalize = req(
            "finalize",
            json!({"type":"tool_recovery","intent_id":"replace","mode":"finalize"}),
        );
        let result = run(&root, &[finalize]);
        if before {
            error(&result[0], "recovery_required");
        } else {
            ok(&result[0]);
            ok(&run(&root, &[request])[0]);
            ok(&run(
                &root,
                &[req(
                    "restore",
                    json!({"type":"tool_recovery","intent_id":"replace","mode":"restore"}),
                )],
            )[0]);
            assert_eq!(
                std::fs::read_to_string(root.path().join("file.txt")).unwrap(),
                "old"
            );
        }
    }
}

#[cfg(all(windows, feature = "test-fault-injection"))]
#[test]
fn restore_crash_never_repeats_write_blindly() {
    for fault in [
        "SYNAPSE_TEST_CRASH_BEFORE_RESTORE",
        "SYNAPSE_TEST_CRASH_AFTER_RESTORE",
    ] {
        let root = TempDir::new().unwrap();
        approve_replacement(&root);
        ok(&run(
            &root,
            &[tool("replace", "m", "replace", "file.txt", Some("new"))],
        )[0]);
        let restore = req(
            "restore",
            json!({"type":"tool_recovery","intent_id":"replace","mode":"restore"}),
        );
        crash_on(&root, &restore, fault);
        let out = run(&root, &[restore.clone()]);
        if fault == "SYNAPSE_TEST_CRASH_BEFORE_RESTORE" {
            error(&out[0], "recovery_required");
            assert_eq!(
                std::fs::read_to_string(root.path().join("file.txt")).unwrap(),
                "new"
            );
            ok(&run(
                &root,
                &[req(
                    "abandon-restore",
                    json!({"type":"tool_recovery","intent_id":"restore","mode":"safe_abandon"}),
                )],
            )[0]);
            ok(&run(
                &root,
                &[req(
                    "retry-restore",
                    json!({"type":"tool_recovery","intent_id":"replace","mode":"restore"}),
                )],
            )[0]);
            assert_eq!(
                std::fs::read_to_string(root.path().join("file.txt")).unwrap(),
                "old"
            );
        } else {
            ok(&out[0]);
            assert_eq!(
                std::fs::read_to_string(root.path().join("file.txt")).unwrap(),
                "old"
            );
            assert_eq!(out, run(&root, &[restore]));
        }
    }
}

#[test]
fn strict_protocol_and_bounds_recover_for_next_request() {
    let root = TempDir::new().unwrap();
    let input = format!(
        "{{bad\n{}\n{}\n{}\n{}\n{}\n",
        req("major", json!({"type":"health"}))
            .to_string()
            .replace("\"version\":1", "\"version\":2"),
        json!({"version":1,"request_id":"extra","extra":true,"command":{"type":"health"}}),
        req("field", json!({"type":"health","extra":true})),
        "x".repeat(65537),
        req("h", json!({"type":"health"}))
    );
    let out = raw(&root, &input);
    assert_eq!(out.len(), 6);
    error(&out[0], "invalid_request");
    error(&out[1], "unsupported_version");
    error(&out[2], "invalid_request");
    error(&out[3], "invalid_request");
    error(&out[4], "request_too_large");
    ok(&out[5]);
    assert_eq!(out[5]["result"]["identity"], "A.R.T.E.M.I.S.");
}

#[test]
fn durable_chat_idempotency_events_and_changed_retry() {
    let root = TempDir::new().unwrap();
    let create = req(
        "c",
        json!({"type":"chat_create","chat_id":"chat","title":"One","scope":"project:a"}),
    );
    let message = req(
        "m",
        json!({"type":"message_append","chat_id":"chat","message_id":"msg","role":"user","content":"Hello"}),
    );
    let first = run(&root, &[create.clone(), message.clone()]);
    first.iter().for_each(ok);
    let reopened = run(
        &root,
        &[
            message.clone(),
            req("read", json!({"type":"chat_get","chat_id":"chat"})),
            req(
                "events",
                json!({"type":"events_read","after":0,"limit":100}),
            ),
        ],
    );
    assert_eq!(first[1], reopened[0]);
    ok(&reopened[1]);
    assert_eq!(
        reopened[1]["result"]["messages"].as_array().unwrap().len(),
        1
    );
    assert_eq!(reopened[1]["result"]["messages"][0]["content"], "Hello");
    assert_eq!(reopened[2]["result"]["events"].as_array().unwrap().len(), 2);
    let changed = run(
        &root,
        &[req(
            "m",
            json!({"type":"message_append","chat_id":"chat","message_id":"msg2","role":"user","content":"Changed"}),
        )],
    );
    error(&changed[0], "idempotency_conflict");
}

#[test]
fn canonical_memory_requires_exact_context_and_retains_revisions() {
    let root = TempDir::new().unwrap();
    let write = |id: &str, revision: u64, content: &str| {
        req(
            id,
            json!({"type":"memory_put","scope":"project:a","key":"constraint","kind":"constraint","content":content,"expected_revision":revision,"provenance":{"source_type":"human","source_id":"decision-1","evidence":"Explicit constraint"},"status":"active"}),
        )
    };
    let out = run(
        &root,
        &[
            write("a", 0, "first"),
            write("b", 0, "conflict"),
            write("c", 1, "second"),
        ],
    );
    ok(&out[0]);
    error(&out[1], "revision_conflict");
    ok(&out[2]);
    let out = run(
        &root,
        &[
            req(
                "foreign",
                json!({"type":"memory_get","scope":"project:a","context_reference":"project:b","key":"constraint"}),
            ),
            req(
                "mem",
                json!({"type":"memory_get","scope":"project:a","context_reference":"project:a","key":"constraint"}),
            ),
        ],
    );
    error(&out[0], "context_denied");
    ok(&out[1]);
    let rev = out[1]["result"]["revisions"].as_array().unwrap();
    assert_eq!(rev.len(), 2);
    assert_eq!(rev[1]["content"], "second");
}

#[test]
fn immutable_missions_and_terminal_stop_survive_restart() {
    let root = TempDir::new().unwrap();
    let contract = json!({"version":1,"scope":"project:a","objective":"Create report","actions":["artifact_create"],"resources":["report.txt"],"rollback":"remove created artifact"});
    let propose = req(
        "p",
        json!({"type":"mission_propose","mission_id":"mission","contract":contract}),
    );
    let out = run(&root, &[propose.clone()]);
    ok(&out[0]);
    let digest = out[0]["result"]["contract_digest"].as_str().unwrap();
    let out = run(
        &root,
        &[
            req(
                "approve",
                json!({"type":"mission_approve","mission_id":"mission","contract_digest":digest}),
            ),
            req(
                "revoke",
                json!({"type":"mission_revoke","mission_id":"mission","reason":"Stop"}),
            ),
        ],
    );
    out.iter().for_each(ok);
    let out = run(
        &root,
        &[
            req(
                "again",
                json!({"type":"mission_approve","mission_id":"mission","contract_digest":digest}),
            ),
            req("get", json!({"type":"mission_get","mission_id":"mission"})),
            propose,
        ],
    );
    error(&out[0], "invalid_transition");
    assert_eq!(out[1]["result"]["state"], "revoked");
    ok(&out[2]);
    let mut modified = contract.clone();
    modified["objective"] = json!("Different");
    let out = run(
        &root,
        &[
            req(
                "replace",
                json!({"type":"mission_propose","mission_id":"mission","contract":modified}),
            ),
            req(
                "p2",
                json!({"type":"mission_propose","mission_id":"cancel","contract":contract}),
            ),
            req(
                "cancel",
                json!({"type":"mission_cancel","mission_id":"cancel","reason":"No longer needed"}),
            ),
            req(
                "cancel-get",
                json!({"type":"mission_get","mission_id":"cancel"}),
            ),
        ],
    );
    error(&out[0], "already_exists");
    ok(&out[1]);
    ok(&out[2]);
    assert_eq!(out[3]["result"]["state"], "cancelled");
}

#[test]
fn registries_persist_and_absent_execution_is_unavailable() {
    let root = TempDir::new().unwrap();
    let out = run(
        &root,
        &[
            req(
                "model",
                json!({"type":"model_register","model":{"id":"local-model","provider":"loopback","endpoint":"http://127.0.0.1:1234","capabilities":["chat"],"memory_bytes":1024}}),
            ),
            req(
                "skill",
                json!({"type":"skill_register","skill":{"id":"report","version":"1","scope":"project:a","provenance":"local human-authored manifest","tools":["artifact_create"],"permissions":["workspace_write"],"instructions":"Write report"}}),
            ),
        ],
    );
    out.iter().for_each(ok);
    let out = run(
        &root,
        &[
            req("models", json!({"type":"models_list"})),
            req("skills", json!({"type":"skills_list","scope":"project:a"})),
            req("caps", json!({"type":"capabilities_list"})),
            req(
                "infer",
                json!({"type":"inference","model_id":"local-model","prompt":"Hi"}),
            ),
            req(
                "execute",
                json!({"type":"mission_execute","mission_id":"none"}),
            ),
        ],
    );
    assert_eq!(out[0]["result"]["models"].as_array().unwrap().len(), 1);
    assert_eq!(out[1]["result"]["skills"].as_array().unwrap().len(), 1);
    ok(&out[2]);
    error(&out[3], "model_unavailable");
    error(&out[4], "capability_unavailable");
}

#[test]
fn request_limit_counts_payload_not_line_ending() {
    let root = TempDir::new().unwrap();
    let request = req("exact", json!({"type":"health"})).to_string();
    let line = format!("{}{}\n", request, " ".repeat(65_536 - request.len()));
    let output = raw(&root, &line);
    assert_eq!(output.len(), 1);
    ok(&output[0]);
    let crlf = format!("{}{}\r\n", request, " ".repeat(65_536 - request.len()));
    let output = raw(&root, &crlf);
    assert_eq!(output.len(), 1);
    ok(&output[0]);
}

#[test]
fn state_directory_has_one_live_process_owner() {
    let root = TempDir::new().unwrap();
    let state = root.path().join("state");
    let binary = env!("CARGO_BIN_EXE_synapse-backend");
    let mut owner = Command::new(binary)
        .args([
            "--state-dir",
            state.to_str().unwrap(),
            "--workspace",
            root.path().to_str().unwrap(),
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    owner
        .stdin
        .as_mut()
        .unwrap()
        .write_all(format!("{}\n", req("owner", json!({"type":"health"}))).as_bytes())
        .unwrap();
    owner.stdin.as_mut().unwrap().flush().unwrap();
    let mut owner_output = String::new();
    BufReader::new(owner.stdout.take().unwrap())
        .read_line(&mut owner_output)
        .unwrap();
    ok(&serde_json::from_str::<Value>(&owner_output).unwrap());
    let alias = state.join("..").join("state");
    let refused = Command::new(binary)
        .args([
            "--state-dir",
            alias.to_str().unwrap(),
            "--workspace",
            root.path().to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(!refused.status.success());
    assert!(String::from_utf8_lossy(&refused.stderr).contains("state_in_use"));
    owner.kill().unwrap();
    owner.wait().unwrap();
    let reopened = run(&root, &[req("after-death", json!({"type":"health"}))]);
    ok(&reopened[0]);
}

#[test]
fn large_chat_and_memory_histories_page_after_restart() {
    let root = TempDir::new().unwrap();
    let content = "x".repeat(20_000);
    let mut writes = vec![req(
        "create",
        json!({"type":"chat_create","chat_id":"paged","title":"History","scope":"project:a"}),
    )];
    for n in 0..12 {
        writes.push(req(&format!("message-{n}"),json!({"type":"message_append","chat_id":"paged","message_id":format!("msg-{n}"),"role":"user","content":content})));
        writes.push(req(&format!("memory-{n}"),json!({"type":"memory_put","scope":"project:a","key":"history","kind":"fact","content":content,"expected_revision":n,"provenance":{"source_type":"human","source_id":"review","evidence":"Large record"},"status":"active"})));
    }
    run(&root, &writes).iter().for_each(ok);
    let first_request = req(
        "chat-page-0",
        json!({"type":"chat_get","chat_id":"paged","limit":100}),
    );
    let first = run(&root, &[first_request.clone()]);
    ok(&first[0]);
    assert_eq!(first[0]["result"]["has_more"], true);
    assert!(first[0]["result"]["messages"].as_array().unwrap().len() < 12);
    assert_eq!(run(&root, &[first_request])[0], first[0]);
    let mut cursor = 0;
    let mut seen = Vec::new();
    for page in 0..12 {
        let out = run(
            &root,
            &[req(
                &format!("chat-page-{}", page + 1),
                json!({"type":"chat_get","chat_id":"paged","after":cursor,"limit":100}),
            )],
        );
        ok(&out[0]);
        assert!(out[0].to_string().len() <= 242_000);
        seen.extend(
            out[0]["result"]["messages"]
                .as_array()
                .unwrap()
                .iter()
                .map(|m| m["message_id"].as_str().unwrap().to_owned()),
        );
        cursor = out[0]["result"]["next_cursor"].as_u64().unwrap();
        if out[0]["result"]["has_more"] == false {
            break;
        }
    }
    assert_eq!(
        seen,
        (0..12).map(|n| format!("msg-{n}")).collect::<Vec<_>>()
    );
    let mut revision = 0;
    let mut seen_revisions = Vec::new();
    for page in 0..12 {
        let out = run(
            &root,
            &[req(
                &format!("memory-page-{page}"),
                json!({"type":"memory_get","scope":"project:a","context_reference":"project:a","key":"history","after_revision":revision,"limit":100}),
            )],
        );
        ok(&out[0]);
        assert!(out[0].to_string().len() <= 242_000);
        seen_revisions.extend(
            out[0]["result"]["revisions"]
                .as_array()
                .unwrap()
                .iter()
                .map(|r| r["revision"].as_u64().unwrap()),
        );
        revision = out[0]["result"]["next_revision"].as_u64().unwrap();
        if out[0]["result"]["has_more"] == false {
            break;
        }
    }
    assert_eq!(seen_revisions, (1..=12).collect::<Vec<_>>());
}

#[test]
fn oversized_historical_receipt_is_rejected_before_replay() {
    let root = TempDir::new().unwrap();
    let request = req("old-page", json!({"type":"health"}));
    ok(&run(&root, &[request.clone()])[0]);
    let db = rusqlite::Connection::open(root.path().join("state").join("core.sqlite3")).unwrap();
    db.execute(
        "UPDATE receipts SET response=?1 WHERE request_id='old-page'",
        ["é".repeat(130_000)],
    )
    .unwrap();
    drop(db);
    let replay = run(&root, &[request]);
    error(&replay[0], "response_too_large");
}

#[test]
fn large_skill_registry_is_traversable_and_details_remain_available() {
    let root = TempDir::new().unwrap();
    let instructions = "x".repeat(32_768);
    let mut registrations = Vec::new();
    for n in 0..12 {
        registrations.push(req(&format!("register-skill-{n}"),json!({"type":"skill_register","skill":{"id":format!("skill-{n}"),"version":"1","scope":"project:a","provenance":"human-authored","tools":[],"permissions":[],"instructions":instructions}})));
    }
    run(&root, &registrations).iter().for_each(ok);
    let default = run(
        &root,
        &[req(
            "default-skill-list",
            json!({"type":"skills_list","scope":"project:a"}),
        )],
    );
    ok(&default[0]);
    assert_eq!(default[0]["result"]["skills"].as_array().unwrap().len(), 12);
    assert!(default[0].to_string().len() < 240_000);
    let mut cursor = 0;
    let mut seen = Vec::new();
    for page in 0..6 {
        let out = run(
            &root,
            &[req(
                &format!("skill-list-{page}"),
                json!({"type":"skills_list","scope":"project:a","after":cursor,"limit":3}),
            )],
        );
        ok(&out[0]);
        assert!(out[0].to_string().len() < 240_000);
        seen.extend(
            out[0]["result"]["skills"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v["id"].as_str().unwrap().to_owned()),
        );
        cursor = out[0]["result"]["next_cursor"].as_u64().unwrap();
        if out[0]["result"]["has_more"] == false {
            break;
        }
    }
    assert_eq!(
        seen,
        (0..12).map(|n| format!("skill-{n}")).collect::<Vec<_>>()
    );
    let details = run(
        &root,
        &[
            req(
                "skill-detail",
                json!({"type":"skill_get","scope":"project:a","skill_id":"skill-11","version":"1"}),
            ),
            req(
                "foreign-skill",
                json!({"type":"skill_get","scope":"project:b","skill_id":"skill-11","version":"1"}),
            ),
        ],
    );
    ok(&details[0]);
    assert_eq!(
        details[0]["result"]["skill"]["instructions"]
            .as_str()
            .unwrap()
            .len(),
        32_768
    );
    error(&details[1], "not_found");
    let mut models = Vec::new();
    for n in 0..5 {
        models.push(req(&format!("register-model-{n}"),json!({"type":"model_register","model":{"id":format!("model-{n}"),"provider":"local","endpoint":"http://127.0.0.1:1234","capabilities":["chat"],"memory_bytes":1024}})));
    }
    run(&root, &models).iter().for_each(ok);
    let mut cursor = 0;
    let mut seen_models = Vec::new();
    for page in 0..4 {
        let out = run(
            &root,
            &[req(
                &format!("model-list-{page}"),
                json!({"type":"models_list","after":cursor,"limit":2}),
            )],
        );
        ok(&out[0]);
        seen_models.extend(
            out[0]["result"]["models"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v["id"].as_str().unwrap().to_owned()),
        );
        cursor = out[0]["result"]["next_cursor"].as_u64().unwrap();
        if out[0]["result"]["has_more"] == false {
            break;
        }
    }
    assert_eq!(
        seen_models,
        (0..5).map(|n| format!("model-{n}")).collect::<Vec<_>>()
    );
    let detail = run(
        &root,
        &[req(
            "model-detail",
            json!({"type":"model_get","model_id":"model-4"}),
        )],
    );
    ok(&detail[0]);
    assert_eq!(
        detail[0]["result"]["model"]["endpoint"],
        "http://127.0.0.1:1234"
    );
    let invalid = run(
        &root,
        &[
            req(
                "zero-skill-limit",
                json!({"type":"skills_list","scope":"project:a","limit":0}),
            ),
            req(
                "huge-model-limit",
                json!({"type":"models_list","limit":101}),
            ),
            req(
                "invalid-model-cursor",
                json!({"type":"models_list","after":u64::MAX}),
            ),
        ],
    );
    invalid
        .iter()
        .for_each(|response| error(response, "invalid_request"));
}

#[test]
fn duplicate_envelope_and_command_keys_are_rejected() {
    let root = TempDir::new().unwrap();
    let input = concat!(
        "{\"version\":1,\"version\":1,\"request_id\":\"dup1\",\"command\":{\"type\":\"health\"}}\n",
        "{\"version\":1,\"request_id\":\"dup2\",\"command\":{\"type\":\"health\",\"type\":\"health\"}}\n"
    );
    let output = raw(&root, input);
    assert_eq!(output.len(), 2);
    error(&output[0], "invalid_request");
    error(&output[1], "invalid_request");
}

#[test]
fn newer_storage_and_different_workspace_are_rejected_at_startup() {
    let root = TempDir::new().unwrap();
    let state = root.path().join("state");
    let other_workspace = root.path().join("other");
    std::fs::create_dir(&other_workspace).unwrap();
    ok(&run(&root, &[req("init", json!({"type":"health"}))])[0]);
    let binary = env!("CARGO_BIN_EXE_synapse-backend");
    let mismatch = Command::new(binary)
        .args([
            "--state-dir",
            state.to_str().unwrap(),
            "--workspace",
            other_workspace.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(!mismatch.status.success());
    assert!(String::from_utf8_lossy(&mismatch.stderr).contains("workspace_mismatch"));
    let db = rusqlite::Connection::open(state.join("core.sqlite3")).unwrap();
    let journal: String = db
        .pragma_query_value(None, "journal_mode", |row| row.get(0))
        .unwrap();
    let synchronous: i64 = db
        .pragma_query_value(None, "synchronous", |row| row.get(0))
        .unwrap();
    assert_eq!(journal.to_lowercase(), "wal");
    assert_eq!(synchronous, 2);
    db.pragma_update(None, "user_version", 5).unwrap();
    drop(db);
    let newer = Command::new(binary)
        .args([
            "--state-dir",
            state.to_str().unwrap(),
            "--workspace",
            root.path().to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(!newer.status.success());
    assert!(String::from_utf8_lossy(&newer.stderr).contains("unsupported_storage_version"));
}
