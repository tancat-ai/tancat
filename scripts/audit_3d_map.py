"""Architectural audit of 3D map (nodes.csv + links.csv)."""

import csv
import os
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 1. Load nodes ──────────────────────────────────────────────────────
nodes_by_label = {}
nodes_by_clean = {}
with open(os.path.join(BASE, "docs/nodes.csv")) as f:
    for row in csv.DictReader(f):
        label = row["label"]
        nodes_by_label[label] = row
        clean = label.lstrip("./")
        nodes_by_clean[clean] = row

# ── 2. Load links ──────────────────────────────────────────────────────
links = []
with open(os.path.join(BASE, "docs/links.csv")) as f:
    for row in csv.DictReader(f):
        links.append(row)

# ── 3. Dead links (source/target not in nodes.csv) ─────────────────────
print("=" * 60)
print("3D MAP ARCHITECTURAL AUDIT")
print("=" * 60)

# Dead nodes: in nodes.csv but file doesn't exist
dead_nodes = []
for label, row in nodes_by_label.items():
    clean = label.lstrip("./")
    full_path = os.path.join(BASE, clean)
    if not os.path.exists(full_path):
        dead_nodes.append((label, row["group"], row["size"]))

print(f"\n1. DEAD NODES (in nodes.csv but file doesn't exist): {len(dead_nodes)}")
for label, group, size in dead_nodes:
    print(f"   [{group}] {label} (size={size})")


# Dead links: source or target not in nodes.csv
def normalize(label: str) -> str | None:
    """Try to find a matching node label."""
    if label in nodes_by_label:
        return label
    if "./" + label in nodes_by_label:
        return "./" + label
    if label.lstrip("./") in nodes_by_clean:
        return "./" + label.lstrip("./")
    return None


dead_links = []
for link in links:
    src = link["source"]
    tgt = link["target"]
    src_norm = normalize(src)
    tgt_norm = normalize(tgt)
    if src_norm is None and tgt_norm is None:
        dead_links.append((src, tgt, link["type"], "both dead"))
    elif src_norm is None:
        dead_links.append((src, tgt, link["type"], "source dead"))
    elif tgt_norm is None:
        dead_links.append((src, tgt, link["type"], "target dead"))

print(f"\n2. DEAD LINKS (source/target not in nodes.csv): {len(dead_links)}")
for src, tgt, typ, reason in dead_links[:40]:
    print(f"   {src} -> {tgt} ({typ}) [{reason}]")

# ── 4. Orphaned docs ──────────────────────────────────────────────────
doc_nodes = {label: row for label, row in nodes_by_label.items() if row["group"] == "Documentation"}

# Build set of docs with references/proximity links
docs_with_links = set()
for link in links:
    src_norm = normalize(link["source"])
    tgt_norm = normalize(link["target"])
    if link["type"] in ("references", "proximity"):
        if src_norm and src_norm in doc_nodes:
            docs_with_links.add(src_norm)
        if tgt_norm and tgt_norm in doc_nodes:
            docs_with_links.add(tgt_norm)

orphaned_docs = [label for label in doc_nodes if label not in docs_with_links]

print(f"\n3. ORPHANED DOCS (Documentation group, zero ref/prox links): {len(orphaned_docs)}")
for label in orphaned_docs:
    print(f"   {label}")

# Docs with proximity-only (no references)
prox_only = []
for label in doc_nodes:
    if label in docs_with_links:
        has_ref = False
        for link in links:
            if link["type"] == "references":
                src_norm = normalize(link["source"])
                tgt_norm = normalize(link["target"])
                if src_norm == label or tgt_norm == label:
                    has_ref = True
                    break
        if not has_ref:
            prox_only.append(label)

print(f"\n4. DOCS WITH PROXIMITY-ONLY (no references): {len(prox_only)}")
for label in prox_only[:15]:
    print(f"   {label}")

# ── 5. Import drift ───────────────────────────────────────────────────
# Get import links
import_links = [link for link in links if link["type"] == "import"]

