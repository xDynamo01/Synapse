use serde_json::{Value, json};
use std::{
    io::{BufRead, BufReader, Write},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    time::{Duration, Instant},
};
struct Session {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
    sequence: u32,
}
struct FixtureProcess(Child);
impl Drop for FixtureProcess {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
impl Session {
    fn new(dir: &tempfile::TempDir) -> Self {
        Self::with_python(dir, None)
    }
    fn with_python(dir: &tempfile::TempDir, python: Option<&str>) -> Self {
        let mut child = Command::new(env!("CARGO_BIN_EXE_synapse-backend"))
            .args([
                "--state-dir",
                dir.path().join("state").to_str().unwrap(),
                "--workspace",
                dir.path().to_str().unwrap(),
            ])
            .env(
                "SYNAPSE_PYTHON_EXECUTABLE",
                python
                    .map(std::path::PathBuf::from)
                    .unwrap_or_else(|| dir.path().join("absent-python.exe")),
            )
            .env_remove("SYNAPSE_MANAGE_LOCAL_MODELS")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let input = child.stdin.take().unwrap();
        let output = BufReader::new(child.stdout.take().unwrap());
        Self {
            child,
            input,
            output,
            sequence: 0,
        }
    }
    fn call(&mut self, command: Value) -> Value {
        self.sequence += 1;
        self.request(&format!("request-{}", self.sequence), command)
    }
    fn request(&mut self, id: &str, command: Value) -> Value {
        writeln!(
            self.input,
            "{}",
            json!({"version":1,"request_id":id,"command":command})
        )
        .unwrap();
        self.input.flush().unwrap();
        let mut line = String::new();
        self.output.read_line(&mut line).unwrap();
        assert!(!line.is_empty(), "CLI closed unexpectedly");
        serde_json::from_str(&line).unwrap()
    }
}

#[test]
#[cfg(windows)]
fn cli_mission_call_budget_stops_generation_before_reserving_model() {
    let python_output = Command::new("py")
        .args(["-3.14", "-c", "import sys; print(sys.executable)"])
        .output()
        .unwrap();
    assert!(python_output.status.success());
    let python = String::from_utf8(python_output.stdout)
        .unwrap()
        .trim()
        .to_owned();
    let fixture = tempfile::tempdir().unwrap();
    std::fs::write(
        fixture.path().join("mission-response"),
        json!({"summary":"Plan fixture","artifacts":[{"path":"test.py","purpose":"Test project"}],
        "checks":[{"kind":"python_unittest","entrypoint":"test.py"}]})
        .to_string(),
    )
    .unwrap();
    let script = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../python/tests/fixture_server.py");
    let mut provider = Command::new(&python)
        .arg("-u")
        .arg(script)
        .arg(fixture.path().join("post"))
        .arg(fixture.path().join("release"))
        .arg("normal")
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let mut provider = FixtureProcess(provider);
    let mut stdout = BufReader::new(provider.0.stdout.take().unwrap());
    let mut port = String::new();
    stdout.read_line(&mut port).unwrap();
    let dir = tempfile::tempdir().unwrap();
    let mut session = Session::with_python(&dir, Some(&python));
    let value=session.call(json!({"type":"model_register","model":{"id":"selected","provider":"lm_studio",
        "endpoint":format!("http://127.0.0.1:{}",port.trim()),"capabilities":["chat"],"memory_bytes":1}}));
    assert_eq!(value["ok"], true, "{value}");
    let value=session.request("plan",json!({"type":"mission_plan_start","mission_id":"mission","scope":"project:a","model_id":"selected",
        "objective":"Create a tiny tested project","review_model_id":"selected","review_generation":{"max_output_tokens":512,"timeout_ms":10000,"reasoning_effort":"none"}}));
    assert_eq!(value["ok"], true, "{value}");
    let end = Instant::now() + Duration::from_secs(10);
    loop {
        let value = session.call(json!({"type":"job_get","job_id":"plan"}));
        if value["result"]["status"] != "running" {
            assert_eq!(value["result"]["status"], "succeeded", "{value}");
            break;
        }
        assert!(Instant::now() < end);
        std::thread::sleep(Duration::from_millis(20));
    }
    let value=session.call(op("budget_set",json!({"mission_id":"mission","budget":{"elapsed_ms":1_800_000,"tokens":null,"inference_calls":1,"ram_bytes":null,"vram_bytes":null}})));
    assert_eq!(value["ok"], true, "{value}");
    let plan = session.call(json!({"type":"mission_plan_get","mission_id":"mission"}));
    let approved=session.call(json!({"type":"mission_approve","mission_id":"mission","contract_digest":plan["result"]["mission"]["contract_digest"]}));
    assert_eq!(approved["ok"], true, "{approved}");
    let result = session.call(json!({"type":"mission_execute","mission_id":"mission"}));
    assert_eq!(result["ok"], false, "{result}");
    assert_eq!(
        result["error"]["code"], "budget_calls_exhausted",
        "{result}"
    );
    let attempts = session.call(op("attempts", json!({"mission_id":"mission"})));
    assert_eq!(attempts["result"]["attempts"].as_array().unwrap().len(), 1);
}
impl Drop for Session {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
fn op(action: &str, payload: Value) -> Value {
    json!({"type":"operational","action":action,"payload":payload})
}
#[test]
fn cli_attempt_receipt_is_idempotent_private_and_survives_reopen() {
    let dir = tempfile::tempdir().unwrap();
    let mut session = Session::new(&dir);
    let registered = session.call(
        json!({"type":"model_register","model":{"id":"manual","provider":"lm_studio",
        "endpoint":"http://127.0.0.1:9","capabilities":["chat"],"memory_bytes":1}}),
    );
    assert_eq!(registered["ok"], true, "{registered}");
    let input = json!({"type":"inference","model_id":"manual","prompt":"CANARY-private-prompt"});
    let first = session.request("inference", input.clone());
    assert_eq!(first["ok"], true, "{first}");
    assert_eq!(session.request("inference", input), first);
    let end = Instant::now() + Duration::from_secs(10);
    loop {
        let value = session.call(json!({"type":"job_get","job_id":"inference"}));
        assert_eq!(value["ok"], true, "{value}");
        if value["result"]["status"] != "running" {
            break;
        }
        assert!(Instant::now() < end);
        std::thread::sleep(Duration::from_millis(20));
    }
    let value = session.call(op("attempts", json!({"job_id":"inference"})));
    assert_eq!(value["ok"], true, "{value}");
    let attempts = value["result"]["attempts"].as_array().unwrap();
    assert_eq!(attempts.len(), 1);
    assert_eq!(attempts[0]["status"], "finished");
    assert_eq!(attempts[0]["metrics"]["input_tokens"], Value::Null);
    assert_eq!(attempts[0]["metrics"]["vram_bytes"], Value::Null);
    assert!(!value.to_string().contains("CANARY"));
    let attempt_id = attempts[0]["attempt_id"].clone();
    drop(session);
    let mut reopened = Session::new(&dir);
    reopened.sequence = 1000;
    let value = reopened.call(op("attempts", json!({"job_id":"inference"})));
    assert_eq!(value["result"]["attempts"][0]["attempt_id"], attempt_id);
    let usage = reopened.call(op("budget_get", json!({"job_id":"inference"})));
    assert_eq!(usage["result"]["usage"]["attempts"], 1);
    assert_eq!(usage["result"]["usage"]["unknown_token_attempts"], 1);
}
#[test]
fn cli_rejects_unknown_mission_budget_and_exposes_exact_contract() {
    let dir = tempfile::tempdir().unwrap();
    let mut session = Session::new(&dir);
    let budget = json!({"elapsed_ms":1000,"tokens":null,"inference_calls":0,"ram_bytes":null,"vram_bytes":null});
    let value = session.call(op(
        "budget_set",
        json!({"mission_id":"missing","budget":budget}),
    ));
    assert_eq!(value["ok"], false);
    assert_eq!(value["error"]["code"], "not_found");
    let value = session.call(op("attempts", json!({"job_id":"missing"})));
    assert_eq!(value["ok"], false);
    assert_eq!(value["error"]["code"], "not_found");
}
