#[cfg(windows)]
use crate::voice::{Phase, Voice};
use crate::{AppShell, ChatMessage, ModelSlot, transport::Connection};
use serde_json::{Value, json};
use slint::{ComponentHandle, ModelRc, SharedString, VecModel};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
    rc::Rc,
    time::{Duration, Instant},
};

struct Admission {
    tag: &'static str,
    command: Value,
    chat: String,
    started: Instant,
    retry_at: Option<Instant>,
    cancelled: bool,
}

#[derive(Default)]
struct State {
    suggested_model: Option<Value>,
    connection: Option<Connection>,
    events_cursor: u64,
    models: Vec<SharedString>,
    model_slots: Vec<String>,
    assigned_models: BTreeMap<String, SharedString>,
    usable_models: Vec<SharedString>,
    chats: BTreeSet<SharedString>,
    projects: BTreeSet<SharedString>,
    chat: String,
    messages: Vec<ChatMessage>,
    chat_cursor: u64,
    chat_loading: bool,
    job: Option<String>,
    pending: usize,
    last_job_poll: Option<Instant>,
    last_health_poll: Option<Instant>,
    last_event_poll: Option<Instant>,
    restore_chat: bool,
    latest_chat: Option<String>,
    mission: Option<String>,
    mission_by_chat: BTreeMap<String, String>,
    settings: Value,
    skill: Value,
    swarm_recommended: bool,
    swarm_approved: bool,
    graph: Value,
    graph_plan: Option<Value>,
    last_graph_poll: Option<Instant>,
    latest_input: Option<(String, String)>,
    mission_digest: Option<String>,
    mission_poll: Option<&'static str>,
    objective: String,
    task_scope: String,
    task_folder: String,
    last_task_command: Option<(&'static str, Value)>,
    task_retry: Option<Instant>,
    task_wait_since: Option<Instant>,
    admission: Option<Admission>,
    #[cfg(windows)]
    voice: Option<Voice>,
    #[cfg(windows)]
    voice_language: Option<String>,
    #[cfg(windows)]
    voice_text: Option<String>,
    #[cfg(windows)]
    voice_request: Option<Value>,
    #[cfg(windows)]
    translating: bool,
    skill_pending: bool,
}

fn rows<T: Clone + 'static>(items: impl IntoIterator<Item = T>) -> ModelRc<T> {
    ModelRc::new(VecModel::from(items.into_iter().collect::<Vec<_>>()))
}

impl State {
    fn slot_model(&self, app: &AppShell, slot: &str) -> SharedString {
        self.assigned_models
            .get(slot)
            .cloned()
            .unwrap_or_else(|| app.get_selected_model())
    }

    fn refresh_slots(&self, app: &AppShell) {
        app.set_model_slots(rows(self.model_slots.iter().map(|id| {
            ModelSlot {
                id: id.as_str().into(),
                label: match id.as_str() {
                    "conversation" => "Conversa",
                    "task" => "Tarefas",
                    "review" => "Revisão",
                    "translation" => "Tradução",
                    other => other,
                }
                .into(),
                selected: if id == "conversation" {
                    app.get_selected_model()
                } else {
                    self.slot_model(app, id)
                },
                available: matches!(id.as_str(), "conversation" | "task" | "review"),
            }
        })));
    }
    fn orchestration(
        &mut self,
        app: &AppShell,
        tag: &'static str,
        action: &str,
        payload: Value,
    ) -> bool {
        self.send(
            app,
            tag,
            json!({"type":"orchestration","action":action,"payload":payload}),
        )
    }

    fn apply_settings(&mut self, app: &AppShell, data: Value) {
        if let Some(mode) = data["model_mode"].as_str() {
            app.set_model_mode(mode.into());
        }
        if let Some(policy) = data["resource_policy"].as_str() {
            app.set_resource_policy(policy.into());
        }
        if let Some(regime) = data["execution_regime"].as_str() {
            app.set_execution_regime(regime.into());
        }
        let transition = &data["transition"];
        app.set_transition_status(transition["status"].as_str().unwrap_or_default().into());
        app.set_swarm_confirmation(
            transition["status"] == "requested"
                && transition["mission_id"].as_str() == self.mission.as_deref(),
        );
        self.assigned_models = [
            ("conversation", "conversation"),
            ("task", "planning"),
            ("review", "review"),
        ]
        .into_iter()
        .filter_map(|(slot, key)| Some((slot.into(), data["assignments"][key].as_str()?.into())))
        .collect();
        self.settings = data;
        self.validate_selection(app);
    }

    fn automatic_for(&self, purpose: &str) -> bool {
        self.settings["purpose_modes"][purpose]
            .as_str()
            .or_else(|| self.settings["model_mode"].as_str())
            == Some("automatic")
    }

    fn validate_selection(&self, app: &AppShell) {
        let selected = self
            .assigned_models
            .get("conversation")
            .cloned()
            .unwrap_or_else(|| {
                if self.usable_models.len() == 1 {
                    self.usable_models[0].clone()
                } else {
                    "".into()
                }
            });
        app.set_selected_model(selected);
        app.set_model_ready(
            !self.usable_models.is_empty()
                && (self.automatic_for("conversation")
                    || self.usable_models.contains(&app.get_selected_model())),
        );
        if !app.get_model_ready()
            && !app.get_selected_model().is_empty()
            && !self.usable_models.is_empty()
        {
            app.set_notice("O modelo atribuído à conversa está indisponível. Atualize a atribuição em Modelos.".into());
        }
        self.refresh_slots(app);
    }

    fn graph_request(&mut self, app: &AppShell, tag: &'static str, action: &str, payload: Value) {
        if self.send(
            app,
            tag,
            json!({"type":"task_graph","action":action,"payload":payload}),
        ) {
            app.set_graph_pending(true);
        }
    }

    fn graph_action(&mut self, app: &AppShell, action: &str) {
        if !app.get_runtime_connected() || app.get_graph_pending() {
            return;
        }
        let id = app.get_graph_id();
        let id = id.trim();
        if id.is_empty() || id.len() > 128 {
            app.set_graph_error("Informe um ID de até 128 bytes.".into());
            return;
        }
        app.set_graph_id(id.into());
        app.set_graph_error("".into());
        if action == "get" {
            self.graph_request(app, "graph", action, json!({"graph_id":id}));
            return;
        }
        let digest = self.graph["digest"]
            .as_str()
            .filter(|_| self.graph["graph_id"] == id);
        if matches!(action, "plan" | "replan") {
            let source = app.get_graph_tasks();
            let tasks = match serde_json::from_str::<Value>(&source) {
                Ok(Value::Array(tasks)) if !tasks.is_empty() && source.len() <= 32_768 => tasks,
                _ => {
                    app.set_graph_error("Cole uma lista JSON de tarefas de até 32 KiB.".into());
                    return;
                }
            };
            if action == "replan" {
                if let Some(digest) = digest {
                    self.graph_request(
                        app,
                        "graph",
                        "replan",
                        json!({"graph_id":id,"digest":digest,"tasks":tasks}),
                    );
                }
                return;
            }
            let objective = app.get_graph_objective();
            if self.task_scope.is_empty()
                || !self.task_folder.eq_ignore_ascii_case(&app.get_task_root())
                || objective.trim().is_empty()
                || objective.trim().len() > 2048
                || id.len() > 124
            {
                app.set_graph_error(
                    "Selecione um projeto registrado e informe o objetivo do RFC.".into(),
                );
                return;
            }
            let rfc = format!("rfc-{id}");
            let mut payload =
                json!({"rfc_id":rfc,"scope":self.task_scope,"objective":objective.trim()});
            if !self.chat.is_empty() {
                payload["chat_id"] = json!(self.chat);
                if let Some((input, chat)) = &self.latest_input
                    && chat == &self.chat
                {
                    payload["input_id"] = json!(input);
                }
            }
            self.graph_plan = Some(json!({"graph_id":id,"rfc_id":rfc,"tasks":tasks}));
            self.graph_request(app, "graph-rfc", "rfc_create", payload);
            return;
        }
        if matches!(action, "activate" | "pause" | "resume" | "cancel") {
            if let Some(digest) = digest {
                self.graph_request(app, "graph", action, json!({"graph_id":id,"digest":digest}));
            } else {
                app.set_graph_error("Carregue a revisão do grafo primeiro.".into());
            }
        }
    }

