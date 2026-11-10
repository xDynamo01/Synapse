#![cfg(windows)]
use serde_json::{Value, json};
use std::{
    io::{BufRead, BufReader, Write},
    path::PathBuf,
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};
use tempfile::TempDir;
static TEST_LOCK: Mutex<()> = Mutex::new(());

fn python_exe() -> String {
    let output = Command::new("py")
        .args(["-3.14", "-c", "import sys; print(sys.executable)"])
        .output()
        .unwrap();
    assert!(output.status.success());
    String::from_utf8(output.stdout).unwrap().trim().to_owned()
}
fn req(id: &str, command: Value) -> Value {
    json!({"version":1,"request_id":id,"command":command})
}

struct Session {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
}
impl Session {
    fn new(root: &TempDir, python: Option<&str>) -> Self {
        let mut cmd = Command::new(env!("CARGO_BIN_EXE_synapse-backend"));
        cmd.args([
            "--state-dir",
            root.path().join("state").to_str().unwrap(),
            "--workspace",
            root.path().to_str().unwrap(),
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
        let executable = python.map(str::to_owned).unwrap_or_else(python_exe);
        cmd.env("SYNAPSE_PYTHON_EXECUTABLE", executable);
        let mut child = cmd.spawn().unwrap();
        let input = child.stdin.take().unwrap();
        let output = BufReader::new(child.stdout.take().unwrap());
        Self {
            child,
            input,
            output,
        }
    }
    fn call(&mut self, value: Value) -> Value {
        writeln!(self.input, "{value}").unwrap();
        self.input.flush().unwrap();
        let mut line = String::new();
        self.output.read_line(&mut line).unwrap();
        assert!(!line.is_empty());
        serde_json::from_str(&line).unwrap()
    }
}
impl Drop for Session {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

struct Fixture {
    address: String,
    marker: PathBuf,
    release_path: PathBuf,
    child: Child,
    _root: TempDir,
}
impl Fixture {
    fn new(hold: bool) -> Self {
        let root = TempDir::new().unwrap();
        let marker = root.path().join("post-seen");
        let release_path = root.path().join("release");
        let script =
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../python/tests/fixture_server.py");
        let mut child = Command::new(python_exe())
            .arg("-u")
            .arg(script)
            .arg(&marker)
            .arg(&release_path)
            .arg(if hold { "hold" } else { "normal" })
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let mut output = BufReader::new(child.stdout.take().unwrap());
        let mut line = String::new();
        output.read_line(&mut line).unwrap();
        let port: u16 = line.trim().parse().expect("fixture port");
        Self {
            address: format!("http://127.0.0.1:{port}"),
            marker,
            release_path,
            child,
            _root: root,
        }
    }
    fn release(&self) {
        std::fs::write(&self.release_path, b"go").unwrap();
    }
    fn wait_post(&self) {
        let start = Instant::now();
        while !self.marker.exists() {
            assert!(
                start.elapsed() < Duration::from_secs(8),
                "provider POST did not arrive"
            );
            thread::sleep(Duration::from_millis(20));
        }
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn register(session: &mut Session, endpoint: &str) {
    let result=session.call(req("model",json!({"type":"model_register","model":{"id":"selected","provider":"lm_studio","endpoint":endpoint,"capabilities":["chat"],"memory_bytes":1024}})));
    assert_eq!(result["ok"], true, "{result}");
}
fn poll(session: &mut Session, job: &str) -> Value {
    let started = Instant::now();
    let mut index = 0;
    loop {
        let result = session.call(req(
            &format!("poll-{job}-{index}"),
            json!({"type":"job_get","job_id":job}),
        ));
        assert_eq!(result["ok"], true, "{result}");
        if result["result"]["status"] != "running" {
            return result["result"].clone();
        }
        assert!(started.elapsed() < Duration::from_secs(18));
        index += 1;
        thread::sleep(Duration::from_millis(25));
    }
}

fn plan_command(id: &str) -> Value {
    json!({"type":"mission_plan_start","mission_id":id,"scope":"project:a","model_id":"selected","objective":"Build the owner requested project","review_model_id":"selected","review_generation":{"max_output_tokens":512,"timeout_ms":10000,"reasoning_effort":"none"}})
}
fn valid_plan() -> Value {
    json!({"summary":"Small tested project","artifacts":[{"path":"test_project.py","purpose":"Implement and test project"}],"checks":[{"kind":"python_unittest","entrypoint":"test_project.py"}]})
}
#[test]
fn structured_plan_proposes_without_effects_and_survives_restart() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(true);
    std::fs::write(
        fixture.marker.parent().unwrap().join("require-one-system"),
        b"required",
    )
    .unwrap();
    std::fs::write(
        fixture.marker.parent().unwrap().join("mission-response"),
        valid_plan().to_string(),
    )
    .unwrap();
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    let skill=session.call(req("skill",json!({"type":"skill_register","skill":{"id":"domain","version":"1","scope":"project:a","provenance":"owner","tools":[],"permissions":[],"instructions":"Only selected guidance"}})));
    assert_eq!(skill["ok"], true, "{skill}");
    session.call(req("memory",json!({"type":"memory_put","scope":"project:a","key":"fact","kind":"fact","content":"Only selected context","expected_revision":0,"provenance":{"source_type":"human","source_id":"owner","evidence":"direct"},"status":"active"})));
    let mut command = plan_command("mission-one");
    command["skill"] =
        json!({"scope":"project:a","id":"domain","version":"1","digest":skill["result"]["digest"]});
    command["context"] = json!([{"scope":"project:a","key":"fact"}]);
    let started = session.call(req("plan-one", command.clone()));
    assert_eq!(started["ok"], true, "{started}");
    assert_eq!(
        session.call(req("plan-one", command))["result"],
        started["result"]
    );
    fixture.wait_post();
    let sent: Value = serde_json::from_slice(&std::fs::read(&fixture.marker).unwrap()).unwrap();
    assert_eq!(
        sent["response_format"]["json_schema"]["name"],
        "mission_plan"
    );
    assert_eq!(sent["max_tokens"], 1024);
    let messages = sent["messages"].to_string();
    assert!(
        messages.contains("Only selected guidance") && messages.contains("Only selected context")
    );
    fixture.release();
    assert_eq!(poll(&mut session, "plan-one")["status"], "succeeded");
    assert_eq!(sent["messages"].as_array().unwrap().len(), 2);
    let proposed = session.call(req(
        "get-plan",
        json!({"type":"mission_plan_get","mission_id":"mission-one"}),
    ));
    assert_eq!(
        proposed["result"]["mission"]["state"], "proposed",
        "{proposed}"
    );
    let contract = &proposed["result"]["mission"]["contract"];
    assert_eq!(contract["objective"], "Build the owner requested project");
    assert_eq!(
        contract["execution"]["limits"],
        json!({"per_file_bytes":8192,"total_bytes":24576,"check_timeout_ms":30000,"preparation_timeout_ms":120000,"max_tool_asset_bytes":2147483648_u64,"job_memory_bytes":536870912,"owned_processes":8,"check_output_bytes":32768,"generation_attempts":1})
    );
    assert_eq!(contract["execution"]["primary_model"]["id"], "selected");
    assert!(!root.path().join("test_project.py").exists());
    assert_eq!(
        session.call(req(
            "learning",
            json!({"type":"learning_get","source_job_id":"plan-one"})
        ))["error"]["code"],
        "not_found"
    );
    drop(session);
    let mut session = Session::new(&root, None);
    let persisted = session.call(req(
        "get-after",
        json!({"type":"mission_plan_get","mission_id":"mission-one"}),
    ));
    assert_eq!(
        persisted["result"]["mission"],
        proposed["result"]["mission"]
    );
    assert_eq!(
        session.call(req("dup", plan_command("mission-one")))["error"]["code"],
        "already_exists"
    );
}

fn write_plan(fixture: &Fixture, value: &Value) {
    std::fs::write(
        fixture.marker.parent().unwrap().join("mission-response"),
        value.to_string(),
    )
    .unwrap();
}
fn assert_error(value: &Value, code: &str) {
    assert_eq!(value["ok"], false, "{value}");
    assert_eq!(value["error"]["code"], code, "{value}");
}
fn legacy_contract() -> Value {
    json!({"version":1,"scope":"project:a","objective":"Legacy mission","actions":["workspace_read"],"resources":["readme.txt"],"rollback":"manual removal"})
}
#[test]
fn invalid_full_results_never_partially_propose_or_leak_output() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(false);
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    let mut cases = vec![];
    for field in [
        "content",
        "executable",
        "argv",
        "environment",
        "grant",
        "approval",
        "swarm",
        "command",
        "extra",
    ] {
        let mut value = valid_plan();
        value[field] = json!("RAW_SECRET_REJECTED");
        cases.push(value);
    }
    for field in ["content", "approval", "command"] {
        let mut value = valid_plan();
        value["artifacts"][0][field] = json!("RAW_SECRET_REJECTED");
        cases.push(value);
        let mut value = valid_plan();
        value["checks"][0][field] = json!("RAW_SECRET_REJECTED");
        cases.push(value);
    }
    for path in [
        "../x.py",
        "dir/x.py",
        "dir\\x.py",
        "C:x.py",
        "CON.py",
        "CON .py",
        "😀.py",
        "con.file.py",
        "NUL.py",
        "COM1.py",
        "lpt9.py",
        "AUX.py",
        "PRN.py",
        "CLOCK$.py",
        "CONIN$.py",
        "CONOUT$.py",
        "file.py ",
        "file.py.",
        "file.exe",
        "café.py",
        "x?.py",
        "x<.py",
        "a..py",
        ".py",
        " x.py",
    ] {
        let mut value = valid_plan();
        value["artifacts"][0]["path"] = json!(path);
        value["checks"][0]["entrypoint"] = json!(path);
        cases.push(value);
    }
    let mut value = valid_plan();
    value["artifacts"]
        .as_array_mut()
        .unwrap()
        .push(json!({"path":"TEST_PROJECT.py","purpose":"Case collision"}));
    cases.push(value);
    for (kind, entrypoint) in [
        ("shell", "test_project.py"),
        ("rust_test", "test_project.py"),
        ("python_unittest", "other.py"),
    ] {
        let mut value = valid_plan();
        value["checks"][0] = json!({"kind":kind,"entrypoint":entrypoint});
        cases.push(value);
    }
    for field in ["summary", "artifacts", "checks"] {
        let mut value = valid_plan();
        value.as_object_mut().unwrap().remove(field);
        cases.push(value);
    }
    let mut value = valid_plan();
    value["summary"] = json!("é".repeat(1025));
    cases.push(value);
    let mut value = valid_plan();
    value["artifacts"][0]["purpose"] = json!("é".repeat(257));
    cases.push(value);
    let mut value = valid_plan();
    value["artifacts"] = json!([]);
    cases.push(value);
    let mut value = valid_plan();
    value["checks"] = json!([]);
    cases.push(value);
    let mut value = valid_plan();
    let check = value["checks"][0].clone();
    value["checks"].as_array_mut().unwrap().push(check);
    cases.push(value);
    // A valid first item plus an invalid later item must also roll the complete batch back.
    let mut value = valid_plan();
    value["artifacts"]
        .as_array_mut()
        .unwrap()
        .push(json!({"path":"bad.exe","purpose":"RAW_SECRET_REJECTED"}));
    cases.push(value);
    for field in ["summary", "purpose"] {
        for bad in ["", "   ", "\0"] {
            let mut value = valid_plan();
            if field == "summary" {
                value["summary"] = json!(bad);
            } else {
                value["artifacts"][0]["purpose"] = json!(bad);
            }
            cases.push(value);
        }
    }
    let mut value = valid_plan();
    value["artifacts"][0]["path"] = json!("x".repeat(127) + ".py");
    cases.push(value);
    let mut value = valid_plan();
    value["artifacts"] = json!(
        (0..17)
            .map(|i| json!({"path":format!("test_{i}.py"),"purpose":"test"}))
            .collect::<Vec<_>>()
    );
    cases.push(value);
    let mut value = valid_plan();
    value["checks"] = json!(vec![value["checks"][0].clone(); 9]);
    cases.push(value);
    cases.push(json!("RAW_SECRET_REJECTED"));
    for (index, plan) in cases.iter().enumerate() {
        write_plan(&fixture, plan);
        let id = format!("negative-{index}");
        let started = session.call(req(&id, plan_command(&id)));
        assert_eq!(started["ok"], true, "{started}");
        let job = poll(&mut session, &id);
        assert_eq!(job["status"], "failed", "case {index}: {plan} -> {job}");
        assert_eq!(job["error"], "invalid_mission_plan");
        assert!(job["content"].is_null());
        let got = session.call(req(
            &format!("get-{id}"),
            json!({"type":"mission_plan_get","mission_id":id}),
        ));
        assert!(got["result"].get("mission").is_none() && got["result"].get("plan").is_none());
        assert_error(
            &session.call(req(
                &format!("mission-{id}"),
                json!({"type":"mission_get","mission_id":id}),
            )),
            "not_found",
        );
    }
    for (index, raw) in [
        "not JSON RAW_SECRET_REJECTED",
        "{} trailing",
        "{\"summary\":\"duplicate\",\"summary\":\"duplicate\",\"artifacts\":[],\"checks\":[]}",
    ]
    .iter()
    .enumerate()
    {
        std::fs::write(
            fixture.marker.parent().unwrap().join("mission-response"),
            raw,
        )
        .unwrap();
        let id = format!("malformed-{index}");
        assert_eq!(session.call(req(&id, plan_command(&id)))["ok"], true);
        assert_eq!(poll(&mut session, &id)["error"], "invalid_mission_plan");
    }
    let mut cursor = 0;
    loop {
        let events = session.call(req(
            &format!("events-{cursor}"),
            json!({"type":"events_read","after":cursor,"limit":200}),
        ));
        let data = &events["result"];
        assert!(!data.to_string().contains("RAW_SECRET_REJECTED"));
        for event in data["events"].as_array().unwrap() {
            assert!(
                ![
                    "mission_proposed",
                    "mission_approved",
                    "tool_observation",
                    "memory_revision",
                    "learning_succeeded"
                ]
                .contains(&event["kind"].as_str().unwrap())
            );
        }
        if data["events"].as_array().unwrap().len() < 200 {
            break;
        }
        cursor = data["next_cursor"].as_u64().unwrap();
    }
    assert!(!root.path().join("test_project.py").exists());
}
#[test]
fn start_rejects_missing_models_foreign_pins_unsupported_provider_and_context_overflow() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(false);
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    for field in ["model_id", "review_model_id"] {
        let mut command = plan_command(field);
        command[field] = json!("missing");
        assert_error(&session.call(req(field, command)), "model_unavailable");
        assert_error(
            &session.call(req(
                &format!("job-{field}"),
                json!({"type":"job_get","job_id":field}),
            )),
            "not_found",
        );
    }
    let mut command = plan_command("same-generation");
    command["review_generation"] =
        json!({"max_output_tokens":1024,"timeout_ms":10000,"reasoning_effort":"provider_default"});
    assert_error(
        &session.call(req("same-generation", command)),
        "invalid_request",
    );
    for (id, provider, endpoint) in [
        ("unsupported", "other", fixture.address.as_str()),
        ("hostname", "lm_studio", "http://localhost:1234"),
        ("remote", "lm_studio", "http://192.168.1.1:1234"),
    ] {
        assert_eq!(session.call(req(&format!("register-{id}"),json!({"type":"model_register","model":{"id":id,"provider":provider,"endpoint":endpoint,"capabilities":["chat"],"memory_bytes":1}})))["ok"],true);
        let mut command = plan_command(id);
        command["model_id"] = json!(id);
        assert_error(
            &session.call(req(id, command)),
            if id == "unsupported" {
                "model_unavailable"
            } else {
                "invalid_endpoint"
            },
        );
    }
    let mut command = plan_command("foreign-skill");
    command["skill"] =
        json!({"scope":"project:b","id":"skill","version":"1","digest":"0".repeat(64)});
    assert_error(
        &session.call(req("foreign-skill", command)),
        "contract_conflict",
    );
    let large=session.call(req("large",json!({"type":"skill_register","skill":{"id":"large","version":"1","scope":"project:a","provenance":"owner","tools":[],"permissions":[],"instructions":"x".repeat(32768)}})));
    assert_eq!(large["ok"], true);
    let mut command = plan_command("large-pin");
    command["skill"] =
        json!({"scope":"project:a","id":"large","version":"1","digest":large["result"]["digest"]});
    assert_error(&session.call(req("large-pin", command)), "invalid_request");
    for key in ["one", "two"] {
        assert_eq!(session.call(req(&format!("memory-{key}"),json!({"type":"memory_put","scope":"project:a","key":key,"kind":"fact","content":"x".repeat(24000),"expected_revision":0,"provenance":{"source_type":"human","source_id":"owner","evidence":"direct"},"status":"active"})))["ok"],true);
    }
    let mut command = plan_command("overflow");
    command["context"] =
        json!([{"scope":"project:a","key":"one"},{"scope":"project:a","key":"two"}]);
    assert_error(&session.call(req("overflow", command)), "invalid_request");
    assert_error(
        &session.call(req(
            "overflow-job",
            json!({"type":"job_get","job_id":"overflow"}),
        )),
        "not_found",
    );
    let mut command = plan_command("unknown-start");
    command["approval"] = json!(true);
    assert_error(
        &session.call(req("unknown-start", command)),
        "invalid_request",
    );
    assert!(!fixture.marker.exists());
}
#[test]
fn reserved_source_and_execution_policy_cannot_be_forged_or_rebound() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(true);
    write_plan(&fixture, &valid_plan());
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    assert_eq!(
        session.call(req("source", plan_command("source-mission")))["ok"],
        true
    );
    fixture.wait_post();
    assert_error(&session.call(req("hijack",json!({"type":"mission_propose","mission_id":"source-mission","contract":legacy_contract()}))),"contract_conflict");
    let mut forged = legacy_contract();
    forged["execution"] = json!({"plan_id":"not-sealed"});
    assert_error(
        &session.call(req(
            "forged",
            json!({"type":"mission_propose","mission_id":"forged","contract":forged}),
        )),
        "invalid_request",
    );
    fixture.release();
    assert_eq!(poll(&mut session, "source")["status"], "succeeded");
    let proposal = session.call(req(
        "source-get",
        json!({"type":"mission_get","mission_id":"source-mission"}),
    ));
    let contract = proposal["result"]["contract"].clone();
    assert_error(
        &session.call(req(
            "rebound",
            json!({"type":"mission_propose","mission_id":"other","contract":contract}),
        )),
        "contract_conflict",
    );
    for field in ["objective", "scope", "rollback"] {
        let mut changed = contract.clone();
        changed[field] = json!("project:forged");
        assert_error(
            &session.call(req(
                &format!("changed-{field}"),
                json!({"type":"mission_propose","mission_id":"source-mission","contract":changed}),
            )),
            "contract_conflict",
        );
    }
    let mut changed = contract.clone();
    changed["execution"]["limits"]["per_file_bytes"] = json!(8193);
    assert_error(
        &session.call(req(
            "changed-limit",
            json!({"type":"mission_propose","mission_id":"source-mission","contract":changed}),
        )),
        "contract_conflict",
    );
    assert_error(
        &session.call(req(
            "same-source",
            json!({"type":"mission_propose","mission_id":"source-mission","contract":contract}),
        )),
        "already_exists",
    );
    assert_eq!(session.call(req("approve-fixture",json!({"type":"mission_approve","mission_id":"source-mission","contract_digest":proposal["result"]["contract_digest"]})))["ok"],true);
    for operation in [
        json!({"type":"read","path":"test_project.py"}),
        json!({"type":"create","path":"test_project.py","content":"disallowed"}),
    ] {
        let id = format!("tool-{}", operation["type"]);
        assert_error(
            &session.call(req(
                &id,
                json!({"type":"tool_execute","mission_id":"source-mission","operation":operation}),
            )),
            "capability_unavailable",
        );
    }
    assert!(!root.path().join("test_project.py").exists());
}
#[test]
fn cancellation_restart_timeout_and_late_results_do_not_propose() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    for mode in ["cancel", "restart", "timeout"] {
        let root = TempDir::new().unwrap();
        let fixture = Fixture::new(true);
        write_plan(&fixture, &valid_plan());
        let mut session = Session::new(&root, None);
        let mut model = json!({"id":"selected","provider":"lm_studio","endpoint":fixture.address,"capabilities":["chat"],"memory_bytes":1024});
        if mode == "timeout" {
            model["generation"] =
                json!({"max_output_tokens":123,"timeout_ms":250,"reasoning_effort":"none"});
        }
        assert_eq!(
            session.call(req(
                "register",
                json!({"type":"model_register","model":model})
            ))["ok"],
            true
        );
        assert_eq!(
            session.call(req("work", plan_command("mission")))["ok"],
            true
        );
        fixture.wait_post();
        assert_error(
            &session.call(req("busy", plan_command("another"))),
            "worker_busy",
        );
        assert_error(
            &session.call(req(
                "busy-inference",
                json!({"type":"inference","model_id":"selected","prompt":"busy"}),
            )),
            "worker_busy",
        );
        if mode == "cancel" {
            assert_eq!(
                session.call(req("cancel", json!({"type":"job_cancel","job_id":"work"})))["result"]
                    ["status"],
                "cancelled"
            );
            fixture.release();
            thread::sleep(Duration::from_millis(100));
            assert_eq!(poll(&mut session, "work")["status"], "cancelled");
        } else if mode == "restart" {
            drop(session);
            session = Session::new(&root, None);
            fixture.release();
            assert_eq!(poll(&mut session, "work")["status"], "interrupted");
        } else {
            let job = poll(&mut session, "work");
            assert_eq!(job["status"], "failed");
            assert_eq!(job["error"], "provider_timeout");
            fixture.release();
        }
        let plan = session.call(req(
            "get-plan",
            json!({"type":"mission_plan_get","mission_id":"mission"}),
        ));
        assert!(plan["result"].get("mission").is_none());
        assert_error(
            &session.call(req(
                "mission",
                json!({"type":"mission_get","mission_id":"mission"}),
            )),
            "not_found",
        );
        assert_error(
            &session.call(req("retry", plan_command("mission"))),
            "already_exists",
        );
    }
}
#[test]
fn legacy_contract_and_request_digests_remain_exactly_compatible() {
    use sha2::{Digest, Sha256};
    use synapse_core::contracts::{MissionContract, Request};
    fn hash<T: serde::Serialize>(value: &T) -> String {
        Sha256::digest(serde_json::to_vec(value).unwrap())
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect()
    }
    let root = TempDir::new().unwrap();
    let mut session = Session::new(&root, None);
    let contract = legacy_contract();
    let parsed: MissionContract = serde_json::from_value(contract.clone()).unwrap();
    assert!(parsed.execution.is_none());
    assert_eq!(serde_json::to_value(&parsed).unwrap(), contract);
    let original_contract = r#"{"version":1,"scope":"project:a","objective":"Legacy mission","actions":["workspace_read"],"resources":["readme.txt"],"rollback":"manual removal"}"#;
    assert_eq!(serde_json::to_string(&parsed).unwrap(), original_contract);
    let request = req(
        "legacy",
        json!({"type":"mission_propose","mission_id":"legacy","contract":contract}),
    );
    let typed: Request = serde_json::from_value(request.clone()).unwrap();
    let original_request = format!(
        "{{\"version\":1,\"request_id\":\"legacy\",\"command\":{{\"type\":\"mission_propose\",\"mission_id\":\"legacy\",\"contract\":{original_contract}}}}}"
    );
    assert_eq!(serde_json::to_string(&typed).unwrap(), original_request);
    let proposal = session.call(request);
    assert_eq!(proposal["ok"], true);
    assert_eq!(proposal["result"]["contract_digest"], hash(&parsed));
    assert!(proposal["result"]["contract"].get("execution").is_none());
}

