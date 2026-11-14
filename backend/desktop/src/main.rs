mod audio;
#[cfg(windows)]
mod audio_tray;
mod bridge;
mod browser;
mod catalog;
#[cfg(windows)]
mod chromium_profile;
mod transport;
mod voice;

use catalog::Catalog;
use eframe::egui::{self, Color32, RichText};
use serde_json::{Value, json};
use std::time::{Duration, Instant};
use transport::Connection;
use voice::{Phase, Transcript, Voice};

const VOICE_SESSION: &str = "presence-voice";

struct VoiceJob {
    id: String,
    translation: bool,
    language: String,
}

fn main() -> eframe::Result {
    let mut args = std::env::args().skip(1);
    let endpoint = args.next().unwrap_or_else(|| "desktop".into());
    if endpoint == "--bridge" {
        let endpoint = args.next().unwrap_or_else(|| "desktop".into());
        if args.next().is_some() {
            eprintln!("Uso: synapse-desktop --bridge [endpoint local]");
            std::process::exit(2);
        }
        if let Err(error) = bridge::serve(endpoint) {
            eprintln!("{error}");
            std::process::exit(1);
        }
        return Ok(());
    }
    let mission = args.next().unwrap_or_default();
    if args.next().is_some() {
        eprintln!("Uso: synapse-desktop [endpoint local] [missão]");
        std::process::exit(2);
    }
    eframe::run_native(
        "Synapse",
        eframe::NativeOptions {
            viewport: egui::ViewportBuilder::default()
                .with_inner_size([1120.0, 760.0])
                .with_min_inner_size([640.0, 520.0]),
            ..Default::default()
        },
        Box::new(|creation| {
            let mut visuals = egui::Visuals::dark();
            visuals.panel_fill = Color32::from_rgb(8, 16, 24);
            visuals.window_fill = visuals.panel_fill;
            visuals.selection.bg_fill = Color32::from_rgb(19, 90, 105);
            creation.egui_ctx.set_visuals(visuals);
            creation.egui_ctx.enable_accesskit();
            Ok(Box::new(Desktop::new(endpoint, mission)))
        }),
    )
}

struct Desktop {
    endpoint: String,
    connection: Connection,
    connected: bool,
    pending: usize,
    error: String,
    workspace: bool,
    browser_visible: bool,
    browser: browser::Browser,
    voice: Voice,
    voice_job: Option<VoiceJob>,
    voice_language: String,
    voice_turn_cancelled: bool,
    translator: Value,
    translator_source: String,
    voice_reply: Option<String>,
    voice_background: bool,
    voice_devices: Option<audio::Devices>,
    #[cfg(windows)]
    tray: Option<audio_tray::Tray>,
    rail: bool,
    model: String,
    automatic_model_budget_mib: u32,
    models: Vec<String>,
    scope: String,
    project_path: String,
    project: Value,
    chat_id: String,
    active_chat: String,
    chat_cursor: u64,
    messages: Vec<Value>,
    message: String,
    context_scope: String,
    context_key: String,
    job_id: Option<String>,
    mission_id: String,
    objective: String,
    git_paths: String,
    mission_skill: Option<Value>,
    chat_skill: Option<Value>,
    skill_package_result: Value,
    skill_package_input: String,
    skill_package_url: String,
    skill_package_source: Option<String>,
    skill_catalog: Value,
    skill_package_download: Option<std::sync::mpsc::Receiver<Result<Value, String>>>,
    mission: Value,
    plan: Value,
    run: Value,
    recovery: Value,
    recovery_mode: Option<&'static str>,
    cursor: u64,
    events: Vec<Value>,
    catalog: Catalog,
    catalog_ready: bool,
    poll: Instant,
}

impl Desktop {
    fn new(endpoint: String, mission_id: String) -> Self {
        let connection = Connection::start(endpoint.clone());
        let mut app = Self {
            endpoint,
            connection,
            connected: false,
            pending: 0,
            error: String::new(),
            workspace: !mission_id.is_empty(),
            browser_visible: false,
            browser: browser::Browser::default(),
            voice: Voice::new(),
            voice_job: None,
            voice_language: "pt-BR".into(),
            voice_turn_cancelled: false,
            translator: Value::Null,
            translator_source: "pt-BR".into(),
            voice_reply: None,
            voice_background: false,
            voice_devices: None,
            #[cfg(windows)]
            tray: None,
            rail: true,
            model: String::new(),
            automatic_model_budget_mib: 0,
            models: Vec::new(),
            scope: String::new(),
            project_path: String::new(),
            project: Value::Null,
            chat_id: String::new(),
            active_chat: String::new(),
            chat_cursor: 0,
            messages: Vec::new(),
            message: String::new(),
            context_scope: String::new(),
            context_key: String::new(),
            job_id: None,
            mission_id,
            objective: String::new(),
            git_paths: String::new(),
            mission_skill: None,
            chat_skill: None,
            skill_package_result: Value::Null,
            skill_package_input: String::new(),
            skill_package_url: String::new(),
            skill_package_source: None,
            skill_catalog: Value::Null,
            skill_package_download: None,
            mission: Value::Null,
            plan: Value::Null,
            run: Value::Null,
            recovery: Value::Null,
            recovery_mode: None,
            cursor: 0,
            events: Vec::new(),
            catalog: Catalog::default(),
            catalog_ready: false,
            poll: Instant::now(),
        };
        app.send("health", json!({"type":"health"}));
        app
    }

    fn send(&mut self, tag: &'static str, command: Value) {
        match self.connection.requests.try_send((tag, command)) {
            Ok(()) => self.pending += 1,
            Err(error) => self.error = error.to_string(),
        }
    }

    fn select_project(&mut self, scope: &str) {
        if self.scope != scope {
            self.scope = scope.into();
            self.mission_skill = None;
            self.git_paths.clear();
        }
        self.project = Value::Null;
        self.send("project", json!({"type":"project_get","scope":scope}));
    }

    fn register_project(&mut self, scope: &str, root: &str) {
        self.send(
            "project",
            json!({"type":"project_register","scope":scope,"root":root}),
        );
    }

    fn chat(&mut self) {
        if !self.active_chat.is_empty() {
            self.send(
                "chat",
                json!({"type":"chat_get","chat_id":self.active_chat,"after":self.chat_cursor}),
            );
        }
    }

    fn mission_query(&mut self, command: &'static str) {
        self.send(
            command,
            json!({"type":command,"mission_id":self.mission_id}),
        );
    }

