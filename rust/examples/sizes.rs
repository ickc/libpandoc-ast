//! The sizes of the AST's types: `cargo run --example sizes`.
fn main() {
    use std::mem::size_of;
    println!(
        "Inline {} Block {} MetaValue {}",
        size_of::<panir::Inline>(),
        size_of::<panir::Block>(),
        size_of::<panir::MetaValue>()
    );
}
