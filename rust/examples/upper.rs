//! A pandoc filter: upper-case all text outside code.
//!
//!     cargo build --example upper
//!     pandoc --filter target/debug/examples/upper input.md

use panir::{Ctx, Filter, Inline, Typewise};

struct Upper;

impl Filter for Upper {
    type Order = Typewise;

    fn inline(&mut self, x: &mut Inline, _: &mut Ctx<Typewise>) -> Option<Vec<Inline>> {
        if let Inline::Str(s) = x {
            *s = s.to_uppercase().into();
        }
        None
    }
}

fn main() {
    panir::filter(|doc, format| panir::apply(doc, &mut Upper, format));
}
