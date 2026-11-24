use serde_json::{Value, json};
use std::{
    env, fs, io,
    net::{SocketAddr, TcpStream},
    os::windows::process::CommandExt,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

const NO_WINDOW: u32 = 0x08000000;
const MODEL_ENDPOINT: &str = "http://127.0.0.1:1234/v1";

pub struct Runtime {
    child: Child,
    pub endpoint: String,
    pub suggested_model: Option<Value>,
}

impl Drop for Runtime {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn background(program: impl AsRef<std::ffi::OsStr>) -> Command {
    let mut command = Command::new(program);
    command.creation_flags(NO_WINDOW).stdin(Stdio::null());
    command
}

fn python() -> Option<PathBuf> {
    if let Some(path) = env::var_os("SYNAPSE_PYTHON_EXECUTABLE") {
        let path = PathBuf::from(path);
        return path.is_file().then_some(path);
    }
    let output = background("py")
        .args(["-3.14", "-c", "import sys; print(sys.executable)"])
        .output()
        .ok()?;
    let path = PathBuf::from(std::str::from_utf8(&output.stdout).ok()?.trim());
    (output.status.success() && path.is_file()).then_some(path)
}

fn local_models() -> Option<Value> {
    let path = env::var_os("SYNAPSE_LMS_EXECUTABLE")
        .map(PathBuf::from)
        .or_else(|| {
            env::var_os("USERPROFILE").map(|home| PathBuf::from(home).join(".lmstudio/bin/lms.exe"))
        })?;
    if !path.is_file() {
        return None;
    }
    let output = background(&path).args(["ls", "--json"]).output().ok()?;
    if !output.status.success() {
        return None;
    }
    let downloaded: Vec<Value> = serde_json::from_slice(&output.stdout).ok()?;
    let address = SocketAddr::from(([127, 0, 0, 1], 1234));
    if TcpStream::connect_timeout(&address, Duration::from_millis(400)).is_err() {
        let output = background(&path)
            .args(["server", "start", "--bind", "127.0.0.1", "--port", "1234"])
            .output()
            .ok()?;
        if !output.status.success() {
            return None;
        }
    }
    let llms: Vec<_> = downloaded
        .iter()
        .filter(|entry| entry["type"] == "llm")
        .collect();
    let resident = background(&path)
        .args(["ps", "--json"])
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| serde_json::from_slice::<Vec<Value>>(&output.stdout).ok());
    let choice = resident
        .as_ref()
        .and_then(|models| {
            models.iter().find_map(|model| {
                llms.iter()
                    .copied()
                    .find(|entry| entry["modelKey"] == model["modelKey"])
            })
        })
        .or_else(|| {
            llms.iter()
                .copied()
                .find(|entry| entry["modelKey"] == "qwen2.5-coder-7b-instruct")
        })
        .or_else(|| {
            llms.iter()
                .copied()
                .min_by_key(|entry| entry["sizeBytes"].as_u64().unwrap_or(u64::MAX))
        })?;
    Some(json!({
        "id": choice["modelKey"].as_str()?,
        "provider": "lm_studio",
        "endpoint": MODEL_ENDPOINT,
        "capabilities": ["chat"],
        "memory_bytes": choice["sizeBytes"].as_u64()?,
        "generation": {"max_output_tokens": 768, "timeout_ms": 120000, "reasoning_effort": "none"}
    }))
}

fn backend(near: &Path) -> Option<PathBuf> {
    if let Some(path) = env::var_os("SYNAPSE_CORE_EXECUTABLE") {
        let path = PathBuf::from(path);
        return path.is_file().then_some(path);
    }
    [
        near.join("synapse-backend.exe"),
        near.join("target/release/synapse-backend.exe"),
        near.join("target/debug/synapse-backend.exe"),
    ]
    .into_iter()
    .find(|path| path.is_file())
}

fn check_python(near: &Path) -> Option<PathBuf> {
    [
        near.join("check-runtime/runtime/python.exe"),
        near.join("../check-runtime/runtime/python.exe"),
        near.join("target/check-runtime/runtime/python.exe"),
        near.join("../windows-check-python/runtime/python.exe"),
        near.join("target/windows-check-python/runtime/python.exe"),
    ]
    .into_iter()
    .find(|path| {
        path.is_file()
            && path
                .parent()
                .and_then(Path::parent)
                .is_some_and(|folder| folder.join("runtime-manifest.json").is_file())
    })
}

fn native_toolchain(command: &mut Command, path: &Path) -> Result<(), String> {
    use std::os::windows::fs::MetadataExt;
    let metadata = match fs::symlink_metadata(path) {
        Ok(value) => value,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
        Err(_) => return Err("Configuração das ferramentas locais indisponível.".into()),
    };
    if !metadata.is_file() || metadata.file_attributes() & 0x400 != 0 || metadata.len() > 16384 {
        return Err("Configuração das ferramentas locais inválida.".into());
    }
    let value: Value = serde_json::from_slice(
        &fs::read(path).map_err(|_| "Configuração das ferramentas locais indisponível.")?,
    )
    .map_err(|_| "Configuração das ferramentas locais inválida.")?;
    let fields = value
        .as_object()
        .ok_or("Configuração das ferramentas locais inválida.")?;
    for (key, value) in fields {
        if ![
            "SYNAPSE_RUNNER_RUST_SYSROOT",
            "SYNAPSE_RUNNER_VC_X64_LIB",
            "SYNAPSE_RUNNER_SDK_UM_X64_LIB",
            "SYNAPSE_RUNNER_SDK_UCRT_X64_LIB",
        ]
        .contains(&key.as_str())
        {
            return Err("Campo desconhecido na configuração das ferramentas locais.".into());
        }
        let path = value
            .as_str()
            .map(Path::new)
            .filter(|path| path.is_absolute() && path.is_dir())
            .ok_or("Pasta das ferramentas locais indisponível.")?;
        if env::var_os(key).is_none() {
            command.env(key, path);
        }
    }
    Ok(())
}

pub fn start() -> Result<Runtime, String> {
    let exe = env::current_exe().map_err(|e| e.to_string())?;
    let binary = backend(exe.parent().ok_or("Pasta do executável indisponível.")?)
        .ok_or("Core não encontrado. Compile synapse-core ou configure SYNAPSE_CORE_EXECUTABLE.")?;
    let base = PathBuf::from(env::var_os("LOCALAPPDATA").ok_or("LOCALAPPDATA indisponível.")?)
        .join("Synapse");
    let state = env::var_os("SYNAPSE_STATE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| base.join("desktop-slint-state-0.3"));
    let workspace = env::var_os("SYNAPSE_WORKSPACE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| base.join("workspace"));
    for directory in [&state, &workspace] {
        fs::create_dir_all(directory)
            .map_err(|error| format!("{} · {error}", directory.display()))?;
    }
    let python =
        python().ok_or("Python 3.14 não encontrado. Configure SYNAPSE_PYTHON_EXECUTABLE.")?;
    let suggested_model = local_models();
    let endpoint = format!("slint-local-{}", std::process::id());
    let log = fs::File::create(state.join(format!("desktop-core-{}.log", std::process::id())))
        .map_err(|error| error.to_string())?;
    let mut command = background(binary);
    let config_root = env::var_os("SYNAPSE_CONFIG_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| base.clone());
    native_toolchain(&mut command, &config_root.join("native-toolchain.json"))?;
    if env::var_os("SYNAPSE_CHECK_PYTHON_EXECUTABLE").is_none() {
        if let Some(check_python) = check_python(exe.parent().unwrap()) {
            command.env("SYNAPSE_CHECK_PYTHON_EXECUTABLE", check_python);
        }
    }
    command
        .arg("--state-dir")
        .arg(&state)
        .arg("--workspace")
        .arg(&workspace)
        .args(["--local-endpoint", &endpoint])
        .env("SYNAPSE_PYTHON_EXECUTABLE", python)
        .stdout(Stdio::null())
        .stderr(log);
    if suggested_model.is_some() && env::var_os("SYNAPSE_MANAGE_LOCAL_MODELS").is_none() {
        command.env("SYNAPSE_MANAGE_LOCAL_MODELS", "1");
    }
    let child = command
        .spawn()
        .map_err(|error| format!("Não foi possível iniciar o Core · {error}"))?;
    let mut runtime = Runtime {
        child,
        endpoint,
        suggested_model,
    };
    let deadline = Instant::now() + Duration::from_secs(7);
    loop {
        match synapse_core::local_pipe::connect(&runtime.endpoint) {
            Ok(pipe) => {
                drop(pipe);
                return Ok(runtime);
            }
            Err(error)
                if matches!(error.raw_os_error(), Some(2 | 231)) && Instant::now() < deadline => {}
            Err(error) => {
                return Err(format!(
                    "Canal do Core indisponível · {error}. Log em {}",
                    state.display()
                ));
            }
        }
        if let Some(status) = runtime
            .child
            .try_wait()
            .map_err(|error: io::Error| error.to_string())?
        {
            return Err(format!(
                "O Core encerrou na inicialização ({status}). Log em {}",
                state.display()
            ));
        }
        thread::sleep(Duration::from_millis(70));
    }
}
