//! The shared filter corpus: each corpus/filters/NAME.lua, written here as
//! Rust filters, must make of its input what pandoc's Lua filter made.

use panir::{
    apply, from_str, to_string, Attr, Block, Bottomup, Ctx, Div, Filter, Inline, Meta, MetaValue,
    Order, Pandoc, Topdown, Typewise,
};
use serde_json::Value;
use std::marker::PhantomData;
use std::mem::take;
use std::path::PathBuf;

const FORMAT: Option<&str> = Some("json");

fn corpus_dir() -> PathBuf {
    [env!("CARGO_MANIFEST_DIR"), "..", "corpus"]
        .iter()
        .collect()
}

fn str_(s: &str) -> Inline {
    Inline::Str(s.into())
}

// Filters whose functions don't depend on each other's calls, in any order.

#[derive(Default)]
struct Upper<O>(PhantomData<O>);

impl<O: Order> Filter for Upper<O> {
    type Order = O;
    fn inline(&mut self, x: &mut Inline, _: &mut Ctx<O>) -> Option<Vec<Inline>> {
        match x {
            Inline::Str(s) => Some(vec![Inline::Str(s.to_uppercase().into())]),
            _ => None,
        }
    }
}

#[derive(Default)]
struct Modify<O>(PhantomData<O>);

impl<O: Order> Filter for Modify<O> {
    type Order = O;
    fn block(&mut self, x: &mut Block, _: &mut Ctx<O>) -> Option<Vec<Block>> {
        match x {
            Block::Header(h) => h.level += 1,
            Block::CodeBlock(c) => c.attr.classes.push("numbered".into()),
            _ => {}
        }
        None
    }
    fn inline(&mut self, x: &mut Inline, _: &mut Ctx<O>) -> Option<Vec<Inline>> {
        match x {
            Inline::Link(l) => {
                l.target.url = format!("https://example.org/{}", l.target.url).into()
            }
            Inline::Image(i) => {
                i.target.url = format!("img/{}", i.target.url).into();
                i.attr.attributes.push(("loading".into(), "lazy".into()));
            }
            _ => {}
        }
        None
    }
}

#[derive(Default)]
struct Splice<O>(PhantomData<O>);

impl<O: Order> Filter for Splice<O> {
    type Order = O;
    fn inline(&mut self, x: &mut Inline, _: &mut Ctx<O>) -> Option<Vec<Inline>> {
        match x {
            Inline::Note(_) | Inline::Emph(_) => Some(vec![]),
            Inline::Strong(c) => Some(take(c)),
            _ => None,
        }
    }
    fn block(&mut self, x: &mut Block, _: &mut Ctx<O>) -> Option<Vec<Block>> {
        match x {
            Block::Div(d) => Some(take(&mut d.content)),
            Block::HorizontalRule => Some(vec![
                Block::Para(vec![str_("one")]),
                Block::Para(vec![str_("two")]),
            ]),
            _ => None,
        }
    }
}

// Rust's one function per kind matches on the constructor, so the Lua
// scenario's point (a constructor's function wins over its type's) is
// written as the order of the match.
#[derive(Default)]
struct Generic<O>(PhantomData<O>);

impl<O: Order> Filter for Generic<O> {
    type Order = O;
    fn inline(&mut self, x: &mut Inline, _: &mut Ctx<O>) -> Option<Vec<Inline>> {
        match x {
            Inline::Str(s) => Some(vec![Inline::Str(format!("{s}!").into())]),
            Inline::Code(c) => Some(vec![Inline::Str(c.text.clone())]),
            _ => None,
        }
    }
    fn block(&mut self, x: &mut Block, _: &mut Ctx<O>) -> Option<Vec<Block>> {
        match x {
            Block::CodeBlock(c) => Some(vec![Block::Para(vec![Inline::Str(c.text.clone())])]),
            _ => None,
        }
    }
}

#[derive(Default)]
struct Once<O>(PhantomData<O>);

impl<O: Order> Filter for Once<O> {
    type Order = O;
    fn inline(&mut self, x: &mut Inline, _: &mut Ctx<O>) -> Option<Vec<Inline>> {
        match x {
            Inline::Str(s) if s == "Some" => Some(vec![Inline::Emph(vec![str_("new")])]),
            Inline::Emph(c) => Some(vec![Inline::Strong(take(c))]),
            _ => None,
        }
    }
}

#[derive(Default)]
struct Lists<O>(PhantomData<O>);

