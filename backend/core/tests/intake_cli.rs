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
            child,
            _root: root,
        }
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn wait_job(session: &mut Session, job: &str) -> Value {
    let until = Instant::now() + Duration::from_secs(15);
    let mut index = 0;
    loop {
        index += 1;
        let reply = session.call(req(
            &format!("poll-{job}-{index}"),
            json!({"type":"job_get","job_id":job}),
        ));
        assert_eq!(reply["ok"], true, "{reply}");
        if reply["result"]["status"] != "running" {
            return reply["result"].clone();
        }
        assert!(Instant::now() < until, "{reply}");
        thread::sleep(Duration::from_millis(20));
    }
}

#[test]
fn unified_input_preserves_manual_model_context_and_mission_continuity() {
    let _guard = TEST_LOCK.lock().unwrap();
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(false);
    let mut session = Session::new(&root, None);
    let setup = [
        json!({"type":"model_register","model":{"id":"selected","provider":"lm_studio",
            "endpoint":fixture.address,"capabilities":["chat"],"memory_bytes":1000}}),
        json!({"type":"chat_create","chat_id":"chat","title":"Unified intake","scope":"project:chat"}),
        json!({"type":"memory_put","scope":"project:reference","key":"constraint","kind":"constraint",
            "content":"Use only the standard library.","expected_revision":0,"provenance":{
            "source_type":"human","source_id":"decision","evidence":"Explicit request"},"status":"active"}),
    ];
    for (n, command) in setup.into_iter().enumerate() {
        let value = session.call(req(&format!("setup-{n}"), command));
        assert_eq!(value["ok"], true, "{value}");
    }
    let truncation = fixture.marker.parent().unwrap().join("truncate-response");
    std::fs::write(&truncation, b"").unwrap();
    let limited=session.call(req("limited",json!({"type":"input_submit","input":{
        "chat_id":"chat","content":"A truncated response must fail safely.","model_id":"selected"}})));
    assert_eq!(limited["ok"], true, "{limited}");
    let failed = wait_job(&mut session, "limited");
    assert_eq!(failed["status"], "failed");
    assert_eq!(failed["error"], "provider_output_limit", "{failed}");
    std::fs::remove_file(&truncation).unwrap();
    let hello = req(
        "hello",
        json!({"type":"input_submit","input":{
        "chat_id":"chat","content":"oi","model_id":"selected"}}),
    );
    let first = session.call(hello.clone());
    assert_eq!(first["ok"], true, "{first}");
    assert_eq!(first["result"]["route"], "conversation");
    assert_eq!(first["result"]["model_id"], "selected");
    assert_eq!(wait_job(&mut session, "hello")["status"], "succeeded");
    assert_eq!(session.call(hello), first);
    let posted: Value = serde_json::from_slice(&std::fs::read(&fixture.marker).unwrap()).unwrap();
    assert!(
        !posted
            .to_string()
            .contains("Use only the standard library.")
    );
    let question = session.call(req(
        "question",
        json!({"type":"input_submit","input":{
        "chat_id":"chat","content":"como implementar um projeto?","model_id":"selected"}}),
    ));
    assert_eq!(question["result"]["route"], "conversation", "{question}");
    assert_eq!(wait_job(&mut session, "question")["status"], "succeeded");
    let translation = session.call(req(
        "translate",
        json!({"type":"input_submit","input":{
        "chat_id":"chat","content":"traduza hello para português","model_id":"selected",
        "model_memory_budget_bytes":1}}),
    ));
    assert_eq!(translation["ok"], true, "{translation}");
    assert_eq!(translation["result"]["route"], "specialized");
    assert_eq!(translation["result"]["capability"], "translation");
    assert_eq!(wait_job(&mut session, "translate")["status"], "succeeded");

    let missing = session.call(req(
        "needs-project",
        json!({"type":"input_submit","input":{
        "chat_id":"chat","content":"crie um arquivo de testes","model_id":"selected"}}),
    ));
    assert_eq!(missing["ok"], true, "{missing}");
    assert_eq!(missing["result"]["status"], "needs_workspace");
    assert!(missing["result"]["job_id"].is_null());
    let invalid = session.call(req(
        "foreign",
        json!({"type":"input_submit","input":{
        "chat_id":"chat","content":"agora deixe mais seguro","model_id":"selected",
        "continuation_id":"another-chat-input"}}),
    ));
    assert_eq!(invalid["error"]["code"], "permission_denied");
    let project = root.path().join("project");
    std::fs::create_dir(&project).unwrap();
    let registered = session.call(req(
        "project",
        json!({"type":"project_register","scope":"project:work","root":project}),
    ));
    assert_eq!(registered["ok"], true, "{registered}");
    std::fs::write(fixture.marker.parent().unwrap().join("mission-response"),
        r#"{"summary":"Create a tested file","artifacts":[{"path":"test_value.py","purpose":"Test arithmetic"}],"checks":[{"kind":"python_unittest","entrypoint":"test_value.py"}]}"#).unwrap();
    let mission=session.call(req("task",json!({"type":"input_submit","input":{
        "chat_id":"chat","intent":"mission","scope":"project:work","content":"Create a tested Python file.",
        "model_id":"selected","review_model_id":"selected",
        "context":[{"scope":"project:reference","key":"constraint"}]}})));
    assert_eq!(mission["ok"], true, "{mission}");
    assert_eq!(mission["result"]["route"], "mission");
    assert_eq!(wait_job(&mut session, "task")["status"], "succeeded");
    let plan = session.call(req(
        "get-task",
        json!({"type":"input_control","action":"get","payload":{"input_id":"task"}}),
    ));
    assert_eq!(plan["result"]["mission"]["state"], "proposed", "{plan}");
    let sealed = &plan["result"]["mission"]["contract"]["execution"]["context_handoff"];
    assert_eq!(sealed["data"]["context_pins"][0]["key"], "constraint");
    assert!(
        sealed["data"]["history"]
            .as_array()
            .unwrap()
            .iter()
            .any(|message| message["role"] == "assistant")
    );
    let planned: Value = serde_json::from_slice(&std::fs::read(&fixture.marker).unwrap()).unwrap();
    assert!(
        planned["messages"]
            .to_string()
            .contains("Recent conversation for continuity")
    );
    assert!(std::fs::read_dir(&project).unwrap().next().is_none());
    let continuation=session.call(req("follow",json!({"type":"input_submit","input":{
        "chat_id":"chat","content":"agora deixe mais seguro","model_id":"selected","review_model_id":"selected"}})));
    assert_eq!(continuation["ok"], true, "{continuation}");
    assert_eq!(continuation["result"]["route"], "mission");
    assert_eq!(continuation["result"]["parent_input_id"], "task");
    assert_eq!(continuation["result"]["context"][0]["key"], "constraint");
    assert_eq!(wait_job(&mut session, "follow")["status"], "succeeded");
    let followed: Value = serde_json::from_slice(&std::fs::read(&fixture.marker).unwrap()).unwrap();
    assert!(followed["messages"].to_string().contains("prior_mission"));
    for (id, content, expected) in [
        ("after-task-hello", "olá", "conversation"),
        (
            "after-task-translation",
            "traduza hello para português",
            "specialized",
        ),
    ] {
        let reply=session.call(req(id,json!({"type":"input_submit","input":{
            "chat_id":"chat","content":content,"model_id":"selected","mission_id":mission["result"]["mission_id"]}})));
        assert_eq!(reply["result"]["route"], expected, "{reply}");
        assert!(reply["result"]["mission_id"].is_null());
        assert_eq!(wait_job(&mut session, id)["status"], "succeeded");
    }
    let long = "Architecture start ".to_owned() + &"z".repeat(16000) + " Architecture end";
    let appended=session.call(req("long-reply",json!({"type":"message_append","chat_id":"chat","message_id":"long-design","role":"assistant","content":long})));
    assert_eq!(appended["ok"], true, "{appended}");
    let bounded=session.call(req("bounded-follow",json!({"type":"input_submit","input":{
        "chat_id":"chat","content":"agora implemente isso","model_id":"selected","review_model_id":"selected","continuation_id":"follow"}})));
    assert_eq!(bounded["ok"], true, "{bounded}");
    assert_eq!(bounded["result"]["history_truncated"], true);
    assert_eq!(
        wait_job(&mut session, "bounded-follow")["status"],
        "succeeded"
    );
    let bounded_plan = session.call(req(
        "bounded-get",
        json!({"type":"mission_plan_get","mission_id":bounded["result"]["mission_id"]}),
    ));
    let latest = &bounded_plan["result"]["mission"]["contract"]["execution"]["context_handoff"]["data"]
        ["history"][0];
    assert_eq!(latest["truncated"], true, "{latest}");
    assert!(
        latest["content_head"]
            .as_str()
            .unwrap()
            .starts_with("Architecture start")
    );
    assert!(
        latest["content_tail"]
            .as_str()
            .unwrap()
            .ends_with("Architecture end")
    );
    let settings = session.call(req(
        "settings",
        json!({"type":"orchestration","action":"settings_get","payload":{}}),
    ));
    assert_eq!(settings["result"]["execution_regime"], "NORMAL");
    let events = session.call(req(
        "events",
        json!({"type":"events_read","after":0,"limit":100}),
    ));
    assert!(
        events["result"]["events"]
            .as_array()
            .unwrap()
            .iter()
            .any(|e| e["kind"] == "input_routed")
    );
    assert!(
        !events["result"]["events"]
            .as_array()
            .unwrap()
            .iter()
            .any(|e| e["kind"] == "swarm_consent_recorded")
    );
}
