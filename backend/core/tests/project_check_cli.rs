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
        Self::with_env(root, python, &[])
    }

    fn with_env(root: &TempDir, python: Option<&str>, settings: &[(&str, &str)]) -> Self {
        let workspace = root.path().join("workspace");
        std::fs::create_dir_all(&workspace).unwrap();
        let binaries=root.path().join("private-binaries");
        std::fs::create_dir_all(&binaries).unwrap();
        let executable = binaries.join(format!(
            "synapse-backend-{}.exe",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::copy(env!("CARGO_BIN_EXE_synapse-backend"), &executable).unwrap();
        let mut cmd = Command::new(executable);
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
        cmd.envs(settings.iter().copied());
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
fn mission_run_integrates_only_verified_owned_candidate() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    assert!(std::env::var_os("SYNAPSE_CHECK_PYTHON_EXECUTABLE").is_some());
    let source = "import unittest\nclass Arithmetic(unittest.TestCase):\n def test_adds(self): self.assertEqual(2+3,5)\n";

    for (scenario, expected) in [
        ("approved", "integrated"),
        ("occupied", "failed"),
        #[cfg(feature = "test-fault-injection")]
        ("postcheck-rollback", "rolled_back"),
        #[cfg(feature = "test-fault-injection")]
        ("publish-crash-before", "recovery_required"),
        #[cfg(feature = "test-fault-injection")]
        ("publish-crash-after", "recovery_required"),
        ("revoke-after-write", "recovery_required"),
        ("workspace-exchanged", "failed"),
        ("git-ancestor", "failed"),
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
            for path in ["notes.md", "summary.txt"] {
                plan["artifacts"]
                    .as_array_mut()
                    .unwrap()
                    .push(json!({"path":path,"purpose":"Documentation"}));
                files.push(json!({"path":path,"content":"Arithmetic validation"}));
            }
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

        let settings: &[(&str, &str)] = match scenario {
            "postcheck-rollback" => &[("SYNAPSE_TEST_REJECT_POSTCHECK_TOOL", "1")],
            "publish-crash-before" => &[("SYNAPSE_TEST_CRASH_AFTER_MISSION_PUBLISH_PREPARE", "1")],
            "publish-crash-after" => &[("SYNAPSE_TEST_CRASH_AFTER_MISSION_PUBLISH_WRITE", "1")],
            _ => &[],
        };
        let mut session = Session::with_env(&root, None, settings);
        if scenario == "occupied" {
            std::fs::write(root.path().join("workspace/test_project.py"), "owner file").unwrap();
        }
        register(&mut session, &fixture.address);
        let mut planning = plan_command("mission");
        if scenario == "approved" {
            let package = json!({"license":"MIT","manifest":{
                "id":"arithmetic","scope":"project:a","version":"1","provenance":"test",
                "tools":[],"permissions":[],"instructions":"ARITHMETIC_DOMAIN_GUIDANCE"
            }});
            let inspected = session.call(req(
                "inspect-skill",
                json!({"type":"skill_inspect","package":package}),
            ));
            assert_eq!(inspected["ok"], true, "{inspected}");
            let registered = session.call(req(
                "install-skill",
                json!({"type":"skill_install","package":package,
                "inspected_digest":inspected["result"]["inspected_digest"]}),
            ));
            assert_eq!(registered["ok"], true, "{registered}");
            planning["skill"] = json!({"id":"arithmetic","scope":"project:a","version":"1",
                "digest":registered["result"]["digest"]});
        }
        assert_eq!(session.call(req("plan", planning))["ok"], true);
        assert_eq!(poll(&mut session, "plan")["status"], "succeeded");
        let execute = json!({"type":"mission_execute","mission_id":"mission"});
        let refused = session.call(req("too-early", execute.clone()));
        assert_eq!(refused["error"]["code"], "permission_denied", "{refused}");
        let proposal = session.call(req(
            "proposal",
            json!({"type":"mission_get","mission_id":"mission"}),
        ));
        let mut approval = json!({"type":"mission_approve","mission_id":"mission",
            "contract_digest":proposal["result"]["contract_digest"]});
        if scenario == "approved" {
            approval["swarm"] = json!("recommended");
        } else if scenario == "generation-cancel" {
            approval["swarm"] = json!("direct");
        }
        let approved = session.call(req("approve", approval));
        assert_eq!(approved["ok"], true, "{approved}");
        if scenario == "workspace-exchanged" {
            std::fs::rename(
                root.path().join("workspace"),
                root.path().join("original-workspace"),
            )
            .unwrap();
            std::fs::create_dir(root.path().join("workspace")).unwrap();
        }
        if scenario == "git-ancestor" {
            std::fs::create_dir(root.path().join(".git")).unwrap();
        }
        let reserved = session.call(req("internal-mission-test",json!({"type":"tool_execute","mission_id":"mission","operation":{"type":"create","path":"test_project.py","content":"denied"}})));
        assert_eq!(reserved["error"]["code"], "invalid_request", "{reserved}");
        let start = req("execute", execute);
        let started = session.call(start.clone());
        assert_eq!(started["result"]["status"], "generating", "{started}");
        if scenario == "approved" || scenario == "generation-cancel" {
            assert_eq!(started["result"]["swarm"]["roles"][0]["status"], "running");
            let expected_source = if scenario == "approved" {
                "recommended"
            } else {
                "direct"
            };
            assert_eq!(started["result"]["swarm"]["source"], expected_source);
            for role in started["result"]["swarm"]["roles"].as_array().unwrap() {
                assert_eq!(role["model_id"], "selected");
            }
            assert_eq!(
                started["result"]["swarm"]["roles"][0]["log"][0]["kind"],
                "generation_started"
            );
            assert_eq!(started["result"]["swarm"]["roles"][1]["log"], json!([]));
        } else {
            assert!(started["result"].get("swarm").is_none());
        }

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

        if scenario.starts_with("publish-crash-") {
            let began = Instant::now();
            loop {
                if let Some(exit) = session.child.try_wait().unwrap() {
                    assert_eq!(
                        exit.code(),
                        Some(if scenario == "publish-crash-before" {
                            87
                        } else {
                            88
                        })
                    );
                    break;
                }
                assert!(began.elapsed() < Duration::from_secs(60));
                thread::sleep(Duration::from_millis(50));
            }
            session = Session::new(&root, None);
        }
        if scenario == "revoke-after-write" {
            let began = Instant::now();
            while !root.path().join("workspace/test_project.py").is_file() {
                assert!(began.elapsed() < Duration::from_secs(60));
                thread::sleep(Duration::from_millis(10));
            }
            let revoked = session.call(req("revoke-write",json!({"type":"mission_revoke","mission_id":"mission","reason":"stop after observed write"})));
            assert_eq!(revoked["ok"], true, "{revoked}");
        }

        let began = Instant::now();
        let mut saw_swarm_publication = false;
        let result = (0..)
            .find_map(|index| {
                let status = session.call(req(
                    &format!("run-status-{index}"),
                    json!({"type":"mission_run_get","mission_id":"mission"}),
                ));
                assert_eq!(status["ok"], true, "{status}");
                let run = &status["result"];
                if scenario == "approved"
                    && matches!(
                        run["status"].as_str(),
                        Some("review_ready" | "publishing" | "postchecking")
                    )
                {
                    let log = run["swarm"]["roles"][1]["log"].as_array().unwrap();
                    assert!(log.iter().any(|event| event["kind"] == "review_approved"));
                    saw_swarm_publication = true;
                }

                if !matches!(
                    run["status"].as_str(),
                    Some(
                        "generating"
                            | "checking"
                            | "reviewing"
                            | "review_ready"
                            | "publishing"
                            | "postchecking"
                            | "rolling_back"
                    )
                ) {
                    return Some(run.clone());
                }
                assert!(began.elapsed() < Duration::from_secs(150), "{status}");
                thread::sleep(Duration::from_millis(50));
                None
            })
            .unwrap();
        assert_eq!(result["status"], expected, "{scenario}: {result}");
        if scenario == "approved" {
            assert!(saw_swarm_publication);
        }
        if scenario == "check-failure" {
            assert_eq!(result["error"], "check_failed", "{result}");
            assert!(result["failed_check_id"].as_str().is_some());
        }
        if scenario == "wrong-artifact" {
            assert_eq!(result["error"], "invalid_generated_candidate", "{result}");
            assert!(result["candidate_digest"].is_null());
        }
        if scenario == "occupied" {
            assert_eq!(result["error"], "artifact_conflict");
        }
        if scenario == "postcheck-rollback" {
            assert_eq!(result["error"], "postcheck_tool_changed");
            assert_eq!(result["completed_postchecks"], 0);
        }
        if scenario == "workspace-exchanged" {
            assert_eq!(result["error"], "workspace_changed", "{result}");
            assert!(
                root.path()
                    .join("original-workspace")
                    .read_dir()
                    .unwrap()
                    .next()
                    .is_none()
            );
        }
        if scenario == "git-ancestor" {
            assert_eq!(result["error"], "workspace_unsupported", "{result}");
        }
        if scenario.starts_with("publish-crash-") || scenario == "revoke-after-write" {
            let file = &result["integration_files"][0];
            assert_eq!(file["path"], "test_project.py", "{result}");
            assert!(file["intent_id"].as_str().is_some());
            if scenario.starts_with("publish-crash-") {
                assert_eq!(file["status"], "prepared", "{result}");
            }
        }
        if scenario.starts_with("publish-crash-") || scenario == "revoke-after-write" {
            let command = json!({"type":"mission_recovery_inspect","mission_id":"mission"});
            let inspection = session.call(req("inspect-recovery", command.clone()));
            assert_eq!(inspection["ok"], true, "{inspection}");
            let inspection = &inspection["result"];
            let file = &inspection["files"][0];
            assert_eq!(inspection["status"], "recovery_required", "{inspection}");
            assert_eq!(file["path"], "test_project.py", "{inspection}");
            assert_eq!(
                file["intent_id"],
                result["integration_files"][0]["intent_id"]
            );
            assert_eq!(file["intent_status"], "prepared", "{inspection}");
            let target = root.path().join("workspace/test_project.py");
            match scenario {
                "publish-crash-before" => {
                    assert_eq!(file["classification"], "absent", "{inspection}");
                    assert!(file["observed_sha256"].is_null());
                    assert!(!target.exists());
                }
                "publish-crash-after" => {
                    assert_eq!(
                        file["classification"], "matching_bytes_unproven",
                        "{inspection}"
                    );
                    assert_eq!(file["identity_recorded"], false, "{inspection}");
                    assert_eq!(file["observed_sha256"], file["expected_sha256"]);
                    assert_eq!(std::fs::read_to_string(&target).unwrap(), source);
                    use std::os::windows::fs::OpenOptionsExt;
                    let lock = std::fs::OpenOptions::new()
                        .read(true)
                        .share_mode(0)
                        .open(&target)
                        .unwrap();
                    let unreadable = session.call(req("inspect-locked", command.clone()));
                    assert_eq!(
                        unreadable["result"]["files"][0]["classification"], "unreadable",
                        "{unreadable}"
                    );
                    drop(lock);
                }
                _ => {
                    assert_eq!(file["classification"], "verified_owned", "{inspection}");
                    assert_eq!(file["identity_recorded"], true, "{inspection}");
                    std::fs::write(&target, "modified by the fixture").unwrap();
                    let changed = session.call(req("inspect-modified", command));
                    assert_eq!(
                        changed["result"]["files"][0]["classification"], "changed",
                        "{changed}"
                    );
                    assert_eq!(
                        std::fs::read_to_string(&target).unwrap(),
                        "modified by the fixture"
                    );
                    std::fs::write(&target, source).unwrap();
                }
            }
        }
        assert!(result.get("swarm").is_none());
        if scenario == "approved" {
            let evidence = session.call(req(
                "skill-use-evidence",
                json!({
                    "type":"skill_mission_evidence","mission_id":"mission"
                }),
            ));
            assert_eq!(evidence["ok"], true, "{evidence}");
            assert_eq!(evidence["result"]["status"], "integrated");
            assert_eq!(evidence["result"]["qa_approved"], true);
            assert_eq!(evidence["result"]["completed_checks"], 2);
            assert_eq!(evidence["result"]["parent"]["scope"], "project:a");
            let generation =
                std::fs::read_to_string(provider.join("mission_generate-post")).unwrap();
            let review = std::fs::read_to_string(provider.join("mission_review-post")).unwrap();
            assert!(generation.contains("temporary implementation role"));
            assert!(review.contains("temporary verification role"));
            assert!(generation.contains("ARITHMETIC_DOMAIN_GUIDANCE"));
            assert!(review.contains("ARITHMETIC_DOMAIN_GUIDANCE"));
        }
        let review_path = provider.join("mission_review-post");
        if matches!(
            scenario,
            "approved"
                | "rejected"
                | "occupied"
                | "postcheck-rollback"
                | "publish-crash-before"
                | "publish-crash-after"
                | "revoke-after-write"
                | "workspace-exchanged"
                | "git-ancestor"
        ) {
            assert_eq!(
                result["completed_checks"],
                if scenario == "approved" { 2 } else { 1 }
            );
            assert_eq!(result["review"]["approved"], scenario != "rejected");
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
                assert_eq!(revoked["result"]["status"], "integrated", "{revoked}");
                assert_eq!(revoked["result"]["completed_postchecks"], 2);
                assert_eq!(revoked["result"]["review"]["approved"], true);
            }
        } else {
            assert!(!review_path.exists());
            assert!(result["review"].is_null());
        }
        let workspace = root.path().join("workspace");
        match scenario {
            "approved" => {
                assert_eq!(
                    std::fs::read_to_string(workspace.join("test_project.py")).unwrap(),
                    source
                );
                assert_eq!(
                    std::fs::read_to_string(workspace.join("test_second.py")).unwrap(),
                    source
                );
                for path in ["notes.md", "summary.txt"] {
                    assert_eq!(
                        std::fs::read_to_string(workspace.join(path)).unwrap(),
                        "Arithmetic validation"
                    );
                }
                assert_eq!(workspace.read_dir().unwrap().count(), 4);
            }
            "publish-crash-after" | "revoke-after-write" => {
                assert_eq!(
                    std::fs::read_to_string(workspace.join("test_project.py")).unwrap(),
                    source
                );
                assert_eq!(workspace.read_dir().unwrap().count(), 1);
            }
            "occupied" => {
                assert_eq!(
                    std::fs::read_to_string(workspace.join("test_project.py")).unwrap(),
                    "owner file"
                );
                assert_eq!(workspace.read_dir().unwrap().count(), 1);
            }
            _ => assert!(workspace.read_dir().unwrap().next().is_none()),
        }
    }
}

#[test]
#[cfg(feature = "test-fault-injection")]
#[ignore = "requires the dedicated Windows Python runtime configured by the owner"]
fn mission_recovery_resolves_only_verified_effects() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    assert!(std::env::var_os("SYNAPSE_CHECK_PYTHON_EXECUTABLE").is_some());
    let source = "import unittest\nclass Good(unittest.TestCase):\n def test_ok(self): self.assertEqual(2+3,5)\n";
    for (scenario, fault, exit_code) in [
        (
            "absent",
            "SYNAPSE_TEST_CRASH_AFTER_MISSION_PUBLISH_PREPARE",
            87,
        ),
        (
            "unproven",
            "SYNAPSE_TEST_CRASH_AFTER_MISSION_PUBLISH_WRITE",
            88,
        ),
        ("finalize", "SYNAPSE_TEST_CRASH_BEFORE_MISSION_FINALIZE", 89),
        (
            "rollback-after",
            "SYNAPSE_TEST_CRASH_BEFORE_MISSION_FINALIZE",
            89,
        ),
        (
            "rollback-before",
            "SYNAPSE_TEST_CRASH_BEFORE_MISSION_FINALIZE",
            89,
        ),
        ("revoked", "SYNAPSE_TEST_CRASH_BEFORE_MISSION_FINALIZE", 89),
    ] {
        let root = TempDir::new().unwrap();
        let fixture = Fixture::new(false);
        let provider = fixture.marker.parent().unwrap();
        std::fs::write(provider.join("mission-response"), valid_plan().to_string()).unwrap();
        std::fs::write(
            provider.join("mission_generate-response"),
            json!({"artifacts":[
            {"path":"test_project.py","content":source}]})
            .to_string(),
        )
        .unwrap();
        std::fs::write(
            provider.join("mission_review-response"),
            json!({"approved":true,"reason":"fixture"}).to_string(),
        )
        .unwrap();
        let mut session = Session::with_env(&root, None, &[(fault, "1")]);
        register(&mut session, &fixture.address);
        assert_eq!(
            session.call(req("plan", plan_command("mission")))["ok"],
            true
        );
        assert_eq!(poll(&mut session, "plan")["status"], "succeeded");
        let proposal = session.call(req(
            "proposal",
            json!({"type":"mission_get","mission_id":"mission"}),
        ));
        let approval = session.call(req(
            "approve",
            json!({"type":"mission_approve","mission_id":"mission",
            "contract_digest":proposal["result"]["contract_digest"]}),
        ));
        assert_eq!(approval["ok"], true, "{approval}");
        assert_eq!(
            session.call(req(
                "execute",
                json!({"type":"mission_execute","mission_id":"mission"})
            ))["ok"],
            true
        );
        wait_recovery_exit(&mut session, exit_code);
        let rollback_fault = match scenario {
            "rollback-before" => Some(("SYNAPSE_TEST_CRASH_BEFORE_MISSION_ROLLBACK_DELETE", 91)),
            "rollback-after" => Some(("SYNAPSE_TEST_CRASH_AFTER_MISSION_ROLLBACK_DELETE", 90)),
            _ => None,
        };
        session = match rollback_fault {
            Some((fault, _)) => Session::with_env(&root, None, &[(fault, "1")]),
            None => Session::new(&root, None),
        };
        let current = session.call(req(
            "initial-recovery",
            json!({"type":"mission_run_get","mission_id":"mission"}),
        ));
        assert_eq!(
            current["result"]["status"], "recovery_required",
            "{current}"
        );
        let file = root.path().join("workspace/test_project.py");
        let command =
            |mode| json!({"type":"mission_recovery_resolve","mission_id":"mission","mode":mode});
        if scenario == "unproven" {
            assert_eq!(std::fs::read_to_string(&file).unwrap(), source);
            for mode in ["finalize", "rollback"] {
                let refusal = session.call(req(mode, command(mode)));
                assert_eq!(refusal["ok"], false, "{refusal}");
            }
            assert_eq!(std::fs::read_to_string(&file).unwrap(), source);
            continue;
        }
        if scenario == "revoked" {
            let stop = session.call(req(
                "revoke",
                json!({"type":"mission_revoke","mission_id":"mission","reason":"fixture"}),
            ));
            assert_eq!(stop["ok"], true, "{stop}");
            let refusal = session.call(req("rollback", command("rollback")));
            assert_eq!(refusal["error"]["code"], "permission_denied", "{refusal}");
            assert_eq!(std::fs::read_to_string(&file).unwrap(), source);
            continue;
        }
        if scenario == "finalize" {
            // Simulate a damaged private journal while no Core owns the store.
            let intent = current["result"]["integration_files"][0]["intent_id"]
                .as_str()
                .unwrap();
            drop(session);
            let db = rusqlite::Connection::open(root.path().join("state/core.sqlite3")).unwrap();
            let operation: String = db
                .query_row(
                    "SELECT operation FROM intent_operations WHERE request_id=?1",
                    [intent],
                    |row| row.get(0),
                )
                .unwrap();
            db.execute(
                "DELETE FROM intent_operations WHERE request_id=?1",
                [intent],
            )
            .unwrap();
            drop(db);
            session = Session::new(&root, None);
            let inspect = session.call(req(
                "damaged-journal",
                json!({"type":"mission_recovery_inspect","mission_id":"mission"}),
            ));
            assert_eq!(inspect["error"]["code"], "journal_mismatch", "{inspect}");
            let refusal = session.call(req("damaged-rollback", command("rollback")));
            assert_eq!(refusal["error"]["code"], "journal_mismatch", "{refusal}");
            assert_eq!(std::fs::read_to_string(&file).unwrap(), source);
            drop(session);
            let db = rusqlite::Connection::open(root.path().join("state/core.sqlite3")).unwrap();
            db.execute(
                "INSERT INTO intent_operations(request_id,operation) VALUES(?1,?2)",
                rusqlite::params![intent, operation],
            )
            .unwrap();
            drop(db);
            session = Session::new(&root, None);
            std::fs::write(&file, "owner edit").unwrap();
            let refusal = session.call(req("edited-finalize", command("finalize")));
            assert_eq!(
                refusal["error"]["code"], "recovery_evidence_insufficient",
                "{refusal}"
            );
            let refusal = session.call(req("edited-rollback", command("rollback")));
            assert_eq!(
                refusal["error"]["code"], "recovery_evidence_insufficient",
                "{refusal}"
            );
            assert_eq!(std::fs::read_to_string(&file).unwrap(), "owner edit");
            std::fs::write(&file, source).unwrap();
        }
        if let Some((_, exit_code)) = rollback_fault {
            let rollback = req("first-resolution", command("rollback"));
            let stdin = session.input.as_mut().unwrap();
            writeln!(stdin, "{rollback}").unwrap();
            stdin.flush().unwrap();
            wait_recovery_exit(&mut session, exit_code);
            session = Session::new(&root, None);
            if scenario == "rollback-before" {
                assert_eq!(std::fs::read_to_string(&file).unwrap(), source);
            } else {
                assert!(!file.exists());
            }
            let replay = session.call(rollback);
            assert_eq!(replay["result"]["status"], "rolling_back", "{replay}");
            let current = session.call(req(
                "after-replay",
                json!({"type":"mission_run_get","mission_id":"mission"}),
            ));
            assert_eq!(
                current["result"]["status"], "recovery_required",
                "{current}"
            );
        }
        let mode = if scenario == "finalize" {
            "finalize"
        } else {
            "rollback"
        };
        let request = req("resolve", command(mode));
        let accepted = session.call(request.clone());
        assert_eq!(accepted["ok"], true, "{accepted}");
        assert_eq!(session.call(request), accepted);
        let expected = if scenario == "finalize" {
            "integrated"
        } else {
            "rolled_back"
        };
        let began = Instant::now();
        for index in 0.. {
            let reply = session.call(req(
                &format!("terminal-{index}"),
                json!({"type":"mission_run_get","mission_id":"mission"}),
            ));
            assert_eq!(reply["ok"], true, "{reply}");
            if reply["result"]["status"] == expected {
                break;
            }
            assert!(began.elapsed() < Duration::from_secs(10), "{reply}");
            thread::sleep(Duration::from_millis(50));
        }
        if scenario == "finalize" {
            assert_eq!(std::fs::read_to_string(&file).unwrap(), source);
        } else {
            assert!(!file.exists());
        }
    }
}

