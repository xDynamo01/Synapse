use base64::{Engine, engine::general_purpose::STANDARD};
use image::{ImageFormat, ImageReader, Limits};
use std::io::{Cursor, Read};
use synapse_core::browser_image::{MAX_BYTES, MAX_DIMENSION};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut bytes = Vec::new();
    std::fs::File::open("input")?
        .take((MAX_BYTES + 1) as u64)
        .read_to_end(&mut bytes)?;
    if bytes.len() > MAX_BYTES {
        return Err("Input too large".into());
    }
    let format = image::guess_format(&bytes)?;
    if !matches!(format, ImageFormat::Png | ImageFormat::Jpeg) {
        return Err("Unsupported format".into());
    }
    let mut limits = Limits::default();
    limits.max_image_width = Some(MAX_DIMENSION);
    limits.max_image_height = Some(MAX_DIMENSION);
    limits.max_alloc = Some(32 * 1024 * 1024);
    if format == ImageFormat::Png
        && image::codecs::png::PngDecoder::with_limits(Cursor::new(&bytes), limits.clone())?
            .is_apng()?
    {
        return Err("Animated PNG is unsupported".into());
    }
    let mut reader = ImageReader::with_format(Cursor::new(bytes), format);
    reader.limits(limits);
    let pixels = reader.decode()?.into_rgba8();
    println!(
        "{} {} {}",
        pixels.width(),
        pixels.height(),
        STANDARD.encode(pixels.as_raw())
    );
    Ok(())
}
