//! pandoc's document AST, generated from pandoc-types.
//!
//! The types (`Pandoc`, `Block`, `Inline`, ...) encode to and from pandoc's
//! JSON with serde: `{"t": "Str", "c": "x"}` is `Inline::Str("x")`.
//! `VisitMut` walks a document to change it. `filter` runs a function as a
//! pandoc JSON filter (`pandoc --filter`).
//!
//! ```
//! use pandom::{Block, Inline, Pandoc};
//!
//! let doc: Pandoc = pandom::from_str(
//!     r#"{"pandoc-api-version":[1,23,1],"meta":{},"blocks":[{"t":"Para","c":[{"t":"Str","c":"hi"}]}]}"#,
//! ).unwrap();
//! assert_eq!(doc.blocks, vec![Block::Para(vec![Inline::Str("hi".into())])]);
//! ```

mod generated;

pub use generated::*;

use std::fmt;
use std::io::{Read, Write};

/// JSON that isn't a pandoc document of this API version.
#[derive(Debug)]
pub struct Error {
    /// Where, in the JSON: e.g. `blocks[0].c[1]`.
    pub path: String,
    pub message: String,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.path.is_empty() || self.path == "." {
            write!(f, "{}", self.message)
        } else {
            write!(f, "{}: {}", self.path, self.message)
        }
    }
}

impl std::error::Error for Error {}

/// A document from pandoc's JSON, checking its `pandoc-api-version`.
pub fn from_str(json: &str) -> Result<Pandoc, Error> {
    let de = &mut serde_json::Deserializer::from_str(json);
    let doc: Pandoc = serde_path_to_error::deserialize(de).map_err(|e| Error {
        path: e.path().to_string(),
        message: e.inner().to_string(),
    })?;
    if doc.api_version.get(..2) != Some(&PANDOC_API_VERSION[..2]) {
        return Err(Error {
            path: "pandoc-api-version".into(),
            message: format!(
                "expected {}.{}.*, got {:?}",
                PANDOC_API_VERSION[0], PANDOC_API_VERSION[1], doc.api_version
            ),
        });
    }
    Ok(doc)
}

/// A document as pandoc's JSON.
pub fn to_string(doc: &Pandoc) -> String {
    serde_json::to_string(doc).expect("the AST always encodes")
}

/// Reads `{"t": tag}` for an enum-like type, checking the tag.
#[doc(hidden)]
pub fn de_tag<'de, D: serde::Deserializer<'de>>(
    d: D,
    name: &'static str,
    tags: &'static [&'static str],
) -> Result<String, D::Error> {
    use serde::de::{self, MapAccess, Visitor};
    struct V(&'static str, &'static [&'static str]);
    impl<'de> Visitor<'de> for V {
        type Value = String;
        fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
            write!(f, "a {}: {{\"t\": ...}}", self.0)
        }
        fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<String, A::Error> {
            let mut tag = None;
            while let Some(key) = map.next_key::<String>()? {
                if key == "t" {
                    tag = Some(map.next_value::<String>()?);
                } else {
                    map.next_value::<de::IgnoredAny>()?;
                }
            }
            let t = tag.ok_or_else(|| de::Error::missing_field("t"))?;
            if !self.1.contains(&t.as_str()) {
                return Err(de::Error::unknown_variant(&t, self.1));
            }
            Ok(t)
        }
    }
    d.deserialize_map(V(name, tags))
}

impl Pandoc {
    /// A document with these blocks and no metadata.
    pub fn new(blocks: Vec<Block>) -> Self {
        Pandoc {
            blocks,
            ..Default::default()
        }
    }

    /// Visit the document with a visitor.
    pub fn visit<V: VisitMut + ?Sized>(&mut self, v: &mut V) {
        v.visit_pandoc(self);
    }
}

/// Run `f` as a pandoc JSON filter: read a document from stdin, change it,
/// write it to stdout. `f` gets the output format pandoc passes (the first
/// argument), if any. Errors go to stderr and exit with status 1.
///
/// ```no_run
/// pandom::filter(|doc, _format| {
///     doc.blocks.retain(|b| !matches!(b, pandom::Block::HorizontalRule));
/// });
/// ```
pub fn filter<F: FnOnce(&mut Pandoc, Option<&str>)>(f: F) {
    let format = std::env::args().nth(1);
    let mut input = String::new();
    let result = std::io::stdin()
        .read_to_string(&mut input)
        .map_err(|e| e.to_string())
        .and_then(|_| from_str(&input).map_err(|e| e.to_string()));
    match result {
        Ok(mut doc) => {
            f(&mut doc, format.as_deref());
            let mut out = std::io::stdout().lock();
            out.write_all(to_string(&doc).as_bytes())
                .expect("writing stdout");
        }
        Err(e) => {
            eprintln!("pandom filter: {e}");
            std::process::exit(1);
        }
    }
}