#[cfg(feature = "test-fault-injection")]
fn wait_recovery_exit(session: &mut Session, expected: i32) {
    let began = Instant::now();
    loop {
        if let Some(exit) = session.child.try_wait().unwrap() {
            assert_eq!(exit.code(), Some(expected));
            return;
        }
        assert!(began.elapsed() < Duration::from_secs(120));
        thread::sleep(Duration::from_millis(50));
    }
}

#[test]
#[ignore = "requires the dedicated Windows Python runtime configured by the owner"]
fn domain_skills_bind_verified_native_deliverables() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|error| error.into_inner());
    assert!(std::env::var_os("SYNAPSE_CHECK_PYTHON_EXECUTABLE").is_some());
    let root = TempDir::new().unwrap();
    let fixture = Fixture::new(false);
    let provider = fixture.marker.parent().unwrap();
    let mut session = Session::new(&root, None);
    register(&mut session, &fixture.address);
    let domains = [
        (
            "game-level",
            "level.json",
            "game_level_validate",
            "Represent the tile map as a JSON object with dimensions and tile IDs.",
            "{\"width\":2,\"height\":2,\"tiles\":[[0,1],[1,0]]}",
        ),
        (
            "research-table",
            "measurements.csv",
            "csv_validate",
            "Use a header, a sample identifier and an explicit measurement unit.",
            "sample_id,value,unit\nA,2.5,mm\nB,3.0,mm\n",
        ),
        (
            "document",
            "brief.md",
            "markdown_validate",
            "Start with a Markdown title and state the purpose in the body.",
            "# Brief\n\nThis document describes the project scope and acceptance criteria.\n",
        ),
        (
            "design-icon",
            "icon.svg",
            "svg_validate",
            "Use a local viewBox and passive SVG geometry only.",
            "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 32 32\"><rect x=\"1\" y=\"1\" width=\"30\" height=\"30\" fill=\"#123456\"/></svg>",
        ),
        (
            "media-captions",
            "captions.vtt",
            "webvtt_validate",
            "Write nonempty subtitle cues in chronological order.",
            "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nOpening\n\n00:00:01.200 --> 00:00:03.000\nNext scene\n",
        ),
        (
            "python-build",
            "module.py",
            "python_compile",
            "Compile the Python source without executing it.",
            "def add(a, b):\n    return a + b\n",
        ),
        (
            "python-dependencies",
            "pyproject.toml",
            "python_manifest_validate",
            "Use exact dependency pins in the Python project manifest.",
            "[project]\nname = 'sample'\nversion = '1.0.0'\ndependencies = ['example==1.2.3']\n",
        ),
    ];
    for (domain, path, kind, instructions, content) in domains {
        let scope = format!("project:{domain}");
        let directory = root.path().join(domain);
        std::fs::create_dir(&directory).unwrap();
        let binding = session.call(req(
            &format!("bind-{domain}"),
            json!({"type":"project_register","scope":scope,"root":directory}),
        ));
        assert_eq!(binding["ok"], true, "{binding}");
        let skill = session.call(req(&format!("skill-{domain}"), json!({"type":"skill_register","skill":{
            "id":domain,"scope":scope,"version":"1.0.0","provenance":"stage 12 fixture","tools":[],"permissions":[],"instructions":instructions
        }})));
        assert_eq!(skill["ok"], true, "{skill}");
        let planned = json!({"summary":format!("Validate {domain}"),"artifacts":[{"path":path,"purpose":instructions}],"checks":[{"kind":kind,"entrypoint":path}]});
        std::fs::write(provider.join("mission-response"), planned.to_string()).unwrap();
        let plan_id = format!("plan-{domain}");
        let mut plan = plan_command(domain);
        plan["scope"] = json!(scope);
        plan["skill"] =
            json!({"scope":scope,"id":domain,"version":"1.0.0","digest":skill["result"]["digest"]});
        let launched = session.call(req(&plan_id, plan));
        assert_eq!(launched["ok"], true, "{launched}");
        let job = poll(&mut session, &plan_id);
        assert_eq!(job["status"], "succeeded", "{job}");
        let posted = std::fs::read_to_string(&fixture.marker).unwrap();
        assert!(
            posted.contains(instructions),
            "Skill instructions did not reach the planner"
        );
        let proposal = session.call(req(
            &format!("proposal-{domain}"),
            json!({"type":"mission_get","mission_id":domain}),
        ));
        assert_eq!(proposal["ok"], true, "{proposal}");
        let approved = session.call(req(&format!("approve-{domain}"), json!({"type":"mission_approve","mission_id":domain,"contract_digest":proposal["result"]["contract_digest"]})));
        assert_eq!(approved["ok"], true, "{approved}");
        let check_id = format!("check-{domain}");
        let check = session.call(req(&check_id, json!({"type":"project_check_start","mission_id":domain,"check_index":0,"artifacts":[{"path":path,"content":content}]})));
        assert_eq!(check["ok"], true, "{check}");
        let completed = wait_check(&mut session, &check_id, |result| {
            result["cleanup"] == "complete"
        });
        assert_eq!(completed["status"], "succeeded", "{completed}");
        assert_eq!(completed["receipt"]["token"]["lpac"], true, "{completed}");
        assert_eq!(
            completed["receipt"]["phases"][0]["phase"],
            if kind == "python_compile" {
                "compile"
            } else {
                "validate"
            },
            "{completed}"
        );
        assert!(
            !directory.join(path).exists(),
            "Validation wrote to the project directory"
        );
    }
}

