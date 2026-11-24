#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use slint::ComponentHandle;
use std::time::Duration;

#[cfg(windows)]
#[allow(dead_code)]
#[path = "../../desktop/src/audio.rs"]
mod audio;
#[cfg(windows)]
mod local_runtime;
mod presence;
mod session;
#[path = "../../desktop/src/transport.rs"]
mod transport;
#[cfg(windows)]
#[allow(dead_code)]
#[path = "../../desktop/src/voice.rs"]
mod voice;

slint::include_modules!();

fn shell() -> Result<AppShell, slint::PlatformError> {
    let app = AppShell::new()?;
    presence::attach(&app);
    let weak = app.as_weak();
    app.on_minimize_window(move || {
        if let Some(app) = weak.upgrade() {
            app.window().set_minimized(true);
        }
    });
    let weak = app.as_weak();
    app.on_maximize_window(move || {
        if let Some(app) = weak.upgrade() {
            let maximize = !app.window().is_maximized();
            app.window().set_maximized(maximize);
            app.set_window_maximized(maximize);
        }
    });
    let weak = app.as_weak();
    app.on_navigate(move |settings| {
        if let Some(app) = weak.upgrade() {
            if !settings && !app.get_settings_open() {
                app.set_console_open(!app.get_console_open());
            }
            app.set_settings_open(settings);
        }
    });
    let weak = app.as_weak();
    app.on_toggle_chat(move || {
        if let Some(app) = weak.upgrade() {
            app.set_chat_open(!app.get_chat_open());
        }
    });
    Ok(app)
}

