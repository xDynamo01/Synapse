use crate::browser;
use eframe::egui;
use serde_json::{Value, json};
use std::sync::mpsc::{self, Receiver, TryRecvError};

#[derive(Default)]
pub struct BrowserAuthPanel {
    origin: String,
    username: String,
    password: String,
    credential: String,
    session: String,
    page: String,
    action: String,
    probe: String,
    marker: String,
    destination: String,
    download: String,
    records: Vec<Value>,
    task: Option<Receiver<Result<Value, String>>>,
    result: Value,
    result_mission: Option<String>,
    notice: Option<String>,
}

impl BrowserAuthPanel {
    pub fn poll(&mut self) {
        let Some(task) = &self.task else { return };
        let outcome = match task.try_recv() {
            Ok(result) => result,
            Err(TryRecvError::Empty) => return,
            Err(TryRecvError::Disconnected) => Err("Operação autenticada interrompida.".into()),
        };
        self.task = None;
        match outcome {
            Ok(value) => {
                if let Some(handle) = value["credential_handle"].as_str() {
                    self.credential = handle.to_owned();
                }
                if let Some(handle) = value["browser_authenticated"]["session_handle"].as_str() {
                    self.session = handle.to_owned();
                }
                if let Some(records) = value["records"].as_array() {
                    self.records.clone_from(records);
                }
                self.notice = None;
                self.result = value;
            }
            Err(error) => {
                self.notice = Some(error);
                self.result = Value::Null;
            }
        }
    }

    fn start(
        &mut self,
        ctx: &egui::Context,
        mission: Option<String>,
        operation: impl FnOnce() -> Result<Value, String> + Send + 'static,
    ) {
        let (send, receive) = mpsc::channel();
        self.task = Some(receive);
        self.result_mission = mission;
        self.result = Value::Null;
        self.notice = None;
        let ctx = ctx.clone();
        std::thread::spawn(move || {
            let _ = send.send(operation());
            ctx.request_repaint();
        });
    }

