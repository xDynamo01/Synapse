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

#[test]
fn generation_is_validated_pinned_sent_and_persisted() {
    let _guard = TEST_LOCK.lock().unwrap();
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(true);
    let mut session = Session::new(&root, None);
    let generation = json!({"max_output_tokens":32,"timeout_ms":120000,"reasoning_effort":"none"});
    let model = json!({"id":"selected","provider":"lm_studio","endpoint":fixture.address,"capabilities":["chat"],"memory_bytes":1024,"generation":generation});
    for (i, bad) in [
        Value::Null,
        json!({"max_output_tokens":1,"timeout_ms":250}),
        json!({"max_output_tokens":"1","timeout_ms":250,"reasoning_effort":"none"}),
        json!({"max_output_tokens":1,"timeout_ms":true,"reasoning_effort":"none"}),
        json!({"max_output_tokens":true,"timeout_ms":250,"reasoning_effort":"none"}),
        json!({"max_output_tokens":0,"timeout_ms":250,"reasoning_effort":"none"}),
        json!({"max_output_tokens":4097,"timeout_ms":250,"reasoning_effort":"none"}),
        json!({"max_output_tokens":1,"timeout_ms":249,"reasoning_effort":"none"}),
        json!({"max_output_tokens":1,"timeout_ms":120001,"reasoning_effort":"none"}),
        json!({"max_output_tokens":1,"timeout_ms":250,"reasoning_effort":"invalid"}),
        json!({"max_output_tokens":1,"timeout_ms":250,"reasoning_effort":"none","extra":1}),
    ]
    .into_iter()
    .enumerate()
    {
        let mut candidate = model.clone();
        candidate["generation"] = bad;
        assert_eq!(
            session.call(req(
                &format!("bad-{i}"),
                json!({"type":"model_register","model":candidate})
            ))["ok"],
            false
        );
    }
    assert_eq!(
        session.call(req("reg", json!({"type":"model_register","model":model})))["ok"],
        true
    );
    assert_eq!(
        session.call(req(
            "start",
            json!({"type":"inference","model_id":"selected","prompt":"hi"})
        ))["ok"],
        true
    );
    fixture.wait_post();
    let body: Value = serde_json::from_slice(&std::fs::read(&fixture.marker).unwrap()).unwrap();
    assert_eq!(
        body,
        json!({"model":"selected","messages":[{"role":"user","content":"hi"}],"stream":false,"max_tokens":32,"reasoning_effort":"none"})
    );
    // Simulate a future registry update while this job is running; no public update API exists yet.
    let db = rusqlite::Connection::open(root.path().join("state/core.sqlite3")).unwrap();
    let mut changed = model.clone();
    changed["generation"]["max_output_tokens"] = json!(99);
    db.execute(
        "UPDATE models SET manifest=?1 WHERE id='selected'",
        [changed.to_string()],
    )
    .unwrap();
    assert_eq!(
        session.call(req("pinned", json!({"type":"job_get","job_id":"start"})))["result"]["generation"],
        generation
    );
    let before = Instant::now();
    assert_eq!(
        session.call(req(
            "cancel-long",
            json!({"type":"job_cancel","job_id":"start"})
        ))["result"]["status"],
        "cancelled"
    );
    assert!(before.elapsed() < Duration::from_secs(3));
    fixture.release();
    drop(session);
    let mut session = Session::new(&root, None);
    assert_eq!(
        session.call(req("read", json!({"type":"job_get","job_id":"start"})))["result"]["generation"],
        generation
    );
    assert_eq!(
        session.call(req(
            "model-read",
            json!({"type":"model_get","model_id":"selected"})
        ))["result"]["model"]["generation"]["max_output_tokens"],
        99
    );
}

