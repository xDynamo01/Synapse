//! Owns staged inputs, a fresh profile and the native execution handoff.
use std::{
    fs::{self, OpenOptions},
    io::Write,
    os::windows::ffi::{OsStrExt, OsStringExt},
    path::{Component, Path, PathBuf, Prefix},
    sync::mpsc::{Receiver, RecvTimeoutError, SyncSender},
    time::{Duration, Instant},
};

use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use super::{Control, Event, Launch, Outcome, assets, python, rust, windows};
use crate::{contracts::CheckKind, store};

pub(crate) struct Tools(Config);
enum Config {
    Python(PathBuf),
    Rust(assets::RustConfig),
}

impl Tools {
    pub(crate) fn configure(kind: &CheckKind) -> Result<Self, &'static str> {
        let path = |name| {
            std::env::var_os(name)
                .map(PathBuf::from)
                .filter(|value| value.is_absolute())
                .ok_or("toolchain_unavailable")
        };
        Ok(Self(match kind {
            CheckKind::RustTest => Config::Rust(assets::RustConfig {
                sysroot: path("SYNAPSE_RUNNER_RUST_SYSROOT")?,
                vc_x64_lib: path("SYNAPSE_RUNNER_VC_X64_LIB")?,
                sdk_um_x64_lib: path("SYNAPSE_RUNNER_SDK_UM_X64_LIB")?,
                sdk_ucrt_x64_lib: path("SYNAPSE_RUNNER_SDK_UCRT_X64_LIB")?,
            }),
            _ => Config::Python(path("SYNAPSE_CHECK_PYTHON_EXECUTABLE")?),
        }))
    }
}

enum Staged {
    Python(PathBuf),
    Rust(assets::RustAssets),
}

fn prepare(
    config: &Config,
    runtime: &Path,
    control: &Control,
) -> Result<(Staged, String), &'static str> {
    let result = match config {
        Config::Python(executable) => assets::verified_python(executable, runtime, control)
            .map(|(executable, digest)| (Staged::Python(executable), digest)),
        Config::Rust(config) => assets::rust(config, runtime, control).map(|assets| {
            let digest = assets.digest.clone();
            (Staged::Rust(assets), digest)
        }),
    };
    result.map_err(|error| match error.as_str() {
        "cancelled" => "cancelled",
        "preparation_timeout" => "preparation_timeout",
        "asset_limit" => "asset_limit",
        _ => "toolchain_unavailable",
    })
}

fn authorize(control: &Control, authorization: &Receiver<()>) -> Result<(), &'static str> {
    loop {
        control.preparation().map_err(|error| failure(&error))?;
        match authorization.recv_timeout(Duration::from_millis(25)) {
            Ok(()) => return control.preparation().map_err(|error| failure(&error)),
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => return Err("cancelled"),
        }
    }
}

fn dos_run_root(path: &Path) -> Option<PathBuf> {
    let Some(Component::Prefix(prefix)) = path.components().next() else {
        return None;
    };
    match prefix.kind() {
        Prefix::Disk(_) if path.is_absolute() => Some(path.to_owned()),
        Prefix::VerbatimDisk(_) if path.is_absolute() => {
            let wide: Vec<_> = path.as_os_str().encode_wide().skip(4).collect();
            let converted = PathBuf::from(std::ffi::OsString::from_wide(&wide));
            (converted.parent()?.canonicalize().ok()?.as_path() == path.parent()?)
                .then_some(converted)
        }
        _ => None,
    }
}

