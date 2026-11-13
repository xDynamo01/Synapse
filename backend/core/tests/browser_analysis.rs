#![cfg(windows)]

#[test]
fn passive_analysis_returns_only_validated_counts() {
    let binary = env!("CARGO_BIN_EXE_synapse-page-analyzer");
    let sibling = std::env::current_exe()
        .unwrap()
        .with_file_name("synapse-page-analyzer.exe");
    std::fs::copy(binary, sibling).unwrap();
    let page = r#"<title>Example</title><h1>Heading</h1><table></table>
        <a href='https://example.com/'>Example</a><form action='/submit'></form>
        <link rel='stylesheet' href='/external.css'>
        <style>@import '/unfetched.css'; @media screen { p { background:url('/unfetched.png') } }</style>
        <p style='background:url(/other.png)'>Example</p>
        <script>fetch('/ignored');</script>"#;
    let summary = synapse_core::browser_analysis::analyze(page).unwrap();
    assert_eq!(
        (
            summary.headings,
            summary.tables,
            summary.links,
            summary.forms
        ),
        (1, 1, 1, 1)
    );
    assert_eq!(
        (
            summary.external_stylesheets,
            summary.css_blocks,
            summary.css_imports,
            summary.css_urls
        ),
        (1, 2, 1, 2)
    );
    let too_large = "x".repeat(synapse_core::browser_analysis::MAX_INPUT + 1);
    assert!(synapse_core::browser_analysis::analyze(&too_large).is_err());
    let css = synapse_core::browser_analysis::analyze_css(
        "@import 'blocked.css'; p { background: url(blocked.png) }",
    )
    .unwrap();
    assert_eq!(
        (css.headings, css.css_blocks, css.css_imports, css.css_urls),
        (0, 1, 1, 1)
    );
}
