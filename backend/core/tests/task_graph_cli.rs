#![cfg(windows)]

use std::{
    io::{BufRead, BufReader, Write},
    path::Path,
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

use serde_json::{Value, json};

struct Process(Child);

impl Drop for Process {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

struct Session {
    _process: Process,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
    request: u64,
}

impl Session {
    fn new(root: &Path, python: &str, check_python: &str) -> Self {
        let workspace = root.join("workspace");
        std::fs::create_dir(&workspace).unwrap();
        // The private test copy allows independent builds to update the debug binary.
        let binaries=root.join("private-binaries");
        std::fs::create_dir_all(&binaries).unwrap();
        let executable = binaries.join("synapse-backend.exe");
        std::fs::copy(env!("CARGO_BIN_EXE_synapse-backend"), &executable).unwrap();
        let mut child = Process(
            Command::new(executable)
                .arg("--state-dir")
                .arg(root.join("state"))
                .arg("--workspace")
                .arg(workspace)
                .env("SYNAPSE_PYTHON_EXECUTABLE", python)
                .env("SYNAPSE_CHECK_PYTHON_EXECUTABLE", check_python)
                .env_remove("SYNAPSE_MANAGE_LOCAL_MODELS")
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .spawn()
                .unwrap(),
        );
        let input = child.0.stdin.take().unwrap();
        let output = BufReader::new(child.0.stdout.take().unwrap());
        Self {
            _process: child,
            input,
            output,
            request: 0,
        }
    }

    fn request(&mut self, command: Value) -> Value {
        self.request += 1;
        let value =
            json!({"version":1,"request_id":format!("fixture-{}",self.request),"command":command});
        writeln!(self.input, "{value}").unwrap();
        self.input.flush().unwrap();
        let mut line = String::new();
        self.output.read_line(&mut line).unwrap();
        let result: Value = serde_json::from_str(&line).unwrap();
        assert_eq!(result["ok"], true, "{value}: {result}");
        result["result"].clone()
    }

    fn graph(&mut self, action: &str, payload: Value) -> Value {
        self.request(json!({"type":"task_graph","action":action,"payload":payload}))
    }

    fn get_graph(&mut self, graph_id: &str) -> Value {
        self.graph("get", json!({"graph_id":graph_id}))
    }
}

fn wait_for(mut done: impl FnMut() -> bool) {
    let start = Instant::now();
    while !done() {
        assert!(
            start.elapsed() < Duration::from_secs(45),
            "fixture timed out"
        );
        thread::sleep(Duration::from_millis(40));
    }
}

fn response(path: &Path, name: &str, value: Value) {
    std::fs::write(path.join(name), value.to_string()).unwrap();
}

#[test]
#[ignore = "requires the dedicated Windows Python checker runtime"]
fn graph_pauses_then_checks_dependent_python_import_and_binds_predecessor_receipts() {
    let check_python = std::env::var("SYNAPSE_CHECK_PYTHON_EXECUTABLE").unwrap();
    let python = Command::new("py")
        .args(["-3.14", "-c", "import sys; print(sys.executable)"])
        .output()
        .unwrap();
    assert!(python.status.success());
    let python = String::from_utf8(python.stdout).unwrap();
    let root = tempfile::tempdir().unwrap();
    let provider = root.path().join("provider");
    std::fs::create_dir(&provider).unwrap();
    let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("../python/tests/fixture_server.py");
    let mut fixture = Process(
        Command::new(python.trim())
            .arg("-u")
            .arg(script)
            .arg(provider.join("marker"))
            .arg(provider.join("release"))
            .arg("normal")
            .stdout(Stdio::piped())
            .spawn()
            .unwrap(),
    );
    let mut port = String::new();
    BufReader::new(fixture.0.stdout.take().unwrap())
        .read_line(&mut port)
        .unwrap();
    let mut session = Session::new(root.path(), python.trim(), &check_python);
    session.request(json!({"type":"model_register","model":{"id":"selected","provider":"lm_studio",
        "endpoint":format!("http://127.0.0.1:{}",port.trim()),"capabilities":["chat"],"memory_bytes":1024}}));

    let workspace = root.path().join("workspace");
    session.request(json!({"type":"project_register","scope":"project:graph","root":workspace}));
    session.request(json!({"type":"chat_create","chat_id":"chat","title":"Graph fixture","scope":"project:graph"}));
    response(
        &provider,
        "mission-response",
        json!({"summary":"Write a helper and its importing Python test",
        "artifacts":[{"path":"helpers.py","purpose":"A Python helper exposing answer() returning 42"},
                     {"path":"test_helpers.py","purpose":"A unittest that imports helpers.answer"}],
        "checks":[{"kind":"python_compile","entrypoint":"helpers.py"},
                  {"kind":"python_unittest","entrypoint":"test_helpers.py"}],
        "tasks":[{"task_id":"second","objective":"Use first to write test_helpers.py","dependencies":["first"],
                  "priority":9,"artifacts":["test_helpers.py"]},
                 {"task_id":"first","objective":"Write helpers.py","dependencies":[],
                  "priority":0,"artifacts":["helpers.py"]}]}),
    );
    let started = session.request(json!({"type":"input_submit","input":{
        "chat_id":"chat","intent":"mission","scope":"project:graph","content":"Create helpers.py exposing answer() returning 42, then a unittest in test_helpers.py importing it. Validate both.",
        "model_id":"selected","review_model_id":"selected"}}));
    let job = started["job_id"].as_str().unwrap();
    let mission_id = started["mission_id"].as_str().unwrap();
    wait_for(|| {
        let result = session.request(json!({"type":"job_get","job_id":job}));
        assert!(
            matches!(result["status"].as_str(), Some("running" | "succeeded")),
            "{result}"
        );
        result["status"] == "succeeded"
    });
    let proposal = session.request(json!({"type":"mission_plan_get","mission_id":mission_id}));
    let plan = &proposal["task_graph"];
    assert_eq!(plan["state"], "draft");
    assert_eq!(plan["rfc"]["chat_id"], "chat");
    assert_eq!(plan["rfc"]["input_id"], job);
    assert_eq!(
        proposal["mission"]["contract"]["execution"]["task_graph_digest"],
        plan["digest"]
    );
    assert!(!workspace.join("helpers.py").exists());

    let hold = provider.join("mission_generate-hold");
    std::fs::write(&hold, b"").unwrap();
    response(
        &provider,
        "mission_generate-response",
        json!({"artifacts":[{"path":"helpers.py","content":"def answer():\n    return 42\n"}]}),
    );
    response(
        &provider,
        "mission_review-response",
        json!({"approved":true,"reason":"Fixture review approved"}),
    );
    let revision = json!({"graph_id":mission_id,"digest":plan["digest"]});
    let activated = session.request(json!({"type":"mission_approve","mission_id":mission_id,"contract_digest":proposal["mission"]["contract_digest"]}));
    assert_eq!(
        activated["newly_approved"],
        json!([
            plan["tasks"][0]["task"]["mission_id"],
            plan["tasks"][1]["task"]["mission_id"]
        ])
    );
    wait_for(|| provider.join("mission_generate-post").exists());
    assert_eq!(session.graph("pause", revision.clone())["state"], "pausing");
    std::fs::remove_file(&hold).unwrap();
    wait_for(|| {
        let state = session.get_graph(mission_id);
        assert!(
            !matches!(
                state["tasks"][1]["status"].as_str(),
                Some("failed" | "receipt_invalid" | "recovery_required")
            ),
            "{state}"
        );
        state["tasks"][1]["status"] == "passed"
    });
    assert_eq!(
        std::fs::read_to_string(workspace.join("helpers.py")).unwrap(),
        "def answer():\n    return 42\n"
    );
    assert!(!workspace.join("test_helpers.py").exists());

    response(
        &provider,
        "mission_generate-response",
        json!({"artifacts":[{"path":"test_helpers.py","content":"import unittest\nfrom helpers import answer\nclass AnswerTest(unittest.TestCase):\n    def test_answer(self):\n        self.assertEqual(answer(), 42)\n"}]}),
    );
    assert_eq!(session.graph("resume", revision)["state"], "active");
    wait_for(|| {
        let state = session.get_graph(mission_id);
        assert!(
            !matches!(
                state["tasks"][0]["status"].as_str(),
                Some("failed" | "receipt_invalid" | "recovery_required")
            ),
            "{state}"
        );
        state["settled"] == true
    });
    assert_eq!(
        std::fs::read_to_string(workspace.join("test_helpers.py")).unwrap(),
        "import unittest\nfrom helpers import answer\nclass AnswerTest(unittest.TestCase):\n    def test_answer(self):\n        self.assertEqual(answer(), 42)\n"
    );
    let request: Value =
        serde_json::from_slice(&std::fs::read(provider.join("mission_generate-post")).unwrap())
            .unwrap();
    let prompt: Value = serde_json::from_str(
        request["messages"].as_array().unwrap().last().unwrap()["content"]
            .as_str()
            .unwrap(),
    )
    .unwrap();
    assert!(
        request["messages"]
            .to_string()
            .contains("Sealed context handoff")
    );
    let finished = session.get_graph(mission_id);
    assert_eq!(finished["state"], "integrated", "{finished}");
    let review_request: Value =
        serde_json::from_slice(&std::fs::read(provider.join("mission_review-post")).unwrap())
            .unwrap();
    assert!(
        review_request["messages"]
            .to_string()
            .contains("Verified predecessor artifacts for independent review")
    );
    assert!(
        review_request["messages"]
            .to_string()
            .contains("def answer()")
    );
    std::fs::write(
        workspace.join("helpers.py"),
        "def answer():\n    return 13\n",
    )
    .unwrap();
    let changed = session.get_graph(mission_id);
    assert_eq!(
        changed["tasks"][1]["status"], "receipt_invalid",
        "{changed}"
    );
    assert_eq!(
        changed["tasks"][0]["status"], "receipt_invalid",
        "{changed}"
    );
    std::fs::write(
        workspace.join("helpers.py"),
        "def answer():\n    return 42\n",
    )
    .unwrap();
    assert_eq!(session.get_graph(mission_id)["state"], "integrated");
    let connection = rusqlite::Connection::open(root.path().join("state/core.sqlite3")).unwrap();
    let dependent = plan["tasks"][0]["task"]["mission_id"].as_str().unwrap();
    let bound: Vec<(String,String)> = connection.prepare(
        "SELECT c.check_digest,d.digest FROM project_checks c JOIN task_graph_check_inputs d ON d.check_id=c.id WHERE c.mission_id=?1 ORDER BY c.id"
    ).unwrap().query_map([dependent], |row| Ok((row.get(0)?,row.get(1)?))).unwrap().collect::<Result<_,_>>().unwrap();
    assert_eq!(
        bound.len(),
        2,
        "both candidate check and publication check must bind dependencies"
    );
    assert_eq!(bound[0], bound[1]);
    connection.execute("UPDATE task_graph_check_inputs SET digest='stale' WHERE check_id=(SELECT id FROM project_checks WHERE mission_id=?1 LIMIT 1)", [dependent]).unwrap();
    let tampered = session.get_graph(mission_id);
    assert_eq!(
        tampered["tasks"][0]["status"], "receipt_invalid",
        "{tampered}"
    );

    let history =
        session.request(json!({"type":"chat_get","chat_id":"chat","after":0,"limit":100}));
    assert!(
        history["messages"]
            .as_array()
            .unwrap()
            .iter()
            .any(|message| message["role"] == "assistant"
                && message["content"]
                    .as_str()
                    .is_some_and(|content| content.contains("integrada"))),
        "{history}"
    );
    assert_eq!(prompt["dependency_inputs"][0]["task_id"], "first");
    assert_eq!(
        prompt["dependency_inputs"][0]["artifacts"][0]["content"],
        "def answer():\n    return 42\n"
    );
    // A failed Swarm revision must retry exact authority and restore the real regime.
    response(
        &provider,
        "mission-response",
        json!({"summary":"Two recoverable JSON outputs",
        "artifacts":[{"path":"retry_first.json","purpose":"First JSON"},{"path":"retry_second.json","purpose":"Dependent JSON"}],
        "checks":[{"kind":"json_validate","entrypoint":"retry_first.json"},{"kind":"json_validate","entrypoint":"retry_second.json"}],
        "tasks":[{"task_id":"first","objective":"Create first JSON","dependencies":[],"priority":0,"artifacts":["retry_first.json"]},
                 {"task_id":"second","objective":"Use first to create second","dependencies":["first"],"priority":1,"artifacts":["retry_second.json"]}]}),
    );
    response(
        &provider,
        "mission_generate-response",
        json!({"artifacts":[{"path":"wrong.json","content":"{}"}]}),
    );
    let retry_input=session.request(json!({"type":"input_submit","input":{
        "chat_id":"chat","intent":"mission","scope":"project:graph","content":"Create retry_first.json and retry_second.json as dependent tasks.","model_id":"selected","review_model_id":"selected"}}));
    let retry_job = retry_input["job_id"].as_str().unwrap();
    let retry_root = retry_input["mission_id"].as_str().unwrap();
    wait_for(|| {
        session.request(json!({"type":"job_get","job_id":retry_job}))["status"] == "succeeded"
    });
    let retry_plan = session.request(json!({"type":"mission_plan_get","mission_id":retry_root}));
    session.request(json!({"type":"mission_approve","mission_id":retry_root,"contract_digest":retry_plan["mission"]["contract_digest"],"swarm":"direct"}));
    wait_for(|| session.get_graph(retry_root)["state"] == "failed");
    let failed_settings =
        session.request(json!({"type":"orchestration","action":"settings_get","payload":{}}));
    assert_eq!(failed_settings["execution_regime"], "NORMAL");
    assert_eq!(failed_settings["transition"]["status"], "failed");
    let original = session.get_graph(retry_root);
    let revision = json!({"graph_id":retry_root,"digest":original["digest"]});
    session.graph("pause", revision.clone());
    let tasks: Vec<_> = original["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .map(|entry| {
            let mut task = entry["task"].clone();
            task.as_object_mut().unwrap().remove("contract_digest");
            task
        })
        .collect();
    let replanned = session.graph(
        "replan",
        json!({"graph_id":retry_root,"digest":original["digest"],"tasks":tasks}),
    );
    assert_eq!(replanned["state"], "draft");
    assert_ne!(
        replanned["tasks"][0]["task"]["mission_id"],
        original["tasks"][0]["task"]["mission_id"]
    );
    assert!(!workspace.join("retry_first.json").exists());
    response(
        &provider,
        "mission_generate-map",
        json!({
        "retry_first.json":{"artifacts":[{"path":"retry_first.json","content":"{\"step\":1}"}]},
        "retry_second.json":{"artifacts":[{"path":"retry_second.json","content":"{\"step\":2}"}]}}),
    );
    std::fs::write(&hold, b"").unwrap();
    session.graph(
        "activate",
        json!({"graph_id":retry_root,"digest":replanned["digest"]}),
    );
    let active =
        session.request(json!({"type":"orchestration","action":"settings_get","payload":{}}));
    assert_eq!(active["execution_regime"], "SWARM", "{active}");
    assert_eq!(active["transition"]["status"], "active");
    std::fs::remove_file(&hold).unwrap();
    wait_for(|| session.get_graph(retry_root)["state"] == "integrated");
    let ended =
        session.request(json!({"type":"orchestration","action":"settings_get","payload":{}}));
    assert_eq!(ended["execution_regime"], "NORMAL");
    assert_eq!(ended["transition"]["status"], "ended");
}