fn main() -> Result<(), slint::PlatformError> {
    let app = shell()?;
    let endpoint = std::env::args().skip(1).find(|arg| !arg.starts_with("--"));
    let local_startup = endpoint.is_none() && cfg!(windows);
    let require_connected = local_startup || endpoint.is_some();
    #[cfg(windows)]
    let runtime = if endpoint.is_none() {
        match local_runtime::start() {
            Ok(runtime) => Some(runtime),
            Err(error) => {
                app.set_notice(error.into());
                None
            }
        }
    } else {
        None
    };
    let _session = if let Some(endpoint) = endpoint {
        Some(session::attach(&app, endpoint))
    } else {
        #[cfg(windows)]
        {
            runtime.as_ref().map(|runtime| {
                session::attach_with_model(
                    &app,
                    runtime.endpoint.clone(),
                    runtime.suggested_model.clone(),
                )
            })
        }
        #[cfg(not(windows))]
        {
            app.set_notice("A inicialização do Core local está disponível no Windows.".into());
            None
        }
    };
    if std::env::args().any(|arg| arg == "--smoke") {
        app.show()?;
        let weak = app.as_weak();
        let delay = if require_connected { 3200 } else { 900 };
        slint::Timer::single_shot(Duration::from_millis(delay), move || {
            if let Some(app) = weak.upgrade() {
                app.hide().expect("close smoke window");
            }
        });
        slint::run_event_loop()?;
        if require_connected && !app.get_runtime_connected() {
            return Err(app.get_notice().to_string().into());
        }
        Ok(())
    } else {
        app.run()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(windows)]
    #[test]
    #[ignore = "requires isolated Core and provider fixture"]
    fn core_pipe_plans_approves_and_executes_task() {
        use std::{cell::Cell, rc::Rc, time::Instant};
        i_slint_backend_testing::init_integration_test_with_system_time();
        let app = shell().unwrap();
        let live = std::env::var_os("SYNAPSE_SLINT_TEST_LIVE").is_some();
        let runtime = if live {
            Some(local_runtime::start().unwrap())
        } else {
            None
        };
        let root = std::path::PathBuf::from(std::env::var("SYNAPSE_SLINT_TEST_TASK_ROOT").unwrap());
        let rust=live && std::env::var_os("SYNAPSE_SLINT_TEST_RUST").is_some();
        let artifact = root.join(if rust {"agent_result.rs"} else {"agent_result.json"});
        assert!(!artifact.exists());
        let _session = if let Some(runtime) = runtime.as_ref() {
            session::attach_with_model(
                &app,
                runtime.endpoint.clone(),
                runtime.suggested_model.clone(),
            )
        } else {
            session::attach(&app, std::env::var("SYNAPSE_SLINT_TEST_ENDPOINT").unwrap())
        };
        let stage = Rc::new(Cell::new(0));
        let progress = stage.clone();
        let weak = app.as_weak();
        let deadline = Instant::now() + Duration::from_secs(if live { 300 } else { 85 });
        let probe = slint::Timer::default();
        probe.start(
            slint::TimerMode::Repeated,
            Duration::from_millis(250),
            move || {
                let app = weak.unwrap();
                match progress.get() {
                    0 if app.get_runtime_connected()
                        && !app.get_selected_model().is_empty()
                        && !app.get_core_capabilities().is_empty() =>
                    {
                        app.set_task_root(root.to_string_lossy().into_owned().into());
                        app.set_draft(
                            if rust {"Crie somente agent_result.rs com exatamente este conteúdo Rust: pub fn answer() -> i32 { 42 } #[test] fn test_answer() { assert_eq!(answer(), 42); } . Use rust_test para agent_result.rs e tasks vazio.".into()} else {"Crie somente agent_result.json contendo exatamente o objeto JSON {\"agent\":\"ARTEMIS\",\"executed\":true}. Valide o JSON.".into()},
                        );
                        app.invoke_plan_task();
                        if app.get_task_busy() {
                            progress.set(1);
                        }
                    }
                    1 if app.get_task_approve_ready() => {
                        assert!(
                            !artifact.exists(),
                            "O planejamento não pode publicar arquivos."
                        );
                        assert!(!app.get_task_execute_ready());
                        assert!(app.get_route_detail().starts_with("Missão · "));
                        app.invoke_execute_task();
                        assert!(!artifact.exists());
                        if live {
                            app.invoke_approve_task();
                            progress.set(2);
                        } else {
                            assert!(app.get_task_swarm_ready());
                            app.invoke_swarm_task();
                            progress.set(5);
                        }
                    }
                    5 if app.get_swarm_confirmation() => {
                        assert_eq!(app.get_execution_regime(), "NORMAL");
                        assert!(!app.get_task_execute_ready());
                        app.invoke_swarm_task();
                        progress.set(2);
                    }
                    2 if app.get_task_execute_ready() => {
                        if !live {
                            assert_eq!(app.get_execution_regime(), "NORMAL");
                            assert_eq!(app.get_transition_status(), "preparing");
                        }
                        app.invoke_execute_task();
                        progress.set(3);
                    }
                    3 if !app.get_task_busy() && (live || (app.get_execution_regime()=="NORMAL" && app.get_transition_status()=="ended")) => {
                        assert!(
                            app.get_cli_output().contains("integrated"),
                            "{}",
                            app.get_cli_output()
                        );
                        if rust {
                            let source=std::fs::read_to_string(&artifact).unwrap();
                            assert!(source.contains("42") && source.contains("#[test]"),"{source}");
                        } else {
                            let actual: serde_json::Value = serde_json::from_slice(&std::fs::read(&artifact).unwrap()).unwrap();
                            assert_eq!(actual,serde_json::json!({"agent":"ARTEMIS","executed":true}));
                        }
                        println!("Arquivo produzido pelo agente: {}\n{}",artifact.display(),app.get_cli_output());
                        progress.set(4);
                        slint::quit_event_loop().unwrap();
                    }
                    _ => {}
                }
                if Instant::now() > deadline || app.get_presence_state() == "error" {
                    slint::quit_event_loop().unwrap();
                }
            },
        );
        app.run().unwrap();
        assert_eq!(
            stage.get(),
            4,
            "{}\n{}",
            app.get_notice(),
            app.get_cli_output()
        );
    }

    #[cfg(windows)]
    #[test]
    #[ignore = "requires isolated Core and graph provider fixture"]
    fn core_pipe_executes_planner_graph_with_confirmed_swarm() {
        use std::{cell::Cell, rc::Rc, time::Instant};
        i_slint_backend_testing::init_integration_test_with_system_time();
        let app = shell().unwrap();
        let _session = session::attach(&app, std::env::var("SYNAPSE_SLINT_TEST_ENDPOINT").unwrap());
        let root = std::path::PathBuf::from(std::env::var("SYNAPSE_SLINT_TEST_TASK_ROOT").unwrap());
        let progress = Rc::new(Cell::new(0));
        let stage = progress.clone();
        let weak = app.as_weak();
        let deadline = Instant::now() + Duration::from_secs(100);
        let timer = slint::Timer::default();
        timer.start(slint::TimerMode::Repeated,Duration::from_millis(200),move || {
            let app=weak.unwrap();
            match stage.get() {
                0 if app.get_runtime_connected() && app.get_model_ready() && !app.get_settings_pending() => {
                    app.invoke_change_setting("resource_policy".into(),"ECONOMICAL".into());stage.set(1);
                }
                1 if !app.get_settings_pending() && app.get_resource_policy()=="ECONOMICAL" => {
                    app.set_task_root(root.to_string_lossy().into_owned().into());
                    app.set_draft("Crie first.json e depois second.json usando o primeiro. Valide os dois.".into());
                    app.invoke_plan_task();stage.set(2);
                }
                2 if app.get_graph_open() && app.get_graph_state()=="draft" && app.get_task_swarm_ready() => {
                    assert!(!root.join("first.json").exists());
                    assert_eq!(app.get_execution_regime(),"NORMAL");
                    app.invoke_swarm_task();stage.set(3);
                }
                3 if app.get_swarm_confirmation() && !app.get_task_busy() => {
                    assert_eq!(app.get_execution_regime(),"NORMAL");
                    app.invoke_swarm_task();stage.set(4);
                }
                4 if app.get_graph_state()=="integrated" && app.get_transition_status()=="ended" && app.get_execution_regime()=="NORMAL" => {
                    assert_eq!(app.get_resource_policy(),"ECONOMICAL");
                    for (name,step) in [("first.json",1),("second.json",2)] {
                        let data:serde_json::Value=serde_json::from_slice(&std::fs::read(root.join(name)).unwrap()).unwrap();
                        assert_eq!(data["step"],step);
                    }
                    stage.set(5); slint::quit_event_loop().unwrap();
                }
                _ => {}
            }
            if Instant::now()>deadline || app.get_presence_state()=="error" {slint::quit_event_loop().unwrap();}
        });
        app.run().unwrap();
        assert_eq!(
            progress.get(),
            5,
            "{}\n{}\n{}",
            app.get_notice(),
            app.get_graph_error(),
            app.get_graph_details()
        );
    }

    #[cfg(windows)]
    #[test]
    #[ignore = "requires local LM Studio, installed Qwen model and isolated state"]
    fn managed_runtime_answers_through_slint() {
        use slint::Model;
        use std::{cell::Cell, rc::Rc, time::Instant};

        i_slint_backend_testing::init_integration_test_with_system_time();
        let runtime = local_runtime::start().unwrap();
        let app = shell().unwrap();
        let _session = session::attach_with_model(
            &app,
            runtime.endpoint.clone(),
            runtime.suggested_model.clone(),
        );
        let started = Rc::new(Cell::new(false));
        let sent = started.clone();
        let deadline = Instant::now() + Duration::from_secs(145);
        let weak = app.as_weak();
        let probe = slint::Timer::default();
        probe.start(
            slint::TimerMode::Repeated,
            Duration::from_millis(200),
            move || {
                let app = weak.unwrap();
                if !sent.get()
                    && app.get_runtime_connected()
                    && !app.get_selected_model().is_empty()
                {
                    app.set_draft("Qual é o seu nome? Responda brevemente em português.".into());
                    app.invoke_send_message();
                    sent.set(true);
                }
                if Instant::now() > deadline
                    || (sent.get()
                        && !app.get_sending()
                        && (app.get_messages().row_count() >= 2
                            || app.get_presence_state() == "error"))
                {
                    slint::quit_event_loop().unwrap();
                }
            },
        );
        app.run().unwrap();
        let messages = app.get_messages();
        assert!(
            started.get() && app.get_runtime_connected(),
            "{}",
            app.get_notice()
        );
        assert_eq!(messages.row_count(), 2, "{}", app.get_notice());
        let reply = messages.row_data(1).unwrap();
        assert!(!reply.from_user && !reply.body.trim().is_empty());
        assert!(
            reply.body.to_uppercase().contains("ARTEMIS")
                || reply.body.to_uppercase().contains("A.R.T.E.M.I.S"),
            "{}",
            reply.body
        );
        println!("ARTEMIS respondeu pelo Core: {}", reply.body);
    }

    #[test]
    fn shell_defaults_and_navigation() {
        i_slint_backend_testing::init_no_event_loop();
        let app = shell().unwrap();
        assert!(!app.get_settings_open());
        assert!(!app.get_chat_open());
        assert!(!app.get_has_text());
        app.window()
            .set_size(slint::LogicalSize::new(1100.0, 720.0));
        app.show().unwrap();
        click(&app, 292.0, 686.0);
        assert!(app.get_chat_open());
        click(&app, 292.0, 686.0);
        assert!(!app.get_chat_open());
        app.set_draft("Olá, ARTEMIS".into());
        assert!(app.get_has_text());
        app.set_draft("".into());
        assert!(!app.get_has_text());
        click(&app, 26.0, 694.0);
        assert!(app.get_settings_open());
        for category in 0..4 {
            click(&app, 140.0, 92.0 + 44.0 * category as f32);
            assert_eq!(app.get_category(), category);
        }
        click(&app, 300.0, 171.0);
        assert!(app.get_projects());
        click(&app, 300.0, 129.0);
        assert!(!app.get_projects());
        assert!(!app.get_runtime_connected());
        click(&app, 26.0, 76.0);
        assert!(!app.get_settings_open());
        assert!(!app.get_console_open());
        click(&app, 26.0, 76.0);
        assert!(app.get_console_open());
        assert!(!app.get_presence_visible());
        click(&app, 105.0, 25.0);
        assert!(!app.get_console_open());
        assert!(app.get_presence_visible());
    }

    #[test]
    fn window_controls_follow_right_edge() {
        use std::{cell::Cell, rc::Rc};

        i_slint_backend_testing::init_no_event_loop();
        let app = shell().unwrap();
        let window_actions = Rc::new(Cell::new(0));
        let observed = window_actions.clone();
        app.on_minimize_window(move || observed.set(observed.get() + 1));
        let observed = window_actions.clone();
        app.on_maximize_window(move || observed.set(observed.get() + 10));
        app.show().unwrap();
        for (width, workspace) in [(1100.0, false), (860.0, true)] {
            app.window().set_size(slint::LogicalSize::new(width, 720.0));
            app.set_console_open(workspace);
            click(&app, 275.0, 26.0);
            assert_eq!(window_actions.get(), 0);
            click(&app, width - 120.0, 26.0);
            click(&app, width - 74.0, 26.0);
            assert_eq!(window_actions.get(), 11);
            window_actions.set(0);
        }
        click(&app, 860.0 - 28.0, 26.0);
        assert!(!app.window().is_visible());
    }

    fn click(app: &AppShell, x: f32, y: f32) {
        use slint::platform::{PointerEventButton, WindowEvent};

        let position = slint::LogicalPosition::new(x, y);
        let button = PointerEventButton::Left;
        app.window()
            .dispatch_event(WindowEvent::PointerPressed { position, button });
        app.window()
            .dispatch_event(WindowEvent::PointerReleased { position, button });
    }

    #[test]
    fn hidden_scrollbar_still_accepts_mouse_wheel() {
        use slint::{LogicalPosition, LogicalSize, ModelRc, VecModel, platform::WindowEvent};
        use std::rc::Rc;

        i_slint_backend_testing::init_no_event_loop();
        let app = shell().unwrap();
        app.window().set_size(LogicalSize::new(1100.0, 720.0));
        app.set_messages(ModelRc::from(Rc::new(VecModel::from(
            (1..=40)
                .map(|index| ChatMessage {
                    body: format!("Mensagem de teste {index}").into(),
                    from_user: index % 2 == 0,
                })
                .collect::<Vec<_>>(),
        ))));
        app.invoke_toggle_chat();
        app.show().unwrap();
        app.window().dispatch_event(WindowEvent::PointerScrolled {
            position: LogicalPosition::new(950.0, 260.0),
            delta_x: 0.0,
            delta_y: -120.0,
        });
        assert!(app.get_chat_scroll_position() < 0.0);
        app.window().dispatch_event(WindowEvent::PointerScrolled {
            position: LogicalPosition::new(950.0, 260.0),
            delta_x: 0.0,
            delta_y: 120.0,
        });
        assert_eq!(app.get_chat_scroll_position(), 0.0);
    }

    #[cfg(windows)]
    #[test]
    #[ignore = "requires an isolated Core pipe and the loopback model fixture"]
    fn core_pipe_workspace_library_and_conversation() {
        use slint::Model;
        use std::{cell::Cell, rc::Rc, time::Instant};

        i_slint_backend_testing::init_integration_test_with_system_time();
        let endpoint = std::env::var("SYNAPSE_SLINT_TEST_ENDPOINT").unwrap();
        let app = shell().unwrap();
        let _session = session::attach(&app, endpoint);
        let stage = Rc::new(Cell::new(0));
        let step = stage.clone();
        let weak = app.as_weak();
        let deadline = Instant::now() + Duration::from_secs(22);
        let probe = slint::Timer::default();
        probe.start(
            slint::TimerMode::Repeated,
            Duration::from_millis(100),
            move || {
                let app = weak.unwrap();
                match step.get() {
                    0 if app.get_runtime_connected()
                        && app.get_model_rows().row_count() == 1
                        && app.get_project_rows().row_count() == 1
                        && app.get_chat_rows().row_count() == 1 =>
                    {
                        app.invoke_open_entry(true, "project:fixture".into());
                        step.set(1);
                    }
                    1 if app.get_library_detail().starts_with("project:fixture") => {
                        app.invoke_open_entry(false, "fixture-history".into());
                        step.set(2);
                    }
                    2 if app.get_library_detail() == "Conversa de teste"
                        && app.get_messages().row_count() == 1 =>
                    {
                        app.set_draft("Mensagem pelo shell Slint".into());
                        app.invoke_send_message();
                        step.set(3);
                    }
                    3 if app.get_chat_open()
                        && !app.get_sending()
                        && app.get_messages().row_count() == 3 =>
                    {
                        assert!(app.get_route_detail().starts_with("Conversa · "));
                        app.invoke_change_setting("resource_policy".into(), "ECONOMICAL".into());
                        step.set(5);
                    }
                    5 if app.get_resource_policy() == "ECONOMICAL" => {
                        assert_eq!(app.get_execution_regime(), "NORMAL");
                        app.invoke_reconnect();
                        if !app.get_runtime_connected() {
                            app.set_resource_policy("".into());
                            step.set(6);
                        }
                    }
                    6 if app.get_runtime_connected()
                        && app.get_resource_policy() == "ECONOMICAL" =>
                    {
                        assert_eq!(app.get_execution_regime(), "NORMAL");
                        step.set(4);
                        slint::quit_event_loop().unwrap();
                    }
                    _ => {}
                }
                if Instant::now() > deadline {
                    slint::quit_event_loop().unwrap();
                }
            },
        );
        app.run().unwrap();
        assert_eq!(
            stage.get(),
            4,
            "notice: {}; detail: {}; messages: {}",
            app.get_notice(),
            app.get_library_detail(),
            app.get_messages().row_count()
        );
    }
}
