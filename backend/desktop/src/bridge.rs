//! Explicit, local standard-input bridge to the same controller used by the window.
use crate::Desktop;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    io::{self, BufRead, Read, Write},
    thread,
    time::{Duration, Instant},
};

#[derive(Deserialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
enum Action {
    State,
    #[cfg(windows)]
    BrowserLoadImage {
        url: String,
    },
    #[cfg(windows)]
    BrowserAnalyzeCss {
        url: String,
    },
    BrowserOpen {
        url: String,
    },
    VoiceEnable {
        #[serde(default)]
        diagnostic: bool,
        model: Option<String>,
    },
    VoiceDisable,
    VoiceDevices,
    VoiceConfigure {
        wake_name: Option<String>,
        input: Option<String>,
        output: Option<String>,
    },
    VoiceFeedPcm {
        pcm: String,
    },
    VoiceInterrupt,
    TranslatorStart {
        source_language: String,
        target_language: String,
    },
    TranslatorStop,
    RegisterProject {
        scope: String,
        root: String,
    },
    SelectProject {
        scope: String,
    },
    OpenChat {
        chat_id: String,
    },
    CreateChat {
        chat_id: String,
        title: String,
        scope: String,
    },
    SendMessage {
        model: String,
        text: String,
        context: Option<MemoryReference>,
    },
    OpenMission {
        mission_id: String,
    },
    Plan {
        mission_id: String,
        scope: String,
        model: String,
        objective: String,
        #[serde(default)]
        git_edit_paths: Vec<String>,
        skill: Option<Value>,
    },
    Approve {
        contract_digest: String,
    },
    Execute,
    InspectRecovery,
    ResolveRecovery {
        mode: RecoveryMode,
    },
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MemoryReference {
    scope: String,
    key: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum RecoveryMode {
    Finalize,
    Rollback,
}

pub fn serve(endpoint: String) -> io::Result<()> {
    let mut desktop = Desktop::new(endpoint, String::new());
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    loop {
        let mut line = Vec::new();
        if (&mut input).take(65537).read_until(b'\n', &mut line)? == 0 {
            break;
        }
        if line.len() > 65536 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Comando da ponte excede 64 KiB.",
            ));
        }
        let result = serde_json::from_slice(&line)
            .map_err(|error| error.to_string())
            .and_then(|action| handle(&mut desktop, action));
        let reply = match result {
            Ok(state) => json!({"ok":true,"state":state}),
            Err(error) => json!({"ok":false,"error":error}),
        };
        serde_json::to_writer(&mut output, &reply)?;
        writeln!(output)?;
        output.flush()?;
    }
    Ok(())
}

fn drain(desktop: &mut Desktop) -> Result<(), String> {
    let until = Instant::now() + Duration::from_secs(10);
    loop {
        desktop.tick();
        if desktop.pending == 0 {
            break;
        }
        if Instant::now() >= until {
            return Err(
                "Aguardando resposta do Core. Consulte o estado antes de repetir a ação.".into(),
            );
        }
        thread::sleep(Duration::from_millis(15));
    }
    if desktop.error.is_empty() {
        Ok(())
    } else {
        Err(desktop.error.clone())
    }
}

