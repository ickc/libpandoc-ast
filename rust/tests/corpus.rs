//! The shared corpus: what every binding must accept and reject.

use pandom::{from_str, to_string};
use std::path::PathBuf;

fn corpus(name: &str) -> Vec<String> {
    let path: PathBuf = [env!("CARGO_MANIFEST_DIR"), "..", "corpus", name]
        .iter()
        .collect();
    let text = std::fs::read_to_string(path).unwrap();
    // split on "\n" only: strings may hold other line separators
    text.split('\n')
        .filter(|l| !l.is_empty())
        .map(String::from)
        .collect()
}

#[test]
fn round_trip() {
    let mut docs = corpus("arbitrary.jsonl");
    docs.extend(corpus("pandoc.jsonl"));
    for (i, line) in docs.iter().enumerate() {
        let doc = from_str(line).unwrap_or_else(|e| panic!("document {i}: {e}"));
        let back: serde_json::Value = serde_json::from_str(&to_string(&doc)).unwrap();
        let orig: serde_json::Value = serde_json::from_str(line).unwrap();
        assert_eq!(back, orig, "document {i}");
    }
}

/// A JSON path as serde_path_to_error prints it: `blocks[0].c[1]`.
fn json_path(p: &serde_json::Value) -> String {
    let mut out = String::new();
    for seg in p.as_array().unwrap() {
        match seg {
            serde_json::Value::Number(n) => out += &format!("[{n}]"),
            serde_json::Value::String(k) if out.is_empty() => out += k,
            serde_json::Value::String(k) => out += &format!(".{k}"),
            _ => unreachable!(),
        }
    }
    out
}

#[test]
fn contents_before_tag() {
    // pandoc writes "t" first; other tools may not (sorted keys)
    let doc = r#"{"pandoc-api-version":[1,23,1],"meta":{},"blocks":[{"c":[{"c":42,"t":"Str"}],"t":"Para"}]}"#;
    let e = from_str(doc).unwrap_err();
    assert_eq!(e.path, "blocks[0]");
    // each level decoded out of order adds its part of the path
    assert!(
        e.message.starts_with("c[0]: c: invalid type: integer `42`"),
        "{}",
        e.message
    );
}

#[test]
fn invalid() {
    for line in corpus("invalid.jsonl") {
        #[derive(serde::Deserialize)]
        struct Case<'a> {
            name: String,
            json_path: serde_json::Value,
            // as written: serde_json::Value would sort the keys, "c" before "t"
            #[serde(borrow)]
            document: &'a serde_json::value::RawValue,
        }
        let case: Case = serde_json::from_str(&line).unwrap();
        let doc = case.document.get();
        // the path of the value, or of its contents ("c") for a node whose
        // contents are the wrong shape
        let want = json_path(&case.json_path);
        match from_str(doc) {
            Ok(_) => panic!("accepted {}", case.name),
            Err(e) => {
                println!("{}: {e}", case.name);
                let got = if e.path == "." {
                    String::new()
                } else {
                    e.path.clone()
                };
                let with_c = if want.is_empty() {
                    "c".to_string()
                } else {
                    format!("{want}.c")
                };
                assert!(
                    got == want || got == with_c,
                    "{}: path {got}, expected {want}",
                    case.name
                );
            }
        }
    }
}