    fn receive(&mut self, tag: &'static str, result: Result<Value, String>) {
        self.pending = self.pending.saturating_sub(1);
        let value = match result {
            Ok(value) => value,
            Err(error) => {
                if tag == "connection" {
                    self.pending = 0;
                    self.connected = false;
                    self.voice.disable();
                    self.voice_job = None;
                    self.project = Value::Null;
                    self.mission = Value::Null;
                    self.run = Value::Null;
                    self.recovery = Value::Null;
                    self.recovery_mode = None;
                }
                if matches!(tag, "voice-turn" | "voice-job" | "voice-mode-change") {
                    self.voice_job = None;
                    self.voice.error = Some(error.clone());
                    if self.voice.phase == Phase::Processing {
                        self.voice.resume();
                    }
                }
                if !matches!(tag, "mission_run_get" | "mission_plan_get")
                    || !error.starts_with("not_found ·")
                {
                    self.error = if tag == "plan-start" && error.starts_with("no_matching_model ·")
                    {
                        "Nenhum modelo compatível cabe no orçamento informado. Ajuste o orçamento ou escolha um modelo.".into()
                    } else {
                        error
                    };
                }
                return;
            }
        };
        match tag {
            "skill-package" => self.skill_package_result = value,
            "model-route" => {
                if let Some(id) = value["model_id"].as_str() {
                    self.model = id.to_owned();
                }
            }
            "health" => {
                self.connected = true;
                self.send("models", json!({"type":"models_list","limit":100}));
                self.send(
                    "voice-mode",
                    json!({"type":"voice_translator_get","session_id":VOICE_SESSION}),
                );
                self.chat();
                if !self.mission_id.is_empty() {
                    self.refresh();
                }
            }
            "voice-mode" | "voice-mode-change" => {
                self.update_voice_mode(value);
                if tag == "voice-mode-change" && self.voice.phase == Phase::Processing {
                    self.voice.resume();
                }
            }
            "voice-turn" => self.voice_turn_received(value),
            "voice-job" => self.voice_job_received(value),
            "project" => {
                if let Some(scope) = value["scope"].as_str() {
                    if self.scope != scope {
                        self.mission_skill = None;
                        self.git_paths.clear();
                    }
                    self.scope = scope.into();
                    self.catalog.projects.insert(scope.into());
                    self.project = value;
                }
            }
            "models" => {
                if let Some(models) = value["models"].as_array() {
                    self.models = models
                        .iter()
                        .filter_map(|model| model["id"].as_str().map(str::to_owned))
                        .collect();
                    if self.model.is_empty() && self.models.len() == 1 {
                        self.model.clone_from(&self.models[0]);
                    }
                }
            }
            "chat-create" => {
                self.active_chat = value["chat_id"].as_str().unwrap_or_default().into();
                self.chat();
            }
            "chat" => {
                if let Some(messages) = value["messages"].as_array() {
                    self.messages.extend(messages.iter().cloned());
                }
                self.chat_cursor = value["next_cursor"].as_u64().unwrap_or(self.chat_cursor);
                if value["has_more"] == true {
                    self.chat();
                }
            }
            "conversation" => {
                self.message.clear();
                self.job_id = value["job_id"].as_str().map(str::to_owned);
                self.chat();
            }
            "job" if value["status"] != "running" => {
                self.job_id = None;
                if value["status"] != "succeeded" {
                    self.error = format!("Conversa: {} {}", value["status"], value["error"]);
                }
                self.chat();
            }
            "plan-start" | "mission_plan_get" => self.plan = value,
            "mission_get" => self.mission = value,
            "approval" => {
                self.mission["state"] = value["state"].clone();
                if let Some(plan) = self.plan.as_object_mut() {
                    plan.remove("swarm_recommendation");
                }
            }
            "mission-cancel" => self.refresh(),
            "mission_run_get" | "mission_execute" | "resolve" => self.run = value,
            "mission_recovery_inspect" => self.recovery = value,
            "events" => {
                self.cursor = value["next_cursor"].as_u64().unwrap_or(self.cursor);
                if let Some(events) = value["events"].as_array() {
                    self.catalog_ready = events.len() < 100;
                    for event in events {
                        self.catalog.observe(event);
                    }
                    self.events.extend(events.iter().cloned());
                    let overflow = self.events.len().saturating_sub(300);
                    self.events.drain(..overflow);
                    if events.iter().any(|event| {
                        matches!(
                            event["kind"].as_str(),
                            Some("voice_translator_started" | "voice_translator_stopped")
                        ) && event["payload"]["session_id"] == VOICE_SESSION
                    }) {
                        self.send(
                            "voice-mode",
                            json!({"type":"voice_translator_get","session_id":VOICE_SESSION}),
                        );
                    }
                }
            }
            _ => {}
        }
    }

    fn refresh(&mut self) {
        self.mission_query("mission_get");
        self.mission_query("mission_run_get");
        self.mission_query("mission_plan_get");
    }