    fn apply_graph(&mut self, app: &AppShell, data: Value) {
        let id = data["graph_id"].as_str().unwrap_or_default();
        app.set_loaded_graph_id(id.into());
        let state = data["state"].as_str().unwrap_or_default();
        app.set_graph_state(state.into());
        if state != "draft" {
            app.set_task_approve_ready(false);
            if !self.swarm_approved || matches!(state, "integrated" | "cancelled" | "failed") {
                app.set_task_swarm_ready(false);
            }
        }
        app.set_graph_summary(
            format!(
                "{id} · revisão {} · {state}\n{}",
                data["revision"],
                data["digest"].as_str().unwrap_or_default()
            )
            .into(),
        );
        let tasks = data["tasks"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|entry| {
                let task = &entry["task"];
                let id = task["task_id"].as_str()?;
                let mission = task["mission_id"].as_str()?;
                let state = entry["status"].as_str()?;
                let dependencies = task["dependencies"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>();
                let outputs = entry["outputs"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|output| output["path"].as_str())
                    .collect::<Vec<_>>();
                let acceptance = entry["acceptance"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|check| {
                        Some(format!(
                            "{} {}",
                            check["kind"].as_str()?,
                            check["entrypoint"].as_str().unwrap_or_default()
                        ))
                    })
                    .collect::<Vec<_>>();
                Some(format!(
                    "{id} · {state} · {mission}\nDependências: {}\nEntregas: {}\nAceite: {}",
                    dependencies.join(", "),
                    outputs.join(", "),
                    acceptance.join(", ")
                ))
            })
            .collect::<Vec<_>>();
        app.set_graph_details(tasks.join("\n\n").into());
        if self.graph["digest"] != data["digest"] {
            let tasks: Vec<_> = data["tasks"]
                .as_array()
                .into_iter()
                .flatten()
                .map(|entry| {
                    let mut task = entry["task"].clone();
                    if let Some(fields) = task.as_object_mut() {
                        fields.remove("contract_digest");
                    }
                    task
                })
                .collect();
            app.set_graph_tasks(
                serde_json::to_string_pretty(&tasks)
                    .unwrap_or_default()
                    .into(),
            );
        }
        self.graph = data;
        self.orchestration(app, "settings-get", "settings_get", json!({}));
    }

    fn context(&self, app: &AppShell) -> Option<Value> {
        let scope = app.get_context_scope();
        let key = app.get_context_key();
        if !scope.trim().is_empty() && !key.trim().is_empty() {
            Some(json!([{"scope":scope.trim(),"key":key.trim()}]))
        } else {
            None
        }
    }

    fn references_ready(&self, app: &AppShell) -> bool {
        if self.skill_pending {
            app.set_notice("Aguardando confirmação da Skill.".into());
            return false;
        }
        if app.get_context_scope().trim().is_empty() != app.get_context_key().trim().is_empty() {
            app.set_notice("Preencha o escopo e a chave da memória.".into());
            return false;
        }
        true
    }

    fn confirm_swarm(&mut self, app: &AppShell) {
        if let Some(id) = self.settings["transition"]["id"].as_str() {
            self.task_request(app, "task-swarm-confirm", json!({"type":"orchestration","action":"transition_confirm","payload":{"transition_id":id}}));
        }
    }

    fn task_request(&mut self, app: &AppShell, tag: &'static str, command: Value) {
        self.last_task_command = Some((tag, command.clone()));
        if self.send(app, tag, command) {
            app.set_task_busy(true);
            app.set_presence_state("processing".into());
        }
    }

    #[cfg(windows)]
    fn tick_voice(&mut self, app: &AppShell) {
        let Some(voice) = self.voice.as_mut() else {
            return;
        };
        let turn = voice.tick();
        let level = (voice.audio.levels().output * 5.0).clamp(0.0, 1.0);
        app.set_voice_level(level);
        app.set_voice_enabled(voice.phase != Phase::Off);
        if let Some(error) = voice.error.take() {
            app.set_notice(error.into());
            app.set_presence_state("error".into());
        }
        let phase = match voice.phase {
            Phase::Listening => "listening",
            Phase::Processing => "processing",
            Phase::Speaking => "speaking",
            _ => "idle",
        };
        if !app.get_sending() && app.get_presence_state() != "error" {
            app.set_presence_state(phase.into());
        }
        if let Some(turn) = turn {
            if turn.overlap {
                app.set_notice("Fala sobreposta ou idioma incerto. Tente novamente.".into());
                voice.resume();
                return;
            }
            if self.chat.is_empty()
                || app.get_task_busy()
                || app.get_sending()
                || self.job.is_some()
                || !app.get_model_ready()
            {
                voice.resume();
                return;
            }
            self.voice_request = Some(
                json!({"type":"voice_turn_start","session_id":"presence-voice","chat_id":self.chat,"model_id":"","language":turn.language,"text":turn.text}),
            );
            self.voice_text = Some(turn.text);
            self.voice_language = Some(turn.language);
            if self.send(
                app,
                "voice-mode",
                json!({"type":"voice_translator_get","session_id":"presence-voice"}),
            ) {
                app.set_sending(true);
                app.set_presence_state("processing".into());
            } else {
                self.voice_language = None;
                self.voice_text = None;
                self.voice_request = None;
                if let Some(voice) = self.voice.as_mut() {
                    voice.resume();
                }
            }
        }
    }

    fn send(&mut self, app: &AppShell, tag: &'static str, command: Value) -> bool {
        let admission = matches!(tag, "conversation" | "voice-turn").then(|| command.clone());
        if self
            .connection
            .as_ref()
            .is_some_and(|connection| connection.requests.try_send((tag, command)).is_ok())
        {
            self.pending += 1;
            if self.admission.is_none() && let Some(command)=admission {
                self.admission=Some(Admission{tag,command,chat:self.chat.clone(),started:Instant::now(),retry_at:None,cancelled:false});
            }
            true
        } else {
            app.set_notice("Canal ocupado ou indisponível. Use reconectar.".into());
            false
        }
    }

    fn cancel_waiting_admission(&mut self, app:&AppShell)->bool {
        if !self.admission.as_ref().is_some_and(|a|a.retry_at.is_some()) {return false;}
        self.admission=None;
        app.set_admission_waiting(false);
        #[cfg(windows)] {
            self.voice_language=None;
            self.voice_text=None;
            self.voice_request=None;
            self.translating=false;
            if let Some(voice)=self.voice.as_mut(){voice.resume();}
        }
        app.set_sending(false);
        app.set_presence_state("idle".into());
        true
    }

    #[cfg(windows)]
    fn cancel_voice_admission(&mut self,app:&AppShell){
        let waiting_mode=self.voice_request.is_some() || self.voice_language.is_some();
        self.voice_language=None;self.voice_text=None;self.voice_request=None;
        if waiting_mode {app.set_admission_waiting(false);}
        if !self.admission.as_ref().is_some_and(|a|a.tag=="voice-turn"){
            if waiting_mode && self.job.is_none(){self.translating=false;app.set_sending(false);}
            return;
        }
        if self.cancel_waiting_admission(app){return;}
        // The exchange may already have reached Core. Keep accounting until
        // its reply identifies whether a durable job needs cancellation.
        self.admission.as_mut().unwrap().cancelled=true;
        app.set_admission_waiting(false);
    }

    fn retry_admission(&mut self, app:&AppShell) {
        if self.pending!=0 {return;}
        let Some(admission)=self.admission.as_ref() else{return;};
        if admission.chat!=self.chat {
            self.cancel_waiting_admission(app);
            return;
        }
        let Some(at)=admission.retry_at else{return;};
        if Instant::now()<at {return;}
        let tag=admission.tag;
        #[cfg(windows)]
        if tag=="voice-turn" && self.voice.as_ref().is_none_or(|voice|voice.phase==Phase::Off){
            self.cancel_voice_admission(app);return;
        }
        if admission.started.elapsed()>=Duration::from_secs(120) {
            self.receive(app,tag,Err("worker_busy: tempo de espera do modelo esgotado; mensagem preservada.".into()));
            return;
        }
        let command=admission.command.clone();
        self.admission.as_mut().unwrap().retry_at=None;
        app.set_admission_waiting(false);
        if !self.send(app,tag,command) {
            self.receive(app,tag,Err("connection: canal indisponível; mensagem preservada.".into()));
        }
    }

    fn connect(&mut self, app: &AppShell, endpoint: &str) {
        if self.pending != 0 {
            return;
        }
        self.connection = Some(Connection::start(endpoint.into()));
        self.restore_chat = self.chat.is_empty();
        app.set_runtime_connected(false);
        app.set_notice("Conectando ao Core…".into());
        self.send(app, "initialize", json!({"type":"health"}));
    }

    fn events(&mut self, app: &AppShell) {
        self.send(
            app,
            "events",
            json!({"type":"events_read","after":self.events_cursor,"limit":50}),
        );
    }

    fn read_chat(&mut self, app: &AppShell) {
        self.chat_loading = self.send(
            app,
            "chat",
            json!({"type":"chat_get","chat_id":self.chat,"after":self.chat_cursor}),
        );
    }

