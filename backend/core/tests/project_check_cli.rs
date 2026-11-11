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
    input: Option<ChildStdin>,
    output: BufReader<ChildStdout>,
}
impl Session {
    fn new(root: &TempDir, python: Option<&str>) -> Self {
        let workspace = root.path().join("workspace");
        std::fs::create_dir_all(&workspace).unwrap();
        let mut cmd = Command::new(env!("CARGO_BIN_EXE_synapse-backend"));
        cmd.args([
            "--state-dir",
            root.path().join("state").to_str().unwrap(),
            "--workspace",
            workspace.to_str().unwrap(),
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
            input: Some(input),
            output,
        }
    }
    fn call(&mut self, value: Value) -> Value {
        let input = self.input.as_mut().unwrap();
        writeln!(input, "{value}").unwrap();
        input.flush().unwrap();
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
#[ignore = "requires the dedicated Windows Python runtime configured by the owner"]
fn approved_check_runs_real_python() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(true);
    std::fs::write(
        fixture.marker.parent().unwrap().join("mission-response"),
        valid_plan().to_string(),
    )
    .unwrap();
    assert!(std::env::var_os("SYNAPSE_CHECK_PYTHON_EXECUTABLE").is_some());
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    let start = session.call(req("plan", plan_command("mission")));
    assert_eq!(start["ok"], true, "{start}");
    fixture.wait_post();
    fixture.release();
    assert_eq!(poll(&mut session, "plan")["status"], "succeeded");

    let passing = "import unittest
class Pass(unittest.TestCase):
 def test_ok(self): self.assertEqual(2+2,4)
";
    let sleeping = "import tempfile,time,unittest
from pathlib import Path
class Slow(unittest.TestCase):
 def test_wait(self):
  Path(tempfile.gettempdir(),'started').write_text('ready')
  time.sleep(25)
";
    let command = |source: &str| json!({"type":"project_check_start","mission_id":"mission","check_index":0,"artifacts":[{"path":"test_project.py","content":source}]});
    let refused = session.call(req("preapproval", command(passing)));
    assert_eq!(refused["error"]["code"], "permission_denied", "{refused}");
    let proposal = session.call(req(
        "proposal",
        json!({"type":"mission_get","mission_id":"mission"}),
    ));
    let approve = session.call(req("approve",json!({"type":"mission_approve","mission_id":"mission","contract_digest":proposal["result"]["contract_digest"]})));
    assert_eq!(approve["ok"], true, "{approve}");
    let wrong = session.call(req("wrong",json!({"type":"project_check_start","mission_id":"mission","check_index":0,"artifacts":[{"path":"other.py","content":passing}]})));
    assert_eq!(wrong["ok"], false, "{wrong}");

    let request = req("check", command(passing));
    let check = session.call(request.clone());
    assert_eq!(check["result"]["status"], "running", "{check}");
    assert_eq!(session.call(request.clone()), check);
    let changed = session.call(req("check", command(sleeping)));
    assert_eq!(
        changed["error"]["code"], "idempotency_conflict",
        "{changed}"
    );
    let completed = wait_check(&mut session, "check", |value| {
        value["cleanup"] == "complete"
    });
    assert_eq!(completed["status"], "succeeded", "{completed}");
    assert_eq!(completed["receipt"]["token"]["lpac"], true);
    assert!(
        completed["tool_digest"]
            .as_str()
            .is_some_and(|digest| digest.len() == 64)
    );

    for id in ["cancel-me", "shutdown-me", "interrupt-me"] {
        let running = session.call(req(id, command(sleeping)));
        assert_eq!(running["result"]["status"], "running", "{running}");
        // Observe the file written by the actual contained test while the
        // CLI stdin is idle. No request is needed to authorize the prepared job.
        let began = Instant::now();
        loop {
            let executing = std::fs::read_dir(root.path().join("state"))
                .unwrap()
                .flatten()
                .any(|entry| {
                    entry
                        .file_name()
                        .to_string_lossy()
                        .starts_with("Synapse.Check.")
                        && entry.path().join("temp/started").is_file()
                        && !entry.path().join("temp/observed").exists()
                });
            if executing {
                for entry in std::fs::read_dir(root.path().join("state"))
                    .unwrap()
                    .flatten()
                {
                    if entry.path().join("temp/started").is_file() {
                        std::fs::write(entry.path().join("temp/observed"), b"seen").unwrap();
                    }
                }
                break;
            }
            assert!(
                began.elapsed() < Duration::from_secs(30),
                "{id} did not execute"
            );
            thread::sleep(Duration::from_millis(50));
        }
        if id == "cancel-me" {
            let stopped = session.call(req(
                "cancel",
                json!({"type":"project_check_cancel","check_id":id}),
            ));
            assert_eq!(stopped["result"]["status"], "cancelled", "{stopped}");
            let result = wait_check(&mut session, id, |value| value["cleanup"] == "complete");
            assert_eq!(result["status"], "cancelled", "{result}");
            assert!(result["receipt"].is_null());
        } else if id == "shutdown-me" {
            drop(session.input.take());
            assert!(session.child.wait().unwrap().success());
            session = Session::new(&root, None);
            let stopped = session.call(req(
                "after-eof",
                json!({"type":"project_check_get","check_id":id}),
            ));
            assert_eq!(stopped["result"]["status"], "interrupted", "{stopped}");
            assert_eq!(stopped["result"]["error"], "core_shutdown", "{stopped}");
            assert_eq!(stopped["result"]["cleanup"], "complete", "{stopped}");
        }
    }
    drop(session);
    let mut restarted = Session::new(&root, None);
    let interrupted = restarted.call(req(
        "after-crash",
        json!({"type":"project_check_get","check_id":"interrupt-me"}),
    ));
    assert_eq!(
        interrupted["result"]["status"], "interrupted",
        "{interrupted}"
    );
    assert_eq!(
        interrupted["result"]["cleanup"], "unverified",
        "{interrupted}"
    );
    let running = restarted.call(req("revoke-me", command(sleeping)));
    assert_eq!(running["result"]["status"], "running", "{running}");
    let revoked = restarted.call(req(
        "revoke-mission",
        json!({"type":"mission_revoke","mission_id":"mission","reason":"fixture stop"}),
    ));
    assert_eq!(revoked["ok"], true, "{revoked}");
    let revoked_check = wait_check(&mut restarted, "revoke-me", |value| {
        value["cleanup"] == "complete"
    });
    assert_eq!(revoked_check["status"], "revoked", "{revoked_check}");
    assert!(revoked_check["receipt"].is_null());
    let denied = restarted.call(req("after-revoke", command(passing)));
    assert_eq!(denied["error"]["code"], "permission_denied", "{denied}");
    assert_eq!(restarted.call(request), check);
    assert!(
        root.path()
            .join("workspace")
            .read_dir()
            .unwrap()
            .next()
            .is_none()
    );
}

fn wait_check(session: &mut Session, id: &str, mut done: impl FnMut(&Value) -> bool) -> Value {
    let began = Instant::now();
    for count in 0.. {
        let result = session.call(req(
            &format!("check-poll-{id}-{count}"),
            json!({"type":"project_check_get","check_id":id}),
        ));
        assert_eq!(result["ok"], true, "{result}");
        if done(&result["result"]) {
            return result["result"].clone();
        }
        assert!(began.elapsed() < Duration::from_secs(150), "{result}");
        thread::sleep(Duration::from_millis(50));
    }
    unreachable!()
}

#[test]
#[ignore = "requires configured Windows Rust, VC and SDK toolchains"]
fn approved_check_runs_real_rust() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|error| error.into_inner());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(true);
    let plan = json!({
        "summary":"Small Rust project",
        "artifacts":[{"path":"calc.rs","purpose":"Implement and test addition"}],
        "checks":[{"kind":"rust_test","entrypoint":"calc.rs"}]
    });
    std::fs::write(
        fixture.marker.parent().unwrap().join("mission-response"),
        plan.to_string(),
    )
    .unwrap();
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    assert_eq!(
        session.call(req("plan", plan_command("mission")))["ok"],
        true
    );
    fixture.wait_post();
    fixture.release();
    assert_eq!(poll(&mut session, "plan")["status"], "succeeded");
    let proposal = session.call(req(
        "proposal",
        json!({"type":"mission_get","mission_id":"mission"}),
    ));
    let approved = session.call(req("approve",json!({"type":"mission_approve","mission_id":"mission","contract_digest":proposal["result"]["contract_digest"]})));
    assert_eq!(approved["ok"], true, "{approved}");
    let source = "#[test] fn adds() { assert_eq!(2 + 3, 5); }";
    let started = session.call(req(
        "rust-check",
        json!({
            "type":"project_check_start","mission_id":"mission","check_index":0,
            "artifacts":[{"path":"calc.rs","content":source}]
        }),
    ));
    assert_eq!(started["result"]["status"], "running", "{started}");
    let done = wait_check(&mut session, "rust-check", |value| {
        value["cleanup"] != "pending"
    });
    assert_eq!(done["status"], "succeeded", "{done}");
    assert_eq!(done["cleanup"], "complete", "{done}");
    let phases = done["receipt"]["phases"].as_array().unwrap();
    assert_eq!(phases.len(), 3);
    for (phase, name) in phases.iter().zip(["emit", "link", "test"]) {
        assert_eq!(phase["phase"], name);
        assert_eq!(phase["exit_code"], 0);
        assert_eq!(phase["token"]["lpac"], true);
    }
}