    fn header(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.heading("SYNAPSE");
            if ui
                .selectable_label(!self.workspace && !self.browser_visible, "Presence")
                .clicked()
            {
                self.workspace = false;
                self.browser_visible = false;
            }
            if ui
                .selectable_label(self.workspace && !self.browser_visible, "Workspace")
                .clicked()
            {
                self.workspace = true;
                self.browser_visible = false;
            }
            if ui
                .selectable_label(self.browser_visible, "Navegador")
                .clicked()
            {
                self.browser_visible = true;
            }
            if self.connected {
                ui.label(RichText::new("Core conectado").color(Color32::LIGHT_GREEN));
            } else if ui.button("Reconectar").clicked() && self.pending == 0 {
                self.connection = Connection::start(self.endpoint.clone());
                self.error.clear();
                self.send("health", json!({"type":"health"}));
            }
        });
        ui.separator();
        ui.horizontal(|ui| {
            ui.label("Projeto");
            if ui
                .add_enabled(
                    self.pending == 0,
                    egui::TextEdit::singleline(&mut self.scope).hint_text("project:meu-projeto"),
                )
                .changed()
            {
                self.project = Value::Null;
                self.mission_skill = None;
                self.git_paths.clear();
            }
            let mut selected = None;
            ui.add_enabled_ui(self.connected && self.pending == 0, |ui| {
                egui::ComboBox::from_id_salt("projects")
                    .selected_text("Projetos cadastrados")
                    .show_ui(ui, |ui| {
                        for scope in &self.catalog.projects {
                            if ui.selectable_label(self.scope == *scope, scope).clicked() {
                                selected = Some(scope.clone());
                            }
                        }
                    });
            });
            if let Some(scope) = selected {
                self.select_project(&scope);
            }
        });
        ui.horizontal_wrapped(|ui| {
            ui.label("Modelo local");
            ui.add(egui::TextEdit::singleline(&mut self.model).hint_text("ID registrado"));
            if self.workspace && !self.browser_visible {
                ui.add(egui::DragValue::new(&mut self.automatic_model_budget_mib)
                    .range(0..=262144).suffix(" MiB"))
                    .on_hover_text("Orçamento para seleção automática no planejamento. Zero usa o modelo escolhido.");
            }
            egui::ComboBox::from_id_salt("models")
                .selected_text("Modelos")
                .show_ui(ui, |ui| {
                    for model in &self.models {
                        ui.selectable_value(&mut self.model, model.clone(), model);
                    }
                });
        });
        if !self.error.is_empty() {
            ui.horizontal_wrapped(|ui| {
                ui.colored_label(Color32::LIGHT_RED, &self.error);
                if ui.small_button("Dispensar").clicked() {
                    self.error.clear();
                }
            });
        }
    }

    fn presence(&mut self, ui: &mut egui::Ui) {
        ui.heading("A.R.T.E.M.I.S");
        self.voice_controls(ui);
        ui.horizontal(|ui| {
            ui.add(egui::TextEdit::singleline(&mut self.chat_id).hint_text("Identificador da conversa"));
            let ready = self.connected && self.pending == 0 && self.job_id.is_none() && !self.chat_id.is_empty();
            let mut previous_chat = None;
            ui.add_enabled_ui(self.connected && self.pending == 0 && self.job_id.is_none(), |ui| {
                egui::ComboBox::from_id_salt("chats").selected_text("Conversas salvas").show_ui(ui, |ui| {
                    for (id, scope) in &self.catalog.chats {
                        if ui.selectable_label(self.active_chat == *id, format!("{id} · {scope}")).clicked() { previous_chat = Some(id.clone()); }
                    }
                });
            });
            if let Some(id) = &previous_chat { self.chat_id.clone_from(id); }
            let open = previous_chat.is_some() || ui.add_enabled(ready, egui::Button::new("Abrir histórico")).clicked();
            let create = ui.add_enabled(ready && !self.scope.is_empty(), egui::Button::new("Novo chat")).clicked();
            if open || create {
                self.active_chat = if open { self.chat_id.clone() } else { String::new() };
                self.messages.clear();
                self.chat_cursor = 0;
                if create { self.send("chat-create", json!({"type":"chat_create","chat_id":self.chat_id,"title":self.chat_id,"scope":self.scope})); }
                else { self.chat(); }
            }
            ui.label(&self.active_chat);
        });
        ui.horizontal(|ui| {
            ui.label("Referência de memória");
            ui.add(
                egui::TextEdit::singleline(&mut self.context_scope).hint_text("project:projeto"),
            );
            ui.add(egui::TextEdit::singleline(&mut self.context_key).hint_text("Chave"));
        });
        if let Some(skills) = self
            .catalog
            .chats
            .get(&self.active_chat)
            .and_then(|scope| self.catalog.skills.get(scope))
        {
            if self
                .chat_skill
                .as_ref()
                .is_some_and(|pin| !skills.contains(pin))
            {
                self.chat_skill = None;
            }
            egui::ComboBox::from_id_salt("chat-skill")
                .selected_text(
                    self.chat_skill
                        .as_ref()
                        .map(skill_label)
                        .unwrap_or_else(|| "Sem Skill".into()),
                )
                .show_ui(ui, |ui| {
                    ui.selectable_value(&mut self.chat_skill, None, "Sem Skill");
                    for skill in skills {
                        ui.selectable_value(
                            &mut self.chat_skill,
                            Some(skill.clone()),
                            if self.catalog.is_active_skill(skill) {
                                format!("{} · ativa", skill_label(skill))
                            } else {
                                skill_label(skill)
                            },
                        );
                    }
                });
        } else {
            self.chat_skill = None;
        }
        egui::ScrollArea::vertical()
            .id_salt("history")
            .stick_to_bottom(true)
            .max_height((ui.available_height() - 90.0).max(80.0))
            .show(ui, |ui| {
                for message in &self.messages {
                    let user = message["role"] == "user";
                    ui.with_layout(
                        if user {
                            egui::Layout::right_to_left(egui::Align::TOP)
                        } else {
                            egui::Layout::left_to_right(egui::Align::TOP)
                        },
                        |ui| {
                            egui::Frame::new()
                                .fill(if user {
                                    Color32::from_rgb(14, 56, 68)
                                } else {
                                    Color32::from_rgb(22, 31, 43)
                                })
                                .inner_margin(12)
                                .corner_radius(10)
                                .show(ui, |ui| {
                                    ui.set_max_width(550.0);
                                    ui.label(message["content"].as_str().unwrap_or_default());
                                });
                        },
                    );
                    ui.add_space(8.0);
                }
            });
        ui.add(
            egui::TextEdit::multiline(&mut self.message)
                .desired_rows(2)
                .desired_width(f32::INFINITY)
                .hint_text("Converse com A.R.T.E.M.I.S"),
        );
        let complete_reference = self.context_scope.is_empty() == self.context_key.is_empty();
        let ready = self.connected
            && self.pending == 0
            && self.job_id.is_none()
            && !self.active_chat.is_empty()
            && !self.model.is_empty()
            && !self.message.trim().is_empty()
            && complete_reference
            && self.catalog_ready;
        if ui.add_enabled(ready, egui::Button::new("Enviar")).clicked() {
            self.send_message(self.chat_skill.clone(), None);
        }
        if self.job_id.is_some() {
            ui.spinner();
        }
    }

    fn fetch_skill(&mut self, address: String, catalog: bool) {
        self.error.clear();
        self.skill_package_result = Value::Null;
        self.skill_package_source = None;
        self.skill_package_input.clear();
        let (send, receive) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let _ = send.send(browser::fetch_skill_document(&address, catalog));
        });
        self.skill_package_download = Some(receive);
    }

    fn inspect_skill_input(&mut self, scope: &str) -> Result<(), String> {
        if self.skill_package_download.is_some() {
            return Err("Aguarde o fim da busca da Skill.".into());
        }
        let mut package = serde_json::from_str::<synapse_core::contracts::SkillPackage>(
            &self.skill_package_input,
        )
        .map_err(|error| format!("Pacote inválido: {error}"))?;
        if package.manifest.scope != scope {
            return Err("O pacote deve pertencer ao projeto selecionado.".into());
        }
        package.source_url.clone_from(&self.skill_package_source);
        self.skill_package_result = Value::Null;
        self.send(
            "skill-package",
            json!({"type":"skill_inspect","package":package}),
        );
        Ok(())
    }

    fn show_skill_import(&mut self, ui: &mut egui::Ui) {
        ui.collapsing("Importar Skill", |ui| {
            ui.horizontal(|ui| {
                ui.add(
                    egui::TextEdit::singleline(&mut self.skill_package_url)
                        .hint_text("URL HTTPS do pacote ou catálogo"),
                );
                let ready = self.pending == 0
                    && self.skill_package_download.is_none()
                    && !self.skill_package_url.trim().is_empty();
                if ui
                    .add_enabled(ready, egui::Button::new("Buscar pacote"))
                    .clicked()
                {
                    self.fetch_skill(self.skill_package_url.trim().to_owned(), false);
                }
                if ui
                    .add_enabled(ready, egui::Button::new("Buscar catálogo"))
                    .clicked()
                {
                    self.skill_catalog = Value::Null;
                    self.fetch_skill(self.skill_package_url.trim().to_owned(), true);
                }
            });
            if self.skill_package_download.is_some() {
                ui.spinner();
                ui.ctx().request_repaint_after(Duration::from_millis(100));
            }
            let mut selected = None;
            if let Some(entries) = self.skill_catalog["packages"].as_array() {
                ui.label(self.skill_catalog["source"].as_str().unwrap_or_default());
                egui::ScrollArea::vertical()
                    .id_salt("skill-catalog")
                    .max_height(130.0)
                    .show(ui, |ui| {
                        for entry in entries {
                            if ui
                                .add_enabled(
                                    self.pending == 0 && self.skill_package_download.is_none(),
                                    egui::Button::new(entry["name"].as_str().unwrap_or_default()),
                                )
                                .on_hover_text(entry["url"].as_str().unwrap_or_default())
                                .clicked()
                            {
                                selected = entry["url"].as_str().map(str::to_owned);
                            }
                        }
                    });
                if entries.is_empty() {
                    ui.label("O catálogo está vazio.");
                }
            }
            if let Some(address) = selected {
                self.fetch_skill(address, false);
            }
            let candidates = self.mission_skill_suggestions();
            if !candidates.is_empty() {
                ui.collapsing("Skills do catálogo para este objetivo", |ui| {
                    for candidate in candidates {
                        let address = candidate["url"].as_str().unwrap_or_default();
                        if ui
                            .add_enabled(
                                self.pending == 0 && self.skill_package_download.is_none(),
                                egui::Button::new(candidate["name"].as_str().unwrap_or_default()),
                            )
                            .on_hover_text(address)
                            .clicked()
                        {
                            self.fetch_skill(address.to_owned(), false);
                        }
                    }
                });
            }
            if let Some(source) = &self.skill_package_source {
                ui.label(source);
            }
            let input = ui.add_enabled(
                self.pending == 0 && self.skill_package_download.is_none(),
                egui::TextEdit::multiline(&mut self.skill_package_input)
                    .hint_text("Pacote JSON da Skill")
                    .desired_rows(3)
                    .desired_width(f32::INFINITY)
                    .char_limit(48_000),
            );
            if input.changed() {
                self.skill_package_source = None;
                self.skill_package_result = Value::Null;
            }
            let ready =
                self.connected && self.pending == 0 && self.skill_package_download.is_none();
            if ui
                .add_enabled(ready, egui::Button::new("Inspecionar"))
                .clicked()
            {
                self.skill_package_result = Value::Null;
                if let Err(error) = self.inspect_skill_input(&self.scope.clone()) {
                    self.error = error;
                }
            }
            if let Some(digest) = self.skill_package_result["inspected_digest"].as_str() {
                let package = &self.skill_package_result["package"];
                let manifest = &package["manifest"];
                ui.label(format!(
                    "{} · {} · {}",
                    skill_label(manifest),
                    manifest["scope"].as_str().unwrap_or_default(),
                    package["license"].as_str().unwrap_or_default()
                ));
                ui.label(manifest["provenance"].as_str().unwrap_or_default());
                if let Some(source) = package["source_url"].as_str() {
                    ui.label(source);
                }
                egui::ScrollArea::vertical()
                    .id_salt("skill-review")
                    .max_height(150.0)
                    .show(ui, |ui| {
                        ui.label(manifest["instructions"].as_str().unwrap_or_default());
                    });
                if ui
                    .add_enabled(
                        ready && manifest["scope"].as_str() == Some(self.scope.as_str()),
                        egui::Button::new("Instalar versão inspecionada"),
                    )
                    .clicked()
                {
                    let command =
                        json!({"type":"skill_install","package":package,"inspected_digest":digest});
                    self.skill_package_result = Value::Null;
                    self.send("skill-package", command);
                }
            } else if let Some(installed) = self.skill_package_result.get("skill") {
                ui.label(format!("Skill instalada · {}", skill_label(installed)));
                if ui.add_enabled(
                    ready && installed["scope"].as_str() == Some(self.scope.as_str()),
                    egui::Button::new("Usar no próximo planejamento"),
                ).clicked() {
                    self.mission_skill = Some(json!({
                        "id": installed["id"], "scope": installed["scope"],
                        "version": installed["version"], "digest": self.skill_package_result["digest"],
                    }));
                }
            }
        });
    }

    fn workspace(&mut self, ui: &mut egui::Ui) {
        self.show_skill_import(ui);
        ui.horizontal(|ui| {
            ui.heading("Workspace");
            if self.mission_skill.is_none() && !self.mission_skill_suggestions().is_empty() {
                ui.label("Skills sugeridas em Importar Skill");
            }

            let toggle = if self.rail {
                "Recolher Context Rail"
            } else {
                "Abrir Context Rail"
            };
            if ui.button(toggle).clicked() {
                self.rail = !self.rail;
            }
        });
        ui.collapsing("Pasta do projeto", |ui| {
            ui.horizontal_wrapped(|ui| {
                ui.add(
                    egui::TextEdit::singleline(&mut self.project_path)
                        .hint_text("Caminho absoluto"),
                );
                let ready = self.connected
                    && self.pending == 0
                    && !self.scope.is_empty()
                    && !self.project_path.is_empty();
                if ui
                    .add_enabled(ready, egui::Button::new("Vincular pasta ao projeto"))
                    .clicked()
                {
                    self.register_project(&self.scope.clone(), &self.project_path.clone());
                }
            });
            if let Some(root) = self.project["root"].as_str() {
                ui.label(root);
            }
        });
        ui.horizontal(|ui| {
            if ui
                .add_enabled(
                    self.pending == 0,
                    egui::TextEdit::singleline(&mut self.mission_id)
                        .hint_text("Identificador da missão"),
                )
                .changed()
            {
                self.mission = Value::Null;
                self.plan = Value::Null;
                self.run = Value::Null;
                self.recovery = Value::Null;
                self.recovery_mode = None;
            }
            let mut previous_mission = None;
            ui.add_enabled_ui(self.connected && self.pending == 0, |ui| {
                egui::ComboBox::from_id_salt("missions")
                    .selected_text("Missões salvas")
                    .show_ui(ui, |ui| {
                        for id in &self.catalog.missions {
                            if ui.selectable_label(self.mission_id == *id, id).clicked() {
                                previous_mission = Some(id.clone());
                            }
                        }
                    });
            });
            if let Some(id) = previous_mission {
                self.mission_id = id;
                self.plan = Value::Null;
                self.mission = Value::Null;
                self.run = Value::Null;
                self.recovery = Value::Null;
                self.recovery_mode = None;
                self.refresh();
            }
            let ready = self.connected && self.pending == 0 && !self.mission_id.is_empty();
            if ui
                .add_enabled(ready, egui::Button::new("Consultar missão"))
                .clicked()
            {
                self.refresh();
            }
            if ui
                .add_enabled(ready, egui::Button::new("Consultar proposta"))
                .clicked()
            {
                self.mission_query("mission_plan_get");
            }
        });
        ui.add(
            egui::TextEdit::multiline(&mut self.objective)
                .desired_rows(2)
                .desired_width(f32::INFINITY)
                .hint_text("Objetivo da missão"),
        );
        if let Some(skills) = self.catalog.skills.get(&self.scope) {
            let selected = self
                .mission_skill
                .as_ref()
                .map(skill_label)
                .unwrap_or_else(|| "Sem Skill".into());
            egui::ComboBox::from_id_salt("mission-skill")
                .selected_text(selected)
                .show_ui(ui, |ui| {
                    ui.selectable_value(&mut self.mission_skill, None, "Sem Skill");
                    for skill in skills {
                        ui.selectable_value(
                            &mut self.mission_skill,
                            Some(skill.clone()),
                            if self.catalog.is_active_skill(skill) {
                                format!("{} · ativa", skill_label(skill))
                            } else {
                                skill_label(skill)
                            },
                        );
                    }
                });
        }
        ui.collapsing("Edição Git local", |ui| {
            ui.add(
                egui::TextEdit::multiline(&mut self.git_paths)
                    .desired_rows(2)
                    .hint_text("Um caminho rastreado por linha"),
            );
        });
        let ready = self.connected && self.pending == 0 && !self.mission_id.is_empty();
        if ui
            .add_enabled(
                ready
                    && !self.scope.is_empty()
                    && (!self.model.is_empty() || self.automatic_model_budget_mib != 0)
                    && !self.objective.trim().is_empty(),
                egui::Button::new("Planejar"),
            )
            .clicked()
        {
            let paths = self
                .git_paths
                .lines()
                .map(str::trim)
                .filter(|path| !path.is_empty())
                .map(str::to_owned)
                .collect();
            let budget = (self.automatic_model_budget_mib != 0)
                .then_some(u64::from(self.automatic_model_budget_mib) * 1024 * 1024);
            self.plan_mission(paths, self.mission_skill.clone(), budget);
        }
        if let Some(candidates) = self.plan["skill_candidates"].as_array() {
            ui.collapsing("Skills encontradas no projeto", |ui| {
                ui.label("Selecione uma versão para o próximo planejamento.");
                for candidate in candidates {
                    if ui
                        .add_enabled(
                            candidate["scope"].as_str() == Some(self.scope.as_str())
                                || candidate["scope"] == "global",
                            egui::Button::new(skill_label(candidate)),
                        )
                        .clicked()
                    {
                        self.mission_skill = Some(json!({
                            "id":candidate["id"],"version":candidate["version"],
                            "scope":candidate["scope"],"digest":candidate["digest"]
                        }));
                    }
                }
            });
        }
        if let Some(reason) = self.plan["swarm_recommendation"]["reason"].as_str() {
            ui.collapsing("Sugestão do Planner · Swarm", |ui| {
                ui.label(reason);
                if let Some(bytes) =
                    self.plan["swarm_recommendation"]["estimated_peak_model_bytes"].as_u64()
                {
                    ui.label(format!(
                        "Sequencial · pico estimado de {:.2} GiB para o modelo",
                        bytes as f64 / 1073741824.0
                    ));
                } else {
                    ui.label("Sequencial · estimativa de memória incompleta");
                }
                if let Some(roles) = self.plan["swarm_recommendation"]["roles"].as_array() {
                    for role in roles {
                        let label = if role["role"] == "implementation" {
                            "Implementação"
                        } else {
                            "Verificação"
                        };
                        ui.label(format!(
                            "{label} · {} · {:.2} GiB estimados",
                            role["model_id"].as_str().unwrap_or_default(),
                            role["memory_bytes"].as_u64().unwrap_or(0) as f64 / 1073741824.0
                        ));
                    }
                }
                for key in ["benefit", "risk"] {
                    if let Some(text) = self.plan["swarm_recommendation"][key].as_str() {
                        ui.label(text);
                    }
                }
            });
        }
        ui.horizontal_wrapped(|ui| {
            let state = self.mission["state"]
                .as_str()
                .unwrap_or_default()
                .to_owned();
            let digest = self.mission["contract_digest"]
                .as_str()
                .unwrap_or_default()
                .to_owned();
            if ui
                .add_enabled(
                    ready && state == "proposed" && !digest.is_empty(),
                    egui::Button::new("Aprovar contrato exibido"),
                )
                .clicked()
            {
                let digest = digest.to_owned();
                self.approve_mission(&digest, None);
            }
            if ui
                .add_enabled(
                    ready
                        && state == "proposed"
                        && !digest.is_empty()
                        && !self.mission["contract"]["execution"].is_null(),
                    egui::Button::new("Aprovar com Swarm"),
                )
                .clicked()
            {
                let consent = if self.plan["mission"]["contract_digest"].as_str()
                    != Some(digest.as_str())
                    || self.plan["swarm_recommendation"].is_null()
                {
                    synapse_core::contracts::SwarmConsent::Direct
                } else {
                    synapse_core::contracts::SwarmConsent::Recommended
                };
                self.approve_mission(&digest, Some(consent));
            }
            if ui
                .add_enabled(
                    ready && state == "approved" && self.run.is_null(),
                    egui::Button::new("Executar missão"),
                )
                .clicked()
            {
                self.mission_query("mission_execute");
            }
            if ui
                .add_enabled(
                    ready
                        && matches!(
                            self.run["status"].as_str(),
                            Some("generating" | "checking" | "reviewing")
                        ),
                    egui::Button::new("Cancelar execução"),
                )
                .clicked()
            {
                self.cancel_mission();
            }
            if ui
                .add_enabled(
                    ready && self.run["status"] == "recovery_required",
                    egui::Button::new("Inspecionar recuperação"),
                )
                .clicked()
            {
                self.mission_query("mission_recovery_inspect");
            }
            for (mode, label) in [
                ("finalize", "Confirmar publicação"),
                ("rollback", "Reverter efeitos"),
            ] {
                if ui
                    .add_enabled(
                        ready
                            && self.run["status"] == "recovery_required"
                            && !self.recovery.is_null(),
                        egui::Button::new(label),
                    )
                    .clicked()
                {
                    self.recovery_mode = Some(mode);
                }
            }
        });
        if let Some(mode) = self.recovery_mode {
            ui.horizontal(|ui| {
                ui.label(format!("Confirmar a operação {}?", if mode == "finalize" { "de publicação" } else { "de reversão" }));
                if ui.button("Confirmar").clicked() && ready {
                    self.send("resolve", json!({"type":"mission_recovery_resolve","mission_id":self.mission_id,"mode":mode}));
                    self.recovery_mode = None;
                }
                if ui.button("Cancelar").clicked() { self.recovery_mode = None; }
            });
        }
        match self.run["error"].as_str() {
            Some("model_capacity_busy") => {
                ui.colored_label(Color32::YELLOW,
                    "O LM Studio já tem outro modelo carregado. Libere espaço e planeje uma nova missão.");
            }
            Some("model_unavailable") => {
                ui.colored_label(Color32::YELLOW,
                    "O modelo da missão está indisponível. Selecione um modelo disponível em um novo plano.");
            }
            _ => {}
        }
        ui.separator();
        if self.rail {
            egui::Panel::right("context-rail")
                .default_size(320.0)
                .resizable(true)
                .show_inside(ui, |ui| self.context_rail(ui));
        }
        if self.run["swarm"]["roles"].is_array() {
            self.swarm_grid(ui);
        } else {
            self.terminal(ui);
        }
    }

    fn swarm_grid(&self, ui: &mut egui::Ui) {
        if let Some(roles) = self.run["swarm"]["roles"].as_array() {
            ui.horizontal(|ui| {
                ui.heading("Swarm");
                if let Some(label) = match self.run["swarm"]["source"].as_str() {
                    Some("direct") => Some("Pedido direto"),
                    Some("recommended") => Some("Recomendação aceita"),
                    _ => None,
                } {
                    ui.label(label);
                }
            });
            ui.columns(roles.len().max(1), |columns| {
                for (column, role) in columns.iter_mut().zip(roles) {
                    let name = if role["role"] == "implementation" {
                        "Implementação"
                    } else {
                        "Verificação"
                    };
                    let status = match role["status"].as_str() {
                        Some("running") => "Em execução",
                        Some("checking") => "Testes da candidata",
                        Some("completed") => "Concluída",
                        _ => "Aguardando",
                    };
                    column.group(|ui| {
                        ui.strong(name);
                        ui.monospace(status);
                        if let Some(model) = role["model_id"].as_str() {
                            ui.monospace(model);
                        }
                        if let Some(log) = role["log"].as_array() {
                            egui::ScrollArea::vertical()
                                .id_salt(name)
                                .max_height(140.0)
                                .show(ui, |ui| {
                                    for event in log {
                                        let line = match event["kind"].as_str() {
                                            Some("generation_started") => {
                                                "Geração iniciada".to_owned()
                                            }
                                            Some("candidate_sealed") => format!(
                                                "Candidata selada · SHA-256 {}",
                                                event["digest"].as_str().unwrap_or_default()
                                            ),
                                            Some("check_passed") => {
                                                format!("Verificação {} concluída", event["number"])
                                            }
                                            Some("check_running") => format!(
                                                "Verificação {} em execução",
                                                event["number"]
                                            ),
                                            Some("review_started") => {
                                                "Revisão independente iniciada".to_owned()
                                            }
                                            Some("review_approved") => {
                                                "QA aprovou a candidata".to_owned()
                                            }
                                            Some("publication_started") => {
                                                "Publicando artefatos aprovados".to_owned()
                                            }
                                            Some("postchecking") => format!(
                                                "Verificações após publicação concluídas: {}",
                                                event["completed"]
                                            ),
                                            _ => continue,
                                        };
                                        ui.monospace(line);
                                    }
                                });
                        }
                    });
                }
            });
        }
    }

    fn terminal(&self, ui: &mut egui::Ui) {
        egui::Frame::new()
            .fill(Color32::from_rgb(6, 13, 20))
            .inner_margin(12)
            .show(ui, |ui| {
                ui.set_min_size(ui.available_size());
                ui.monospace(
                    RichText::new(format!("artemis@workspace:{}$", self.scope))
                        .color(Color32::from_rgb(63, 222, 230)),
                );
                egui::ScrollArea::vertical()
                    .id_salt("terminal")
                    .stick_to_bottom(true)
                    .show(ui, |ui| {
                        for event in self.events.iter().filter(|event| {
                            !self.mission_id.is_empty()
                                && event["payload"]["mission_id"] == self.mission_id
                        }) {
                            ui.monospace(format!(
                                "[{}] {} {}",
                                event["cursor"], event["kind"], event["payload"]
                            ));
                        }
                    });
            });
    }

    fn context_rail(&self, ui: &mut egui::Ui) {
        ui.heading("Context Rail");
        egui::ScrollArea::vertical().id_salt("rail").show(ui, |ui| {
            let scope = self.mission["contract"]["scope"]
                .as_str()
                .unwrap_or(&self.scope);
            ui.label(scope);
            let root = if self.mission.is_null() {
                self.plan["project_root"]
                    .as_str()
                    .or_else(|| self.project["root"].as_str())
            } else {
                self.mission["project_root"].as_str()
            };
            if let Some(root) = root {
                ui.label(root);
            }
            if let Some(diff) = self.run["git_diff"].as_array() {
                ui.collapsing("Alterações Git revisadas", |ui| {
                    for file in diff {
                        ui.collapsing(file["path"].as_str().unwrap_or_default(), |ui| {
                            for (label, field) in [("Antes", "before"), ("Depois", "after")] {
                                if let Some(text) = file[field].as_str() {
                                    ui.label(label);
                                    ui.monospace(text);
                                }
                            }
                        });
                    }
                });
            }
            for (title, value) in [
                ("Proposta", &self.plan),
                ("Contrato", &self.mission),
                ("Execução e QA", &self.run),
                ("Recuperação", &self.recovery),
            ] {
                if !value.is_null() {
                    egui::CollapsingHeader::new(title)
                        .default_open(title == "Contrato" || title == "Execução e QA")
                        .show(ui, |ui| {
                            ui.monospace(serde_json::to_string_pretty(value).unwrap_or_default());
                        });
                }
            }
        });
    }
}