# Group by source
imports_by_source = defaultdict(set)
for link in import_links:
    src_norm = normalize(link["source"])
    if src_norm:
        imports_by_source[src_norm].add(link["target"])

# Check for missing imports (actual Python imports not in links)
# We'll read the actual imports from key files
print("\n5. ACTUAL PYTHON IMPORTS vs LINKS IMPORTS:")

# Read streamlit_app.py imports
sa_imports = []
sa_path = os.path.join(BASE, "streamlit_app.py")
if os.path.exists(sa_path):
    with open(sa_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("from src.") and "import" in line:
                # Extract module
                mod = line.split("from src.")[1].split(".")[0]
                sa_imports.append(f"./src/{mod}.py")
            elif line.startswith("import src.") or line.startswith("from src."):
                mod = line.replace("import src.", "").replace("from src.", "").split(".")[0]
                sa_imports.append(f"./src/{mod}.py")

# Read cli imports
cli_imports = {}
cli_dir = os.path.join(BASE, "cli")
if os.path.isdir(cli_dir):
    for fname in os.listdir(cli_dir):
        if fname.endswith(".py"):
            fpath = os.path.join(cli_dir, fname)
            imports = []
            with open(fpath, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("from cli.") and "import" in line:
                        mod = line.split("from cli.")[1].split(".")[0]
                        imports.append(f"./cli/{mod}.py")
                    elif line.startswith("from src.") and "import" in line:
                        mod = line.split("from src.")[1].split(".")[0]
                        imports.append(f"./src/{mod}.py")
            if imports:
                cli_imports[f"./cli/{fname}"] = imports

# Check streamlit_app.py
print("\n   streamlit_app.py actual imports:")
for imp in sorted(set(sa_imports)):
    print(f"      {imp}")

print("\n   streamlit_app.py recorded import links:")
if "./streamlit_app.py" in imports_by_source:
    for imp in sorted(imports_by_source["./streamlit_app.py"]):
        print(f"      {imp}")
else:
    print("      (none found)")

# Check for new modules without import links
print("\n6. NEW MODULES (in nodes.csv but no import links as source):")
new_modules = [
    "src/analyzer.py",
    "src/config.py",
    "src/code_postprocessor.py",
    "src/url_utils.py",
    "src/report_builder.py",
    "src/report_formatters.py",
    "src/evidence_report.py",
]
for mod in new_modules:
    label = f"./{mod}"
    if label in nodes_by_label:
        has_import_links = label in imports_by_source
        has_incoming = False
        for link in links:
            if normalize(link["target"]) == label and link["type"] == "import":
                has_incoming = True
                break
        print(f"   {mod}: nodes=yes, outgoing_imports={has_import_links}, incoming_imports={has_incoming}")
    else:
        print(f"   {mod}: NOT in nodes.csv")

# Check for stale references in docs
print("\n7. STALE DOC REFERENCES (docs reference deleted files):")
stale_refs = []
for link in links:
    tgt = link["target"]
    # Check if target is a known deleted file
    if "page_context_scraper" in tgt:
        stale_refs.append((link["source"], tgt, link["type"]))

for src, tgt, typ in stale_refs:
    print(f"   {src} -> {tgt} ({typ})")

# Check for evidence/build artifact nodes
print("\n8. EVIDENCE FILES (should be excluded from 3D map):")
evidence_nodes = [label for label in nodes_by_label if "/evidence/" in label]
print(f"   Count: {len(evidence_nodes)}")

print("\n9. BUILD ARTIFACTS (should be excluded from 3D map):")
build_nodes = [label for label in nodes_by_label if "egg-info" in label]
for n in build_nodes:
    print(f"   {n}")

print("\n10. SUMMARY:")
print(f"   Total nodes: {len(nodes_by_label)}")
print(f"   Dead nodes: {len(dead_nodes)}")
print(f"   Dead links: {len(dead_links)}")
print(f"   Orphaned docs: {len(orphaned_docs)}")
print(f"   Evidence files: {len(evidence_nodes)}")
print(f"   Build artifacts: {len(build_nodes)}")