#[test]
fn foreground_planning_preempts_learning_and_excludes_chat_history() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(false);
    write_plan(&fixture, &valid_plan());
    let hold = fixture.marker.parent().unwrap().join("learning-hold");
    std::fs::write(&hold, b"hold").unwrap();
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    assert_eq!(
        session.call(req(
            "chat",
            json!({"type":"chat_create","chat_id":"chat","title":"chat","scope":"project:a"})
        ))["ok"],
        true
    );
    assert_eq!(session.call(req("turn",json!({"type":"conversation_start","chat_id":"chat","model_id":"selected","content":"PRIVATE_CHAT_CONTENT"})))["ok"],true);
    assert_eq!(poll(&mut session, "turn")["status"], "succeeded");
    let start = Instant::now();
    let learning = fixture.marker.parent().unwrap().join("learning-post");
    while !learning.exists() {
        assert!(start.elapsed() < Duration::from_secs(8));
        thread::sleep(Duration::from_millis(20));
    }
    assert_eq!(
        session.call(req("plan", plan_command("mission")))["ok"],
        true
    );
    assert_eq!(poll(&mut session, "plan")["status"], "succeeded");
    let sent: Value = serde_json::from_slice(&std::fs::read(&fixture.marker).unwrap()).unwrap();
    assert_eq!(
        sent["response_format"]["json_schema"]["name"],
        "mission_plan"
    );
    assert_eq!(sent["messages"].as_array().unwrap().len(), 2);
    assert!(
        !sent["messages"]
            .to_string()
            .contains("PRIVATE_CHAT_CONTENT")
    );
    std::fs::remove_file(hold).unwrap();
}
#[test]
fn complete_model_manifests_and_explicit_review_generation_are_pinned_without_budget_increase() {
    use sha2::{Digest, Sha256};
    use synapse_core::contracts::ModelManifest;
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(false);
    write_plan(&fixture, &valid_plan());
    let mut session = Session::new(&root, None);
    let primary = json!({"id":"selected","provider":"lm_studio","endpoint":fixture.address,"capabilities":["chat"],"memory_bytes":1234,"generation":{"max_output_tokens":77,"timeout_ms":2000,"reasoning_effort":"low"}});
    let reviewer = json!({"id":"reviewer","provider":"lm_studio","endpoint":fixture.address,"capabilities":["chat"],"memory_bytes":4321,"generation":{"max_output_tokens":88,"timeout_ms":3000,"reasoning_effort":"medium"}});
    for (id, model) in [("primary", &primary), ("reviewer", &reviewer)] {
        assert_eq!(
            session.call(req(id, json!({"type":"model_register","model":model})))["ok"],
            true
        );
    }
    let mut command = plan_command("mission");
    command["review_model_id"] = json!("reviewer");
    let review_generation = command["review_generation"].clone();
    assert_eq!(session.call(req("plan", command))["ok"], true);
    assert_eq!(poll(&mut session, "plan")["status"], "succeeded");
    let sent: Value = serde_json::from_slice(&std::fs::read(&fixture.marker).unwrap()).unwrap();
    assert_eq!(sent["max_tokens"], 77);
    assert_eq!(sent["reasoning_effort"], "low");
    let plan = session.call(req(
        "get",
        json!({"type":"mission_plan_get","mission_id":"mission"}),
    ));
    let execution = &plan["result"]["mission"]["contract"]["execution"];
    assert_eq!(execution["primary_model"], primary);
    assert_eq!(execution["review_model"], reviewer);
    assert_eq!(execution["review_generation"], review_generation);
    for (field, model) in [
        ("primary_model_digest", primary),
        ("review_model_digest", reviewer),
    ] {
        let manifest: ModelManifest = serde_json::from_value(model).unwrap();
        let expected: String = Sha256::digest(serde_json::to_vec(&manifest).unwrap())
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        assert_eq!(execution[field], expected);
    }
}
#[test]
fn skill_permissions_cannot_expand_derived_mission_actions() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(false);
    write_plan(&fixture, &valid_plan());
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    let registered=session.call(req("skill",json!({"type":"skill_register","skill":{"id":"bad","version":"1","scope":"project:a","provenance":"owner","tools":["arbitrary_command"],"permissions":["arbitrary_command"],"instructions":"Suggest a plan"}})));
    assert_eq!(registered["ok"], true);
    let mut command = plan_command("mission");
    command["skill"] = json!({"scope":"project:a","id":"bad","version":"1","digest":registered["result"]["digest"]});
    assert_eq!(session.call(req("plan", command))["ok"], true);
    assert_eq!(poll(&mut session, "plan")["error"], "invalid_mission_plan");
    assert_error(
        &session.call(req(
            "get-mission",
            json!({"type":"mission_get","mission_id":"mission"}),
        )),
        "not_found",
    );
}