fn skill_label(skill: &Value) -> String {
    format!(
        "{} · {}",
        skill["id"].as_str().unwrap_or_default(),
        skill["version"].as_str().unwrap_or_default()
    )
}

impl Desktop {
    fn send_message(&mut self, skill: Option<Value>, budget: Option<u64>) {
        let mut command = json!({"type":"conversation_start","chat_id":self.active_chat,"model_id":self.model,"content":self.message});
        if let Some(budget) = budget {
            command["model_id"] = json!("");
            command["model_memory_budget_bytes"] = json!(budget);
        }
        if let Some(skill) = skill {
            command["skill"] = skill;
        }
        let references = if self.context_key.is_empty() {
            self.catalog.references(&self.message)
        } else {
            Ok(vec![
                json!({"scope":self.context_scope,"key":self.context_key}),
            ])
        };
        match references {
            Ok(references) => {
                if !references.is_empty() {
                    command["context"] = json!(references);
                }
                self.send("conversation", command);
            }
            Err(error) => self.error = error.into(),
        }
    }

    fn mission_skill_suggestions(&self) -> Vec<Value> {
        if self.mission_skill.is_some() {
            return Vec::new();
        }
        catalog::matching_skill_packages(&self.skill_catalog, &self.objective)
    }

    fn plan_mission(
        &mut self,
        git_edit_paths: Vec<String>,
        skill: Option<Value>,
        budget: Option<u64>,
    ) {
        let mut command = json!({"type":"mission_plan_start","mission_id":self.mission_id,"scope":self.scope,"model_id":self.model,"review_model_id":self.model,"objective":self.objective,"review_generation":{"max_output_tokens":512,"timeout_ms":120000,"reasoning_effort":"none"}});
        if let Some(budget) = budget {
            command["model_id"] = json!("");
            command["review_model_id"] = json!("");
            command["model_memory_budget_bytes"] = json!(budget);
        }
        if !git_edit_paths.is_empty() {
            command["git_edit_paths"] = json!(git_edit_paths);
        }
        if let Some(skill) = skill {
            command["skill"] = skill;
        }
        self.send("plan-start", command);
    }

