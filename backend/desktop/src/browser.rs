use eframe::egui;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    path::Path,
    process::{Command, Stdio},
    sync::mpsc::{self, Receiver, TryRecvError},
    time::{Duration, Instant},
};

#[derive(Deserialize)]
struct Page {
    origin: String,
    text: String,
    images: Vec<String>,
    stylesheets: Vec<String>,
    markup: Option<String>,
    analysis: Option<Value>,
    analysis_error: Option<String>,
}

#[derive(Default)]
pub struct Browser {
    address: String,
    quarantine: Option<Receiver<Result<Value, String>>>,
    quarantine_receipt: Option<Value>,
    loaded_address: String,
    login_action: String,
    username_field: String,
    password_field: String,
    username: String,
    password: String,
    login: Option<Receiver<Result<Value, String>>>,
    login_notice: Option<String>,
    page: Option<Page>,
    error: Option<String>,
    pending: Option<Receiver<Result<Page, String>>>,
    #[cfg(windows)]
    image: Option<Receiver<Result<synapse_core::browser_image::Pixels, String>>>,
    texture: Option<egui::TextureHandle>,
    #[cfg(windows)]
    stylesheet: Option<Receiver<Result<Value, String>>>,
    stylesheet_summary: Option<Value>,
    #[cfg(windows)]
    pixels: Option<synapse_core::browser_image::Pixels>,
}

impl Browser {
    pub fn open(&mut self, address: String) -> Result<(), String> {
        #[cfg(windows)]
        if self.image.is_some() || self.stylesheet.is_some() {
            return Err("Aguarde o carregamento do recurso.".into());
        }
        if self.pending.is_some() || self.login.is_some() {
            return Err("Uma página já está sendo carregada.".into());
        }
        if address.len() > 4096
            || !address
                .get(..8)
                .is_some_and(|prefix| prefix.eq_ignore_ascii_case("https://"))
        {
            return Err("Informe um endereço HTTPS válido.".into());
        }
        self.address = address.clone();
        self.loaded_address = address.clone();
        self.page = None;
        self.password.clear();
        self.username.clear();
        self.login_action.clear();
        self.login_notice = None;
        self.stylesheet_summary = None;
        self.texture = None;
        #[cfg(windows)]
        {
            self.image = None;
            self.pixels = None;
        }
        self.error = None;
        let (send, receive) = mpsc::channel();
        std::thread::spawn(move || {
            let _ = send.send(read(&address));
        });
        self.pending = Some(receive);
        Ok(())
    }

    #[cfg(windows)]
    pub fn quarantine_text(&mut self, address: String) -> Result<(), String> {
        if self.quarantine.is_some() {
            return Err("Já há um download em andamento.".into());
        }
        if address.len() > 4096
            || !address
                .get(..8)
                .is_some_and(|prefix| prefix.eq_ignore_ascii_case("https://"))
        {
            return Err("Informe um endereço HTTPS válido.".into());
        }
        self.error = None;
        self.quarantine_receipt = None;
        let (send, receive) = mpsc::channel();
        std::thread::spawn(move || {
            let _ = send.send(read_json(&["--quarantine-text", "--", &address], 4096));
        });
        self.quarantine = Some(receive);
        Ok(())
    }