#[test]
fn configured_short_deadline_is_honored() {
    let _guard = TEST_LOCK.lock().unwrap();
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(true);
    let mut session = Session::new(&root, None);
    let model = json!({"id":"selected","provider":"lm_studio","endpoint":fixture.address,"capabilities":["chat"],"memory_bytes":1,"generation":{"max_output_tokens":1,"timeout_ms":250,"reasoning_effort":"provider_default"}});
    assert_eq!(
        session.call(req("reg", json!({"type":"model_register","model":model})))["ok"],
        true
    );
    let start = Instant::now();
    session.call(req(
        "short",
        json!({"type":"inference","model_id":"selected","prompt":"hi"}),
    ));
    let job = poll(&mut session, "short");
    assert_eq!(job["error"], "provider_timeout", "{job}");
    assert!(start.elapsed() < Duration::from_secs(7));
}

#[test]
fn conversation_fixture_persists_once_and_replays_across_restart() {
    let _guard = TEST_LOCK.lock().unwrap();
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(false);
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    assert_eq!(
        session.call(req(
            "chat",
            json!({"type":"chat_create","chat_id":"one","title":"One","scope":"project:test"})
        ))["ok"],
        true
    );
    let start = req(
        "turn-1",
        json!({"type":"conversation_start","chat_id":"one","model_id":"selected","content":"Olá, ação?"}),
    );
    let first = session.call(start.clone());
    assert_eq!(first["ok"], true, "{first}");
    assert_eq!(first["result"]["status"], "running");
    let done = poll(&mut session, "turn-1");
    assert_eq!(done["status"], "succeeded", "{done}");
    assert_eq!(done["content"], "Olá, ação");
    let first_payload: Value =
        serde_json::from_slice(&std::fs::read(&fixture.marker).unwrap()).unwrap();
    assert_eq!(
        first_payload["messages"],
        json!([{"role":"user","content":"Olá, ação?"}])
    );
    let replay = session.call(start.clone());
    assert_eq!(first, replay);
    drop(session);
    let mut session = Session::new(&root, None);
    assert_eq!(session.call(start)["result"], first["result"]);
    assert_eq!(
        session.call(req(
            "other-chat",
            json!({"type":"chat_create","chat_id":"other","title":"Other","scope":"project:other"})
        ))["ok"],
        true
    );
    assert_eq!(session.call(req("other-msg",json!({"type":"message_append","chat_id":"other","message_id":"secret-other","role":"user","content":"other project secret"})))["ok"],true);
    assert_eq!(session.call(req("manual-assistant",json!({"type":"message_append","chat_id":"one","message_id":"manual-assistant","role":"assistant","content":"manual answer"})))["ok"],true);
    assert_eq!(session.call(req("manual-system",json!({"type":"message_append","chat_id":"one","message_id":"manual-system","role":"system","content":"system instruction"})))["ok"],true);
    let second=session.call(req("turn-2",json!({"type":"conversation_start","chat_id":"one","model_id":"selected","content":"E agora?"})));
    assert_eq!(second["ok"], true, "{second}");
    assert_eq!(poll(&mut session, "turn-2")["status"], "succeeded");
    let second_payload: Value =
        serde_json::from_slice(&std::fs::read(&fixture.marker).unwrap()).unwrap();
    assert_eq!(
        second_payload["messages"],
        json!([{"role":"user","content":"Olá, ação?"},{"role":"assistant","content":"Olá, ação"},{"role":"assistant","content":"manual answer"},{"role":"system","content":"system instruction"},{"role":"user","content":"E agora?"}])
    );
    assert!(!second_payload.to_string().contains("other project secret"));
    let chat = session.call(req("read", json!({"type":"chat_get","chat_id":"one"})));
    let messages = chat["result"]["messages"].as_array().unwrap();
    assert_eq!(messages.len(), 6, "{chat}");
    assert_eq!(messages[0]["role"], "user");
    assert_eq!(messages[1]["role"], "assistant");
    assert_eq!(messages[0]["content"], "Olá, ação?");
    assert_eq!(messages[1]["content"], "Olá, ação");
    assert_eq!(messages[2]["content"], "manual answer");
    assert_eq!(messages[3]["content"], "system instruction");
    assert_eq!(messages[4]["content"], "E agora?");
    assert_eq!(messages[5]["content"], "Olá, ação");
}

