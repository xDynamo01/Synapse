use serde_json::{Value, json};
use std::{
    fs::File,
    io::{BufRead, BufReader, Read, Write},
    sync::mpsc::{self, Receiver, SyncSender},
    time::{SystemTime, UNIX_EPOCH},
};

pub type Reply = (&'static str, Result<Value, String>);

pub struct Connection {
    pub requests: SyncSender<(&'static str, Value)>,
    pub replies: Receiver<Reply>,
}

impl Connection {
    pub fn start(endpoint: String) -> Self {
        let (requests, input) = mpsc::sync_channel(8);
        let (output, replies) = mpsc::channel();
        std::thread::spawn(move || {
            let epoch = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos();
            for (index, (tag, command)) in input.into_iter().enumerate() {
                let id = format!("desktop-{}-{epoch}-{index}", std::process::id());
                let result = open(&endpoint)
                    .map(BufReader::new)
                    .map_err(|error| error.to_string())
                    .and_then(|mut stream| exchange(&mut stream, &id, command));
                let reply = match result {
                    Ok(value) => value,
                    Err(error) => {
                        let _ = output.send(("connection", Err(error)));
                        break;
                    }
                };
                let reply = if reply["ok"] == true {
                    Ok(reply["result"].clone())
                } else {
                    Err(format!(
                        "{} · {}",
                        reply["error"]["code"].as_str().unwrap_or("Core"),
                        reply["error"]["message"]
                            .as_str()
                            .unwrap_or("Comando recusado")
                    ))
                };
                if output.send((tag, reply)).is_err() {
                    break;
                }
            }
        });
        Self { requests, replies }
    }
}

#[cfg(windows)]
fn open(endpoint: &str) -> std::io::Result<File> {
    // Other local clients can use the host between requests. Only retry
    // opening the channel, before any bytes of a request have been sent.
    let until = std::time::Instant::now() + std::time::Duration::from_millis(500);
    loop {
        match synapse_core::local_pipe::connect(endpoint) {
            Err(error)
                if error.raw_os_error() == Some(231) && std::time::Instant::now() < until =>
            {
                std::thread::sleep(std::time::Duration::from_millis(15));
            }
            result => return result,
        }
    }
}

#[cfg(not(windows))]
fn open(_endpoint: &str) -> std::io::Result<File> {
    Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "A conexão local do desktop está disponível no Windows.",
    ))
}

fn exchange(stream: &mut BufReader<File>, id: &str, command: Value) -> Result<Value, String> {
    let mut input = stream.get_ref();
    serde_json::to_writer(
        &mut input,
        &json!({"version":1,"request_id":id,"command":command}),
    )
    .map_err(|error| error.to_string())?;
    input
        .write_all(b"\n")
        .and_then(|()| input.flush())
        .map_err(|error| error.to_string())?;
    let mut line = Vec::new();
    stream
        .take(1024 * 1024)
        .read_until(b'\n', &mut line)
        .map_err(|error| error.to_string())?;
    if line.last() != Some(&b'\n') {
        return Err("O Core encerrou a conexão ou enviou uma resposta incompleta.".into());
    }
    let reply: Value = serde_json::from_slice(&line).map_err(|error| error.to_string())?;
    if reply["version"] != 1 || reply["request_id"] != id || !reply["ok"].is_boolean() {
        return Err("A resposta do Core não corresponde à solicitação.".into());
    }
    Ok(reply)
}