    pub fn poll(&mut self) {
        if let Some(receiver) = &self.quarantine {
            match receiver.try_recv() {
                Ok(Ok(receipt)) => {
                    self.quarantine_receipt = Some(receipt);
                    self.quarantine = None;
                }
                Ok(Err(error)) => {
                    self.error = Some(error);
                    self.quarantine = None;
                }
                Err(TryRecvError::Disconnected) => {
                    self.error = Some("O leitor de downloads encerrou.".into());
                    self.quarantine = None;
                }
                Err(TryRecvError::Empty) => {}
            }
        }
        if let Some(reply) = self.login.as_ref().and_then(|job| match job.try_recv() {
            Ok(reply) => Some(reply),
            Err(TryRecvError::Disconnected) => Some(Err("O processo de login encerrou.".into())),
            Err(TryRecvError::Empty) => None,
        }) {
            self.login_notice = Some(match reply {
                Ok(value) if value["authenticated"] == true => "Sessão confirmada na Wikipedia de testes nesta tentativa.".into(),
                Ok(value) if value["authenticated"] == false => "A Wikipedia de testes não confirmou a sessão para esta conta.".into(),
                Ok(value) if value["submitted"] == true && value["login_form_present"] == false =>
                    "Formulário enviado. A resposta deixou de mostrar o formulário; a autenticação ainda precisa ser verificada.".into(),
                Ok(_) => "O servidor ainda mostra um formulário de login.".into(),
                Err(error) => error,
            });
            self.login = None;
        }
        #[cfg(windows)]
        {
            self.poll_image();
            if let Some(receiver) = &self.stylesheet {
                match receiver.try_recv() {
                    Ok(Ok(summary)) => self.stylesheet_summary = Some(summary),
                    Ok(Err(error)) => self.error = Some(error),
                    Err(TryRecvError::Disconnected) => {
                        self.error = Some("O analisador CSS encerrou.".into())
                    }
                    Err(TryRecvError::Empty) => return,
                }
                self.stylesheet = None;
            }
        }
        let Some(pending) = &self.pending else {
            return;
        };
        match pending.try_recv() {
            Ok(Ok(page)) => self.page = Some(page),
            Ok(Err(error)) => self.error = Some(error),
            Err(TryRecvError::Disconnected) => self.error = Some("O leitor foi encerrado.".into()),
            Err(TryRecvError::Empty) => return,
        }
        self.pending = None;
    }

    pub fn state(&self) -> Value {
        let mut state = json!({"loading":self.pending.is_some(),"error":self.error,
            "page":self.page.as_ref().map(|page| json!({"origin":page.origin,"text":page.text,"images":page.images,"stylesheets":page.stylesheets,"analysis":page.analysis,"analysis_error":page.analysis_error}))});
        #[cfg(windows)]
        {
            state["quarantine_loading"] = json!(self.quarantine.is_some());
            state["quarantine_receipt"] = json!(self.quarantine_receipt);
            state["stylesheet"] = json!(self.stylesheet_summary);
            state["stylesheet_loading"] = json!(self.stylesheet.is_some());
            state["image_loading"] = json!(self.image.is_some());
            state["image"] = json!(
                self.pixels
                    .as_ref()
                    .map(|image| [image.width, image.height])
            );
        }
        state
    }

    #[cfg(windows)]
    pub fn load_stylesheet(&mut self, address: String) -> Result<(), String> {
        let origin = self
            .page
            .as_ref()
            .filter(|page| page.stylesheets.contains(&address))
            .ok_or("Escolha uma folha CSS listada na página aberta.")?
            .origin
            .clone();
        if self.stylesheet.is_some() {
            return Err("Uma folha CSS já está sendo analisada.".into());
        }
        self.error = None;
        self.stylesheet_summary = None;
        let (send, receive) = mpsc::channel();
        std::thread::spawn(move || {
            let result = (|| {
                let response =
                    read_json(&["--origin", &origin, "--css", "--", &address], 2_000_000)?;
                let css = response["css"]
                    .as_str()
                    .ok_or("A folha CSS está ausente.")?;
                synapse_core::browser_analysis::analyze_css(css).map(|summary| json!(summary))
            })();
            let _ = send.send(result);
        });
        self.stylesheet = Some(receive);
        Ok(())
    }

