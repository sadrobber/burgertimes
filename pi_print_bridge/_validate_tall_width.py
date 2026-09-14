"""Static validation only — imports server, calls build_escpos_ticket directly.
No Flask, no HTTP, no send_to_printer, no test print.
"""
import sys
sys.path.insert(0, "/app/pi_print_bridge")
import server

print(f"TALL_LINE_WIDTH = {server.TALL_LINE_WIDTH}")
assert server.TALL_LINE_WIDTH == 32, f"Expected 32, got {server.TALL_LINE_WIDTH}"

def decode_lines(payload: bytes):
    text = payload.decode("cp1252", errors="replace")
    return text.split("\n")

# ---- Case 1: user's reported regression ----
order1 = {
    "order_number": "TEST1",
    "items": [
        {"quantity": 1, "name": "Menu Sandwich Curry", "formula": "menu",
         "included_drink": "Fanta Orange", "burger_config": None, "sauces": []},
        {"quantity": 1, "name": "Tarte Daim", "formula": None,
         "included_drink": None, "burger_config": None, "sauces": []},
    ],
    "customer_first_name": "Youssra",
    "customer_last_name": "Witfrow",
    "customer_phone": "+33 758695588",
    "fulfillment": "delivery",
    "address_line1": "11 Boulevard du Jardin Exotique",
    "postal_code": "98000",
    "city": "Monaco",
    "total": 19.25,
    "payment_method": "card_in_person",
}

payload1 = server.build_escpos_ticket(order1)
lines1 = decode_lines(payload1)
print("\n=== CASE 1 LINES ===")
for i, ln in enumerate(lines1):
    print(f"{i:02d}: {ln!r}")

required_case1 = [
    "1x Menu Sandwich Curry",
    "11 Boulevard du Jardin Exotique",
    "Paiement : Carte sur place",
]
print("\n=== CASE 1 CHECKS ===")
case1_ok = True
for target in required_case1:
    found = any(target in ln for ln in lines1)
    print(f"  {'OK' if found else 'FAIL'}: '{target}' present on a single line = {found}")
    if not found:
        case1_ok = False

# ---- Case 2: original long-line word-boundary case ----
order2 = {
    "order_number": "TEST2",
    "items": [
        {"quantity": 1, "name": "Menu Tacos", "formula": "menu",
         "included_drink": "Coca-Cola",
         "burger_config": {
             "meats": [{"name": "Viande Hachee"}, {"name": "Kebab"}],
             "supplements": [{"name": "Raclette"}],
         },
         "sauces": ["Samoura"]},
    ],
    "customer_first_name": "Youssra",
    "customer_last_name": "Witfrow",
    "customer_phone": "+33 758695588",
    "fulfillment": "delivery",
    "address_line1": "11 Boulevard du Jardin Exotique",
    "postal_code": "98000",
    "city": "Monaco",
    "total": 19.25,
    "payment_method": "card_in_person",
}

payload2 = server.build_escpos_ticket(order2)
lines2 = decode_lines(payload2)
print("\n=== CASE 2 LINES ===")
for i, ln in enumerate(lines2):
    print(f"{i:02d}: {ln!r}")

# Check tokens 'Hachee,' and 'Kebab)' appear intact anywhere as whole tokens.
joined2 = "\n".join(lines2)
print("\n=== CASE 2 CHECKS ===")
case2_ok = True
# Must contain intact tokens
for tok in ["Hachee,", "Kebab)"]:
    ok = tok in joined2
    print(f"  {'OK' if ok else 'FAIL'}: intact token '{tok}' present = {ok}")
    if not ok:
        case2_ok = False

# Must NOT contain any of these bad mid-word splits at line ends
bad_endings = ["Hach", "Hache", "Keb", "Keba"]
for ln in lines2:
    stripped = ln.rstrip()
    for bad in bad_endings:
        if stripped.endswith(bad):
            print(f"  FAIL: line ends with mid-word split '{bad}': {ln!r}")
            case2_ok = False

# Header / divider integrity
print("\n=== HEADER/DIVIDER CHECKS ===")
header_ok = any("BURGER TIMES" in ln for ln in lines1)
cmd_ok = any(ln.startswith("COMMANDE #") or "COMMANDE #" in ln for ln in lines1)
divider_ok = any(ln.strip() == "-" * 32 for ln in lines1)
print(f"  {'OK' if header_ok else 'FAIL'}: 'BURGER TIMES' header present")
print(f"  {'OK' if cmd_ok else 'FAIL'}: 'COMMANDE #' line present")
print(f"  {'OK' if divider_ok else 'FAIL'}: 32-char dashed DIVIDER present")

print("\n=== SUMMARY ===")
print(f"Case 1 (regression fix): {'PASS' if case1_ok else 'FAIL'}")
print(f"Case 2 (word-boundary):  {'PASS' if case2_ok else 'FAIL'}")
print(f"Header/Divider:          {'PASS' if (header_ok and cmd_ok and divider_ok) else 'FAIL'}")

overall = case1_ok and case2_ok and header_ok and cmd_ok and divider_ok
print(f"\nOVERALL: {'PASS' if overall else 'FAIL'}")
sys.exit(0 if overall else 1)