    fn cancel_mission(&mut self) {
        self.send(
            "mission-cancel",
            json!({
                "type":"mission_cancel","mission_id":self.mission_id,
                "reason":"Cancelamento solicitado no Workspace"
            }),
        );
    }

    fn approve_mission(
        &mut self,
        digest: &str,
        swarm: Option<synapse_core::contracts::SwarmConsent>,
    ) {
        if self.mission["state"] != "proposed" || self.mission["contract_digest"] != digest {
            self.error = "A aprovação exige o digest da proposta selecionada.".into();
            return;
        }
        let mut command =
            json!({"type":"mission_approve","mission_id":self.mission_id,"contract_digest":digest});
        if let Some(swarm) = swarm {
            command["swarm"] = json!(swarm);
        }
        self.send("approval", command);
    }

    fn voice_controls(&mut self, ui: &mut egui::Ui) {
        let levels = self.voice.audio.levels();
        let (region, _) = ui.allocate_exact_size(
            egui::vec2(ui.available_width(), 105.0),
            egui::Sense::hover(),
        );
        let center = region.center();
        let time = ui.input(|input| input.time) as f32;
        let amplitude = match self.voice.phase {
            Phase::Listening => levels.input.clamp(0.0, 1.0),
            Phase::Speaking => levels.output.clamp(0.0, 1.0),
            _ => 0.0,
        };
        let radius = 23.0
            + if self.voice.phase == Phase::Speaking {
                amplitude.sqrt() * 19.0
            } else {
                0.0
            };
        let brightness = (125.0 + amplitude.sqrt() * 130.0) as u8;
        let color = Color32::from_rgb(28, brightness, 220);
        let painter = ui.painter();
        for offset in [7.0, 13.0] {
            painter.circle_stroke(
                center,
                radius + offset,
                egui::Stroke::new(1.0, color.gamma_multiply(0.4)),
            );
        }
        painter.circle_stroke(center, radius, egui::Stroke::new(1.5, color));
        painter.circle_filled(center, radius / 5.0, color);
        if self.voice.phase == Phase::Processing {
            let offset = egui::Vec2::angled(time * 3.4) * (radius + 13.0);
            painter.circle_filled(center + offset, 3.5, color);
        }
        ui.horizontal_wrapped(|ui| {
            ui.label(if self.voice.phase == Phase::Wake {
                format!("Aguardando {}", self.voice.wake_name)
            } else {
                self.voice.phase.label().into()
            });
            if levels.capturing {
                ui.colored_label(Color32::LIGHT_GREEN, "Microfone ativo");
            }
            if !levels.eligible && self.voice.phase != Phase::Off {
                ui.label("Sessão de áudio indisponível");
            }
            if self.voice.phase == Phase::Off {
                if ui
                    .add_enabled(self.connected, egui::Button::new("Ativar microfone"))
                    .clicked()
                {
                    if let Err(error) = self.voice.enable(false) {
                        self.voice.error = Some(error);
                    }
                }
            } else {
                if ui.button("Desativar microfone").clicked() {
                    self.mute_voice();
                }
                if ui.button("Interromper").clicked() {
                    self.interrupt_voice();
                }
            }
            if self.voice.translator {
                ui.label(format!(
                    "Tradutor · {} ↔ {}",
                    self.translator["source_language"]
                        .as_str()
                        .unwrap_or_default(),
                    self.translator["target_language"]
                        .as_str()
                        .unwrap_or_default()
                ));
                if ui.button("Encerrar tradução").clicked() {
                    self.stop_translator();
                }
            } else {
                egui::ComboBox::from_id_salt("voice-source")
                    .selected_text(&self.translator_source)
                    .show_ui(ui, |ui| {
                        ui.selectable_value(
                            &mut self.translator_source,
                            "pt-BR".into(),
                            "Português → inglês",
                        );
                        ui.selectable_value(
                            &mut self.translator_source,
                            "en-US".into(),
                            "Inglês → português",
                        );
                    });
                if ui
                    .add_enabled(
                        self.connected && self.pending == 0,
                        egui::Button::new("Iniciar tradução"),
                    )
                    .clicked()
                {
                    let source = self.translator_source.clone();
                    let target = if source == "pt-BR" { "en-US" } else { "pt-BR" };
                    self.start_translator(&source, target);
                }
            }
        });
        if let Some(error) = &self.voice.error {
            ui.colored_label(Color32::LIGHT_RED, error);
        }
        if self.voice.translator {
            if let Some(reply) = &self.voice_reply {
                ui.label(reply);
            }
        }
        ui.collapsing("Áudio", |ui| {
            ui.add(
                egui::Slider::new(&mut self.voice.idle_seconds, 5..=120)
                    .suffix(" s")
                    .text("Tempo sem fala"),
            );
            ui.add_enabled(
                self.voice.phase == Phase::Off,
                egui::TextEdit::singleline(&mut self.voice.wake_name)
                    .hint_text("Palavra de ativação"),
            );
            if ui.button("Listar dispositivos").clicked() {
                match self.voice.audio.devices() {
                    Ok(devices) => self.voice_devices = Some(devices),
                    Err(error) => self.voice.error = Some(error),
                }
            }
            if let Some(devices) = &self.voice_devices {
                let mut input = self.voice.input.clone();
                let mut output = self.voice.output.clone();
                choose_audio_device(
                    ui,
                    "voice-input",
                    "Microfone padrão",
                    &mut input,
                    &devices.inputs,
                );
                choose_audio_device(
                    ui,
                    "voice-output",
                    "Saída padrão",
                    &mut output,
                    &devices.outputs,
                );
                if input != self.voice.input || output != self.voice.output {
                    self.interrupt_voice();
                    if let Err(error) = self.voice.switch(input, output) {
                        self.voice.error = Some(error);
                    }
                }
            }
            #[cfg(windows)]
            {
                let mut enabled = self.voice_background;
                if ui
                    .checkbox(&mut enabled, "Manter áudio ativo na bandeja ao fechar")
                    .changed()
                {
                    if enabled {
                        let context = ui.ctx().clone();
                        match audio_tray::Tray::with_wakeup(move || context.request_repaint()) {
                            Ok(tray) => {
                                self.tray = Some(tray);
                                self.voice_background = true;
                            }
                            Err(error) => self.voice.error = Some(error),
                        }
                    } else {
                        self.tray = None;
                        self.voice_background = false;
                    }
                }
            }
        });
    }