#[test]
fn oversized_conversation_is_rejected_without_appending_new_user() {
    let _guard = TEST_LOCK.lock().unwrap();
    let root = TempDir::new().unwrap();
    let mut session = Session::new(&root, None);
    register(&mut session, "http://127.0.0.1:65534");
    assert_eq!(
        session.call(req(
            "chat",
            json!({"type":"chat_create","chat_id":"one","title":"One","scope":"project:test"})
        ))["ok"],
        true
    );
    for n in 0..2 {
        let message=session.call(req(&format!("old-{n}"),json!({"type":"message_append","chat_id":"one","message_id":format!("old-{n}"),"role":"user","content":"a".repeat(30_000)})));
        assert_eq!(message["ok"], true, "{message}");
    }
    let rejected=session.call(req("too-much",json!({"type":"conversation_start","chat_id":"one","model_id":"selected","content":"new message"})));
    assert_eq!(rejected["error"]["code"], "invalid_request", "{rejected}");
    let chat = session.call(req("read", json!({"type":"chat_get","chat_id":"one"})));
    assert_eq!(chat["result"]["messages"].as_array().unwrap().len(), 2);
    assert_eq!(
        chat["result"]["messages"][1]["content"]
            .as_str()
            .unwrap()
            .len(),
        30_000
    );
}

#[test]
fn cancellation_is_durable_and_late_answer_is_suppressed() {
    let _guard = TEST_LOCK.lock().unwrap();
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(true);
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    session.call(req(
        "chat",
        json!({"type":"chat_create","chat_id":"one","title":"One","scope":"project:test"}),
    ));
    assert_eq!(session.call(req("turn",json!({"type":"conversation_start","chat_id":"one","model_id":"selected","content":"secret"})))["ok"],true);
    thread::sleep(Duration::from_millis(800));
    let status = session.call(req("prekill", json!({"type":"job_get","job_id":"turn"})));
    assert_eq!(status["result"]["status"], "running", "{status}");
    fixture.wait_post();
    let cancel = session.call(req("cancel", json!({"type":"job_cancel","job_id":"turn"})));
    assert_eq!(cancel["result"]["status"], "cancelled", "{cancel}");
    fixture.release();
    thread::sleep(Duration::from_millis(150));
    drop(session);
    let mut session = Session::new(&root, None);
    assert_eq!(
        session.call(req("read-job", json!({"type":"job_get","job_id":"turn"})))["result"]["status"],
        "cancelled"
    );
    let chat = session.call(req("read-chat", json!({"type":"chat_get","chat_id":"one"})));
    assert_eq!(
        chat["result"]["messages"].as_array().unwrap().len(),
        1,
        "{chat}"
    );
}

#[test]
fn missing_model_and_worker_crash_are_explicit() {
    let _guard = TEST_LOCK.lock().unwrap();
    let root = TempDir::new().unwrap();
    let mut session = Session::new(&root, None);
    let absent = session.call(req(
        "absent",
        json!({"type":"inference","model_id":"none","prompt":"hello"}),
    ));
    assert_eq!(absent["error"]["code"], "model_unavailable");
    drop(session);
    let mut session = Session::new(&root, Some("C:\\missing\\python.exe"));
    register(&mut session, "http://127.0.0.1:65534");
    let unavailable = session.call(req(
        "no-runtime",
        json!({"type":"inference","model_id":"selected","prompt":"hello"}),
    ));
    assert_eq!(unavailable["ok"], true);
    let failed = poll(&mut session, "no-runtime");
    assert_eq!(failed["error"], "worker_unavailable", "{failed}");
    drop(session);
    let mut session = Session::new(&root, Some("C:\\Windows\\System32\\cmd.exe"));
    let started = session.call(req(
        "crash",
        json!({"type":"inference","model_id":"selected","prompt":"hello"}),
    ));
    assert_eq!(started["ok"], true);
    let failed = poll(&mut session, "crash");
    assert_eq!(failed["status"], "failed");
    assert!(
        failed["error"] == "worker_protocol" || failed["error"] == "worker_unavailable",
        "{failed}"
    );
}

