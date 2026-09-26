---
title: A *feature* tour
author:
  - name: Ada
    affiliation: [one, two]
  - Grace
draft: false
count: 3
abstract: |
  A paragraph.

  Another, with `code`.
nested:
  deeper:
    deepest: [x, true, 1.5]
---

# Heading {#intro .unnumbered key="value"}

Some *emphasis*, **strong**, ~~struck~~, ~sub~, ^sup^, [small caps]{.smallcaps},
[underlined]{.underline}, "double" and 'single' quotes, `code`{.python},
$x^2$ and $$\int f$$, a [link](https://example.com "Title"), an
![image](img.png){width=50%}, a footnote,[^1] and a citation [@doe99, p. 3;
-@roe01] with @moe02 in text. Line\
break and <b>raw html</b>.

[^1]: The note, with two paragraphs.

    The second.

::: {#box .note}
A div.
:::

| A line
|    block

> A quote.
>
> - nested
> - list

3. three
4. four

(a) alpha
(b) beta

Term
: Definition one.

: Definition two.

```haskell
main = pure ()
```

```{=latex}
\relax
```

------

| Left | Center | Right |
|:-----|:------:|------:|
| a    | b      | c     |

: A table caption {#tbl}

+-------+------------------+
| Grid  | Table            |
+=======+==================+
| spans | two              |
| rows  | lines            |
+-------+------------------+
| - a   | b                |
+-------+------------------+

![A figure caption](fig.png){#fig}