    #[cfg(windows)]
    pub fn load_image(&mut self, address: String) -> Result<(), String> {
        let origin = self
            .page
            .as_ref()
            .filter(|page| page.images.contains(&address))
            .ok_or("Escolha uma imagem listada na página aberta.")?
            .origin
            .clone();
        use base64::{Engine, engine::general_purpose::STANDARD};
        if self.image.is_some() {
            return Err("Uma imagem já está sendo carregada.".into());
        }
        self.pixels = None;
        self.error = None;
        self.texture = None;
        let (send, receive) = mpsc::channel();
        std::thread::spawn(move || {
            let result = (|| {
                let response =
                    read_json(&["--origin", &origin, "--image", "--", &address], 3_000_000)?;
                let encoded = response["image"].as_str().ok_or("Imagem ausente.")?;
                let bytes = STANDARD
                    .decode(encoded)
                    .map_err(|_| "Resposta de imagem inválida.")?;
                synapse_core::browser_image::decode(&bytes)
            })();
            let _ = send.send(result);
        });
        self.image = Some(receive);
        Ok(())
    }

    #[cfg(windows)]
    fn poll_image(&mut self) {
        if let Some(receive) = &self.image {
            match receive.try_recv() {
                Ok(Ok(image)) => {
                    self.pixels = Some(image);
                    self.image = None;
                }
                Ok(Err(error)) => {
                    self.error = Some(error);
                    self.image = None;
                }
                Err(TryRecvError::Disconnected) => {
                    self.error = Some("O leitor de imagens encerrou.".into());
                    self.image = None;
                }
                Err(TryRecvError::Empty) => {}
            }
        }
    }