    pub fn show(
        &mut self,
        ui: &mut egui::Ui,
        endpoint: &str,
        mission_id: &str,
        scope: &str,
        mission: &Value,
        can_submit: bool,
    ) -> Option<Value> {
        let mut proposal = None;
        ui.collapsing("Sites autenticados", |ui| {
            let idle = self.task.is_none();
            if ui.add_enabled(idle, egui::TextEdit::singleline(&mut self.origin)
                .hint_text("Origem HTTPS do site")).changed() {
                self.credential.clear();
                self.session.clear();
                self.username.clear();
                self.password.clear();
                self.page.clear();
                self.action.clear();
                self.probe.clear();
                self.marker.clear();
                self.destination.clear();
                self.notice = None;
                self.records.clear();
                self.result = Value::Null;
            }
            ui.add_enabled(idle, egui::TextEdit::singleline(&mut self.username).hint_text("Usuário"));
            ui.add_enabled(idle, egui::TextEdit::singleline(&mut self.password).password(true).hint_text("Senha"));
            let ready = idle && !self.origin.trim().is_empty();
            ui.horizontal_wrapped(|ui| {
                if ui.add_enabled(ready && !self.username.is_empty() && !self.password.is_empty(),
                    egui::Button::new("Guardar credencial local")).clicked() {
                    let query = json!({"mode":"store_credentials","origin":self.origin.trim(),
                        "username":std::mem::take(&mut self.username),"password":std::mem::take(&mut self.password)});
                    self.start(ui.ctx(), None, move || browser::auth_worker(query));
                }
                if ui.add_enabled(ready && self.task.is_none(), egui::Button::new("Consultar cofre")).clicked() {
                    let query = json!({"mode":"list","origin":self.origin.trim()});
                    self.start(ui.ctx(), None, move || browser::auth_worker(query));
                }
            });
            for record in &self.records {
                let Some(handle) = record["handle"].as_str() else { continue };
                let (label, selected) = if record["kind"] == "session" {
                    ("Sessão", &mut self.session)
                } else {
                    ("Credencial", &mut self.credential)
                };
                ui.selectable_value(selected, handle.to_owned(), format!("{label} · {handle}"));
            }
            ui.add_enabled(idle, egui::TextEdit::singleline(&mut self.credential).hint_text("Referência da credencial"));
            ui.add_enabled(idle, egui::TextEdit::singleline(&mut self.session).hint_text("Referência da sessão"));
            for (label, value) in [("Remover credencial",self.credential.clone()), ("Revogar sessão",self.session.clone())] {
                if ui.add_enabled(ready && self.task.is_none() && !value.is_empty(), egui::Button::new(label)).clicked() {
                    let query = json!({"mode":"revoke","origin":self.origin.trim(),"handle":value});
                    self.records.retain(|record| record["handle"] != value);
                    if self.credential == value { self.credential.clear(); }
                    if self.session == value { self.session.clear(); }
                    self.start(ui.ctx(), None, move || browser::auth_worker(query));
                }
            }

            ui.add_enabled(idle, egui::TextEdit::singleline(&mut self.page).hint_text("URL da página de login"));
            ui.add_enabled(idle, egui::TextEdit::singleline(&mut self.action).hint_text("URL exata do envio"));
            ui.add_enabled(idle, egui::TextEdit::singleline(&mut self.probe).hint_text("URL que confirma a sessão"));
            ui.add_enabled(idle, egui::TextEdit::singleline(&mut self.marker).hint_text("Texto visível após o login"));
            ui.add_enabled(idle, egui::TextEdit::singleline(&mut self.destination).hint_text("URL da página autenticada a ler"));
            let login = [self.page.trim(),self.action.trim(),self.probe.trim(),self.marker.trim(),
                         self.credential.trim()].iter().all(|value| !value.is_empty());
            let read = !self.destination.trim().is_empty() && !self.session.trim().is_empty();
            let propose = can_submit && idle && mission.is_null() && !mission_id.is_empty() && !scope.is_empty();
            let active = idle && mission["state"] == "approved" && mission["mission_id"] == mission_id;
            for (action, label, allowed, resources, request) in [
                ("browser_login", "Login", login,
                    json!([self.page.trim(),self.action.trim(),self.probe.trim(),format!("credential:{}",self.credential.trim()),format!("marker:{}",self.marker.trim())]),
                    json!({"mode":"login","page":self.page.trim(),"action":self.action.trim(),"probe":self.probe.trim(),
                           "expected_text":self.marker.trim(),"credential_handle":self.credential.trim()})),
                ("browser_session_read", "Leitura autenticada", read,
                    json!([self.destination.trim(),format!("session:{}",self.session.trim())]),
                    json!({"mode":"read","destination":self.destination.trim(),"session_handle":self.session.trim()})),
            ] {
                if ui.add_enabled(propose && allowed, egui::Button::new(format!("Propor {label}"))).clicked() {
                    proposal = Some(json!({"type":"mission_propose","mission_id":mission_id,
                        "contract":{"version":1,"scope":scope,"objective":label,
                        "actions":["browser_read",action],"resources":resources,"rollback":"Revogar a sessão local"}}));
                }
                let in_contract = mission["contract"]["actions"].as_array()
                    .is_some_and(|actions| actions.iter().any(|item| item == action));
                let approved_resources = mission["contract"]["resources"].as_array()
                    .zip(resources.as_array())
                    .is_some_and(|(approved, requested)| requested.iter().all(|item| approved.contains(item)));
                if ui.add_enabled(active && allowed && in_contract && approved_resources && self.task.is_none(),
                    egui::Button::new(format!("Executar {label}"))).clicked() {
                    let endpoint = endpoint.to_owned();
                    let mission_id = mission_id.to_owned();
                    self.start(ui.ctx(), Some(mission_id.clone()), move || browser::authenticated_operation(&endpoint,&mission_id,request));
                }
            }
            if self.task.is_some() { ui.spinner(); }
            let show_result = self.result_mission.as_deref().is_none_or(|id| id == mission_id);
            if show_result {
                if let Some(error) = &self.notice { ui.label(error); }
                if self.result["revoked"] == true { ui.label("Referência removida do cofre."); }
                if mission["state"] == "approved" {
                    if self.result["browser_authenticated"]["authenticated"] == true {
                        ui.label("Sessão confirmada e guardada no cofre.");
                    }
                    if let Some(text) = self.result["browser_authenticated"]["text"].as_str() {
                        ui.collapsing("Página coletada", |ui| { ui.label(text); });
                    }
                }
            }
        });
        ui.collapsing("Downloads da missão", |ui| {
            let idle = self.task.is_none();
            ui.add_enabled(
                idle,
                egui::TextEdit::singleline(&mut self.download)
                    .hint_text("Endereço HTTPS final do arquivo de texto"),
            );
            let destination = self.download.trim();
            let propose = can_submit
                && idle
                && mission.is_null()
                && !mission_id.is_empty()
                && !scope.is_empty()
                && !destination.is_empty();
            if ui
                .add_enabled(propose, egui::Button::new("Propor download em quarentena"))
                .clicked()
            {
                proposal = Some(json!({"type":"mission_propose","mission_id":mission_id,
                    "contract":{"version":1,"scope":scope,"objective":"Guardar texto em quarentena",
                        "actions":["browser_read","browser_download"],"resources":[destination],
                        "rollback":"Descartar o arquivo cifrado em quarentena"}}));
            }
            let contract = &mission["contract"];
            let active = idle
                && mission["state"] == "approved"
                && mission["mission_id"] == mission_id
                && contract["actions"]
                    .as_array()
                    .is_some_and(|items| items.iter().any(|item| item == "browser_download"))
                && contract["resources"]
                    .as_array()
                    .is_some_and(|items| items.iter().any(|item| item == destination));
            if ui
                .add_enabled(active, egui::Button::new("Guardar em quarentena"))
                .clicked()
            {
                let (endpoint, mission_id, destination) = (
                    endpoint.to_owned(),
                    mission_id.to_owned(),
                    destination.to_owned(),
                );
                self.start(ui.ctx(), Some(mission_id.clone()), move || {
                    browser::quarantine_for_mission(&endpoint, &mission_id, &destination)
                });
            }
            if self.result_mission.as_deref() == Some(mission_id) {
                if !idle {
                    ui.spinner();
                }
                if let Some(digest) = self.result["quarantine"]["sha256"].as_str() {
                    ui.label(format!("Arquivo cifrado em quarentena · SHA-256 {digest}"));
                }
                if contract["actions"]
                    .as_array()
                    .is_some_and(|items| items.iter().any(|item| item == "browser_download"))
                {
                    if let Some(error) = &self.notice {
                        ui.label(error);
                    }
                }
            }
        });
        proposal
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration, Instant};

