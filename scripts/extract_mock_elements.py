"""Extract element data from mock_insurance_site.html for eval resolver."""

import json
import re

html = open("generated_tests/mock_insurance_site.html", encoding="utf-8").read()

elements = []
seen = set()

# Extract all elements with id attributes
for match in re.finditer(
    r"<(input|select|textarea|button|div|h2|h3|h4|label|fieldset|legend|ul|span)\b[^>]*>",
    html,
):
    tag = match.group(1)
    attrs_str = match.group(0)

    id_match = re.search(r'id=["\x27]([^"\x27]+)["\x27]', attrs_str)
    element_id = id_match.group(1) if id_match else ""
    if not element_id or element_id in seen:
        continue
    seen.add(element_id)

    type_match = re.search(r'type=["\x27]([^"\x27]+)["\x27]', attrs_str)
    el_type = type_match.group(1) if type_match else ""

    name_match = re.search(r'name=["\x27]([^"\x27]+)["\x27]', attrs_str)
    el_name = name_match.group(1) if name_match else ""

    ph_match = re.search(r'placeholder=["\x27]([^"\x27]+)["\x27]', attrs_str)
    placeholder = ph_match.group(1) if ph_match else ""

    al_match = re.search(r'aria-label=["\x27]([^"\x27]+)["\x27]', attrs_str)
    aria_label = al_match.group(1) if al_match else ""

    # Extract visible text for buttons/labels
    text = ""
    if tag == "button":
        escaped_id = re.escape(element_id)
        btn_pat = re.compile(r"<button[^>]*id=[" "\x27]" + escaped_id + r"[" "\x27][^>]*>([^<]*)</button>")
        btn_match = btn_pat.search(html)
        if btn_match:
            text = btn_match.group(1).strip()

    # Determine ARIA role
    role = ""
    if tag == "input":
        if el_type in ("email", "password", "text", "number", "date"):
            role = "textbox"
        elif el_type == "radio":
            role = "radio"
        elif el_type == "checkbox":
            role = "checkbox"
        elif el_type == "range":
            role = "slider"
    elif tag == "select":
        role = "combobox"
    elif tag == "button":
        role = "button"
    elif tag == "textarea":
        role = "textbox"
    elif tag in ("h2", "h3", "h4"):
        role = "heading"
    elif tag == "label":
        role = "text"
    elif tag == "fieldset":
        role = "region"
    elif tag == "legend":
        role = "text"
    elif tag == "div":
        # Only include meaningful divs (pages, alerts, price displays)
        if any(k in element_id for k in ("page", "Success", "Declined", "details", "price", "excess", "summary")):
            role = "generic"
        else:
            continue
    elif tag == "ul":
        role = "list"
    elif tag == "span":
        role = "text"

    selector = f"#{element_id}"

    elements.append(
        {
            "selector": selector,
            "tag": tag,
            "role": role,
            "text": text[:100] if text else "",
            "id": element_id,
            "name": el_name,
            "type": el_type,
            "placeholder": placeholder,
            "aria_label": aria_label,
            "data_test": "",
        }
    )

print(f"Found {len(elements)} unique elements with IDs")

# Save as scraped page data
base_url = "http://localhost:8767/mock_insurance_site.html"
scraped = {base_url: elements}
out_path = "scripts/eval/scraped_pages/http_localhost_8767_mock_insurance_site.html.json"
with open(out_path, "w") as f:
    json.dump(scraped, f, indent=2)
print(f"Saved {len(elements)} elements to {out_path}")

# Quick summary
for e in elements[:15]:
    t = e["text"][:50] if e["text"] else "-"
    print(f"  {e['selector']:45} {e['tag']:10} {e['role']:10} {t}")