    #[cfg(windows)]
    fn tick_tray(&mut self, ctx: &egui::Context) {
        if let Some(event) = self.tray.as_ref().and_then(audio_tray::Tray::take_event) {
            match event {
                audio_tray::Event::Open => {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Visible(true));
                    ctx.send_viewport_cmd(egui::ViewportCommand::Focus);
                }
                audio_tray::Event::Mute => {
                    self.mute_voice();
                }
                audio_tray::Event::Exit => {
                    self.voice_background = false;
                    self.mute_voice();
                    ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                }
            }
        }
        if self.voice_background && ctx.input(|input| input.viewport().close_requested()) {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            ctx.send_viewport_cmd(egui::ViewportCommand::Visible(false));
        }
    }

    fn update_voice_mode(&mut self, value: Value) {
        let active = value["active"] == true;
        if self.voice.translator != active {
            self.voice_reply = None;
        }
        self.translator = value;
        self.voice.set_translator(active);
    }

    fn start_translator(&mut self, source: &str, target: &str) {
        self.send("voice-mode-change", json!({"type":"voice_translator_start","session_id":VOICE_SESSION,"source_language":source,"target_language":target}));
    }

    fn stop_translator(&mut self) {
        self.interrupt_voice();
        self.send(
            "voice-mode-change",
            json!({"type":"voice_translator_stop","session_id":VOICE_SESSION}),
        );
    }

    fn cancel_voice_turn(&mut self) {
        self.voice_turn_cancelled = true;
        self.voice_reply = None;
        if let Some(job) = self.voice_job.take() {
            if self.connected {
                self.send("voice-cancel", json!({"type":"job_cancel","job_id":job.id}));
            }
        }
    }

    fn interrupt_voice(&mut self) {
        self.cancel_voice_turn();
        self.voice.interrupt();
    }

    fn mute_voice(&mut self) {
        self.cancel_voice_turn();
        self.voice.disable();
    }

    fn accept_transcript(&mut self, turn: Transcript) {
        if turn.overlap {
            self.voice.error =
                Some("Fala sobreposta ou idioma incerto. Fale um de cada vez.".into());
            self.voice.resume();
            return;
        }
        if !self.voice.translator {
            if let Some(target) = spoken_translation_target(&turn.text) {
                if target != turn.language {
                    self.start_translator(&turn.language, target);
                } else {
                    self.voice.error = Some("Escolha um idioma de destino diferente.".into());
                    self.voice.resume();
                }
                return;
            }
        }
        if self.model.is_empty()
            || (!self.voice.translator && self.active_chat.is_empty())
            || self.job_id.is_some()
            || self.voice_job.is_some()
        {
            self.voice.error =
                Some("Selecione um modelo e abra uma conversa antes de falar.".into());
            self.voice.resume();
            return;
        }
        self.voice.error = None;
        self.voice_turn_cancelled = false;
        self.voice_language.clone_from(&turn.language);
        let mut command = json!({"type":"voice_turn_start","session_id":VOICE_SESSION,"model_id":self.model,"text":turn.text,"language":turn.language});
        if !self.active_chat.is_empty() {
            command["chat_id"] = json!(self.active_chat);
        }
        if !self.voice.translator {
            let refs = if self.context_scope.is_empty() && self.context_key.is_empty() {
                self.catalog.references(&turn.text)
            } else if !self.context_scope.is_empty() && !self.context_key.is_empty() {
                Ok(vec![
                    json!({"scope":self.context_scope,"key":self.context_key}),
                ])
            } else {
                Err("Informe o projeto e a chave de memória.")
            };
            match refs {
                Ok(refs) if !refs.is_empty() => command["context"] = json!(refs),
                Ok(_) => (),
                Err(error) => {
                    self.voice.error = Some(error.into());
                    self.voice.resume();
                    return;
                }
            }
        }
        self.send("voice-turn", command);
    }

    fn voice_turn_received(&mut self, value: Value) {
        if self.voice_turn_cancelled {
            if let Some(id) = value["job_id"].as_str() {
                self.send("voice-cancel", json!({"type":"job_cancel","job_id":id}));
            }
            return;
        }
        if value["status"] == "stopped" {
            self.update_voice_mode(json!({"active":false}));
            if self.voice.phase == Phase::Processing {
                self.voice.resume();
            }
        } else if let Some(id) = value["job_id"].as_str() {
            let translation = value["mode"] == "translator";
            self.voice_job = Some(VoiceJob {
                id: id.into(),
                translation,
                language: value["target_language"]
                    .as_str()
                    .unwrap_or(&self.voice_language)
                    .into(),
            });
        } else if self.voice.phase == Phase::Processing {
            self.voice.resume();
        }
    }

    fn voice_job_received(&mut self, value: Value) {
        if value["status"] == "running" {
            return;
        }
        let Some(job) = self.voice_job.take() else {
            return;
        };
        if !job.translation {
            self.chat();
        }
        if self.voice_turn_cancelled || self.voice.phase != Phase::Processing {
            return;
        }
        if value["status"] == "succeeded" {
            if let Some(text) = value["content"].as_str() {
                self.voice_reply = Some(text.into());
                self.voice.speak(text, &job.language);
                return;
            }
        }
        self.voice.error = Some(format!(
            "Resposta de voz: {}",
            value["status"].as_str().unwrap_or("falhou")
        ));
        self.voice.resume();
    }

    fn tick(&mut self) {
        self.browser.poll();
        if let Some(download) = &self.skill_package_download {
            use std::sync::mpsc::TryRecvError;
            let result = match download.try_recv() {
                Ok(result) => Some(result),
                Err(TryRecvError::Empty) => None,
                Err(TryRecvError::Disconnected) => {
                    Some(Err("A busca da Skill foi interrompida.".into()))
                }
            };
            if let Some(result) = result {
                self.skill_package_download = None;
                match result {
                    Ok(value) if value.get("packages").is_some() => self.skill_catalog = value,
                    Ok(value) => {
                        self.skill_package_source = value["source"].as_str().map(str::to_owned);
                        self.skill_package_input =
                            value["document"].as_str().unwrap_or_default().to_owned();
                    }
                    Err(error) => self.error = error,
                }
            }
        }
        while let Ok((tag, reply)) = self.connection.replies.try_recv() {
            self.receive(tag, reply);
        }
        if let Some(turn) = self.voice.tick() {
            self.accept_transcript(turn);
        }
        if self.connected && self.pending == 0 && self.poll.elapsed() >= Duration::from_millis(850)
        {
            self.poll = Instant::now();
            if let Some(job) = &self.voice_job {
                let command = if job.translation {
                    "voice_translation_get"
                } else {
                    "job_get"
                };
                self.send("voice-job", json!({"type":command,"job_id":job.id}));
            }
            if let Some(job) = &self.job_id {
                self.send("job", json!({"type":"job_get","job_id":job}));
            }
            self.send(
                "events",
                json!({"type":"events_read","after":self.cursor,"limit":100}),
            );
            if self.workspace {
                if self.plan["status"] == "running" {
                    self.mission_query("mission_plan_get");
                }
                if self.plan["status"] == "succeeded" && self.mission.is_null() {
                    self.mission_query("mission_get");
                }
                if !self.run.is_null()
                    && !matches!(
                        self.run["status"].as_str(),
                        Some(
                            "integrated"
                                | "rolled_back"
                                | "recovery_required"
                                | "failed"
                                | "cancelled"
                                | "revoked"
                                | "rejected"
                                | "interrupted"
                        )
                    )
                {
                    self.mission_query("mission_run_get");
                }
            }
        }
    }
}