    fn select_chat(&mut self, app: &AppShell, id: &str) {
        if self.chat == id && self.chat_loading {
            return;
        }
        self.chat = id.into();
        self.chat_cursor = 0;
        self.messages.clear();
        app.set_messages(rows([]));
        app.set_chat_open(true);
        app.set_presence_state("idle".into());
        app.set_library_detail("Carregando conversa…".into());
        self.read_chat(app);
    }

    fn receive(&mut self, app: &AppShell, tag: &str, result: Result<Value, String>) {
        self.pending = self.pending.saturating_sub(1);
        if tag=="admission-cancel" {
            app.set_presence_state("idle".into());
            match result {
                Ok(data) if data["status"]=="cancelled" => {self.job=None;app.set_notice("Envio cancelado.".into());},
                Ok(data) if matches!(data["status"].as_str(),Some("succeeded"|"failed"|"interrupted")) => {self.job=None;app.set_notice("Voz desativada; o processamento já havia terminado.".into());},
                other => {
                    app.set_presence_state("error".into());
                    app.set_notice(match other {Err(error)=>format!("Cancelamento não confirmado: {error}"),_=>"Cancelamento não confirmado pelo Core.".into()}.into());
                }
            }
            app.set_sending(self.job.is_some());
            #[cfg(windows)]
            if self.job.is_none(){self.translating=false;}
            return;
        }
        if self.admission.as_ref().is_some_and(|a|a.tag==tag && a.cancelled){
            self.admission=None;app.set_admission_waiting(false);
            let job=result.as_ref().ok().and_then(|data|data["job_id"].as_str());
            if let Some(job)=job {
                self.job=Some(job.to_owned());
                self.last_job_poll=None;
                if self.send(app,"admission-cancel",json!({"type":"job_cancel","job_id":job})){return;}
                app.set_sending(true);app.set_presence_state("error".into());
                app.set_notice("Cancelamento não enviado; operação continua monitorada.".into());return;
            }
            app.set_sending(false);app.set_presence_state("idle".into());
            #[cfg(windows)]
            {self.translating=false;}
            app.set_notice("Envio cancelado.".into());return;
        }
        let data = match result {
            Ok(data) => data,
            Err(error) => {
                if error.starts_with("worker_busy")
                    && let Some(admission)=self.admission.as_mut()
                    && admission.tag==tag && admission.chat==self.chat
                    && admission.started.elapsed()<Duration::from_secs(120) {
                    admission.retry_at=Some(Instant::now()+Duration::from_millis(750));
                    app.set_admission_waiting(true);
                    app.set_notice("Mensagem aguardando o modelo local…".into());
                    return;
                }
                if tag=="connection" || self.admission.as_ref().is_some_and(|a|a.tag==tag) {
                    self.admission=None;
                    app.set_admission_waiting(false);
                }
                if matches!(tag, "task-start" | "task-execute") && error.starts_with("worker_busy")
                {
                    let since = self.task_wait_since.get_or_insert_with(Instant::now);
                    if since.elapsed() < Duration::from_secs(120) {
                        self.task_retry = Some(Instant::now() + Duration::from_millis(750));
                        app.set_notice(
                            "Aguardando o modelo local concluir a operação anterior…".into(),
                        );
                        return;
                    }
                }
                if matches!(tag, "skill-active" | "connection") {
                    self.skill_pending = false;
                }
                if tag.starts_with("graph") {
                    self.graph_plan = None;
                    app.set_graph_pending(false);
                    app.set_graph_error(error.into());
                    return;
                }
                if tag == "connection" {
                    app.set_graph_pending(false);
                }
                if tag.starts_with("settings") || tag == "connection" {
                    app.set_settings_pending(false);
                }
                if tag.starts_with("task-") || tag == "connection" {
                    self.mission_poll = None;
                    app.set_task_busy(false);
                    if !matches!(
                        tag,
                        "task-approve"
                            | "task-approve-swarm"
                            | "task-swarm-request"
                            | "task-swarm-withdraw"
                    ) {
                        app.set_task_approve_ready(false);
                    }
                    if tag != "task-execute" {
                        app.set_task_execute_ready(false);
                    }
                    app.set_presence_state("error".into());
                    app.set_cli_output(error.clone().into());
                }
                if tag == "connection" {
                    self.pending = 0;
                    self.connection = None;
                    app.set_runtime_connected(false);
                    self.job = None;
                    #[cfg(windows)]
                    if let Some(voice) = self.voice.as_mut() {
                        voice.disable();
                    }
                }
                if matches!(
                    tag,
                    "connection" | "create" | "conversation" | "initialize" | "health"
                ) {
                    app.set_sending(false);
                    app.set_presence_state("error".into());
                }
                if tag == "job" {
                    self.job = None;
                    app.set_sending(false);
                    app.set_presence_state("error".into());
                }
                #[cfg(windows)]
                if matches!(tag, "voice-mode" | "voice-turn" | "job" | "connection")
                    && self.voice_language.take().is_some()
                {
                    self.voice_text = None;
                    self.voice_request = None;
                    self.translating = false;
                    app.set_sending(false);
                    app.set_presence_state("error".into());
                    if let Some(voice) = self.voice.as_mut() {
                        voice.resume();
                    }
                }
                if matches!(tag, "chat" | "project") {
                    if tag == "chat" {
                        self.chat_loading = false;
                    }
                    app.set_library_detail(error.clone().into());
                }
                app.set_notice(error.into());
                return;
            }
        };
        if self.admission.as_ref().is_some_and(|a|a.tag==tag){self.admission=None;app.set_admission_waiting(false);}
        #[cfg(windows)]
        if tag=="conversation"{self.translating=false;}
        match tag {
            "graph" => {
                app.set_graph_pending(false);
                self.apply_graph(app, data);
            }
            "graph-rfc" => {
                app.set_graph_pending(false);
                if let Some(mut plan) = self.graph_plan.take() {
                    plan["rfc_digest"] = data["digest"].clone();
                    self.graph_request(app, "graph", "plan", plan);
                }
            }
            "settings-get" | "settings-put" => {
                app.set_settings_pending(false);
                self.apply_settings(app, data);
            }
            "skill-active" => {
                self.skill_pending = false;
                self.skill = data;
                app.set_skill_detail(
                    self.skill["version"]
                        .as_str()
                        .map(|v| format!("Skill vinculada · {v}"))
                        .unwrap_or_default()
                        .into(),
                );
            }
            "task-swarm-request" => {
                app.set_task_busy(false);
                app.set_presence_state("idle".into());
                self.apply_settings(app, data);
                app.set_notice("Confirme o Swarm para esta proposta.".into());
            }
            "task-swarm-withdraw" => {
                app.set_task_busy(false);
                app.set_presence_state("idle".into());
                self.apply_settings(app, data);
            }
            "task-swarm-confirm" => {
                self.swarm_approved = false;
                app.set_task_swarm_ready(false);
                app.set_task_busy(false);
                app.set_task_execute_ready(true);
                app.set_presence_state("idle".into());
                self.apply_settings(app, data);
            }
            "task-project" => {
                self.task_scope = data["scope"].as_str().unwrap_or_default().into();
                self.task_folder = data["root"].as_str().unwrap_or_default().into();
                app.set_task_root(self.task_folder.as_str().into());
                let command = self.intake(app, &self.objective, "mission");
                self.task_request(app, "task-start", command);
            }
            "task-start" | "conversation" | "voice-turn" if data["route"] == "mission" => {
                self.show_intake(app, &data);
                app.set_sending(false);
                app.set_console_open(true);
                #[cfg(windows)]
                if self.voice_language.take().is_some()
                    && let Some(voice) = self.voice.as_mut()
                {
                    voice.resume();
                }
                #[cfg(windows)]
                let transcript = self.voice_text.take();
                if data["status"] == "running"
                    && let Some(id) = data["mission_id"].as_str()
                {
                    self.mission = Some(id.into());
                    self.mission_by_chat.insert(self.chat.clone(), id.into());
                    app.set_task_approve_ready(false);
                    app.set_task_swarm_ready(false);
                    app.set_swarm_confirmation(false);
                    app.set_task_execute_ready(false);
                    app.set_task_busy(true);
                    if tag != "voice-turn" {
                        app.set_draft("".into());
                    }
                    self.read_chat(app);
                } else {
                    #[cfg(windows)]
                    if let Some(transcript) = transcript
                        && app.get_draft().trim().is_empty()
                    {
                        app.set_draft(transcript.into());
                    }
                    app.set_task_busy(false);
                    app.set_presence_state("idle".into());
                    app.set_notice(if data["status"] == "needs_workspace" {
                        "Escolha a pasta do projeto no Workspace.".into()
                    } else {
                        data["reason"]
                            .as_str()
                            .unwrap_or("Identifique o resultado que deseja continuar.")
                            .into()
                    });
                    return;
                }
                self.task_retry = None;
                self.task_wait_since = None;
                self.mission_poll = Some("task-plan");
                app.set_cli_output("ARTEMIS está preparando a proposta pelo Core…".into());
            }
            "task-plan" => {
                app.set_cli_output(
                    serde_json::to_string_pretty(&data)
                        .unwrap_or_default()
                        .into(),
                );
                if data["status"] != "running" {
                    self.mission_poll = None;
                    app.set_task_busy(false);
                    if data["task_graph"].is_object() {
                        self.mission_digest = data["mission"]["contract_digest"]
                            .as_str()
                            .map(str::to_owned);
                        self.swarm_approved = false;
                        self.swarm_recommended = data["swarm_recommendation"].is_object();
                        app.set_task_approve_ready(self.mission_digest.is_some());
                        app.set_task_swarm_ready(self.mission_digest.is_some());
                        app.set_task_execute_ready(false);
                        app.set_graph_id(
                            data["task_graph"]["graph_id"]
                                .as_str()
                                .unwrap_or_default()
                                .into(),
                        );
                        self.apply_graph(app, data["task_graph"].clone());
                        app.set_graph_open(true);
                        app.set_presence_state("idle".into());
                        app.set_notice("Grafo pronto para revisão no Workspace.".into());
                        return;
                    }
                    self.mission_digest = data["mission"]["contract_digest"]
                        .as_str()
                        .map(str::to_owned);
                    let proposed =
                        data["mission"]["state"] == "proposed" && self.mission_digest.is_some();
                    self.swarm_approved = false;
                    self.swarm_recommended = data["swarm_recommendation"].is_object();
                    app.set_task_approve_ready(proposed);
                    app.set_task_swarm_ready(
                        proposed && data["mission"]["contract"]["execution"].is_object(),
                    );
                    app.set_swarm_confirmation(
                        proposed
                            && self.settings["transition"]["status"] == "requested"
                            && self.settings["transition"]["mission_id"].as_str()
                                == self.mission.as_deref(),
                    );
                    app.set_presence_state(if proposed { "idle" } else { "error" }.into());
                    app.set_notice(
                        if proposed {
                            "Proposta pronta para revisão no Workspace."
                        } else {
                            "O Core não conseguiu preparar a tarefa. Consulte o Workspace."
                        }
                        .into(),
                    );
                }
            }
            "task-approve" | "task-approve-swarm" => {
                if data["graph_id"].is_string() {
                    self.apply_graph(app, data.clone());
                    app.set_task_busy(false);
                    app.set_task_approve_ready(false);
                    app.set_task_execute_ready(false);
                    self.swarm_approved = tag == "task-approve-swarm";
                    app.set_task_swarm_ready(self.swarm_approved);
                    if self.swarm_approved {
                        self.confirm_swarm(app);
                    }
                    return;
                }
                app.set_task_swarm_ready(false);
                app.set_swarm_confirmation(false);
                app.set_task_busy(false);
                app.set_task_approve_ready(false);
                app.set_task_execute_ready(data["state"] == "approved" && tag == "task-approve");
                if tag == "task-approve-swarm" && data["state"] == "approved" {
                    self.swarm_approved = true;
                    app.set_task_swarm_ready(true);
                    app.set_swarm_confirmation(true);
                    self.confirm_swarm(app);
                }
                app.set_presence_state("idle".into());
                app.set_cli_output(
                    serde_json::to_string_pretty(&data)
                        .unwrap_or_default()
                        .into(),
                );
            }
            "task-execute" => {
                self.task_retry = None;
                self.task_wait_since = None;
                app.set_task_execute_ready(false);
                self.mission_poll = Some("task-run");
                self.orchestration(app, "settings-get", "settings_get", json!({}));
            }
            "task-run" => {
                app.set_cli_output(
                    serde_json::to_string_pretty(&data)
                        .unwrap_or_default()
                        .into(),
                );
                if !matches!(
                    data["status"].as_str(),
                    Some(
                        "generating"
                            | "review_ready"
                            | "checking"
                            | "reviewing"
                            | "publishing"
                            | "postchecking"
                            | "rolling_back"
                    )
                ) {
                    self.mission_poll = None;
                    self.orchestration(app, "settings-get", "settings_get", json!({}));
                    app.set_task_busy(false);
                    app.set_presence_state(
                        if matches!(
                            data["status"].as_str(),
                            Some("integrated" | "cancelled" | "rolled_back")
                        ) {
                            "idle"
                        } else {
                            "error"
                        }
                        .into(),
                    );
                    app.set_notice(
                        format!(
                            "Tarefa · {}",
                            data["status"].as_str().unwrap_or("consulte o Workspace")
                        )
                        .into(),
                    );
                }
            }
            "task-cancel" => {
                self.swarm_approved = false;
                self.mission_poll = None;
                self.orchestration(app, "settings-get", "settings_get", json!({}));
                app.set_swarm_confirmation(false);
                app.set_task_swarm_ready(false);
                app.set_task_busy(false);
                app.set_task_execute_ready(false);
                app.set_task_approve_ready(false);
                app.set_presence_state("idle".into());
                app.set_cli_output(
                    serde_json::to_string_pretty(&data)
                        .unwrap_or_default()
                        .into(),
                );
            }
            "health" => {
                app.set_runtime_connected(true);
                app.set_core_detail(
                    format!(
                        "{} · protocolo {} · armazenamento {}",
                        data["identity"].as_str().unwrap_or("Core"),
                        data["protocol_version"],
                        data["storage_schema"]
                    )
                    .into(),
                );
            }
            "initialize" => {
                app.set_runtime_connected(true);
                app.set_core_detail(
                    format!(
                        "{} · protocolo {} · armazenamento {}",
                        data["identity"].as_str().unwrap_or("Core"),
                        data["protocol_version"],
                        data["storage_schema"]
                    )
                    .into(),
                );
                app.set_notice("Core conectado".into());
                self.models.clear();
                app.set_local_provider(false);
                self.usable_models.clear();
                self.send(app, "models", json!({"type":"models_list"}));
                self.events(app);
                self.send(app, "capabilities", json!({"type":"capabilities_list"}));
                self.orchestration(app, "settings-get", "settings_get", json!({}));
                self.send(
                    app,
                    "specialists",
                    json!({"type":"input_control","action":"capabilities_list","payload":{}}),
                );
                if !self.chat.is_empty() {
                    let id = self.chat.clone();
                    self.select_chat(app, &id);
                }
            }
            "specialists" => {
                let entries = data["capabilities"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|descriptor| descriptor["id"].as_str().map(SharedString::from));
                app.set_specialists(rows(std::iter::once("Automático".into()).chain(entries)));
            }
            "capabilities" => {
                self.model_slots = data["model_slots"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|slot| slot.as_str().map(str::to_owned))
                    .collect();
                self.refresh_slots(app);
                let text = data["capabilities"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|item| {
                        Some(format!(
                            "{} · {}",
                            item["id"].as_str()?,
                            item["status"].as_str()?
                        ))
                    })
                    .collect::<Vec<_>>()
                    .join("\n");
                app.set_core_capabilities(text.into());
            }
            "models" => {
                for model in data["models"].as_array().into_iter().flatten() {
                    if let Some(id) = model["id"].as_str() {
                        let provider = model["provider"]
                            .as_str()
                            .unwrap_or("provedor desconhecido");
                        if provider == "lm_studio" {
                            app.set_local_provider(true);
                        }
                        let ready = model["operational"] == true;
                        self.models.push(
                            format!(
                                "{id} · {provider} · {}",
                                if ready {
                                    "operacional"
                                } else {
                                    "operação não verificada"
                                }
                            )
                            .into(),
                        );
                        if model["capabilities"]
                            .as_array()
                            .is_some_and(|items| items.iter().any(|item| item == "chat"))
                        {
                            self.usable_models.push(id.into());
                        }
                    }
                }
                if data["has_more"] == true {
                    self.send(
                        app,
                        "models",
                        json!({"type":"models_list","after":data["next_cursor"]}),
                    );
                } else {
                    app.set_model_rows(rows(self.models.clone()));
                    app.set_chat_models(rows(self.usable_models.clone()));
                    if self.usable_models.is_empty()
                        && let Some(model) = self.suggested_model.take()
                    {
                        self.send(
                            app,
                            "register-model",
                            json!({"type":"model_register","model":model}),
                        );
                        return;
                    }
                    if self.usable_models.is_empty() {
                        app.set_notice(
                            "Core conectado. Nenhum modelo de conversa disponível no catálogo."
                                .into(),
                        );
                    }
                    self.validate_selection(app);
                }
            }
            "register-model" => {
                self.models.clear();
                self.usable_models.clear();
                self.send(app, "models", json!({"type":"models_list"}));
            }
            "events" => {
                if let Some(events) = data["events"].as_array() {
                    let mut output = app.get_event_output().to_string();
                    for event in events {
                        let payload = &event["payload"];
                        match event["kind"].as_str() {
                            Some("chat_created") => {
                                if let Some(id) = payload["chat_id"].as_str() {
                                    self.chats.insert(id.into());
                                    self.latest_chat = Some(id.into());
                                }
                            }
                            Some("workspace_project_registered") => {
                                if let Some(scope) = payload["scope"].as_str() {
                                    self.projects.insert(scope.into());
                                }
                            }
                            _ => {}
                        }
                        output.push_str(&format!(
                            "{}  {}\n",
                            event["cursor"],
                            event["kind"].as_str().unwrap_or("evento")
                        ));
                    }
                    if events.len() == 50 {
                        self.events_cursor =
                            data["next_cursor"].as_u64().unwrap_or(self.events_cursor);
                        self.events(app);
                    }
                    self.events_cursor = data["next_cursor"].as_u64().unwrap_or(self.events_cursor);
                    let tail = output.lines().rev().take(18).collect::<Vec<_>>();
                    app.set_event_output(
                        tail.into_iter().rev().collect::<Vec<_>>().join("\n").into(),
                    );
                    if self.mission.is_none() && !app.get_task_busy() {
                        app.set_cli_output(app.get_event_output());
                    }
                    app.set_chat_rows(rows(self.chats.iter().cloned()));
                    app.set_project_rows(rows(self.projects.iter().cloned()));
                    if events.len() < 50 && self.restore_chat {
                        self.restore_chat = false;
                        if let Some(id) = self.latest_chat.clone() {
                            self.select_chat(app, &id);
                        }
                    }
                }
            }
            "project" => {
                self.task_scope = data["scope"].as_str().unwrap_or_default().into();
                self.task_folder = data["root"].as_str().unwrap_or_default().into();
                app.set_task_root(self.task_folder.as_str().into());
                app.set_library_detail(
                    format!(
                        "{}\n{}",
                        data["scope"].as_str().unwrap_or_default(),
                        data["root"].as_str().unwrap_or_default()
                    )
                    .into(),
                );
            }
            "chat" if data["chat_id"].as_str() == Some(&self.chat) => {
                self.chat_loading = false;
                if !app.get_projects() {
                    app.set_library_detail(data["title"].as_str().unwrap_or("Conversa").into());
                }
                for message in data["messages"].as_array().into_iter().flatten() {
                    let role = message["role"].as_str();
                    if let (Some(body), Some("user" | "assistant")) =
                        (message["content"].as_str(), role)
                    {
                        self.messages.push(ChatMessage {
                            body: body.into(),
                            from_user: role == Some("user"),
                        });
                    }
                }
                self.chat_cursor = data["next_cursor"].as_u64().unwrap_or(self.chat_cursor);
                if data["has_more"] == true {
                    self.read_chat(app);
                } else {
                    app.set_messages(rows(self.messages.clone()));
                }
            }
            "create" | "task-chat" => {
                self.chat = data["chat_id"].as_str().unwrap_or_default().into();
                self.chats.insert(self.chat.as_str().into());
                app.set_chat_rows(rows(self.chats.iter().cloned()));
                if tag == "task-chat" {
                    self.register_task_project(app);
                } else {
                    self.start_turn(app);
                }
            }
            "conversation" => {
                self.show_intake(app, &data);
                self.job = data["job_id"].as_str().map(str::to_owned);
                if self.job.is_none() {
                    app.set_sending(false);
                    app.set_presence_state("idle".into());
                    app.set_notice(
                        data["reason"]
                            .as_str()
                            .unwrap_or("O Core aguarda mais informações.")
                            .into(),
                    );
                    return;
                }
                app.set_draft("".into());
                app.set_chat_open(true);
                self.read_chat(app);
            }
            #[cfg(windows)]
            "voice-mode" => {
                let Some(mut command) = self.voice_request.take() else {
                    return;
                };
                self.translating = data["active"] == true;
                if self.translating {
                    let translation = self.settings["assignments"]["translation"]
                        .as_str()
                        .filter(|id| self.usable_models.iter().any(|model| model.as_str() == *id))
                        .map(SharedString::from)
                        .unwrap_or_else(|| app.get_selected_model());
                    command["model_id"] = json!(translation.as_str());
                } else if self.references_ready(app) {
                    if let Some(context) = self.context(app) {
                        command["context"] = context;
                    }
                    if !self.skill.is_null() {
                        command["skill"] = self.skill.clone();
                    }
                } else {
                    app.set_sending(false);
                    self.voice_language = None;
                    self.voice_text = None;
                    if let Some(voice) = self.voice.as_mut() {
                        voice.resume();
                    }
                    return;
                }
                if !self.send(app, "voice-turn", command) {
                    app.set_sending(false);
                    self.voice_language = None;
                    self.voice_text = None;
                    if let Some(voice) = self.voice.as_mut() {
                        voice.resume();
                    }
                }
            }
            #[cfg(windows)]
            "voice-turn" => {
                self.voice_text = None;
                self.show_intake(app, &data);
                self.translating = data["mode"] == "translator";
                if self.translating {
                    self.voice_language = data["target_language"]
                        .as_str()
                        .map(str::to_owned)
                        .or(self.voice_language.take());
                }
                self.job = data["job_id"].as_str().map(str::to_owned);
                app.set_chat_open(true);
                if self.job.is_none() {
                    if data["status"] == "needs_clarification" {
                        app.set_notice("Identifique o resultado que deseja continuar.".into());
                    }
                    self.voice_language = None;
                    app.set_sending(false);
                    if let Some(voice) = self.voice.as_mut() {
                        voice.resume();
                    }
                }
                self.read_chat(app);
            }
            "job" if data["status"] != "running" => {
                self.job = None;
                app.set_sending(false);
                let ok = data["status"] == "succeeded";
                #[cfg(windows)]
                if let Some(language) = self.voice_language.take() {
                    if let Some(voice) = self.voice.as_mut() {
                        if ok && let Some(text) = data["content"].as_str() {
                            voice.speak(text, &language);
                        } else {
                            voice.resume();
                        }
                    }
                }
                #[cfg(windows)]
                {
                    self.translating = false;
                }
                app.set_presence_state(if ok { "idle" } else { "error" }.into());
                app.set_notice(if ok {
                    "Resposta concluída".into()
                } else {
                    format!(
                        "Conversa: {} · {}",
                        data["status"].as_str().unwrap_or("estado desconhecido"),
                        data["error"].as_str().unwrap_or("sem detalhes do Core")
                    )
                    .into()
                });
                self.read_chat(app);
            }
            _ => {}
        }
    }

