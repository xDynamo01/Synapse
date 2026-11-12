mod bridge;
mod catalog;
mod transport;

use catalog::Catalog;
use eframe::egui::{self, Color32, RichText};
use serde_json::{Value, json};
use std::time::{Duration, Instant};
use transport::Connection;

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
    rail: bool,
    model: String,
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
            rail: true,
            model: String::new(),
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
                    self.project = Value::Null;
                    self.mission = Value::Null;
                    self.run = Value::Null;
                    self.recovery = Value::Null;
                    self.recovery_mode = None;
                }
                if !matches!(tag, "mission_run_get" | "mission_plan_get")
                    || !error.starts_with("not_found ·")
                {
                    self.error = error;
                }
                return;
            }
        };
        match tag {
            "health" => {
                self.connected = true;
                self.send("models", json!({"type":"models_list","limit":100}));
                self.chat();
                if !self.mission_id.is_empty() {
                    self.refresh();
                }
            }
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
            }
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
            ui.selectable_value(&mut self.workspace, false, "Presence");
            ui.selectable_value(&mut self.workspace, true, "Workspace");
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
            self.send_message();
        }
        if self.job_id.is_some() {
            ui.spinner();
        }
    }

    fn workspace(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.heading("Workspace");
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
                            skill_label(skill),
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
                    && !self.model.is_empty()
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
            self.plan_mission(paths, self.mission_skill.clone());
        }
        ui.horizontal_wrapped(|ui| {
            let state = self.mission["state"]
                .as_str()
                .unwrap_or_default()
                .to_owned();
            let digest = self.mission["contract_digest"].as_str().unwrap_or_default();
            if ui
                .add_enabled(
                    ready && state == "proposed" && !digest.is_empty(),
                    egui::Button::new("Aprovar contrato exibido"),
                )
                .clicked()
            {
                let digest = digest.to_owned();
                self.approve_mission(&digest);
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
        ui.separator();
        if self.rail {
            egui::Panel::right("context-rail")
                .default_size(320.0)
                .resizable(true)
                .show_inside(ui, |ui| self.context_rail(ui));
            self.terminal(ui);
        } else {
            self.terminal(ui);
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
    fn send_message(&mut self) {
        let mut command = json!({"type":"conversation_start","chat_id":self.active_chat,"model_id":self.model,"content":self.message});
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

    fn plan_mission(&mut self, git_edit_paths: Vec<String>, skill: Option<Value>) {
        let mut command = json!({"type":"mission_plan_start","mission_id":self.mission_id,"scope":self.scope,"model_id":self.model,"review_model_id":self.model,"objective":self.objective,"review_generation":{"max_output_tokens":512,"timeout_ms":120000,"reasoning_effort":"none"}});
        if !git_edit_paths.is_empty() {
            command["git_edit_paths"] = json!(git_edit_paths);
        }
        if let Some(skill) = skill {
            command["skill"] = skill;
        }
        self.send("plan-start", command);
    }

    fn approve_mission(&mut self, digest: &str) {
        if self.mission["state"] != "proposed" || self.mission["contract_digest"] != digest {
            self.error = "A aprovação exige o digest da proposta selecionada.".into();
            return;
        }
        self.send(
            "approval",
            json!({"type":"mission_approve","mission_id":self.mission_id,"contract_digest":digest}),
        );
    }

    fn tick(&mut self) {
        while let Ok((tag, reply)) = self.connection.replies.try_recv() {
            self.receive(tag, reply);
        }
        if self.connected && self.pending == 0 && self.poll.elapsed() >= Duration::from_millis(850)
        {
            self.poll = Instant::now();
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

impl eframe::App for Desktop {
    fn ui(&mut self, ui: &mut egui::Ui, _: &mut eframe::Frame) {
        self.tick();
        egui::Frame::new().inner_margin(14).show(ui, |ui| {
            self.header(ui);
            ui.add_space(12.0);
            if self.workspace {
                self.workspace(ui);
            } else {
                self.presence(ui);
            }
        });
        ui.ctx()
            .request_repaint_after(Duration::from_millis(if self.pending > 0 {
                80
            } else {
                250
            }));
    }
}
