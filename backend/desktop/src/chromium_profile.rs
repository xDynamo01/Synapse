//! Explicit manual sign-in with dedicated Chromium data directories.
use std::{
    path::{Path, PathBuf},
    process::{Command, Stdio},
};

const TEST_LOGIN: &str = "https://test.wikipedia.org/wiki/Special:UserLogin";

#[derive(Clone, Copy)]
pub enum Profile {
    Primary,
    Comparison,
}

impl Profile {
    fn directory(self) -> Result<PathBuf, String> {
        let local = std::env::var_os("LOCALAPPDATA").ok_or("LOCALAPPDATA indisponível.")?;
        let local = Path::new(&local);
        if !local.is_absolute() {
            return Err("LOCALAPPDATA inválido.".into());
        }
        Ok(local
            .join("Synapse")
            .join("browser")
            .join("chromium")
            .join(match self {
                Self::Primary => "testwiki-primary",
                Self::Comparison => "testwiki-comparison",
            }))
    }

    pub fn open(self) -> Result<(), String> {
        let executable =
            chromium().ok_or("Instale o Chrome ou o Edge para abrir o perfil interativo.")?;
        let directory = self.directory()?;
        std::fs::create_dir_all(&directory).map_err(|e| e.to_string())?;
        let canonical = directory.canonicalize().map_err(|e| e.to_string())?;
        // Reject redirected profiles, including junctions in the dedicated path.
        let canonical_local = directory
            .ancestors()
            .nth(4)
            .ok_or("Caminho de perfil inválido.")?
            .canonicalize()
            .map_err(|e| e.to_string())?;
        let relative = directory
            .ancestors()
            .nth(4)
            .and_then(|root| directory.strip_prefix(root).ok())
            .ok_or("Caminho de perfil inválido.")?;
        if canonical != canonical_local.join(relative) {
            return Err("O diretório do perfil foi redirecionado.".into());
        }
        let mut data_dir = std::ffi::OsString::from("--user-data-dir=");
        data_dir.push(&directory);
        let mut child = Command::new(executable)
            .arg(data_dir)
            .args([
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-sync",
                "--disable-extensions",
                "--new-window",
                TEST_LOGIN,
            ])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| e.to_string())?;
        std::thread::spawn(move || {
            let _ = child.wait();
        });
        Ok(())
    }
}

fn chromium() -> Option<PathBuf> {
    ["ProgramFiles", "ProgramFiles(x86)"]
        .into_iter()
        .filter_map(std::env::var_os)
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .flat_map(|root| {
            [
                root.join("Google/Chrome/Application/chrome.exe"),
                root.join("Microsoft/Edge/Application/msedge.exe"),
            ]
        })
        .find(|path| path.is_file())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn uses_two_distinct_synapse_directories() {
        let primary = Profile::Primary.directory().unwrap();
        let comparison = Profile::Comparison.directory().unwrap();
        assert_eq!(primary.parent(), comparison.parent());
        assert_ne!(primary, comparison);
        assert!(primary.ends_with("Synapse/browser/chromium/testwiki-primary"));
    }
}