    fn show_intake(&mut self, app: &AppShell, data: &Value) {
        if let Some(input) = data["input_id"].as_str() {
            self.latest_input = Some((input.into(), self.chat.clone()));
        }
        let route = match data["route"].as_str() {
            Some("conversation") => "Conversa",
            Some("specialized") => "Especialista",
            Some("mission") => "Missão",
            _ => return,
        };
        let details = ["capability", "model_id", "mission_id"]
            .into_iter()
            .filter_map(|key| data[key].as_str());
        let pins = data["context_pins"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|pin| {
                Some(format!(
                    "{}/{} rev. {}",
                    pin["scope"].as_str()?,
                    pin["key"].as_str()?,
                    pin["revision"].as_u64()?
                ))
            })
            .collect::<Vec<_>>();
        app.set_context_used(pins.join(" · ").into());
        app.set_route_detail(
            std::iter::once(route)
                .chain(details)
                .collect::<Vec<_>>()
                .join(" · ")
                .into(),
        );
    }

    fn intake(&self, app: &AppShell, content: &str, intent: &str) -> Value {
        let slot = if intent == "mission" {
            "task"
        } else {
            "conversation"
        };
        let mut input = json!({"chat_id":self.chat,"content":content,"intent":intent});
        if self.settings.is_null() {
            let model = self.slot_model(app, slot);
            if !model.is_empty() {
                input["model_id"] = json!(model.as_str());
            }
        }
        let capability = app.get_selected_specialist();
        if intent == "auto" && !capability.is_empty() && capability != "Automático" {
            input["capability"] = json!(capability.as_str());
        }
        if intent == "mission" || self.task_folder.eq_ignore_ascii_case(&app.get_task_root()) {
            if !self.task_scope.is_empty() {
                input["scope"] = json!(self.task_scope);
            }
            if intent == "mission" && self.settings.is_null() {
                input["review_model_id"] = json!(self.slot_model(app, "review").as_str());
            }
        }
        if intent != "mission"
            && let Some(mission) = self.mission_by_chat.get(&self.chat)
        {
            input["mission_id"] = json!(mission);
        }
        if let Some(context) = self.context(app) {
            input["context"] = context;
        }
        if !self.skill.is_null() {
            input["skill"] = self.skill.clone();
        }
        json!({"type":"input_submit","input":input})
    }