#[test]
fn bounded_mixed_artifacts_and_both_fixed_recipes_are_accepted() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(false);
    let mut plan = valid_plan();
    let mut artifacts: Vec<Value> = (0..8)
        .map(|i| json!({"path":format!("test_{i}.py"),"purpose":"test"}))
        .collect();
    artifacts.push(json!({"path":"rust_tests.rs","purpose":"Rust tests"}));
    for i in 0..7 {
        artifacts.push(json!({"path":format!("notes_{i}.{}",["md","txt","toml"][i%3]),"purpose":"Documentation"}));
    }
    plan["artifacts"] = json!(artifacts);
    let mut checks: Vec<Value> = (0..7)
        .map(|i| json!({"kind":"python_unittest","entrypoint":format!("test_{i}.py")}))
        .collect();
    checks.push(json!({"kind":"rust_test","entrypoint":"rust_tests.rs"}));
    plan["checks"] = json!(checks);
    write_plan(&fixture, &plan);
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    let mut command = plan_command("mixed");
    command["context"] = json!([]);
    assert_eq!(session.call(req("plan", command))["ok"], true);
    assert_eq!(poll(&mut session, "plan")["status"], "succeeded");
    let proposal = session.call(req(
        "get",
        json!({"type":"mission_plan_get","mission_id":"mixed"}),
    ));
    assert_eq!(proposal["result"]["plan"], plan);
    assert_eq!(
        proposal["result"]["mission"]["contract"]["resources"]
            .as_array()
            .unwrap()
            .len(),
        16
    );
}

