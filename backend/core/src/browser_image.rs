use base64::{Engine, engine::general_purpose::STANDARD};

pub const MAX_BYTES: usize = 2 * 1024 * 1024;
pub const MAX_DIMENSION: u32 = 1024;

pub struct Pixels {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}

pub fn decode(bytes: &[u8]) -> Result<Pixels, String> {
    if bytes.is_empty() || bytes.len() > MAX_BYTES {
        return Err("Imagem excede o limite de entrada.".into());
    }
    #[cfg(windows)]
    {
        let limit = (MAX_DIMENSION as usize).pow(2) * 4;
        parse(&crate::runner::browser_content::run(
            "synapse-image-decoder.exe",
            bytes,
            limit.div_ceil(3) * 4 + 128,
        )?)
    }
    #[cfg(not(windows))]
    {
        Err("Isolamento de imagens indisponível nesta plataforma.".into())
    }
}

#[cfg(any(windows, test))]
fn parse(value: &str) -> Result<Pixels, String> {
    let invalid = || "Saída de imagem inválida.".to_owned();
    let mut fields = value.trim_end().split(' ');
    let mut dimension = || {
        fields
            .next()
            .and_then(|s| s.parse::<u32>().ok())
            .filter(|n| (1..=MAX_DIMENSION).contains(n))
            .ok_or_else(invalid)
    };
    let width = dimension()?;
    let height = dimension()?;
    let count = width as usize * height as usize * 4;
    let data = fields
        .next()
        .filter(|s| s.len() == count.div_ceil(3) * 4)
        .ok_or_else(invalid)?;
    if fields.next().is_some() {
        return Err(invalid());
    }
    let rgba = STANDARD.decode(data).map_err(|_| invalid())?;
    if rgba.len() != count {
        return Err(invalid());
    }
    Ok(Pixels {
        width,
        height,
        rgba,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn output_must_match_dimensions_and_exact_rgba_length() {
        assert_eq!(parse("1 1 AQIDBA==\n").unwrap().rgba, [1, 2, 3, 4]);
        for invalid in [
            "0 1 AQIDBA==",
            "1025 1 AQIDBA==",
            "1 1 AQID",
            "1 1 AQIDBA== extra",
        ] {
            assert!(parse(invalid).is_err());
        }
    }
}