impl<O: Order> Filter for Lists<O> {
    type Order = O;
    fn inlines(&mut self, xs: &mut Vec<Inline>, _: &mut Ctx<O>) {
        let n = xs.len();
        xs.retain(|x| !matches!(x, Inline::Space));
        xs.push(Inline::Str(format!("<{n}>").into()));
    }
    fn blocks(&mut self, xs: &mut Vec<Block>, _: &mut Ctx<O>) {
        *xs = take(xs)
            .into_iter()
            .flat_map(|b| {
                let rule = matches!(b, Block::Header(_)).then_some(Block::HorizontalRule);
                std::iter::once(b).chain(rule)
            })
            .collect();
    }
}

#[derive(Default)]
struct MetaScenario<O>(PhantomData<O>);

impl<O: Order> Filter for MetaScenario<O> {
    type Order = O;
    fn meta(&mut self, m: &mut Meta, ctx: &mut Ctx<O>) {
        m.insert("draft".into(), MetaValue::MetaBool(true));
        m.insert(
            "format".into(),
            MetaValue::MetaString(ctx.format().unwrap_or("").into()),
        );
        m.insert(
            "tags".into(),
            MetaValue::MetaList(vec![
                MetaValue::MetaString("a".into()),
                MetaValue::MetaInlines(vec![str_("b")]),
            ]),
        );
        m.remove("count");
    }
    fn pandoc(&mut self, doc: &mut Pandoc, _: &mut Ctx<O>) {
        let draft = matches!(doc.meta.get("draft"), Some(MetaValue::MetaBool(true)));
        doc.blocks.insert(
            0,
            Block::Para(vec![str_(if draft { "draft" } else { "final" })]),
        );
    }
}

// Noting each call, as the Lua scenarios do.

struct Noting<O> {
    seen: Vec<String>,
    strong: bool,
    order: PhantomData<O>,
}

impl<O> Noting<O> {
    fn new(strong: bool) -> Self {
        Noting {
            seen: vec![],
            strong,
            order: PhantomData,
        }
    }

    /// The paragraph listing the notes.
    fn listing(&self) -> Block {
        Block::Para(panir::inlines(&self.seen.join(" ")))
    }
}

impl<O: Order> Filter for Noting<O> {
    type Order = O;
    fn inline(&mut self, x: &mut Inline, _: &mut Ctx<O>) -> Option<Vec<Inline>> {
        let note = match x {
            Inline::Str(s) => format!("Str:{s}"),
            Inline::Code(c) => format!("Code:{}", c.text),
            Inline::Emph(_) => "Emph".into(),
            Inline::Strong(_) if self.strong => "Strong".into(),
            Inline::Note(_) => "Note".into(),
            Inline::Link(_) => "Link".into(),
            _ => return None,
        };
        self.seen.push(note);
        None
    }
    fn block(&mut self, x: &mut Block, _: &mut Ctx<O>) -> Option<Vec<Block>> {
        let note = match x {
            Block::Para(_) => "Para",
            Block::Header(_) => "Header",
            Block::Div(_) => "Div",
            Block::Table(_) => "Table",
            Block::Figure(_) => "Figure",
            Block::BlockQuote(_) => "BlockQuote",
            _ => return None,
        };
        self.seen.push(note.into());
        None
    }
    fn inlines(&mut self, xs: &mut Vec<Inline>, _: &mut Ctx<O>) {
        self.seen.push(format!("Inlines{}", xs.len()));
    }
    fn blocks(&mut self, xs: &mut Vec<Block>, _: &mut Ctx<O>) {
        self.seen.push(format!("Blocks{}", xs.len()));
    }
    fn meta(&mut self, _: &mut Meta, _: &mut Ctx<O>) {
        self.seen.push("Meta".into());
    }
    fn pandoc(&mut self, _: &mut Pandoc, _: &mut Ctx<O>) {
        self.seen.push("Pandoc".into());
    }
}

// Top-down.

struct Skip;

impl Filter for Skip {
    type Order = Topdown;
    fn inline(&mut self, x: &mut Inline, ctx: &mut Ctx<Topdown>) -> Option<Vec<Inline>> {
        match x {
            Inline::Str(s) => Some(vec![Inline::Str(s.to_uppercase().into())]),
            Inline::Emph(_) => {
                ctx.skip_children();
                None
            }
            _ => None,
        }
    }
    fn block(&mut self, x: &mut Block, ctx: &mut Ctx<Topdown>) -> Option<Vec<Block>> {
        match x {
            Block::Header(h) => Some(vec![Block::Para(take(&mut h.content))]),
            Block::Div(_) => {
                ctx.skip_children();
                None
            }
            Block::BlockQuote(q) => {
                ctx.skip_children();
                Some(vec![Div {
                    attr: Attr::default(),
                    content: take(q),
                }
                .into()])
            }
            _ => None,
        }
    }
}