    fn start_turn(&mut self, app: &AppShell) {
        let command = self.intake(app, app.get_draft().trim(), "auto");
        if !self.send(app, "conversation", command) {
            app.set_sending(false);
            app.set_presence_state("error".into());
        }
    }

    fn poll_job(&mut self,app:&AppShell,job:&str){
        #[cfg(windows)]
        let kind=if self.translating{"voice_translation_get"}else{"job_get"};
        #[cfg(not(windows))]
        let kind="job_get";
        self.send(app,"job",json!({"type":kind,"job_id":job}));
    }

    fn register_task_project(&mut self, app: &AppShell) {
        let folder = app.get_task_root().to_string();
        let scope = if self.task_folder.eq_ignore_ascii_case(&folder) && !self.task_scope.is_empty()
        {
            self.task_scope.clone()
        } else {
            use std::hash::{Hash, Hasher};
            let mut hash = std::collections::hash_map::DefaultHasher::new();
            folder.to_lowercase().replace('\\', "/").hash(&mut hash);
            format!("project:desktop-{:016x}", hash.finish())
        };
        self.task_request(
            app,
            "task-project",
            json!({"type":"project_register","scope":scope,"root":folder}),
        );
    }
}

pub fn attach(app: &AppShell, endpoint: String) -> slint::Timer {
    attach_with_model(app, endpoint, None)
}

