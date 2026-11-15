use cssparser::{Parser, Token};
use scraper::{Html, Selector};
use std::io::Read;
use synapse_core::browser_analysis::{MAX_INPUT, Summary};

fn scan_css(parser: &mut Parser<'_>, summary: &mut Summary, depth: usize) {
    if depth == 24 {
        return;
    }
    while let Ok(token) = parser.next().cloned() {
        match token {
            Token::AtKeyword(name) if name.eq_ignore_ascii_case("import") => {
                summary.css_imports += 1
            }
            Token::UnquotedUrl(_) => summary.css_urls += 1,
            Token::Function(name) if name.eq_ignore_ascii_case("url") => summary.css_urls += 1,
            Token::CurlyBracketBlock
            | Token::SquareBracketBlock
            | Token::ParenthesisBlock
            | Token::Function(_) => {
                let _ = parser.parse_nested_block(|child| {
                    scan_css(child, summary, depth + 1);
                    Ok::<_, cssparser::ParseError<()>>(())
                });
            }
            _ => {}
        }
    }
}

fn escaped(output: &mut String, value: &str) {
    for ch in value.chars() {
        match ch {
            '&' => output.push_str("&amp;"),
            '"' => output.push_str("&quot;"),
            '<' => output.push_str("&lt;"),
            '>' => output.push_str("&gt;"),
            _ => output.push(ch),
        }
    }
}

fn project_html(page: &Html) -> String {
    use scraper::ElementRef;
    use scraper::node::Node;
    enum Work<'a> {
        Open(ElementRef<'a>),
        Close(&'a str),
        Text(&'a str),
    }
    let mut output = String::new();
    let mut stack = vec![Work::Open(page.root_element())];
    while let Some(item) = stack.pop() {
        let node = match item {
            Work::Open(element) => element,
            Work::Close(name) => {
                output.push_str("</");
                output.push_str(name);
                output.push('>');
                continue;
            }
            Work::Text(text) => {
                escaped(&mut output, text);
                continue;
            }
        };
        let name = node.value().name();
        if matches!(
            name,
            "head"
                | "script"
                | "style"
                | "noscript"
                | "template"
                | "svg"
                | "math"
                | "iframe"
                | "object"
                | "embed"
                | "audio"
                | "video"
        ) {
            continue;
        }
        let attributes: Option<&[&str]> = match name {
            "a" => Some(&["href"]),
            "form" => Some(&["action", "method", "enctype", "id"]),
            "input" => Some(&["name", "type", "value", "disabled", "form"]),
            "fieldset" => Some(&["disabled"]),
            "h1" | "h2" | "h3" | "h4" | "h5" | "h6" | "div" | "p" | "li" | "ul" | "ol" | "br"
            | "pre" | "label" | "legend" | "table" | "tr" | "th" | "td" => Some(&[]),
            _ => None,
        };
        if let Some(attributes) = attributes {
            output.push('<');
            output.push_str(name);
            for attribute in attributes {
                if let Some(value) = node.value().attr(attribute) {
                    if matches!(*attribute, "href" | "action")
                        && value.contains(':')
                        && !value.starts_with("https://")
                    {
                        continue;
                    }
                    output.push(' ');
                    output.push_str(attribute);
                    output.push_str("=\"");
                    escaped(&mut output, value);
                    output.push('"');
                }
            }
            output.push('>');
            if !matches!(name, "br" | "input") {
                stack.push(Work::Close(name));
            }
        }
        for child in node.children().rev() {
            match child.value() {
                Node::Text(text) => stack.push(Work::Text(&text.text)),
                Node::Element(_) => stack.push(Work::Open(ElementRef::wrap(child).unwrap())),
                _ => {}
            }
        }
    }
    output
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    let mode = std::env::args().nth(1);
    if mode.as_deref() == Some("--project-broker") {
        std::io::stdin()
            .take((MAX_INPUT + 1) as u64)
            .read_to_string(&mut input)?;
        let result = synapse_core::browser_analysis::project(&input)?;
        println!("{}", serde_json::to_string(&result)?);
        return Ok(());
    }
    std::fs::File::open("input")?
        .take((MAX_INPUT + 1) as u64)
        .read_to_string(&mut input)?;
    if input.len() > MAX_INPUT {
        return Err("Input too large".into());
    }
    if mode.as_deref() == Some("--css") {
        let mut summary = Summary {
            css_blocks: 1,
            ..Summary::default()
        };
        scan_css(&mut Parser::new(&input), &mut summary, 0);
        println!("{}", serde_json::to_string(&summary)?);
        return Ok(());
    }
    let page = Html::parse_document(&input);
    if mode.as_deref() == Some("--project") {
        println!("{}", serde_json::to_string(&project_html(&page))?);
        return Ok(());
    }
    let count = |selector: &str| page.select(&Selector::parse(selector).unwrap()).count() as u32;
    let mut summary = Summary {
        headings: count("h1,h2,h3,h4,h5,h6"),
        tables: count("table"),
        links: count("a[href]"),
        forms: count("form"),
        external_stylesheets: count("link[rel~=stylesheet i][href]"),
        css_blocks: 0,
        css_imports: 0,
        css_urls: 0,
    };
    for style in page.select(&Selector::parse("style,[style]").unwrap()) {
        let block = style
            .value()
            .name()
            .eq("style")
            .then(|| style.text().collect::<String>());
        for source in block
            .as_deref()
            .into_iter()
            .chain(style.value().attr("style"))
        {
            summary.css_blocks += 1;
            scan_css(&mut Parser::new(source), &mut summary, 0);
        }
    }
    println!("{}", serde_json::to_string(&summary)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn projection_preserves_content_order_and_removes_active_markup() {
        let source = Html::parse_document(
            r#"
            <p>A <a href="/next?q=&quot;important&quot;" onclick="run()">B</a> C</p>
            <script>Never run or project this.</script>
            <form method="post" action="/session"><input name="secret" type="password">
            <input name="csrf" type="hidden" value="&quot;&lt;img src=abc&gt;"></form>
            <iframe src="https://elsewhere.example.com">Not projected.</iframe>
            <a href="javascript:run()">Unsupported navigation</a>
        "#,
        );
        let projected = project_html(&source);
        assert!(projected.contains(r#"<p>A <a href="/next?q=&quot;important&quot;">B</a> C</p>"#));
        assert!(projected.contains(r#"<form action="/session" method="post">"#));
        assert!(
            projected.contains(r#"name="csrf" type="hidden" value="&quot;&lt;img src=abc&gt;""#)
        );
        for forbidden in [
            "<script",
            "onclick",
            "<iframe",
            "javascript:",
            "<img",
            "Not projected.",
        ] {
            assert!(!projected.contains(forbidden), "{forbidden}");
        }
    }
}
