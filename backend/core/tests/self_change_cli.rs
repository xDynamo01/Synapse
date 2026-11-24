#![cfg(windows)]
//! Actual CLI negatives never open consent dialogs or alter the real product.
use serde_json::{Value, json};
use std::{
    io::Write,
    process::{Command, Stdio},
};
use tempfile::TempDir;
fn run(root: &TempDir, commands: &[Value]) -> Vec<Value> {
    let mut child = Command::new(env!("CARGO_BIN_EXE_synapse-backend"))
        .args([
            "--state-dir",
            root.path().join("state").to_str().unwrap(),
            "--workspace",
            root.path().join("workspace").to_str().unwrap(),
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut input = child.stdin.take().unwrap();
    for command in commands {
        use sha2::{Digest, Sha256};
        let digest = Sha256::digest(serde_json::to_vec(command).unwrap())
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        writeln!(
            input,
            "{}",
            json!({"version":1,"request_id":format!("r-{digest}"),"command":command})
        )
        .unwrap();
    }
    drop(input);
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    String::from_utf8(output.stdout)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect()
}
fn fixture() -> (TempDir, Value) {
    use sha2::{Digest, Sha256};
    let root = tempfile::tempdir().unwrap();
    let workspace = root.path().join("workspace");
    std::fs::create_dir(&workspace).unwrap();
    std::fs::write(workspace.join("module.rs"), "before\n").unwrap();
    let base = Sha256::digest(b"before\n")
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>();
    let proposal = json!({"id":"self-1","context":{"conversation":"chat-a","project":"project-a","mission":"mission-a","swarm":"swarm-a"},"proposer_agent":"untrusted-agent","root":workspace,"path":"module.rs","base_version":env!("CARGO_PKG_VERSION"),"base_digest":base,"content":"SECRET_CANARY_NEW\n"});
    (root, proposal)
}
#[test]
fn actual_cli_binds_all_contexts_and_rejects_forged_human_approval() {
    let (root, proposal) = fixture();
    let reply = run(
        &root,
        &[json!({"type":"self_change","action":"propose","payload":proposal})],
    );
    assert_eq!(reply[0]["ok"], true, "{reply:?}");
    let reference = json!({"id":"self-1","context":proposal["context"],"change_digest":reply[0]["result"]["change_digest"]});
    let mut commands = Vec::new();
    for key in ["conversation", "project", "mission", "swarm"] {
        let mut foreign = reference.clone();
        foreign["context"][key] = json!("foreign");
        commands.push(json!({"type":"self_change","action":"get","payload":foreign}));
    }
    let mut forged = reference.clone();
    forged["principal"] = json!("human-owner");
    forged["approved"] = json!(true);
    commands.push(json!({"type":"self_change","action":"approve","payload":forged}));
    commands.push(json!({"type":"self_change","action":"approve","payload":reference}));
    commands.push(json!({"type":"self_change","action":"publish","payload":reference}));
    let replies = run(&root, &commands);
    assert!(replies.iter().all(|r| r["ok"] == false), "{replies:?}");
    let diagnostics = run(
        &root,
        &[
            json!({"type":"self_change","action":"get","payload":reference}),
            json!({"type":"events_read","after":0,"limit":100}),
        ],
    );
    assert!(
        diagnostics.iter().all(|r| r["ok"] == true),
        "{diagnostics:?}"
    );
    assert!(
        diagnostics[0]["result"]["proposer_principal"]
            .as_str()
            .unwrap()
            .starts_with("S-1-")
    );
    assert!(
        !serde_json::to_string(&diagnostics)
            .unwrap()
            .contains("SECRET_CANARY")
    );
    assert!(
        !serde_json::to_string(&replies)
            .unwrap()
            .contains("SECRET_CANARY")
    );
    assert_eq!(
        std::fs::read(root.path().join("workspace/module.rs")).unwrap(),
        b"before\n"
    );
}
#[test]
fn actual_cli_generic_mission_approval_never_grants_self_change() {
    let (root, proposal) = fixture();
    let setup = run(
        &root,
        &[
            json!({"type":"self_change","action":"propose","payload":proposal}),
            json!({"type":"mission_propose","mission_id":"generic","contract":{"version":1,"scope":"project:a","objective":"Generic fixture work","actions":["artifact_replace"],"resources":["module.rs"],"rollback":"verified backup"}}),
        ],
    );
    assert!(setup.iter().all(|r| r["ok"] == true), "{setup:?}");
    let reference = json!({"id":"self-1","context":proposal["context"],"change_digest":setup[0]["result"]["change_digest"]});
    let replies = run(
        &root,
        &[
            json!({"type":"mission_approve","mission_id":"generic","contract_digest":setup[1]["result"]["contract_digest"]}),
            json!({"type":"self_change","action":"prepare","payload":reference}),
            json!({"type":"self_change","action":"publish","payload":reference}),
        ],
    );
    assert_eq!(replies[0]["ok"], true, "{replies:?}");
    assert_eq!(replies[1]["ok"], false);
    assert_eq!(replies[2]["ok"], false);
    assert_eq!(
        std::fs::read(root.path().join("workspace/module.rs")).unwrap(),
        b"before\n"
    );
}
#[test]
fn actual_cli_protected_source_cannot_be_registered_as_generic_project() {
    let (root, _) = fixture();
    let source = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let reply = run(
        &root,
        &[json!({"type":"project_register","scope":"project:forged-source","root":source})],
    );
    assert_eq!(reply[0]["ok"], false, "{reply:?}");
}

#[test]
fn runtime_configuration_is_protected_without_blocking_sibling_workspace(){
    let (root,_)=fixture();
    let config=root.path().join("configuration");
    let workspace=config.join("workspace");
    std::fs::create_dir_all(&workspace).unwrap();
    std::fs::write(config.join("voice-runtime.json"),"{}").unwrap();
    let frames=[
        json!({"version":1,"request_id":"config","command":{"type":"project_register","scope":"project:config","root":config}}),
        json!({"version":1,"request_id":"workspace","command":{"type":"project_register","scope":"project:workspace","root":workspace}}),
    ];
    let mut child=Command::new(env!("CARGO_BIN_EXE_synapse-backend"))
        .args(["--state-dir",root.path().join("state").to_str().unwrap(),"--workspace",root.path().join("workspace").to_str().unwrap()])
        .env("SYNAPSE_CONFIG_ROOT",&config)
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
    let mut input=child.stdin.take().unwrap();
    for frame in frames {writeln!(input,"{frame}").unwrap();}drop(input);
    let output=child.wait_with_output().unwrap();assert!(output.status.success());
    let replies:Vec<Value>=String::from_utf8(output.stdout).unwrap().lines().map(|line|serde_json::from_str(line).unwrap()).collect();
    assert_eq!(replies[0]["ok"],false,"{replies:?}");
    assert_eq!(replies[1]["ok"],true,"{replies:?}");
    assert_eq!(std::fs::read_to_string(config.join("voice-runtime.json")).unwrap(),"{}");
}
