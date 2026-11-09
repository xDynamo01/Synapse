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
    error(&out[3], "capability_unavailable");
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
    db.pragma_update(None, "user_version", 2).unwrap();
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
