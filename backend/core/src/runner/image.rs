use super::{
    Control,
    windows::{Profile, create_private_directory as windows_private},
};
use crate::browser_image::MAX_DIMENSION;

pub(crate) fn run(bytes: &[u8]) -> Result<String, String> {
    let root = tempfile::Builder::new()
        .prefix("Synapse.Image.")
        .tempdir()
        .map_err(|e| e.to_string())?;
    let path = root.path().join("decode");
    windows_private(&path)?;
    windows_private(&path.join("scratch"))?;
    let name = root
        .path()
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or("Diretório de imagem inválido.")?;
    let decoder = std::env::current_exe()
        .map_err(|e| e.to_string())?
        .with_file_name("synapse-image-decoder.exe");
    let staged = path.join("decoder.exe");
    std::fs::copy(decoder, &staged)
        .map_err(|_| "Compile synapse-image-decoder junto do desktop.")?;
    std::fs::write(path.join("input"), bytes).map_err(|e| e.to_string())?;
    let profile = Profile::create(name)?;
    profile.protect(&path, false)?;
    let limit = (MAX_DIMENSION as usize).pow(2) * 4;
    let control = Control::with_output_limit(limit.div_ceil(3) * 4 + 128);
    let result = profile.launch(&staged, &[], &path, &path.join("scratch"), &control);
    if result
        .as_ref()
        .is_err_and(|e| e == "descendant_cleanup_failed")
    {
        profile.preserve();
        let _ = root.keep();
        return Err("Não foi possível confirmar o encerramento do decodificador.".into());
    }
    profile.remove()?;
    root.close().map_err(|e| e.to_string())?;
    let receipt = result?;
    if receipt.exit_code != 0
        || !receipt.token.lpac
        || receipt.token.capabilities != 0
        || !receipt.token.job
    {
        return Err("Imagem inválida ou decodificação isolada indisponível.".into());
    }
    Ok(receipt.output)
}