#[test]
fn restart_interrupts_running_job_without_duplicating_user_message() {
    let _guard = TEST_LOCK.lock().unwrap();
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(true);
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    session.call(req(
        "chat",
        json!({"type":"chat_create","chat_id":"one","title":"One","scope":"project:test"}),
    ));
    let started=session.call(req("turn",json!({"type":"conversation_start","chat_id":"one","model_id":"selected","content":"secret"})));
    assert_eq!(started["ok"], true, "{started}");
    thread::sleep(Duration::from_millis(800));
    let status = session.call(req("prekill", json!({"type":"job_get","job_id":"turn"})));
    assert_eq!(status["result"]["status"], "running", "{status}");
    fixture.wait_post();
    session.child.kill().unwrap();
    session.child.wait().unwrap();
    drop(session);
    fixture.release();
    let mut session = Session::new(&root, None);
    let job = session.call(req("status", json!({"type":"job_get","job_id":"turn"})));
    assert_eq!(job["result"]["status"], "interrupted", "{job}");
    assert_eq!(session.call(req("turn",json!({"type":"conversation_start","chat_id":"one","model_id":"selected","content":"secret"})))["result"]["status"],"running");
    let chat = session.call(req("read-chat", json!({"type":"chat_get","chat_id":"one"})));
    assert_eq!(chat["result"]["messages"].as_array().unwrap().len(), 1);
}

fn powershell(script: &str) -> String {
    let output = Command::new("powershell.exe")
        .args(["-NoProfile", "-Command", script])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout).unwrap().trim().to_owned()
}

#[test]
fn abrupt_core_death_closes_owned_worker_job() {
    let _guard = TEST_LOCK.lock().unwrap();
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(true);
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    let started = session.call(req(
        "hard-death",
        json!({"type":"inference","model_id":"selected","prompt":"secret"}),
    ));
    assert_eq!(started["ok"], true, "{started}");
    thread::sleep(Duration::from_millis(800));
    let status = session.call(req(
        "predeath",
        json!({"type":"job_get","job_id":"hard-death"}),
    ));
    assert_eq!(status["result"]["status"], "running", "{status}");
    fixture.wait_post();
    let core_pid = session.child.id();
    let worker_pid = powershell(&format!(
        "Get-CimInstance Win32_Process -Filter 'ParentProcessId = {core_pid}' | Where-Object {{ $_.Name -like 'python*' }} | Select-Object -ExpandProperty ProcessId"
    ));
    assert!(!worker_pid.is_empty(), "owned Python worker not found");
    session.child.kill().unwrap();
    session.child.wait().unwrap();
    let started = Instant::now();
    while !powershell(&format!("Get-CimInstance Win32_Process -Filter 'ProcessId = {worker_pid}' | Select-Object -ExpandProperty ProcessId")).is_empty() {
        assert!(started.elapsed()<Duration::from_secs(5),"worker survived Core death");
        thread::sleep(Duration::from_millis(50));
    }
    drop(session);
}

#[test]
fn hanging_provider_reports_timeout_without_prompt_in_error() {
    let _guard = TEST_LOCK.lock().unwrap();
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(true);
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    assert_eq!(
        session.call(req(
            "timeout",
            json!({"type":"inference","model_id":"selected","prompt":"private data"})
        ))["ok"],
        true
    );
    let result = poll(&mut session, "timeout");
    assert_eq!(result["status"], "failed", "{result}");
    assert_eq!(result["error"], "provider_timeout", "{result}");
    assert!(!result.to_string().contains("private data"));
}