fn choose_audio_device(
    ui: &mut egui::Ui,
    id: &str,
    default: &str,
    selected: &mut Option<String>,
    names: &[String],
) {
    egui::ComboBox::from_id_salt(id)
        .selected_text(selected.as_deref().unwrap_or(default))
        .show_ui(ui, |ui| {
            ui.selectable_value(selected, None, default);
            for name in names {
                ui.selectable_value(selected, Some(name.clone()), name);
            }
        });
}

fn spoken_translation_target(text: &str) -> Option<&'static str> {
    let words = text
        .to_lowercase()
        .replace(['ê', 'é'], "e")
        .replace('ç', "c")
        .replace('ã', "a");
    match words.trim_matches(|ch: char| !ch.is_alphabetic() && !ch.is_ascii_digit()) {
        "traduza para ingles" | "iniciar traducao para ingles" | "translate to english" => {
            Some("en-US")
        }
        "translate to portuguese"
        | "start translating to portuguese"
        | "traduza para portugues"
        | "iniciar traducao para portugues" => Some("pt-BR"),
        _ => None,
    }
}

impl eframe::App for Desktop {
    fn logic(&mut self, ctx: &egui::Context, _: &mut eframe::Frame) {
        self.tick();
        #[cfg(windows)]
        self.tick_tray(ctx);
        let delay = if self.voice.phase != Phase::Off {
            30
        } else if self.pending > 0 || self.voice_background {
            80
        } else {
            250
        };
        ctx.request_repaint_after(Duration::from_millis(delay));
    }