pub fn attach_with_model(app: &AppShell, endpoint: String, model: Option<Value>) -> slint::Timer {
    let state = Rc::new(RefCell::new(State {
        suggested_model: model,
        ..State::default()
    }));
    state.borrow_mut().connect(app, &endpoint);
    {
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_assign_model(move |slot, model| {
            let Some(app) = weak.upgrade() else { return };
            let mut state = session.borrow_mut();
            if app.get_sending() || app.get_task_busy() || !state.usable_models.contains(&model) {
                return;
            }
            let key = match slot.as_str() {
                "conversation" => "conversation",
                "task" => "planning",
                "review" => "review",
                _ => return,
            };
            if !app.get_settings_pending()
                && state.orchestration(
                    &app,
                    "settings-put",
                    "settings_put",
                    json!({"purpose_modes":{(key):"manual"},"assignments":{(key):model.as_str()}}),
                )
            {
                app.set_settings_pending(true);
            }
        });
    }
    {
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_change_setting(move |field, value| {
            let Some(app) = weak.upgrade() else { return };
            if app.get_settings_pending() || app.get_sending() || app.get_task_busy() {
                return;
            }
            let patch = match (field.as_str(), value.as_str()) {
                ("model_mode", "automatic" | "manual") => json!({
                    "model_mode":value.as_str(),
                    "purpose_modes":{"conversation":null,"planning":null,"review":null,"translation":null}
                }),
                ("resource_policy", "RESPONSIVE" | "ECONOMICAL") => json!({"resource_policy":value.as_str()}),
                _ => return,
            };
            if session.borrow_mut().orchestration(
                &app,
                "settings-put",
                "settings_put",
                patch,
            ) {
                app.set_settings_pending(true);
            }
        });
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_graph_action(move |action| {
            let Some(app) = weak.upgrade() else { return };
            session.borrow_mut().graph_action(&app, &action);
        });
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_choose_skill(move |scope, id| {
            let Some(app) = weak.upgrade() else { return };
            let mut state = session.borrow_mut();
            if state.skill_pending {
                return;
            }
            state.skill = Value::Null;
            app.set_skill_detail("".into());
            if !scope.trim().is_empty() && !id.trim().is_empty() {
                state.skill_pending = state.send(
                    &app,
                    "skill-active",
                    json!({"type":"skill_active","scope":scope.trim(),"skill_id":id.trim()}),
                );
            }
        });
    }
    let workspace = std::env::var_os("SYNAPSE_WORKSPACE_DIR")
        .map(std::path::PathBuf::from)
        .or_else(|| {
            std::env::var_os("LOCALAPPDATA")
                .map(|base| std::path::PathBuf::from(base).join("Synapse/workspace"))
        });
    if let Some(workspace) = workspace {
        app.set_task_root(workspace.to_string_lossy().into_owned().into());
    }
    {
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_plan_task(move || {
            let Some(app) = weak.upgrade() else { return };
            let mut state = session.borrow_mut();
            if app.get_sending()
                || app.get_task_busy()
                || state.pending >= 6
                || !app.get_runtime_connected()
            {
                return;
            }
            if !state.references_ready(&app) {
                return;
            }
            let objective = app.get_draft().trim().to_owned();
            if objective.is_empty()
                || objective.len() > 2048
                || app.get_task_root().is_empty()
                || !app.get_model_ready()
            {
                app.set_notice(
                    "Escolha um modelo, a pasta da tarefa e um objetivo de até 2048 bytes.".into(),
                );
                return;
            }
            state.objective = objective;
            state.task_retry = None;
            state.task_wait_since = None;
            app.set_console_open(true);
            app.set_task_approve_ready(false);
            app.set_task_execute_ready(false);
            if state.chat.is_empty() {
                let stamp = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_nanos();
                state.task_request(&app, "task-chat", json!({"type":"chat_create","chat_id":format!("slint-{stamp}"),"scope":"project:desktop","title":"Tarefa no Workspace"}));
            } else {
                state.register_task_project(&app);
            }
        });
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_approve_task(move || {
            let Some(app) = weak.upgrade() else { return };
            let mut state = session.borrow_mut();
            if !app.get_task_approve_ready() || app.get_task_busy() || app.get_swarm_confirmation()
            {
                return;
            }
            if let (Some(id), Some(digest)) = (state.mission.clone(), state.mission_digest.clone())
            {
                state.task_request(
                    &app,
                    "task-approve",
                    json!({"type":"mission_approve","mission_id":id,"contract_digest":digest}),
                );
            }
        });
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_swarm_task(move || {
            let Some(app) = weak.upgrade() else { return };
            let mut state = session.borrow_mut();
            if !app.get_task_swarm_ready() || (!app.get_task_approve_ready() && !state.swarm_approved) || app.get_task_busy() {
                return;
            }
            if state.swarm_approved {
                state.confirm_swarm(&app);
                return;
            }
            let (Some(id), Some(digest)) = (state.mission.clone(), state.mission_digest.clone()) else { return };
            if app.get_swarm_confirmation() {
                let consent = if state.swarm_recommended { "recommended" } else { "direct" };
                state.task_request(&app, "task-approve-swarm", json!({"type":"mission_approve","mission_id":id,"contract_digest":digest,"swarm":consent}));
            } else {
                state.task_request(&app, "task-swarm-request", json!({"type":"orchestration","action":"transition_request","payload":{"regime":"SWARM","mission_id":id}}));
            }
        });
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_withdraw_swarm(move || {
            let Some(app) = weak.upgrade() else { return };
            if app.get_swarm_confirmation() && app.get_task_approve_ready() && !app.get_task_busy() {
                session.borrow_mut().task_request(&app, "task-swarm-withdraw", json!({"type":"orchestration","action":"transition_request","payload":{"regime":"NORMAL"}}));
            }
        });
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_execute_task(move || {
            let Some(app) = weak.upgrade() else { return };
            let mut state = session.borrow_mut();
            if !app.get_task_execute_ready() || app.get_task_busy() {
                return;
            }
            if let Some(id) = state.mission.clone() {
                state.task_request(
                    &app,
                    "task-execute",
                    json!({"type":"mission_execute","mission_id":id}),
                );
            }
        });
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_cancel_task(move || {
            let Some(app)=weak.upgrade() else {return}; let mut state=session.borrow_mut();
            if let Some(id)=state.mission.clone() { state.task_request(&app,"task-cancel",json!({"type":"mission_cancel","mission_id":id,"reason":"Cancelamento solicitado no Workspace"})); }
        });
    }
    {
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_new_chat(move || {
            let Some(app) = weak.upgrade() else { return };
            let mut state = session.borrow_mut();
            state.cancel_waiting_admission(&app);
            if state.task_retry.take().is_some() {
                state.task_wait_since = None;
                if state
                    .last_task_command
                    .as_ref()
                    .is_some_and(|(tag, _)| *tag == "task-start")
                {
                    app.set_task_busy(false);
                    app.set_presence_state("idle".into());
                    app.set_notice("Planejamento cancelado.".into());
                    return;
                }
            }
            if app.get_sending() || app.get_task_busy() || state.pending >= 6 || state.job.is_some()
            {
                return;
            }
            #[cfg(windows)]
            if let Some(voice) = state.voice.as_mut() {
                voice.disable();
            }
            state.chat.clear();
            state.messages.clear();
            state.chat_cursor = 0;
            state.restore_chat = false;
            app.set_messages(rows([]));
            app.set_voice_enabled(false);
            app.set_draft("".into());
            app.set_chat_open(true);
            app.set_presence_state("idle".into());
            app.set_notice("Nova conversa. Envie uma mensagem para começar.".into());
        });
    }
    #[cfg(windows)]
    {
        app.set_voice_supported(true);
        let (weak, session) = (app.as_weak(), state.clone());
        app.on_toggle_voice(move || {
            let Some(app) = weak.upgrade() else { return };
            let mut state = session.borrow_mut();
            if let Some(voice) = state
                .voice
                .as_mut()
                .filter(|voice| voice.phase != Phase::Off)
            {
                voice.disable();
                state.cancel_voice_admission(&app);
                app.set_voice_enabled(false);
                if !app.get_sending() {
                    app.set_presence_state("idle".into());
                }
                return;
            }
            if !app.get_runtime_connected() || app.get_sending() || !app.get_model_ready() {
                return;
            }
            if state.chat.is_empty() {
                app.set_notice(
                    "Abra uma conversa ou envie uma mensagem antes de ativar o microfone.".into(),
                );
                app.set_presence_state("error".into());
                return;
            }
            let voice = state.voice.get_or_insert_with(Voice::new);
            match voice.enable(false) {
                Ok(()) => {
                    app.set_voice_enabled(true);
                    app.set_presence_state("idle".into());
                    app.set_notice("Diga Artemis para começar a falar.".into());
                }
                Err(error) => {
                    app.set_notice(error.into());
                    app.set_presence_state("error".into());
                }
            }
        });
    }
    let (weak, session) = (app.as_weak(), state.clone());
    app.on_reconnect(move || {
        if let Some(app) = weak.upgrade() {
            session.borrow_mut().connect(&app, &endpoint);
        }
    });
    let (weak, session) = (app.as_weak(), state.clone());
    app.on_command(move |input| {
        let Some(app) = weak.upgrade() else { return };
        let mut state = session.borrow_mut();
        match input.trim() {
            "status" => {
                state.send(&app, "health", json!({"type":"health"}));
            }
            "eventos" => {
                app.set_cli_output(app.get_event_output());
                state.events(&app);
            }
            _ => app.set_notice("Comandos disponíveis: status, eventos".into()),
        }
    });
    let (weak, session) = (app.as_weak(), state.clone());
    app.on_open_entry(move |projects, id| {
        let Some(app) = weak.upgrade() else { return };
        let mut state = session.borrow_mut();
        state.cancel_waiting_admission(&app);
        if state.job.is_some() || app.get_sending() || app.get_task_busy() || state.pending >= 6 {
            app.set_notice("Aguarde a operação em andamento.".into());
        } else if projects {
            app.set_projects(true);
            state.restore_chat = false;
            state.send(
                &app,
                "project",
                json!({"type":"project_get","scope":id.as_str()}),
            );
        } else {
            app.set_projects(false);
            state.restore_chat = false;
            state.select_chat(&app, &id);
        }
    });
    let (weak, session) = (app.as_weak(), state.clone());
    app.on_cancel_message(move || {
        let Some(app)=weak.upgrade() else{return;};
        if session.borrow_mut().cancel_waiting_admission(&app){app.set_notice("Envio cancelado; mensagem preservada.".into());}
    });
    let (weak, session) = (app.as_weak(), state.clone());
    app.on_send_message(move || {
        let Some(app) = weak.upgrade() else { return };
        let mut state = session.borrow_mut();
        let draft = app.get_draft();
        #[cfg(windows)]
        if state.voice.as_ref().is_some_and(|voice| matches!(voice.phase, Phase::Processing | Phase::Speaking)) {
            return;
        }
        if !app.get_runtime_connected() || app.get_task_busy() || app.get_sending() || state.job.is_some() || draft.trim().is_empty()
            || !app.get_model_ready() {
            return;
        }
        if !state.references_ready(&app) {
            return;
        }
        if draft.trim().len() > 32_768 {
            app.set_notice("Mensagem excede o limite do Core.".into());
            return;
        }
        app.set_sending(true);
        app.set_presence_state("processing".into());
        if state.chat.is_empty() {
            let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos();
            let title = draft.split_whitespace().take(8).collect::<Vec<_>>().join(" ").chars().take(80).collect::<String>();
            if !state.send(&app, "create", json!({"type":"chat_create","chat_id":format!("slint-{stamp}"),"scope":"project:desktop","title":title})) {
                app.set_sending(false);
                app.set_presence_state("error".into());
            }
        } else {
            state.start_turn(&app);
        }
    });
    let timer = slint::Timer::default();
    let weak = app.as_weak();
    timer.start(
        slint::TimerMode::Repeated,
        Duration::from_millis(33),
        move || {
            let Some(app) = weak.upgrade() else { return };
            let mut state = state.borrow_mut();
            while let Some((tag, reply)) = state
                .connection
                .as_ref()
                .and_then(|connection| connection.replies.try_recv().ok())
            {
                state.receive(&app, tag, reply);
            }
            if app.get_console_open()
                && app.get_graph_open()
                && state.pending == 0
                && !app.get_graph_pending()
                && app.get_graph_error().is_empty()
                && matches!(state.graph["state"].as_str(), Some("active" | "pausing"))
                && state.graph["settled"] != true
                && state.graph["graph_id"].as_str() == Some(app.get_graph_id().trim())
                && state
                    .last_graph_poll
                    .is_none_or(|at| at.elapsed() >= Duration::from_secs(1))
            {
                state.last_graph_poll = Some(Instant::now());
                state.graph_action(&app, "get");
            }
            #[cfg(windows)]
            state.tick_voice(&app);
            state.retry_admission(&app);
            if state.pending == 0 && state.task_retry.is_some_and(|at| Instant::now() >= at) {
                state.task_retry = None;
                if let Some((tag, command)) = state.last_task_command.clone() {
                    state.send(&app, tag, command);
                }
            }
            if state.pending == 0
                && let Some(tag) = state.mission_poll
                && state
                    .last_job_poll
                    .is_none_or(|last| last.elapsed() >= Duration::from_millis(450))
            {
                state.last_job_poll = Some(Instant::now());
                let kind = if tag == "task-plan" {
                    "mission_plan_get"
                } else {
                    "mission_run_get"
                };
                if let Some(id) = state.mission.clone() {
                    state.send(&app, tag, json!({"type":kind,"mission_id":id}));
                }
            }
            if state.pending == 0
                && let Some(job) = state.job.clone()
                && state
                    .last_job_poll
                    .is_none_or(|last| last.elapsed() >= Duration::from_millis(450))
            {
                state.last_job_poll = Some(Instant::now());
                state.poll_job(&app,&job);
            } else if state.pending == 0 && app.get_runtime_connected() && state.job.is_none() {
                if state
                    .last_health_poll
                    .is_none_or(|last| last.elapsed() >= Duration::from_secs(5))
                {
                    state.last_health_poll = Some(Instant::now());
                    state.send(&app, "health", json!({"type":"health"}));
                } else if state
                    .last_event_poll
                    .is_none_or(|last| last.elapsed() >= Duration::from_secs(2))
                {
                    state.last_event_poll = Some(Instant::now());
                    state.events(&app);
                }
            }
        },
    );
    timer
}