pub(super) fn run(
    mut launch: Launch,
    control: &Control,
    sender: &SyncSender<Event>,
    authorization: &Receiver<()>,
) -> Outcome {
    let Some(root) = dos_run_root(&launch.root) else {
        return Outcome {
            receipt: None,
            error: Some("run_path_unavailable"),
            cleanup_complete: true,
        };
    };
    launch.root = root;
    let started = Instant::now();
    let mut profile = None;
    let mut owned_root = None;
    let operation = (|| {
        control.preparation().map_err(|error| failure(&error))?;
        windows::create_private_directory(&launch.root).map_err(|_| "run_create_failed")?;
        owned_root = Some(assets::sealed_directory(&launch.root).and_then(|handle| {
            let identity = assets::directory_identity(&handle)?;
            Ok((handle, identity))
        }));
        if !matches!(owned_root, Some(Ok(_))) {
            return Err("run_identity_failed");
        }
        let runtime = launch.root.join("runtime");
        let project = launch.root.join("project");
        let output = launch.root.join("output");
        let temp = launch.root.join("temp");
        for path in [&runtime, &project, &output, &temp] {
            fs::create_dir(path).map_err(|_| "run_create_failed")?;
        }
        let package = windows::Profile::create(&launch.profile_name)
            .map_err(|_| "containment_unavailable")?;
        let package = profile.insert(package);
        for path in [&launch.root, &runtime, &project] {
            package
                .protect(path, false)
                .map_err(|_| "containment_unavailable")?;
        }
        for path in [&output, &temp] {
            package
                .protect(path, true)
                .map_err(|_| "containment_unavailable")?;
        }
        let (staged, mut digest) = prepare(&launch.tools.0, &runtime, control)?;
        if let Some(script) = python::adapter_source(launch.recipe.kind) {
            digest = store::digest(&(digest, launch.recipe.kind, script))
                .map_err(|_| "toolchain_unavailable")?;
        }
        sender
            .send(Event::Prepared(digest))
            .map_err(|_| "cancelled")?;
        authorize(control, authorization)?;

        for artifact in &launch.artifacts {
            control.preparation().map_err(|error| failure(&error))?;
            let relative = Path::new(&artifact.path);
            if relative.file_name() != Some(relative.as_os_str()) || artifact.path.contains(':') {
                return Err("invalid_artifact");
            }
            OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(project.join(relative))
                .and_then(|mut file| file.write_all(artifact.content.as_bytes()))
                .map_err(|_| "artifact_stage_failed")?;
        }
        let entrypoint = Path::new(&launch.recipe.entrypoint);
        match staged {
            Staged::Python(interpreter) if launch.recipe.kind == CheckKind::PythonUnittest => {
                python::run(
                    package,
                    &interpreter,
                    &project,
                    entrypoint,
                    &output,
                    &temp,
                    control,
                )
                .map(|receipts| {
                    receipts
                        .into_iter()
                        .zip(["compile", "test"])
                        .map(|(r, p)| (p, r))
                        .collect::<Vec<_>>()
                })
            }
            Staged::Python(interpreter) => python::run_adapter(
                package,
                &interpreter,
                python::AdapterRun {
                    kind: launch.recipe.kind,
                    project: &project,
                    entrypoint,
                    output: &output,
                    temporary: &temp,
                },
                control,
            )
            .map(|phase| vec![phase]),
            Staged::Rust(tools) => rust::run(
                package,
                &tools,
                rust::RustRun {
                    project: &project,
                    source: &project.join(entrypoint),
                    output: &output,
                    temp: &temp,
                },
                control,
            )
            .map(|receipt| {
                let mut phases = vec![("emit", receipt.emission)];
                phases.extend(receipt.link.map(|value| ("link", value)));
                phases.extend(receipt.test.map(|value| ("test", value)));
                phases
            }),
        }
        .map_err(|error| failure(&error))
    })();

    if matches!(operation, Err("descendant_cleanup_failed")) {
        if let Some(profile) = profile {
            profile.preserve();
        }
        return Outcome {
            receipt: None,
            error: Some("descendant_cleanup_failed"),
            cleanup_complete: false,
        };
    }
    let profile_cleaned = profile.is_none_or(|value| value.remove().is_ok());
    // All owned jobs have closed before removing staged files. The original
    // handle prevented replacement until the same identity was verified.
    let root_cleaned = match owned_root {
        None => true,
        Some(Err(_)) => false,
        Some(Ok((original, identity))) => {
            let matches = assets::sealed_directory(&launch.root)
                .and_then(|handle| assets::directory_identity(&handle))
                .is_ok_and(|current| current == identity);
            drop(original);
            matches && fs::remove_dir_all(&launch.root).is_ok()
        }
    };
    let cleanup_complete = profile_cleaned && root_cleaned;
    let (receipt, error) = match operation {
        Ok(phases) => {
            let expected = match launch.recipe.kind {
                CheckKind::PythonUnittest | CheckKind::RustTest => "test",
                CheckKind::PythonCompile => "compile",
                _ => "validate",
            };
            let succeeded = phases
                .last()
                .is_some_and(|(name, phase)| *name == expected && phase.exit_code == 0);
            let phases: Vec<_> = phases
                .into_iter()
                .map(|(name, receipt)| phase(name, receipt))
                .collect();
            let token = phases.first().map(|phase| &phase["token"]);
            (
                Some(
                    json!({"token":token,"phases":phases,"elapsed_ms":started.elapsed().as_millis() as u64}),
                ),
                if succeeded {
                    None
                } else {
                    Some("check_failed")
                },
            )
        }
        Err(error) => (None, Some(error)),
    };
    Outcome {
        receipt,
        error: if cleanup_complete {
            error
        } else {
            Some("cleanup_incomplete")
        },
        cleanup_complete,
    }
}

fn phase(name: &str, receipt: windows::Receipt) -> Value {
    let digest: String = Sha256::digest(receipt.output.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    let token = receipt.token;
    json!({
        "phase": name, "exit_code": receipt.exit_code,
        "output_digest": digest,
        "token": {
            "lpac": token.lpac, "sid": token.sid, "integrity": token.integrity,
            "capabilities": token.capabilities, "job": token.job,
            "verification_method": token.verification_method, "class46_query": token.class46_query
        }
    })
}

fn failure(error: &str) -> &'static str {
    match error {
        "cancelled" => "cancelled",
        "preparation_timeout" => "preparation_timeout",
        "deadline_exceeded" => "deadline_exceeded",
        "output_limit" => "output_limit",
        "descendant_cleanup_failed" => "descendant_cleanup_failed",
        _ if error.starts_with("lpac_") => "containment_unavailable",
        _ => "check_execution_failed",
    }
}
