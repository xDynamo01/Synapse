fn main() {
    let ui = slint_build::CompilerConfiguration::new()
        .embed_resources(slint_build::EmbedResourcesKind::EmbedFiles);
    slint_build::compile_with_config("ui/app.slint", ui).expect("compile Synapse desktop shell");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        embed_windows_icon();
    }
}

fn embed_windows_icon() {
    use resvg::{tiny_skia, usvg};
    use std::{fs, path::PathBuf};

    const SVG: &str = "ui/assets/synapse.svg";
    const SIZES: [u16; 7] = [16, 20, 24, 32, 48, 64, 256];
    println!("cargo:rerun-if-changed={SVG}");
    let out = PathBuf::from(std::env::var_os("OUT_DIR").expect("Cargo output directory"));
    let source = fs::read(SVG).expect("read app mark");
    let tree = usvg::Tree::from_data(&source, &usvg::Options::default()).expect("parse app mark");

    // ICO directory followed by one PNG frame per Windows shell size.
    let mut ico = vec![0, 0, 1, 0];
    ico.extend_from_slice(&(SIZES.len() as u16).to_le_bytes());
    let mut frames = Vec::new();
    let mut offset = 6 + 16 * SIZES.len() as u32;
    for size in SIZES {
        let mut canvas = tiny_skia::Pixmap::new(size.into(), size.into()).expect("icon canvas");
        let scale = f32::from(size) / tree.size().width();
        resvg::render(
            &tree,
            tiny_skia::Transform::from_scale(scale, scale),
            &mut canvas.as_mut(),
        );
        let frame = canvas.encode_png().expect("encode icon frame");
        ico.extend_from_slice(&[size as u8, size as u8, 0, 0, 1, 0, 32, 0]);
        ico.extend_from_slice(&(frame.len() as u32).to_le_bytes());
        ico.extend_from_slice(&offset.to_le_bytes());
        offset += frame.len() as u32;
        frames.extend(frame);
    }
    ico.extend(frames);
    let icon_path = out.join("synapse.ico");
    fs::write(&icon_path, ico).expect("write multiresolution app icon");

    let resource = out.join("synapse.rc");
    let icon_path = icon_path.to_string_lossy().replace('\\', "/");
    fs::write(&resource, format!("1 ICON \"{icon_path}\"\n")).expect("write icon resource");
    embed_resource::compile(&resource, embed_resource::NONE)
        .manifest_required()
        .expect("embed Synapse app icon");
}