    fn ui(&mut self, ui: &mut egui::Ui, _: &mut eframe::Frame) {
        egui::Frame::new().inner_margin(14).show(ui, |ui| {
            self.header(ui);
            ui.add_space(12.0);
            if self.browser_visible {
                self.browser.show(ui);
            } else if self.workspace {
                self.workspace(ui);
            } else {
                self.presence(ui);
            }
        });
    }
}

#[cfg(test)]
mod workspace_view_tests {
    use super::*;

    fn visible_text(desktop: &mut Desktop) -> Vec<String> {
        fn collect(shape: &egui::Shape, text: &mut Vec<String>) {
            match shape {
                egui::Shape::Text(label) => text.push(label.galley.job.text.clone()),
                egui::Shape::Vec(shapes) => {
                    for child in shapes {
                        collect(child, text);
                    }
                }
                _ => {}
            }
        }
        let context = egui::Context::default();
        let input = egui::RawInput {
            screen_rect: Some(egui::Rect::from_min_size(
                egui::Pos2::ZERO,
                egui::vec2(1280.0, 900.0),
            )),
            ..Default::default()
        };
        let frame = context.run_ui(input, |ui| desktop.workspace(ui));
        let mut text = Vec::new();
        for item in frame.shapes {
            collect(&item.shape, &mut text);
        }
        text
    }

    #[test]
    fn workspace_suggests_catalog_skills_until_a_version_is_pinned() {
        let mut desktop = Desktop::new("workspace-catalog-test".into(), String::new());
        desktop.objective = "Implementar um leitor CSV".into();
        desktop.skill_catalog = json!({"packages":[
            {"name":"Leitor CSV","url":"https://example.com/reader.json"},
            {"name":"Calcular juros","url":"https://example.com/interest.json"}
        ]});
        let suggestions = desktop.mission_skill_suggestions();
        assert_eq!(suggestions.len(), 1);
        assert_eq!(suggestions[0]["name"], "Leitor CSV");
        let shown = visible_text(&mut desktop);
        assert!(
            shown
                .iter()
                .any(|line| line == "Skills sugeridas em Importar Skill")
        );
        desktop.mission_skill =
            Some(json!({"id":"reader","version":"1","scope":"project:fixture"}));
        assert!(desktop.mission_skill_suggestions().is_empty());
        let hidden = visible_text(&mut desktop);
        assert!(
            !hidden
                .iter()
                .any(|line| line == "Skills sugeridas em Importar Skill")
        );
    }

    #[test]
    fn active_swarm_grid_is_visible_with_context_rail_closed() {
        let mut desktop = Desktop::new("workspace-view-test".into(), String::new());
        desktop.rail = false;
        desktop.scope = "project:fixture".into();
        let ordinary = visible_text(&mut desktop);
        assert!(
            ordinary
                .iter()
                .any(|line| line == "artemis@workspace:project:fixture$")
        );
        assert!(!ordinary.iter().any(|line| line == "Implementação"));

        desktop.run = json!({"status":"generating","swarm":{"source":"direct","roles":[
            {"role":"implementation","status":"running","model_id":"fixture",
             "log":[{"kind":"generation_started"}]},
            {"role":"verification","status":"waiting","model_id":"fixture","log":[]}
        ]}});
        let active = visible_text(&mut desktop);
        for label in ["Implementação", "Verificação", "Geração iniciada"] {
            assert!(
                active.iter().any(|line| line == label),
                "{label}: {active:?}"
            );
        }
        assert!(
            !active
                .iter()
                .any(|line| line.starts_with("artemis@workspace"))
        );

        desktop.run = json!({"status":"integrated"});
        let integrated = visible_text(&mut desktop);
        assert!(
            integrated
                .iter()
                .any(|line| line.starts_with("artemis@workspace"))
        );
        assert!(!integrated.iter().any(|line| line == "Implementação"));
    }
}