#[test]
#[ignore = "requires the dedicated Windows Python runtime configured by the owner"]
fn mission_run_checks_candidate_before_separate_review() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    assert!(std::env::var_os("SYNAPSE_CHECK_PYTHON_EXECUTABLE").is_some());
    let source = "import unittest\nclass Arithmetic(unittest.TestCase):\n def test_adds(self): self.assertEqual(2+3,5)\n";

    for (scenario, expected) in [
        ("approved", "review_ready"),
        ("rejected", "rejected"),
        ("check-failure", "failed"),
        ("wrong-artifact", "failed"),
        ("generation-cancel", "cancelled"),
        ("generation-restart", "interrupted"),
    ] {
        let root = TempDir::new().unwrap();
        let fixture = Fixture::new(false);
        let provider = fixture.marker.parent().unwrap();
        let mut plan = valid_plan();
        let mut files = vec![json!({
            "path": if scenario == "wrong-artifact" { "outside.py" } else { "test_project.py" },
            "content": if scenario == "check-failure" {source.replace("2+3,5", "2+3,6")} else {source.to_owned()}
        })];
        if scenario == "approved" {
            plan["artifacts"]
                .as_array_mut()
                .unwrap()
                .push(json!({"path":"test_second.py","purpose":"Second check"}));
            plan["checks"]
                .as_array_mut()
                .unwrap()
                .push(json!({"kind":"python_unittest","entrypoint":"test_second.py"}));
            files.push(json!({"path":"test_second.py","content":source}));
        }
        std::fs::write(provider.join("mission-response"), plan.to_string()).unwrap();
        std::fs::write(
            provider.join("mission_generate-response"),
            json!({"artifacts":files}).to_string(),
        )
        .unwrap();
        std::fs::write(
            provider.join("mission_review-response"),
            json!({"approved":scenario != "rejected","reason":"Fixture review decision"})
                .to_string(),
        )
        .unwrap();
        let hold = provider.join("mission_generate-hold");
        if scenario.starts_with("generation-") {
            std::fs::write(&hold, "").unwrap();
        }

        let mut session = Session::new(&root, None);
        register(&mut session, &fixture.address);
        assert_eq!(
            session.call(req("plan", plan_command("mission")))["ok"],
            true
        );
        assert_eq!(poll(&mut session, "plan")["status"], "succeeded");
        let execute = json!({"type":"mission_execute","mission_id":"mission"});
        let refused = session.call(req("too-early", execute.clone()));
        assert_eq!(refused["error"]["code"], "permission_denied", "{refused}");
        let proposal = session.call(req(
            "proposal",
            json!({"type":"mission_get","mission_id":"mission"}),
        ));
        let approved = session.call(req("approve",json!({"type":"mission_approve","mission_id":"mission","contract_digest":proposal["result"]["contract_digest"]})));
        assert_eq!(approved["ok"], true, "{approved}");
        let start = req("execute", execute);
        let started = session.call(start.clone());
        assert_eq!(started["result"]["status"], "generating", "{started}");
        assert_eq!(session.call(start), started);
        if scenario.starts_with("generation-") {
            let began = Instant::now();
            while !provider.join("mission_generate-post").is_file() {
                assert!(began.elapsed() < Duration::from_secs(12));
                thread::sleep(Duration::from_millis(20));
            }
            if scenario == "generation-cancel" {
                let cancelled = session.call(req("cancel-run", json!({"type":"mission_cancel","mission_id":"mission","reason":"fixture cancellation"})));
                assert_eq!(cancelled["ok"], true, "{cancelled}");
            } else {
                drop(session);
                session = Session::new(&root, None);
            }
            std::fs::remove_file(&hold).unwrap();
        }

        let began = Instant::now();
        let result = (0..)
            .find_map(|index| {
                let status = session.call(req(
                    &format!("run-status-{index}"),
                    json!({"type":"mission_run_get","mission_id":"mission"}),
                ));
                assert_eq!(status["ok"], true, "{status}");
                let run = &status["result"];
                if !matches!(
                    run["status"].as_str(),
                    Some("generating" | "checking" | "reviewing")
                ) {
                    return Some(run.clone());
                }
                assert!(began.elapsed() < Duration::from_secs(150), "{status}");
                thread::sleep(Duration::from_millis(50));
                None
            })
            .unwrap();
        assert_eq!(result["status"], expected, "{scenario}: {result}");
        if scenario == "check-failure" {
            assert_eq!(result["error"], "check_failed", "{result}");
            assert!(result["failed_check_id"].as_str().is_some());
        }
        if scenario == "wrong-artifact" {
            assert_eq!(result["error"], "invalid_generated_candidate", "{result}");
            assert!(result["candidate_digest"].is_null());
        }
        let review_path = provider.join("mission_review-post");
        if matches!(scenario, "approved" | "rejected") {
            assert_eq!(
                result["completed_checks"],
                if scenario == "approved" { 2 } else { 1 }
            );
            assert_eq!(result["review"]["approved"], scenario == "approved");
            assert!(
                result["candidate_digest"]
                    .as_str()
                    .is_some_and(|hash| hash.len() == 64)
            );
            let generation: Value = serde_json::from_slice(
                &std::fs::read(provider.join("mission_generate-post")).unwrap(),
            )
            .unwrap();
            let review: Value =
                serde_json::from_slice(&std::fs::read(review_path).unwrap()).unwrap();
            assert_ne!(generation["messages"], review["messages"]);
            assert_ne!(generation["max_tokens"], review["max_tokens"]);
            assert!(review["messages"].to_string().contains("observed_checks"));
            if scenario == "approved" {
                let revoke = session.call(req("revoke-ready",json!({"type":"mission_revoke","mission_id":"mission","reason":"fixture stop after review"})));
                assert_eq!(revoke["ok"], true, "{revoke}");
                let revoked = session.call(req(
                    "after-revoke-ready",
                    json!({"type":"mission_run_get","mission_id":"mission"}),
                ));
                assert_eq!(revoked["result"]["status"], "revoked", "{revoked}");
                assert_eq!(revoked["result"]["review"]["approved"], true);
            }
        } else {
            assert!(!review_path.exists());
            assert!(result["review"].is_null());
        }
        assert!(
            root.path()
                .join("workspace")
                .read_dir()
                .unwrap()
                .next()
                .is_none()
        );
    }
}
