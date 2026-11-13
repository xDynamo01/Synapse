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
}

#[derive(Default)]
pub struct Browser {
    address: String,
    page: Option<Page>,
    error: Option<String>,
    pending: Option<Receiver<Result<Page, String>>>,
    #[cfg(windows)]
    image: Option<Receiver<Result<synapse_core::browser_image::Pixels, String>>>,
    texture: Option<egui::TextureHandle>,
    #[cfg(windows)]
    pixels: Option<synapse_core::browser_image::Pixels>,
}

impl Browser {
    pub fn open(&mut self, address: String) -> Result<(), String> {
        #[cfg(windows)]
        if self.image.is_some() {
            return Err("Aguarde o carregamento da imagem.".into());
        }
        if self.pending.is_some() {
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
        self.page = None;
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

    pub fn poll(&mut self) {
        #[cfg(windows)]
        self.poll_image();
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
            "page":self.page.as_ref().map(|page| json!({"origin":page.origin,"text":page.text,"images":page.images}))});
        #[cfg(windows)]
        {
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
        if let Some(page) = &self.page {
            ui.label(&page.origin);
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
        if let Some(address) = selected {
            if let Err(error) = self.load_image(address) {
                self.error = Some(error);
            }
        }
    }
}

fn read(address: &str) -> Result<Page, String> {
    serde_json::from_value(read_json(&["--", address], 1_000_000)?)
        .map_err(|_| "O leitor devolveu uma página inválida.".into())
}

fn read_json(args: &[&str], limit: u64) -> Result<Value, String> {
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
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command.spawn().map_err(|error| error.to_string())?;
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
