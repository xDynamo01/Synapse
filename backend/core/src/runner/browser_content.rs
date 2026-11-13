use super::{
    Control,
    windows::{Profile, create_private_directory as windows_private},
};

pub(crate) fn run(
    binary: &str,
    bytes: &[u8],
    output_limit: usize,
    args: &[String],
) -> Result<String, String> {
    let root = tempfile::Builder::new()
        .prefix("Synapse.Content.")
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
        .with_file_name(binary);
    let staged = path.join("decoder.exe");
    std::fs::copy(decoder, &staged)
        .map_err(|_| "Compile os analisadores do Core junto do desktop.")?;
    std::fs::write(path.join("input"), bytes).map_err(|e| e.to_string())?;
    let profile = Profile::create(name)?;
    profile.protect(&path, false)?;
    let control = Control::with_output_limit(output_limit);
    let result = profile.launch(&staged, args, &path, &path.join("scratch"), &control);
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