fn handle(desktop: &mut Desktop, action: Action) -> Result<Value, String> {
    if desktop.connected {
        desktop.error.clear();
    }
    drain(desktop)?;
    if !desktop.connected {
        return Err("O Core local está desconectado.".into());
    }
    match action {
        Action::State => (),
        #[cfg(windows)]
        Action::BrowserLoadImage { url } => desktop.browser.load_image(url)?,
        #[cfg(windows)]
        Action::BrowserAnalyzeCss { url } => desktop.browser.load_stylesheet(url)?,
        Action::BrowserOpen { url } => desktop.browser.open(url)?,
        Action::VoiceEnable { diagnostic, model } => {
            if let Some(model) = model {
                desktop.model = model;
            }
            desktop.voice.enable(diagnostic)?;
        }
        Action::VoiceDevices => desktop.voice_devices = Some(desktop.voice.audio.devices()?),
        Action::VoiceDisable => desktop.mute_voice(),
        Action::VoiceConfigure {
            wake_name,
            input,
            output,
        } => {
            if let Some(name) = wake_name {
                desktop.voice.wake_name = name;
            }
            desktop.interrupt_voice();
            desktop.voice.switch(input, output)?;
        }
        Action::VoiceFeedPcm { pcm } => desktop.voice.diagnostic_pcm(&pcm)?,
        Action::VoiceInterrupt => desktop.interrupt_voice(),
        Action::TranslatorStart {
            source_language,
            target_language,
        } => desktop.start_translator(&source_language, &target_language),
        Action::TranslatorStop => desktop.stop_translator(),
        Action::RegisterProject { scope, root } => desktop.register_project(&scope, &root),
        Action::SelectProject { scope } => desktop.select_project(&scope),
        Action::OpenChat { chat_id } => {
            if desktop.job_id.is_some() {
                return Err("A conversa ainda está em andamento.".into());
            }
            desktop.active_chat = chat_id;
            desktop.chat_cursor = 0;
            desktop.messages.clear();
            desktop.chat();
        }
        Action::CreateChat {
            chat_id,
            title,
            scope,
        } => {
            if desktop.job_id.is_some() {
                return Err("A conversa ainda está em andamento.".into());
            }
            desktop.active_chat.clear();
            desktop.chat_cursor = 0;
            desktop.messages.clear();
            desktop.send(
                "chat-create",
                json!({"type":"chat_create","chat_id":chat_id,"title":title,"scope":scope}),
            );
        }
        Action::SendMessage {
            model,
            text,
            context,
        } => {
            if desktop.active_chat.is_empty() || desktop.job_id.is_some() {
                return Err("Abra uma conversa sem resposta em andamento.".into());
            }
            while !desktop.catalog_ready {
                desktop.send(
                    "events",
                    json!({"type":"events_read","after":desktop.cursor,"limit":100}),
                );
                drain(desktop)?;
            }
            let (scope, key) = context
                .map(|reference| (reference.scope, reference.key))
                .unwrap_or_default();
            if scope.is_empty() != key.is_empty() {
                return Err("Informe o projeto e a chave de memória.".into());
            }
            desktop.context_scope = scope;
            desktop.context_key = key;
            desktop.model = model;
            desktop.message = text;
            desktop.send_message();
        }
        Action::OpenMission { mission_id } => {
            desktop.workspace = true;
            desktop.mission_id = mission_id;
            desktop.plan = Value::Null;
            desktop.mission = Value::Null;
            desktop.run = Value::Null;
            desktop.recovery = Value::Null;
            desktop.refresh();
        }
        Action::Plan {
            mission_id,
            scope,
            model,
            objective,
            git_edit_paths,
            skill,
        } => {
            desktop.workspace = true;
            desktop.mission_id = mission_id;
            if desktop.scope != scope {
                desktop.project = Value::Null;
                desktop.scope = scope;
            }
            desktop.model = model;
            desktop.objective = objective;
            desktop.plan = Value::Null;
            desktop.mission = Value::Null;
            desktop.run = Value::Null;
            desktop.recovery = Value::Null;
            desktop.plan_mission(git_edit_paths, skill);
        }
        Action::Approve { contract_digest } => desktop.approve_mission(&contract_digest),
        Action::Execute if desktop.mission["state"] == "approved" && desktop.run.is_null() => {
            desktop.mission_query("mission_execute")
        }
        Action::InspectRecovery if desktop.run["status"] == "recovery_required" => {
            desktop.mission_query("mission_recovery_inspect")
        }
        Action::ResolveRecovery { mode }
            if desktop.run["status"] == "recovery_required" && !desktop.recovery.is_null() =>
        {
            let mode = match mode {
                RecoveryMode::Finalize => "finalize",
                RecoveryMode::Rollback => "rollback",
            };
            desktop.send("resolve", json!({"type":"mission_recovery_resolve","mission_id":desktop.mission_id,"mode":mode}));
        }
        _ => return Err("A ação não está disponível para a missão selecionada.".into()),
    }
    drain(desktop)?;
    Ok(
        json!({"connected":desktop.connected,"browser":desktop.browser.state(),"project":desktop.project,"voice":desktop.voice.status(),"translator":desktop.translator,
        "voice_devices":desktop.voice_devices.as_ref().map(|devices| json!({"inputs":devices.inputs,"outputs":devices.outputs})),
        "voice_job":desktop.voice_job.as_ref().map(|job| &job.id),"voice_reply":desktop.voice_reply,"cursor":desktop.cursor,"chat_id":desktop.active_chat,"messages":desktop.messages,
        "conversation_job":desktop.job_id,"mission_id":desktop.mission_id,"proposal":desktop.plan,"mission":desktop.mission,
        "execution":desktop.run,"recovery":desktop.recovery}),
    )
}
