"""Static-only validation of build_escpos_ticket tall-mode wrapping.

NO Flask, NO sockets, NO real printer contact. Pure function call.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

# Strip leading ESC/POS control-code byte sequences from a decoded line
# so we can measure the *visible* length. Common ones:
#   ESC E n     (bold on/off)       -> \x1bE.
#   GS  ! n     (size)              -> \x1d!.
#   ESC a n     (align)             -> \x1ba.
#   ESC @       (init)              -> \x1b@
#   ESC t n     (codepage)          -> \x1bt.
CTRL_RE = re.compile(r"^(?:\x1b[Eatab@!]\x00|\x1bE.|\x1d!.|\x1ba.|\x1bt.|\x1b@)+")


def visible(line: str) -> str:
    prev = None
    s = line
    while prev != s:
        prev = s
        s = CTRL_RE.sub("", s)
    return s


def test_build_ticket_wraps_at_word_boundaries():
    order = {
        "order_number": "42",
        "created_at": "2026-01-15T12:30:00+00:00",
        "fulfillment": "delivery",
        "customer_first_name": "Elias",
        "customer_last_name": "Benzi",
        "customer_phone": "0785549297",
        "address_line1": "12 rue de la villaine",
        "postal_code": "06240",
        "city": "Beausoleil",
        "total": 28.6,
        "payment_method": "cash",
        "items": [
            {
                "quantity": 1,
                "name": "Menu Mac Chicken",
                "formula": "menu",
                "included_drink": "Coca-Cola",
                "burger_config": None,
                "sauces": [],
            },
            {
                "quantity": 1,
                "name": "Menu Tacos",
                "formula": "menu",
                "included_drink": "Coca-Cola",
                "burger_config": {
                    "meats": [{"name": "Viande Hachee"}, {"name": "Kebab"}],
                    "supplements": [{"name": "Raclette"}],
                },
                "sauces": ["Samoura"],
            },
        ],
    }

    raw = server.build_escpos_ticket(order)
    assert isinstance(raw, bytes)

    # (c1) ends with FEED_LINES + CUT unchanged
    assert raw.endswith(server.FEED_LINES + server.CUT), "must end with feed+cut"
    # Also assert 6 blank feed lines
    assert server.FEED_LINES == b"\n" * 6

    decoded = raw.decode("cp1252", errors="replace")
    lines = decoded.split("\n")

    # Header lines should be present and untouched
    joined_vis = [visible(l) for l in lines]
    assert "BURGER TIMES" in joined_vis, "header BURGER TIMES missing/altered"
    assert any(l.startswith("COMMANDE #42") for l in joined_vis), "COMMANDE header missing"
    assert "LIVRAISON" in joined_vis, "fulfillment label missing"
    # date/time: "dd/mm/yyyy HH:MM" present as its own line (non-empty w/ '/' and ':')
    assert any(re.match(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}$", l) for l in joined_vis), "date/time line missing"

    # Dashed divider lines: 32 dashes, unchanged
    divider = "-" * 32
    divider_count = sum(1 for l in joined_vis if l == divider)
    assert divider_count >= 3, f"expected >=3 divider lines, got {divider_count}"

    # Identify "tall body" lines: everything AFTER the second divider that
    # is itself not a divider and not empty.
    second_div_idx = [i for i, l in enumerate(joined_vis) if l == divider][1]
    body_slice = joined_vis[second_div_idx + 1:]
    # Strip trailing empty feed lines
    while body_slice and body_slice[-1] == "":
        body_slice.pop()

    tall_body = [l for l in body_slice if l != divider and l != ""]

    # (a) every tall body line <= 16 visible chars
    for l in tall_body:
        assert len(l) <= server.TALL_LINE_WIDTH, (
            f"tall line too long ({len(l)} > {server.TALL_LINE_WIDTH}): {l!r}"
        )

    # (b) no mid-word splits: each of these tokens must appear whole on some line
    body_text_lines = tall_body
    must_appear_whole = [
        "(Viande",
        "Hachee, Kebab)",
        "Chicken",
        "Benzi",
        "villaine",
        "Beausoleil",
        "0785549297",
    ]
    for tok in must_appear_whole:
        found = any(tok in l for l in body_text_lines)
        assert found, f"expected token {tok!r} intact on some tall line, body was:\n" + "\n".join(body_text_lines)

    # Also: no tall line should end with a hyphen-broken word (heuristic:
    # a line ending with a letter followed by a line starting with a letter
    # is only OK if the previous line ended on a whole word — i.e. textwrap
    # never breaks inside a word, so any two consecutive body lines where
    # line1 does not end at a word boundary and line2 starts with lowercase
    # letters that would form a real English/French word... Simpler check:
    # textwrap.wrap never splits inside a word, so just re-run textwrap on
    # each source phrase and confirm none of the pieces contain a partial-
    # word fragment. Skipped — the token check above already covers it.

    print("TALL_LINE_WIDTH =", server.TALL_LINE_WIDTH)
    print(f"tall body lines ({len(tall_body)}):")
    for l in tall_body:
        print(f"  [{len(l):2d}] {l!r}")


if __name__ == "__main__":
    test_build_ticket_wraps_at_word_boundaries()
    print("\nALL CHECKS PASSED")