    pub fn show(&mut self, ui: &mut egui::Ui) {
        #[cfg(windows)]
        {
            if self.image.is_some() {
                ui.spinner();
            }
            if self.texture.is_none() {
                if let Some(image) = &self.pixels {
                    let pixels = egui::ColorImage::from_rgba_unmultiplied(
                        [image.width as usize, image.height as usize],
                        &image.rgba,
                    );
                    self.texture = Some(ui.ctx().load_texture(
                        "browser-image",
                        pixels,
                        egui::TextureOptions::LINEAR,
                    ));
                }
            }
        }
        ui.heading("Navegador");
        #[cfg(windows)]
        if ui
            .add_enabled(
                self.quarantine.is_none() && !self.address.is_empty(),
                egui::Button::new("Guardar endereço como texto em quarentena"),
            )
            .clicked()
        {
            if let Err(error) = self.quarantine_text(self.address.trim().to_owned()) {
                self.error = Some(error);
            }
        }
        if let Some(receipt) = &self.quarantine_receipt {
            ui.label(format!(
                "Texto em quarentena · {} bytes · SHA-256 {}",
                receipt["quarantine"]["bytes"],
                receipt["quarantine"]["sha256"].as_str().unwrap_or_default()
            ));
        }
        #[cfg(windows)]
        ui.collapsing("Wikipedia de testes · perfis Chromium", |ui| {
            use crate::chromium_profile::Profile;
            ui.label("Abre uma janela separada para login manual.");
            for (label, profile) in [
                ("Abrir perfil de teste", Profile::Primary),
                ("Abrir perfil de comparação", Profile::Comparison),
            ] {
                if ui.button(label).clicked() {
                    self.error = profile.open().err();
                }
            }
        });
        if ui
            .add_enabled(
                self.login.is_none(),
                egui::Button::new("Verificar sessão da Wikipedia"),
            )
            .clicked()
        {
            let (send, receive) = mpsc::channel();
            std::thread::spawn(move || {
                let _ = send.send(read_json(
                    &["--check-session", "--", "https://test.wikipedia.org/"],
                    4096,
                ));
            });
            self.login = Some(receive);
            self.login_notice = None;
        }
        if let Some(notice) = &self.login_notice {
            ui.label(notice);
        }
        if let Some(page) = &self.page {
            if page
                .analysis
                .as_ref()
                .and_then(|summary| summary["forms"].as_u64())
                .unwrap_or(0)
                > 0
            {
                ui.collapsing("Login manual (teste)", |ui| {
                    ui.label("Informe o destino HTTPS exato e os nomes dos campos do formulário.");
                    ui.add(egui::TextEdit::singleline(&mut self.login_action).hint_text("Destino do formulário"));
                    ui.add(egui::TextEdit::singleline(&mut self.username_field).hint_text("Nome do campo de usuário"));
                    ui.add(egui::TextEdit::singleline(&mut self.password_field).hint_text("Nome do campo de senha"));
                    ui.add(egui::TextEdit::singleline(&mut self.username).hint_text("Usuário"));
                    ui.add(egui::TextEdit::singleline(&mut self.password).password(true).hint_text("Senha"));
                    let ready = self.login.is_none() && [&self.login_action, &self.username_field, &self.password_field, &self.username, &self.password].iter().all(|field| !field.is_empty());
                    if ui.add_enabled(ready, egui::Button::new("Enviar login ao destino indicado")).clicked() {
                        let origin = page.origin.clone();
                        let address = self.loaded_address.clone();
                        let data = json!({"action":self.login_action,"username_field":self.username_field,"password_field":self.password_field,"username":std::mem::take(&mut self.username),"password":std::mem::take(&mut self.password)});
                        let (send, receive) = mpsc::channel();
                        std::thread::spawn(move || {
                            let reply = serde_json::to_vec(&data).map_err(|_| "Login inválido.".into())
                                .and_then(|input| read_process(&["--origin", &origin, "--login", "--", &address], 4096, Some(&input)));
                            let _ = send.send(reply);
                        });
                        self.login = Some(receive);
                        self.login_notice = None;
                    }
                    if self.login.is_some() { ui.spinner(); }

                });
            }
        }
        ui.horizontal(|ui| {
            let response = ui.add(
                egui::TextEdit::singleline(&mut self.address)
                    .hint_text("https://")
                    .desired_width((ui.available_width() - 85.0).max(100.0)),
            );
            let enter =
                response.lost_focus() && ui.input(|input| input.key_pressed(egui::Key::Enter));
            if ui
                .add_enabled(self.pending.is_none(), egui::Button::new("Abrir"))
                .clicked()
                || enter
            {
                if let Err(error) = self.open(self.address.trim().to_owned()) {
                    self.error = Some(error);
                }
            }
        });
        if self.pending.is_some() {
            ui.spinner();
        }
        if let Some(error) = &self.error {
            ui.colored_label(egui::Color32::LIGHT_RED, error);
        }
        #[cfg(windows)]
        let mut selected = None;
        #[cfg(windows)]
        let mut stylesheet = None;
        if let Some(page) = &self.page {
            ui.label(&page.origin);
            #[cfg(windows)]
            if !page.stylesheets.is_empty() {
                ui.collapsing("Folhas CSS da página", |ui| {
                    for address in &page.stylesheets {
                        if ui
                            .add_enabled(
                                self.stylesheet.is_none(),
                                egui::Button::new("Analisar folha CSS"),
                            )
                            .on_hover_text(address)
                            .clicked()
                        {
                            stylesheet = Some(address.clone());
                        }
                    }
                    if self.stylesheet.is_some() {
                        ui.spinner();
                    }
                    if let Some(summary) = &self.stylesheet_summary {
                        ui.label(format!(
                            "Importações: {} · Referências URL: {}",
                            summary["css_imports"], summary["css_urls"]
                        ));
                    }
                });
            }
            if let Some(summary) = &page.analysis {
                ui.collapsing("Estrutura da página", |ui| {
                    for (label, field) in [
                        ("Títulos", "headings"),
                        ("Tabelas", "tables"),
                        ("Links", "links"),
                        ("Formulários", "forms"),
                        ("Folhas externas", "external_stylesheets"),
                        ("Blocos CSS", "css_blocks"),
                        ("Importações CSS", "css_imports"),
                        ("URLs em CSS", "css_urls"),
                    ] {
                        ui.label(format!("{label} · {}", summary[field]));
                    }
                });
            }
            if let Some(error) = &page.analysis_error {
                ui.label(error);
            }
            ui.separator();
            egui::ScrollArea::vertical().show(ui, |ui| {
                if let Some(texture) = &self.texture {
                    ui.add(egui::Image::from_texture(texture).max_width(ui.available_width()));
                }
                #[cfg(windows)]
                for address in &page.images {
                    if ui
                        .add_enabled(self.image.is_none(), egui::Button::new("Carregar imagem"))
                        .on_hover_text(address)
                        .clicked()
                    {
                        selected = Some(address.clone());
                    }
                }
                ui.add(egui::Label::new(&page.text).selectable(true));
            });
        }
        #[cfg(windows)]
        if let Some(address) = stylesheet {
            if let Err(error) = self.load_stylesheet(address) {
                self.error = Some(error);
            }
        }
        #[cfg(windows)]
        if let Some(address) = selected {
            if let Err(error) = self.load_image(address) {
                self.error = Some(error);
            }
        }
    }
}

