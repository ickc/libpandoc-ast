//! A pandoc filter: upper-case all text outside code.
//!
//!     cargo build --example upper
//!     pandoc --filter target/debug/examples/upper input.md

use panir::{walk_inline, Inline, VisitMut};

struct Upper;

impl VisitMut for Upper {
    fn visit_inline(&mut self, x: &mut Inline) {
        walk_inline(self, x);
        if let Inline::Str(s) = x {
            *s = s.to_uppercase();
        }
    }
}

fn main() {
    panir::filter(|doc, _format| doc.visit(&mut Upper));
}