#[cfg(feature = "test-fault-injection")]
#[test]
#[ignore = "requires the dedicated Windows Python runtime and Git"]
fn git_tracked_edit_detects_changes_and_restores_verified_original() {
    let _guard = TEST_LOCK.lock().unwrap_or_else(|error| error.into_inner());
    let root = TempDir::new().unwrap();
    let workspace = root.path().join("workspace");
    std::fs::create_dir(&workspace).unwrap();
    let git = |args: &[&str]| {
        let result = Command::new("git")
            .current_dir(&workspace)
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env("GIT_CONFIG_GLOBAL", "NUL")
            .args(["-c", "core.hooksPath=NUL"])
            .args(args)
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
    };
    let path = workspace.join("test_project.py");
    let note = workspace.join("notes.txt");
    let before = "import unittest\nclass Test(unittest.TestCase):\n def test_ok(self): self.assertEqual(1,1)\n";
    let after = "import unittest\nclass Test(unittest.TestCase):\n def test_ok(self): self.assertEqual(2,2)\n";
    git(&["init", "--quiet", "--object-format=sha1"]);
    std::fs::write(&path, before).unwrap();
    std::fs::write(&note, "old note").unwrap();
    git(&["add", "--", "test_project.py", "notes.txt"]);
    git(&[
        "-c",
        "user.name=Synapse QA",
        "-c",
        "user.email=qa@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "Baseline",
    ]);
    let index = std::fs::read(workspace.join(".git/index")).unwrap();
    let head = std::fs::read(workspace.join(".git/HEAD")).unwrap();

    let fixture = Fixture::new(false);
    let provider = fixture.marker.parent().unwrap();
    for (name, body) in [
        ("mission-response", valid_plan()),
        (
            "mission_generate-response",
            json!({"artifacts":[{"path":"test_project.py","content":after}]}),
        ),
        (
            "mission_review-response",
            json!({"approved":true,"reason":"fixture"}),
        ),
    ] {
        std::fs::write(provider.join(name), body.to_string()).unwrap();
    }
    let mut session = Session::with_env(
        &root,
        None,
        &[("SYNAPSE_TEST_CRASH_BEFORE_MISSION_FINALIZE", "1")],
    );
    register(&mut session, &fixture.address);
    let project = session.call(req(
        "bind",
        json!({"type":"project_register","scope":"project:a","root":workspace}),
    ));
    assert_eq!(project["ok"], true, "{project}");
    let plan = |id: &str| {
        let mut command = plan_command(id);
        command["git_edit_paths"] = json!(["test_project.py"]);
        command
    };
    std::fs::write(&path, "user edit").unwrap();
    let dirty = session.call(req("dirty", plan("dirty")));
    assert_eq!(dirty["error"]["code"], "git_target_conflict", "{dirty}");
    std::fs::write(&path, before).unwrap();
    let mut expanded = valid_plan();
    expanded["artifacts"]
        .as_array_mut()
        .unwrap()
        .push(json!({"path":"extra.txt","purpose":"Unauthorized extra output"}));
    std::fs::write(provider.join("mission-response"), expanded.to_string()).unwrap();
    let start = session.call(req("expanded-plan", plan("expanded")));
    assert_eq!(start["ok"], true, "{start}");
    assert_eq!(
        poll(&mut session, "expanded-plan")["error"],
        "invalid_mission_plan"
    );
    std::fs::write(provider.join("mission-response"), valid_plan().to_string()).unwrap();
    let start = session.call(req("plan", plan("git-edit")));
    assert_eq!(start["ok"], true, "{start}");
    assert_eq!(poll(&mut session, "plan")["status"], "succeeded");
    let proposal = session.call(req(
        "proposal",
        json!({"type":"mission_get","mission_id":"git-edit"}),
    ));
    assert_eq!(
        proposal["result"]["contract"]["actions"]
            .as_array()
            .unwrap()
            .iter()
            .any(|action| action == "artifact_replace"),
        true,
        "{proposal}"
    );
    let approval = session.call(req("approve", json!({"type":"mission_approve","mission_id":"git-edit","contract_digest":proposal["result"]["contract_digest"]})));
    assert_eq!(approval["ok"], true, "{approval}");
    std::fs::write(&path, "concurrent target edit").unwrap();
    let execute = json!({"type":"mission_execute","mission_id":"git-edit"});
    let refused = session.call(req("conflict", execute.clone()));
    assert_eq!(refused["error"]["code"], "git_base_changed", "{refused}");
    assert_eq!(
        std::fs::read_to_string(&path).unwrap(),
        "concurrent target edit"
    );
    std::fs::write(&path, before).unwrap();
    std::fs::write(&note, "concurrent unrelated note").unwrap();
    git(&["add", "--", "notes.txt"]);
    let changed_index = std::fs::read(workspace.join(".git/index")).unwrap();
    let refused = session.call(req("index-conflict", execute.clone()));
    assert_eq!(refused["error"]["code"], "git_base_changed", "{refused}");
    assert_eq!(
        std::fs::read(workspace.join(".git/index")).unwrap(),
        changed_index
    );
    std::fs::write(workspace.join(".git/index"), &index).unwrap();
    let run = session.call(req("execute", execute));
    assert_eq!(run["ok"], true, "{run}");
    wait_recovery_exit(&mut session, 89);
    assert_eq!(std::fs::read_to_string(&path).unwrap(), after);
    assert_eq!(
        std::fs::read_to_string(&note).unwrap(),
        "concurrent unrelated note"
    );
    session = Session::new(&root, None);
    let inspection = session.call(req(
        "inspect",
        json!({"type":"mission_recovery_inspect","mission_id":"git-edit"}),
    ));
    assert_eq!(inspection["ok"], true, "{inspection}");
    std::fs::write(&path, "postpublication user edit").unwrap();
    let blocked = session.call(req(
        "rollback-conflict",
        json!({"type":"mission_recovery_resolve","mission_id":"git-edit","mode":"rollback"}),
    ));
    assert_eq!(
        blocked["error"]["code"], "recovery_evidence_insufficient",
        "{blocked}"
    );
    assert_eq!(
        std::fs::read_to_string(&path).unwrap(),
        "postpublication user edit"
    );
    std::fs::write(&path, after).unwrap();
    let rollback = session.call(req(
        "rollback",
        json!({"type":"mission_recovery_resolve","mission_id":"git-edit","mode":"rollback"}),
    ));
    assert_eq!(rollback["ok"], true, "{rollback}");
    let began = Instant::now();
    for i in 0.. {
        let run = session.call(req(
            &format!("status-{i}"),
            json!({"type":"mission_run_get","mission_id":"git-edit"}),
        ));
        assert_eq!(run["ok"], true, "{run}");
        if run["result"]["status"] == "rolled_back" {
            break;
        }
        assert!(began.elapsed() < Duration::from_secs(15), "{run}");
        thread::sleep(Duration::from_millis(30));
    }
    assert_eq!(std::fs::read_to_string(&path).unwrap(), before);
    assert_eq!(
        std::fs::read_to_string(&note).unwrap(),
        "concurrent unrelated note"
    );
    assert_eq!(std::fs::read(workspace.join(".git/index")).unwrap(), index);
    assert_eq!(std::fs::read(workspace.join(".git/HEAD")).unwrap(), head);
}