#[cfg(test)]
mod tests {
    use super::*;

    fn queued_turn(tag:&'static str)->(AppShell,State,std::sync::mpsc::Receiver<(&'static str,Value)>,Value){
        i_slint_backend_testing::init_no_event_loop();
        let app=crate::shell().unwrap();
        app.set_draft("Preserve esta mensagem".into());app.set_sending(true);
        let(requests,commands)=std::sync::mpsc::sync_channel(8);
        let(_,replies)=std::sync::mpsc::channel();
        let mut state=State{connection:Some(Connection{requests,replies}),chat:"original-chat".into(),..State::default()};
        let command=json!({"type":"input_submit","input":{"chat_id":"original-chat","content":"Preserve esta mensagem","model_id":"manual-model","context":[{"scope":"project:original","key":"constraint"}]}});
        assert!(state.send(&app,tag,command.clone()));
        assert_eq!(commands.recv().unwrap(),(tag,command.clone()));
        state.receive(&app,tag,Err("worker_busy · Preserve input and retry admission".into()));
        (app,state,commands,command)
    }

    #[test]
    fn busy_turn_retries_exact_payload_and_clears_only_after_admission(){
        let(app,mut state,commands,command)=queued_turn("conversation");
        assert!(app.get_sending());assert_eq!(app.get_draft(),"Preserve esta mensagem");
        app.set_selected_model("different-model".into());
        state.admission.as_mut().unwrap().retry_at=Some(Instant::now());
        state.retry_admission(&app);
        assert_eq!(commands.recv().unwrap(),("conversation",command));
        assert_eq!(state.pending,1);
        state.retry_admission(&app);assert!(commands.try_recv().is_err());
        state.receive(&app,"conversation",Ok(json!({"route":"conversation","job_id":"accepted"})));
        assert!(state.admission.is_none());assert_eq!(state.job.as_deref(),Some("accepted"));
        assert_eq!(commands.recv().unwrap().1["type"],"chat_get");
        assert!(commands.try_recv().is_err());
    }

    #[test]
    fn busy_turn_timeout_preserves_draft_and_stops_retrying(){
        let(app,mut state,commands,_)=queued_turn("conversation");
        let admission=state.admission.as_mut().unwrap();
        admission.started=Instant::now()-Duration::from_secs(121);admission.retry_at=Some(Instant::now());
        state.retry_admission(&app);
        assert!(state.admission.is_none());assert!(!app.get_sending());
        assert_eq!(app.get_draft(),"Preserve esta mensagem");assert!(commands.try_recv().is_err());
    }

    #[test]
    fn queued_turn_cannot_move_into_another_chat_and_can_be_cancelled(){
        let(app,mut state,commands,_)=queued_turn("conversation");
        state.chat="another-chat".into();state.retry_admission(&app);
        assert!(state.admission.is_none());assert!(!app.get_sending());assert!(commands.try_recv().is_err());
    }

    #[test]
    fn queued_voice_turn_can_be_cancelled_without_late_submission(){
        let(app,mut state,commands,_)=queued_turn("voice-turn");
        #[cfg(windows)] {state.voice_language=Some("pt-BR".into());state.voice_text=Some("Synthetic transcript".into());}
        assert!(state.cancel_waiting_admission(&app));
        assert!(state.admission.is_none());state.retry_admission(&app);
        assert!(commands.try_recv().is_err());assert!(!app.get_sending());
        #[cfg(windows)] {assert!(state.voice_language.is_none());assert!(state.voice_text.is_none());}
    }

    #[cfg(windows)]
    #[test]
    fn voice_disable_cancels_waiting_turn_even_with_an_unrelated_pending_request(){
        let(app,mut state,commands,_)=queued_turn("voice-turn");
        state.pending=1;
        state.cancel_voice_admission(&app);
        assert!(state.admission.is_none());assert!(!app.get_admission_waiting());
        state.pending=0;state.retry_admission(&app);
        assert!(commands.try_recv().is_err());assert!(!app.get_sending());
    }

    #[cfg(windows)]
    #[test]
    fn voice_disable_during_exchange_suppresses_late_busy_retry(){
        let(app,mut state,commands,_)=queued_turn("voice-turn");
        state.admission.as_mut().unwrap().retry_at=None;state.pending=1;
        state.cancel_voice_admission(&app);
        assert!(state.admission.as_ref().unwrap().cancelled);
        state.receive(&app,"voice-turn",Err("worker_busy · Preserve input".into()));
        assert_eq!(state.pending,0);assert!(state.admission.is_none());
        assert!(!app.get_sending());assert!(commands.try_recv().is_err());
    }

    #[cfg(windows)]
    #[test]
    fn voice_disable_during_successful_exchange_cancels_the_exact_admitted_job(){
        let(app,mut state,commands,_)=queued_turn("voice-turn");
        state.translating=true;
        state.admission.as_mut().unwrap().retry_at=None;state.pending=1;
        state.cancel_voice_admission(&app);
        state.receive(&app,"voice-turn",Ok(json!({"job_id":"late-job"})));
        assert_eq!(commands.recv().unwrap(),("admission-cancel",json!({"type":"job_cancel","job_id":"late-job"})));
        assert_eq!(state.pending,1);assert!(state.admission.is_none());assert!(state.voice_language.is_none());
        state.receive(&app,"admission-cancel",Ok(json!({"status":"cancelled"})));
        assert_eq!(state.pending,0);assert!(!app.get_sending());assert!(!state.translating);assert!(commands.try_recv().is_err());
    }

    #[cfg(windows)]
    #[test]
    fn voice_disable_before_mode_reply_drops_the_unsent_transcript(){
        let(app,mut state,commands,_)=queued_turn("voice-turn");
        state.admission=None;state.pending=1;
        state.voice_request=Some(json!({"type":"voice_turn_start","text":"Unsent transcript"}));
        state.voice_language=Some("pt-BR".into());state.voice_text=Some("Unsent transcript".into());
        state.cancel_voice_admission(&app);
        state.receive(&app,"voice-mode",Ok(json!({"active":false})));
        assert_eq!(state.pending,0);assert!(!app.get_sending());
        assert!(state.voice_request.is_none());assert!(state.voice_language.is_none());
        assert!(commands.try_recv().is_err());
    }

    #[cfg(windows)]
    #[test]
    fn refused_cancellation_keeps_the_exact_job_monitored_and_does_not_claim_success(){
        let(app,mut state,commands,_)=queued_turn("voice-turn");
        state.translating=true;
        state.admission.as_mut().unwrap().retry_at=None;state.pending=1;
        state.cancel_voice_admission(&app);
        state.receive(&app,"voice-turn",Ok(json!({"job_id":"late-job"})));
        assert_eq!(commands.recv().unwrap().1["job_id"],"late-job");
        state.receive(&app,"admission-cancel",Err("permission_denied".into()));
        assert_eq!(state.job.as_deref(),Some("late-job"));assert!(app.get_sending());
        assert!(app.get_notice().contains("não confirmado"));assert_eq!(app.get_presence_state(),"error");
        assert!(state.voice_language.is_none());
        assert!(state.translating);state.poll_job(&app,"late-job");
        assert_eq!(commands.recv().unwrap().1,json!({"type":"voice_translation_get","job_id":"late-job"}));
    }

    #[cfg(windows)]
    #[test]
    fn cancelled_translation_cannot_redirect_polling_of_a_later_typed_conversation(){
        let(app,mut state,commands,_)=queued_turn("voice-turn");
        state.translating=true;state.cancel_waiting_admission(&app);
        assert!(!state.translating);
        state.receive(&app,"conversation",Ok(json!({"route":"conversation","job_id":"typed-job"})));
        assert_eq!(commands.recv().unwrap().1["type"],"chat_get");
        state.receive(&app,"chat",Ok(json!({"chat_id":"original-chat","messages":[],"has_more":false,"next_cursor":0})));
        state.poll_job(&app,"typed-job");
        assert_eq!(commands.recv().unwrap().1,json!({"type":"job_get","job_id":"typed-job"}));
    }

    #[test]
    fn core_slots_drive_cards_and_task_model_choices() {
        i_slint_backend_testing::init_no_event_loop();
        let app = crate::shell().unwrap();
        app.set_selected_model("conversation-model".into());
        let (requests, commands) = std::sync::mpsc::sync_channel(8);
        let (_, replies) = std::sync::mpsc::channel();
        let mut state = State {
            connection: Some(Connection { requests, replies }),
            usable_models: vec![
                "conversation-model".into(),
                "task-model".into(),
                "review-model".into(),
            ],
            ..State::default()
        };
        state
            .assigned_models
            .insert("task".into(), "task-model".into());
        state
            .assigned_models
            .insert("review".into(), "review-model".into());
        state.receive(
            &app,
            "capabilities",
            Ok(json!({"model_slots":["conversation","task","review","translation"]})),
        );
        use slint::Model;
        assert_eq!(app.get_model_slots().row_count(), 4);
        assert_eq!(
            app.get_model_slots().row_data(1).unwrap().selected,
            "task-model"
        );
        assert!(!app.get_model_slots().row_data(3).unwrap().available);
        state.receive(
            &app,
            "task-project",
            Ok(json!({"scope":"project:test","root":"C:/test"})),
        );
        let (_, command) = commands.recv().unwrap();
        assert_eq!(command["type"], "input_submit");
        assert_eq!(command["input"]["intent"], "mission");
        assert_eq!(command["input"]["model_id"], "task-model");
        assert_eq!(command["input"]["review_model_id"], "review-model");
        state.model_slots = vec!["conversation".into(), "review".into()];
        state.refresh_slots(&app);
        assert_eq!(app.get_model_slots().row_count(), 2);
    }
}
