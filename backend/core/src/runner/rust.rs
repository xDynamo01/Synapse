//! Fixed Rust test recipe for the pinned Windows compiler closure.
use std::path::{Component, Path};

use super::{
    Control,
    assets::{RustAssets, sealed_directory, sealed_output},
    windows::{Profile, Receipt},
};

// Fixed crate name and compiler/codegen options produce this second object
// role. rustc emits LLVM IR for the allocator when --emit=obj skips linking.
// The bundled matching LLVM linker consumes that IR inside the boundary.
const ALLOCATOR_BITCODE: &str = "check.69k8lx4lt251s9o86j9vjqm0g.rcgu.bc";

pub(super) struct RustRun<'a> {
    pub project: &'a Path,
    pub source: &'a Path,
    pub output: &'a Path,
    pub temp: &'a Path,
}

#[derive(Debug)]
pub(super) struct RustReceipt {
    pub tool_digest: String,
    pub emission: Receipt,
    pub link: Option<Receipt>,
    pub test: Option<Receipt>,
}

fn argument(path: &Path) -> Result<String, String> {
    path.to_str()
        .filter(|value| !value.contains('\0'))
        .map(str::to_owned)
        .ok_or_else(|| "rust_invalid_path".into())
}

pub(super) fn run(
    profile: &Profile,
    tools: &RustAssets,
    paths: RustRun<'_>,
    control: &Control,
) -> Result<RustReceipt, String> {
    let relative = paths
        .source
        .strip_prefix(paths.project)
        .map_err(|_| "rust_entrypoint")?;
    let mut components = relative.components();
    if !matches!(components.next(), Some(Component::Normal(_)))
        || components.next().is_some()
        || relative.extension().and_then(|value| value.to_str()) != Some("rs")
        || argument(relative)?.contains(':')
    {
        return Err("rust_entrypoint".into());
    }
    let _output_directory = sealed_directory(paths.output)?;
    if std::fs::read_dir(paths.output)
        .map_err(|_| "rust_output_directory")?
        .next()
        .is_some()
    {
        return Err("rust_output_not_empty".into());
    }

    let object = paths.output.join("check.obj");
    let allocator = paths.output.join(ALLOCATOR_BITCODE);
    let executable = paths.output.join("check.exe");
    let mut emit_args = vec![
        "--sysroot".into(),
        argument(&tools.sysroot)?,
        "--crate-name".into(),
        "check".into(),
        "--test".into(),
        "--edition=2024".into(),
        "--emit=obj".into(),
        "-Csave-temps".into(),
        "-Ccodegen-units=1".into(),
        "-Cdebuginfo=0".into(),
        "-o".into(),
        argument(&object)?,
        argument(paths.source)?,
    ];
    for directory in &tools.native_dirs {
        emit_args.extend(["-L".into(), format!("native={}", argument(directory)?)]);
    }
    let emission = profile.launch(
        &tools.compiler,
        &emit_args,
        paths.project,
        paths.temp,
        control,
    )?;
    let mut receipt = RustReceipt {
        tool_digest: tools.digest.clone(),
        emission,
        link: None,
        test: None,
    };
    if receipt.emission.exit_code != 0 {
        return Ok(receipt);
    }

    // No compiler text is interpreted as a command, path or trust decision.
    // Keep the checked file handles open until the contained linker has exited.
    drop(sealed_directory(paths.output)?);
    let object_handle = sealed_output(&object)?;
    let allocator_handle = sealed_output(&allocator)?;
    let mut link_args = vec![
        "-flavor".into(),
        "link".into(),
        "/NOLOGO".into(),
        "/OPT:REF,NOICF".into(),
        "/DEFAULTLIB:msvcrt".into(),
        format!("/OUT:{}", argument(&executable)?),
        argument(&object)?,
        argument(&allocator)?,
    ];
    for library in &tools.libraries {
        link_args.push(argument(library)?);
    }
    for directory in &tools.native_dirs {
        link_args.push(format!("/LIBPATH:{}", argument(directory)?));
    }
    let link = profile.launch(
        &tools.linker,
        &link_args,
        paths.project,
        paths.temp,
        control,
    )?;
    drop((object_handle, allocator_handle));
    let linked = link.exit_code == 0;
    receipt.link = Some(link);
    if linked {
        drop(sealed_directory(paths.output)?);
        let executable_handle = sealed_output(&executable)?;
        receipt.test =
            Some(profile.launch(&executable, &[], paths.project, paths.temp, control)?);
        drop(executable_handle);
    }
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::runner::assets::{RustConfig, rust as copy_rust};
    use std::{
        io::ErrorKind,
        net::{IpAddr, Ipv4Addr, Ipv6Addr, TcpListener, TcpStream},
        path::PathBuf,
        time::Instant,
    };

    fn live_listener(ip: IpAddr) -> TcpListener {
        let listener = TcpListener::bind((ip, 0)).unwrap();
        let client = TcpStream::connect(listener.local_addr().unwrap()).unwrap();
        let (accepted, _) = listener.accept().unwrap();
        drop((client, accepted));
        listener.set_nonblocking(true).unwrap();
        listener
    }

    #[test]
    #[ignore = "requires owner-configured pinned Windows Rust, VC and SDK paths"]
    fn pinned_rust_runs_passing_and_failing_tests_in_lpac() {
        let configured = |name| {
            std::env::var_os(name)
                .map(PathBuf::from)
                .unwrap_or_else(|| panic!("{name} is required"))
        };
        let config = RustConfig {
            sysroot: configured("SYNAPSE_RUNNER_RUST_SYSROOT"),
            vc_x64_lib: configured("SYNAPSE_RUNNER_VC_X64_LIB"),
            sdk_um_x64_lib: configured("SYNAPSE_RUNNER_SDK_UM_X64_LIB"),
            sdk_ucrt_x64_lib: configured("SYNAPSE_RUNNER_SDK_UCRT_X64_LIB"),
        };
        let current = std::env::current_dir().unwrap();
        let root = tempfile::TempDir::new_in(current.ancestors().last().unwrap()).unwrap();
        let name = format!(
            "Synapse.RustGate.{}",
            root.path()
                .file_name()
                .unwrap()
                .to_string_lossy()
                .replace('.', "")
        );
        let profile = Profile::create(&name).unwrap();
        let runtime = root.path().join("runtime");
        let project = root.path().join("project");
        let temp = root.path().join("temp");
        let pass_output = root.path().join("pass");
        let fail_output = root.path().join("fail");
        let network_output = root.path().join("network");
        let budget_output = root.path().join("budget");
        for directory in [
            &runtime,
            &project,
            &temp,
            &pass_output,
            &fail_output,
            &network_output,
            &budget_output,
        ] {
            std::fs::create_dir(directory).unwrap();
        }
        profile.protect(root.path(), false).unwrap();
        profile.protect(&runtime, false).unwrap();
        profile.protect(&project, false).unwrap();
        for directory in [
            &temp,
            &pass_output,
            &fail_output,
            &network_output,
            &budget_output,
        ] {
            profile.protect(directory, true).unwrap();
        }
        let pass_source = project.join("check.rs");
        let fail_source = project.join("failing suite.rs");
        let network_source = project.join("loopback.rs");
        let budget_source = project.join("output_budget.rs");
        std::fs::write(
            &pass_source,
            "#[test]\nfn arithmetic() { assert_eq!(2 + 2, 4); }\n",
        )
        .unwrap();
        std::fs::write(
            &fail_source,
            "#[test]\nfn arithmetic() { assert_eq!(2 + 2, 5); }\n",
        )
        .unwrap();
        let v4 = live_listener(Ipv4Addr::LOCALHOST.into());
        let v6 = live_listener(Ipv6Addr::LOCALHOST.into());
        let network_fixture = r#"
            use std::{ffi::c_void, net::{SocketAddr, TcpStream}, time::Duration};

            #[repr(C, align(8))]
            struct WsaData([u8; 512]);
            unsafe extern "system" {
                fn WSAStartup(version: u16, data: *mut c_void) -> i32;
                fn WSACleanup() -> i32;
            }

            fn connect_error(address: &str) -> Option<i32> {
                let address: SocketAddr = address.parse().unwrap();
                TcpStream::connect_timeout(&address, Duration::from_millis(500))
                    .expect_err("unexpected successful loopback connection")
                    .raw_os_error()
            }

            #[test]
            fn loopback() {
                let mut data = WsaData([0; 512]);
                let startup = unsafe { WSAStartup(0x0202, (&mut data as *mut WsaData).cast()) };
                if startup != 0 {
                    panic!("winsock_startup={startup}; no connect attempted");
                }
                let _ = unsafe { WSACleanup() };
                let ipv4 = connect_error("IPV4_ENDPOINT");
                let ipv6 = connect_error("IPV6_ENDPOINT");
                panic!("ipv4_connect_error={ipv4:?}; ipv6_connect_error={ipv6:?}");
            }
        "#
        .replace("IPV4_ENDPOINT", &v4.local_addr().unwrap().to_string())
        .replace("IPV6_ENDPOINT", &v6.local_addr().unwrap().to_string());
        std::fs::write(&network_source, network_fixture).unwrap();
        std::fs::write(
            &budget_source,
            "#[test]\nfn output() { panic!(\"{}\", \"x\".repeat(20_000)); }\n",
        )
        .unwrap();
        let staging = Instant::now();
        let tools = copy_rust(&config, &runtime, &Control::new()).unwrap();
        eprintln!(
            "pinned Rust tool digest {} ({} bytes) staged in {:?}",
            tools.digest,
            tools.bytes,
            staging.elapsed()
        );
        let run_case = |source: &Path, output: &Path| {
            run(
                &profile,
                &tools,
                RustRun {
                    project: &project,
                    source,
                    output,
                    temp: &temp,
                },
                &Control::new(),
            )
        };
        let passing = run_case(&pass_source, &pass_output);
        let failing = run_case(&fail_source, &fail_output);
        let network = run_case(&network_source, &network_output);
        let budget_control = Control::new();
        let budget = run(
            &profile,
            &tools,
            RustRun {
                project: &project,
                source: &budget_source,
                output: &budget_output,
                temp: &temp,
            },
            &budget_control,
        )
        .unwrap();
        let first = budget.test.unwrap();
        assert_eq!(first.exit_code, 101);
        assert!((20_000..32 * 1024).contains(&first.output.len()));
        let budget_executable = budget_output.join("check.exe");
        let budget_executable_handle = sealed_output(&budget_executable).unwrap();
        let second = profile.launch(&budget_executable, &[], &project, &temp, &budget_control);
        drop(budget_executable_handle);
        assert_eq!(second.unwrap_err(), "output_limit");
        eprintln!(
            "aggregate output budget refused a second {}-byte phase",
            first.output.len()
        );
        let ordinary = profile.launch_policy(
            &tools.compiler,
            &[],
            &project,
            &temp,
            &Control::new(),
            false,
        );
        profile.remove().unwrap();
        let ordinary = ordinary.unwrap_err();
        assert!(
            ordinary.contains("aap=true")
                && ordinary.contains("combined=(1, 3)")
                && ordinary.contains("suspended_child_reaped=true; resumed=false"),
            "{ordinary}"
        );
        for (result, expected_exit, expected_output) in
            [(passing, 0, "1 passed"), (failing, 101, "1 failed")]
        {
            let receipt = result.unwrap();
            eprintln!("Rust fixture receipt: {receipt:?}");
            assert_eq!(receipt.tool_digest, tools.digest);
            assert_eq!(receipt.emission.exit_code, 0);
            let link = receipt.link.unwrap();
            assert_eq!(link.exit_code, 0);
            let test = receipt.test.unwrap();
            assert_eq!(test.exit_code, expected_exit);
            assert!(test.output.contains(expected_output));
            for observed in [&receipt.emission, &link, &test] {
                assert!(observed.token.lpac && observed.token.job);
                assert_eq!(observed.token.capabilities, 0);
                assert_eq!(observed.token.integrity, 4096);
                assert_eq!(
                    observed.token.verification_method,
                    "kernel_accesscheck_package_policy"
                );
                assert_eq!(observed.token.class46_query, "unsupported:87");
                assert_eq!(observed.token.sid, test.token.sid);
            }
        }
        let network = network.unwrap();
        eprintln!("Rust loopback fixture receipt: {network:?}");
        assert_eq!(network.emission.exit_code, 0);
        assert_eq!(network.link.unwrap().exit_code, 0);
        let test = network.test.unwrap();
        assert_eq!(test.exit_code, 101);
        assert!(
            test.output.contains("winsock_startup=")
                || (test.output.contains("ipv4_connect_error=")
                    && test.output.contains("ipv6_connect_error="))
        );
        assert_eq!(v4.accept().unwrap_err().kind(), ErrorKind::WouldBlock);
        assert_eq!(v6.accept().unwrap_err().kind(), ErrorKind::WouldBlock);
    }
}
