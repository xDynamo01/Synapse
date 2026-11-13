//! Bounded, inert page summaries from the Windows LPAC worker.
use serde::{Deserialize, Serialize};

pub const MAX_INPUT: usize = 384 * 1024;
const MAX_OUTPUT: usize = 4096;

#[derive(Serialize, Deserialize, Debug)]
#[serde(deny_unknown_fields)]
pub struct Summary {
    pub headings: u32,
    pub tables: u32,
    pub links: u32,
    pub forms: u32,
    pub external_stylesheets: u32,
    pub css_blocks: u32,
    pub css_imports: u32,
    pub css_urls: u32,
}

pub fn analyze(html: &str) -> Result<Summary, String> {
    if html.len() > MAX_INPUT {
        return Err("HTML excede o limite da análise.".into());
    }
    #[cfg(windows)]
    {
        let output = crate::runner::browser_content::run(
            "synapse-page-analyzer.exe",
            html.as_bytes(),
            MAX_OUTPUT,
        )?;
        parse(&output)
    }
    #[cfg(not(windows))]
    Err("Análise isolada indisponível nesta plataforma.".into())
}

#[cfg(any(windows, test))]
fn parse(output: &str) -> Result<Summary, String> {
    let invalid = || "O analisador devolveu um resumo inválido.".to_owned();
    let summary: Summary = serde_json::from_str(output).map_err(|_| invalid())?;
    if [
        summary.headings,
        summary.tables,
        summary.links,
        summary.forms,
        summary.external_stylesheets,
        summary.css_blocks,
        summary.css_imports,
        summary.css_urls,
    ]
    .into_iter()
    .any(|count| count as usize > MAX_INPUT)
    {
        return Err(invalid());
    }
    Ok(summary)
}
