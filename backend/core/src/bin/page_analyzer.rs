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

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    std::fs::File::open("input")?
        .take((MAX_INPUT + 1) as u64)
        .read_to_string(&mut input)?;
    if input.len() > MAX_INPUT {
        return Err("Input too large".into());
    }
    if std::env::args().nth(1).as_deref() == Some("--css") {
        let mut summary = Summary {
            css_blocks: 1,
            ..Summary::default()
        };
        scan_css(&mut Parser::new(&input), &mut summary, 0);
        println!("{}", serde_json::to_string(&summary)?);
        return Ok(());
    }
    let page = Html::parse_document(&input);
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
