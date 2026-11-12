#![cfg(windows)]

use serde_json::{Value, json};
use std::{
    fs::File,
    io::{BufRead, BufReader, Write},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use synapse_core::local_pipe;
use tempfile::TempDir;

struct Host(Child);

impl Drop for Host {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn connect(endpoint: &str) -> BufReader<File> {
    let began = Instant::now();
    loop {
        match local_pipe::connect(endpoint) {
            Ok(file) => return BufReader::new(file),
            Err(error) if began.elapsed() >= Duration::from_secs(10) => panic!("{error}"),
            Err(_) => thread::sleep(Duration::from_millis(25)),
        }
    }
}

fn call(stream: &mut BufReader<File>, id: &str, command: &Value) -> Value {
    let request = json!({"version":1,"request_id":id,"command":command});
    writeln!(stream.get_ref(), "{request}").unwrap();
    let mut line = String::new();
    stream.read_line(&mut line).unwrap();
    let reply: Value = serde_json::from_str(&line).unwrap();
    assert_eq!(reply["request_id"], id);
    assert_eq!(reply["ok"], true, "{reply}");
    reply
}

#[test]
fn local_client_reconnects_to_the_same_core_without_repeating_effects() {
    let dirs = TempDir::new().unwrap();
    let workspace = dirs.path().join("workspace");
    std::fs::create_dir(&workspace).unwrap();
    let epoch = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let endpoint = format!("test-{}-{epoch}", std::process::id());
    let mut host = Host(
        Command::new(env!("CARGO_BIN_EXE_synapse-backend"))
            .arg("--state-dir")
            .arg(dirs.path().join("state"))
            .arg("--workspace")
            .arg(workspace)
            .arg("--local-endpoint")
            .arg(&endpoint)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .spawn()
            .unwrap(),
    );
    let mut client = connect(&endpoint);
    call(
        &mut client,
        "chat",
        &json!({"type":"chat_create","chat_id":"chat","title":"History","scope":"project:demo"}),
    );
    let append = json!({"type":"message_append","chat_id":"chat","message_id":"msg","role":"user","content":"salve"});
    let original = call(&mut client, "append", &append);
    drop(client);

    let mut client = connect(&endpoint);
    assert!(host.0.try_wait().unwrap().is_none());
    assert_eq!(call(&mut client, "append", &append), original);
    let history = call(
        &mut client,
        "history",
        &json!({"type":"chat_get","chat_id":"chat"}),
    );
    assert_eq!(history["result"]["messages"].as_array().unwrap().len(), 1);
    let events = call(
        &mut client,
        "events",
        &json!({"type":"events_read","after":0,"limit":20}),
    );
    assert!(
        events["result"]["events"]
            .as_array()
            .unwrap()
            .iter()
            .any(|event| event["kind"] == "chat_created")
    );
}
