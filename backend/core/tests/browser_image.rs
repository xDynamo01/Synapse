#![cfg(windows)]

#[test]
fn image_decoder_runs_in_lpac_and_rejects_invalid_input() {
    use image::{DynamicImage, ImageFormat, Rgba, RgbaImage};
    use std::io::Cursor;
    let bin = std::path::Path::new(env!("CARGO_BIN_EXE_synapse-image-decoder"));
    let sibling = std::env::current_exe()
        .unwrap()
        .with_file_name("synapse-image-decoder.exe");
    std::fs::copy(bin, &sibling).unwrap();
    let picture = DynamicImage::ImageRgba8(RgbaImage::from_pixel(2, 1, Rgba([1, 2, 3, 255])));
    let mut png = Cursor::new(Vec::new());
    picture.write_to(&mut png, ImageFormat::Png).unwrap();
    let result = synapse_core::browser_image::decode(png.get_ref()).unwrap();
    assert_eq!((result.width, result.height), (2, 1));
    assert_eq!(result.rgba, [1, 2, 3, 255].repeat(2));
    let mut jpeg = Cursor::new(Vec::new());
    DynamicImage::ImageRgb8(picture.to_rgb8())
        .write_to(&mut jpeg, ImageFormat::Jpeg)
        .unwrap();
    let result = synapse_core::browser_image::decode(jpeg.get_ref()).unwrap();
    assert_eq!((result.width, result.height, result.rgba.len()), (2, 1, 8));
    let mut oversized = Cursor::new(Vec::new());
    DynamicImage::new_rgba8(1025, 1)
        .write_to(&mut oversized, ImageFormat::Png)
        .unwrap();
    assert!(synapse_core::browser_image::decode(oversized.get_ref()).is_err());
    assert!(synapse_core::browser_image::decode(b"<svg/>").is_err());
    assert!(synapse_core::browser_image::decode(&png.get_ref()[..12]).is_err());
}
