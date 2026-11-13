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
}

#[derive(Default)]
pub struct Browser {
    address: String,
    page: Option<Page>,
    error: Option<String>,
    pending: Option<Receiver<Result<Page, String>>>,
}

impl Browser {
    pub fn open(&mut self, address: String) -> Result<(), String> {
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
        self.error = None;
        let (send, receive) = mpsc::channel();
        std::thread::spawn(move || {
            let _ = send.send(read(&address));
        });
        self.pending = Some(receive);
        Ok(())
    }

    pub fn poll(&mut self) {
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
        json!({"loading":self.pending.is_some(),"error":self.error,
            "page":self.page.as_ref().map(|page| json!({"origin":page.origin,"text":page.text}))})
    }

    pub fn show(&mut self, ui: &mut egui::Ui) {
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
        if let Some(page) = &self.page {
            ui.label(&page.origin);
            ui.separator();
            egui::ScrollArea::vertical().show(ui, |ui| {
                ui.add(egui::Label::new(&page.text).selectable(true));
            });
        }
    }
}

fn read(address: &str) -> Result<Page, String> {
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
            "--",
            address,
        ])
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
    let output = std::thread::spawn(move || bounded(output, 1_000_000));
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