    fn center_of(shapes: &[egui::epaint::ClippedShape], label: &str) -> Option<egui::Pos2> {
        fn find(shape: &egui::Shape, label: &str) -> Option<egui::Pos2> {
            match shape {
                egui::Shape::Text(text) if text.galley.job.text == label => {
                    Some(text.pos + 0.5 * text.galley.size())
                }
                egui::Shape::Vec(shapes) => shapes.iter().find_map(|shape| find(shape, label)),
                _ => None,
            }
        }
        shapes.iter().find_map(|shape| find(&shape.shape, label))
    }

    #[test]
    #[ignore = "requires the configured local Python and an isolated LOCALAPPDATA"]
    fn workspace_vault_button_stores_a_disposable_credential() {
        let context = egui::Context::default();
        let mut panel = BrowserAuthPanel {
            origin: "https://example.com".into(),
            username: "workspace-fixture".into(),
            password: "disposable-fixture".into(),
            ..Default::default()
        };
        let mut frame = |click: Option<egui::Pos2>| {
            let mut events = vec![];
            if let Some(pos) = click {
                events.push(egui::Event::PointerMoved(pos));
                for pressed in [true, false] {
                    events.push(egui::Event::PointerButton {
                        pos,
                        button: egui::PointerButton::Primary,
                        pressed,
                        modifiers: egui::Modifiers::NONE,
                    });
                }
            }
            context.run_ui(
                egui::RawInput {
                    screen_rect: Some(egui::Rect::from_min_size(
                        egui::Pos2::ZERO,
                        egui::vec2(1000.0, 900.0),
                    )),
                    events,
                    ..Default::default()
                },
                |ui| {
                    panel.show(
                        ui,
                        "fixture",
                        "mission",
                        "project:fixture",
                        &Value::Null,
                        true,
                    );
                },
            )
        };
        let header = center_of(&frame(None).shapes, "Sites autenticados").expect("vault header");
        frame(Some(header));
        let button =
            center_of(&frame(None).shapes, "Guardar credencial local").expect("vault button");
        frame(Some(button));

        let deadline = Instant::now() + Duration::from_secs(10);
        while panel.task.is_some() && Instant::now() < deadline {
            panel.poll();
            std::thread::sleep(Duration::from_millis(20));
        }
        assert!(panel.password.is_empty());
        assert_eq!(panel.credential.len(), 32, "{:?}", panel.notice);
        let listed =
            browser::auth_worker(json!({"mode":"list","origin":"https://example.com"})).unwrap();
        assert_eq!(
            listed["records"],
            json!([{"handle":panel.credential,"kind":"credentials"}])
        );
        browser::auth_worker(
            json!({"mode":"revoke","origin":"https://example.com","handle":panel.credential}),
        )
        .unwrap();
    }
}
