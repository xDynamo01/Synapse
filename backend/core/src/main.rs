use std::{
    env,
    io::{self, BufRead, BufReader, BufWriter, Write},
    path::PathBuf,
    sync::mpsc,
    time::Duration,
};
use synapse_core::{
    Core, Response,
    contracts::{CoreError, MAX_REQUEST_BYTES},
};

fn arguments() -> Result<(PathBuf, PathBuf, Option<String>), String> {
    let mut args = env::args_os().skip(1);
    let mut state = None;
    let mut workspace = None;
    let mut endpoint = None;
    while let Some(flag) = args.next() {
        let value = args.next().ok_or("Expected a value after each option")?;
        match flag.to_str() {
            Some("--state-dir") if state.is_none() => state = Some(PathBuf::from(value)),
            Some("--workspace") if workspace.is_none() => workspace = Some(PathBuf::from(value)),
            Some("--local-endpoint") if endpoint.is_none() => {
                endpoint = Some(value.into_string().map_err(|_| "Invalid local endpoint")?);
            }
            _ => return Err(
                "Usage: synapse-backend --state-dir PATH --workspace PATH [--local-endpoint NAME]"
                    .into(),
            ),
        }
    }
    Ok((
        state.ok_or("Missing --state-dir")?,
        workspace.ok_or("Missing --workspace")?,
        endpoint,
    ))
}

fn emit(writer: &mut impl Write, response: &Response) -> io::Result<()> {
    serde_json::to_writer(&mut *writer, response)?;
    writer.write_all(b"\n")?;
    writer.flush()
}

fn serve(core: &mut Core) -> io::Result<()> {
    let (sender, receiver) = mpsc::sync_channel(1);
    std::thread::spawn(move || {
        if let Err(error) = read_lines(io::stdin().lock(), |line| sender.send(Ok(line)).is_ok()) {
            let _ = sender.send(Err(error));
        }
    });
    let stdout = io::stdout();
    let mut writer = BufWriter::new(stdout.lock());
    loop {
        match receiver.recv_timeout(Duration::from_millis(50)) {
            Ok(line) => {
                let (line, too_large) = line?;
                process_line(core, &mut writer, &line, too_large)?;
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                // Keep the same Core writer while stdin is idle. Retain pending
                // results in Core if a transient storage error prevents commit.
                let _ = core.poll_mission();
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => return Ok(()),
        }
    }
}

fn read_lines(
    input: impl io::Read,
    mut submit: impl FnMut((Vec<u8>, bool)) -> bool,
) -> io::Result<()> {
    let mut reader = BufReader::new(input);
    let mut line = Vec::with_capacity(4096);
    let mut too_large = false;
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            if !line.is_empty() || too_large {
                submit((line, too_large));
            }
            break;
        }
        let end = available.iter().position(|b| *b == b'\n');
        let take = end.map_or(available.len(), |pos| pos + 1);
        let content_len = end.unwrap_or(take);
        if !too_large {
            // Reserve one byte for a possible CR in a CRLF line ending.
            let remaining = (MAX_REQUEST_BYTES + 1).saturating_sub(line.len());
            line.extend_from_slice(&available[..content_len.min(remaining)]);
            if content_len > remaining {
                too_large = true;
            }
        }
        reader.consume(take);
        if end.is_some() {
            if !submit((std::mem::take(&mut line), too_large)) {
                return Ok(());
            }
            too_large = false;
        }
    }
    Ok(())
}

fn process_line(
    core: &mut Core,
    writer: &mut impl Write,
    line: &[u8],
    too_large: bool,
) -> io::Result<()> {
    let response = if too_large {
        Response::failure(
            None,
            core.event_cursor(),
            CoreError::new("request_too_large", "Request exceeds 65536 bytes"),
        )
    } else {
        let line = line.strip_suffix(b"\n").unwrap_or(line);
        let line = line.strip_suffix(b"\r").unwrap_or(line);
        core.dispatch_line(line)
    };
    emit(writer, &response)
}

fn main() {
    let result = arguments().and_then(|(state, workspace, endpoint)| {
        let core = Core::open(state, workspace).map_err(|error| error.to_string())?;
        Ok((core, endpoint))
    });
    let (mut core, endpoint) = match result {
        Ok(core) => core,
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(2)
        }
    };
    let result = match endpoint {
        Some(endpoint) => serve_local(&mut core, &endpoint),
        None => serve(&mut core),
    };
    if let Err(error) = result {
        drop(core);
        eprintln!("I/O error: {error}");
        std::process::exit(1)
    }
}

#[cfg(windows)]
fn serve_local(core: &mut Core, endpoint: &str) -> io::Result<()> {
    let listener = synapse_core::local_pipe::Listener::bind(endpoint)?;
    let (submit, receive) = mpsc::sync_channel::<(Vec<u8>, bool, mpsc::SyncSender<Vec<u8>>)>(1);
    std::thread::spawn(move || -> io::Result<()> {
        loop {
            let session = listener.accept()?;
            let mut output = session.0;
            let _ = read_lines(session.0, |(line, oversized)| {
                let (reply, response) = mpsc::sync_channel(1);
                submit.send((line, oversized, reply)).is_ok()
                    && response
                        .recv()
                        .is_ok_and(|bytes| output.write_all(&bytes).is_ok())
            });
        }
    });
    loop {
        match receive.recv_timeout(Duration::from_millis(50)) {
            Ok((line, oversized, reply)) => {
                let mut bytes = Vec::new();
                process_line(core, &mut bytes, &line, oversized)?;
                let _ = reply.send(bytes);
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                let _ = core.poll_local_host();
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                return Err(io::Error::other("Local endpoint closed"));
            }
        }
    }
}

#[cfg(not(windows))]
fn serve_local(_core: &mut Core, _endpoint: &str) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "Local desktop transport is available on Windows",
    ))
}
