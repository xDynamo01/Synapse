use std::{
    env,
    io::{self, BufRead, BufReader, BufWriter, Write},
    path::PathBuf,
};
use synapse_core::{
    Core, Response,
    contracts::{CoreError, MAX_REQUEST_BYTES},
};

fn arguments() -> Result<(PathBuf, PathBuf), String> {
    let mut args = env::args_os().skip(1);
    let mut state = None;
    let mut workspace = None;
    while let Some(flag) = args.next() {
        let value = args.next().ok_or("Expected a value after each option")?;
        match flag.to_str() {
            Some("--state-dir") if state.is_none() => state = Some(PathBuf::from(value)),
            Some("--workspace") if workspace.is_none() => workspace = Some(PathBuf::from(value)),
            _ => return Err("Usage: synapse-backend --state-dir PATH --workspace PATH".into()),
        }
    }
    Ok((
        state.ok_or("Missing --state-dir")?,
        workspace.ok_or("Missing --workspace")?,
    ))
}

fn emit(writer: &mut impl Write, response: &Response) -> io::Result<()> {
    serde_json::to_writer(&mut *writer, response)?;
    writer.write_all(b"\n")?;
    writer.flush()
}

fn serve(core: &mut Core) -> io::Result<()> {
    let stdin = io::stdin();
    let mut reader = BufReader::new(stdin.lock());
    let stdout = io::stdout();
    let mut writer = BufWriter::new(stdout.lock());
    let mut line = Vec::with_capacity(4096);
    let mut too_large = false;
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            if !line.is_empty() || too_large {
                process_line(core, &mut writer, &line, too_large)?;
            }
            break;
        }
        let end = available.iter().position(|b| *b == b'\n');
        let take = end.map_or(available.len(), |pos| pos + 1);
        let content_len = end.unwrap_or(take);
        if !too_large {
            let remaining = MAX_REQUEST_BYTES.saturating_sub(line.len());
            line.extend_from_slice(&available[..content_len.min(remaining)]);
            if content_len > remaining {
                too_large = true;
            }
        }
        reader.consume(take);
        if end.is_some() {
            process_line(core, &mut writer, &line, too_large)?;
            line.clear();
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
    let result = arguments().and_then(|(state, workspace)| {
        Core::open(state, workspace).map_err(|error| error.to_string())
    });
    let mut core = match result {
        Ok(core) => core,
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(2)
        }
    };
    if let Err(error) = serve(&mut core) {
        eprintln!("I/O error: {error}");
        std::process::exit(1)
    }
}