fn read(address: &str) -> Result<Page, String> {
    let mut page: Page = serde_json::from_value(read_json(&["--", address], 4_000_000)?)
        .map_err(|_| "O leitor devolveu uma página inválida.")?;
    if let Some(markup) = page.markup.take() {
        #[cfg(windows)]
        match synapse_core::browser_analysis::analyze(&markup) {
            Ok(summary) => page.analysis = Some(json!(summary)),
            Err(error) => page.analysis_error = Some(error),
        }
        #[cfg(not(windows))]
        let _ = markup;
    }
    Ok(page)
}

pub fn fetch_skill_document(address: &str, catalog: bool) -> Result<Value, String> {
    if address.len() > 4096 {
        return Err("O endereço da Skill excede o limite.".into());
    }
    let mode = if catalog {
        "--skill-catalog"
    } else {
        "--skill-package"
    };
    read_json(&[mode, "--", address], 310_000)
}

fn read_json(args: &[&str], limit: u64) -> Result<Value, String> {
    read_process(args, limit, None)
}

fn read_process(args: &[&str], limit: u64, input: Option<&[u8]>) -> Result<Value, String> {
    let python = std::env::var_os("SYNAPSE_PYTHON_EXECUTABLE")
        .ok_or("Configure o Python local do Synapse.")?;
    if !Path::new(&python).is_absolute() {
        return Err("O executável do Python deve ter caminho absoluto.".into());
    }
    let mut command = Command::new(python);
    command
        .args([
            "-I",
            "-B",
            "-c",
            include_str!("../../python/synapse_ai/browser_read.py"),
        ])
        .args(args)
        .stdin(if input.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    if input.is_some_and(|bytes| bytes.len() > 8192) {
        return Err("Login excede o limite de entrada.".into());
    }
    let mut child = command.spawn().map_err(|error| error.to_string())?;
    if let Some(input) = input {
        use std::io::Write;
        if child.stdin.take().unwrap().write_all(input).is_err() {
            let _ = child.kill();
            let _ = child.wait();
            return Err("Falha ao entregar o formulário ao leitor.".into());
        }
    }
    // Drain the pipes concurrently so long pages do not block the process.
    let output = child.stdout.take().unwrap();
    let errors = child.stderr.take().unwrap();
    let output = std::thread::spawn(move || bounded(output, limit));
    let errors = std::thread::spawn(move || bounded(errors, 4096));
    let start = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) if start.elapsed() < Duration::from_secs(20) => {
                std::thread::sleep(Duration::from_millis(25))
            }
            result => {
                let _ = child.kill();
                let _ = child.wait();
                break Err(match result {
                    Err(error) => error.to_string(),
                    _ => "O leitor excedeu o tempo de resposta.".into(),
                });
            }
        }
    }?;
    let output = output.join().map_err(|_| "Falha ao ler a página.")??;
    let errors = errors.join().map_err(|_| "Falha ao ler o erro.")??;
    if !status.success() {
        return Err(String::from_utf8_lossy(&errors).trim().to_owned());
    }
    serde_json::from_slice(&output).map_err(|_| "O leitor devolveu uma resposta inválida.".into())
}

fn bounded(input: impl std::io::Read, limit: u64) -> Result<Vec<u8>, String> {
    use std::io::Read;
    let mut bytes = Vec::new();
    input
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| error.to_string())?;
    if bytes.len() as u64 > limit {
        return Err("A resposta do leitor excedeu o limite.".into());
    }
    Ok(bytes)
}