#[test]
fn merged_system_overflow_is_atomic_for_planner_and_conversation() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(false);
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    assert_eq!(
        session.call(req(
            "chat",
            json!({"type":"chat_create","chat_id":"chat","title":"chat","scope":"project:a"})
        ))["ok"],
        true
    );
    let skill=session.call(req("skill",json!({"type":"skill_register","skill":{"id":"guide","version":"1","scope":"project:a","provenance":"owner","tools":[],"permissions":[],"instructions":"S".repeat(17000)}})));
    assert_eq!(skill["ok"], true);
    assert_eq!(session.call(req("context",json!({"type":"memory_put","scope":"project:a","key":"selected","kind":"fact","content":"C".repeat(17000),"expected_revision":0,"provenance":{"source_type":"human","source_id":"owner","evidence":"direct"},"status":"active"})))["ok"],true);
    let pin =
        json!({"scope":"project:a","id":"guide","version":"1","digest":skill["result"]["digest"]});
    let context = json!([{"scope":"project:a","key":"selected"}]);
    for (id, mut command) in [
        ("plan-overflow", plan_command("mission")),
        (
            "conversation-overflow",
            json!({"type":"conversation_start","chat_id":"chat","model_id":"selected","content":"original human"}),
        ),
    ] {
        command["skill"] = pin.clone();
        command["context"] = context.clone();
        let before =
            session.call(req(&format!("before-{id}"), json!({"type":"health"})))["event_cursor"]
                .clone();
        let rejected = session.call(req(id, command));
        assert_error(&rejected, "invalid_request");
        assert_eq!(rejected["event_cursor"], before);
        assert_error(
            &session.call(req(
                &format!("job-{id}"),
                json!({"type":"job_get","job_id":id}),
            )),
            "not_found",
        );
    }
    let chat = session.call(req(
        "chat-after",
        json!({"type":"chat_get","chat_id":"chat"}),
    ));
    assert!(chat["result"]["messages"].as_array().unwrap().is_empty());
    assert_error(
        &session.call(req(
            "plan-after",
            json!({"type":"mission_plan_get","mission_id":"mission"}),
        )),
        "not_found",
    );
    assert!(!fixture.marker.exists());
}
