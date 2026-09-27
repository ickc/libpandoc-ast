#!/usr/bin/env python3
"""Demote headers, and number them in their text: a pandoc filter.

pandoc --filter ./demote.py input.md
"""

from panir import Filter, Header, Space, Str

f = Filter()
counter = 0


@f.on(Header)
def demote(h: Header) -> None:
    global counter
    counter += 1
    h.level += 1
    h.content[:0] = [Str(f"{counter}."), Space()]


if __name__ == "__main__":
    f.main()