struct TopLists;

impl Filter for TopLists {
    type Order = Topdown;
    fn inlines(&mut self, xs: &mut Vec<Inline>, ctx: &mut Ctx<Topdown>) {
        if xs.len() == 1 {
            ctx.skip_children();
        } else {
            xs.reverse();
        }
    }
    fn inline(&mut self, x: &mut Inline, _: &mut Ctx<Topdown>) -> Option<Vec<Inline>> {
        match x {
            Inline::Str(s) => Some(vec![Inline::Str(s.to_uppercase().into())]),
            _ => None,
        }
    }
}

/// Run a stateless scenario in the order given.
fn stateless<F: Filter + Default, G: Filter + Default>(doc: &mut Pandoc, bottomup: bool) {
    if bottomup {
        apply(doc, &mut G::default(), FORMAT);
    } else {
        apply(doc, &mut F::default(), FORMAT);
    }
}

/// The scenario `name` on `doc`; `bottomup` for a stateless one run bottom-up.
/// `None` if there is no Rust version of it.
fn scenario(name: &str, doc: &mut Pandoc, bottomup: bool) -> Option<()> {
    match name {
        "upper" => stateless::<Upper<Typewise>, Upper<Bottomup>>(doc, bottomup),
        "modify" => stateless::<Modify<Typewise>, Modify<Bottomup>>(doc, bottomup),
        "splice" => stateless::<Splice<Typewise>, Splice<Bottomup>>(doc, bottomup),
        "generic" => stateless::<Generic<Typewise>, Generic<Bottomup>>(doc, bottomup),
        "once" => stateless::<Once<Typewise>, Once<Bottomup>>(doc, bottomup),
        "lists" => stateless::<Lists<Typewise>, Lists<Bottomup>>(doc, bottomup),
        "meta" => stateless::<MetaScenario<Typewise>, MetaScenario<Bottomup>>(doc, bottomup),
        "typewise" => {
            let mut f = Noting::<Typewise>::new(false);
            apply(doc, &mut f, FORMAT);
            doc.blocks.push(f.listing());
        }
        "topdown" => {
            let mut f = Noting::<Topdown>::new(false);
            apply(doc, &mut f, FORMAT);
            doc.blocks.push(f.listing());
        }
        "bottomup" => {
            let mut f = Noting::<Bottomup>::new(true);
            apply(doc, &mut f, FORMAT);
            doc.blocks.push(f.listing());
        }
        "skip" => apply(doc, &mut Skip, FORMAT),
        "toplists" => apply(doc, &mut TopLists, FORMAT),
        _ => return None,
    }
    Some(())
}

#[test]
fn as_pandocs_lua() {
    let text = std::fs::read_to_string(corpus_dir().join("filters.jsonl")).unwrap();
    let lines: Vec<Value> = text
        .split('\n')
        .filter(|l| !l.is_empty())
        .map(|l| serde_json::from_str(l).unwrap())
        .collect();
    let mut lua: Vec<String> = std::fs::read_dir(corpus_dir().join("filters"))
        .unwrap()
        .filter_map(|e| {
            e.unwrap()
                .file_name()
                .into_string()
                .ok()?
                .strip_suffix(".lua")
                .map(String::from)
        })
        .collect();
    lua.sort();
    let mut names: Vec<String> = lines
        .iter()
        .map(|l| l["name"].as_str().unwrap().to_owned())
        .collect();
    names.sort();
    assert_eq!(
        names, lua,
        "corpus/filters.jsonl is stale: run scripts/filters-corpus.sh"
    );
    let mut failed = vec![];
    for line in &lines {
        let name = line["name"].as_str().unwrap();
        let mut runs = vec![false];
        runs.extend(line["also"].as_array().unwrap().iter().map(|t| {
            assert_eq!(t, "bottomup");
            true
        }));
        for bottomup in runs {
            let mut doc = from_str(&line["input"].to_string()).unwrap();
            scenario(name, &mut doc, bottomup)
                .unwrap_or_else(|| panic!("no Rust filter for {name}"));
            let out: Value = serde_json::from_str(&to_string(&doc)).unwrap();
            if out != line["output"] {
                failed.push(format!(
                    "{name}{}",
                    if bottomup { ", bottomup" } else { "" }
                ));
            }
        }
    }
    assert!(failed.is_empty(), "differ from pandoc's Lua: {failed:?}");
}
