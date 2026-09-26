//! The shared corpus: what every binding must accept and reject.

use libpandoc_ast::{from_str, to_string};
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

#[test]
fn invalid() {
    for line in corpus("invalid.jsonl") {
        let case: serde_json::Value = serde_json::from_str(&line).unwrap();
        let doc = serde_json::to_string(&case["document"]).unwrap();
        match from_str(&doc) {
            Ok(_) => panic!("accepted {}", case["name"]),
            Err(e) => println!("{}: {e}", case["name"]),
        }
    }
}
