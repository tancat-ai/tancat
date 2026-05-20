"""Generate 3D map data (nodes.csv, links.csv, 3d_map_data.json) for Cosmograph.

Improvements (2026-05-20):
- Dynamic import scanning via AST instead of hardcoded lists
- Dead link filtering — only creates links where both source and target exist
- Dynamic test → source link detection
- Scripts README gets proximity links to files it documents
"""

import ast
import csv
import json
import os
from collections import Counter

###############################################################################
# 1. LAYER MAP — all .py files → group
###############################################################################
LAYER_MAP = {
    # Interface
    "streamlit_app.py": "interface",
    "cli/main.py": "interface",
    "cli/config.py": "interface",
    "cli/input_parser.py": "interface",
    "cli/test_orchestrator.py": "interface",
    "cli/evidence_generator.py": "interface",
    "cli/report_generator.py": "interface",
    "cli/__init__.py": "interface",
    # Orchestration
    "src/orchestrator.py": "orchestration",
    "src/pipeline_run_service.py": "orchestration",
    "src/pipeline_writer.py": "orchestration",
    "src/pipeline_report_service.py": "orchestration",
    "src/pipeline_models.py": "orchestration",
    # Intelligence
    "src/spec_analyzer.py": "intelligence",
    "src/test_generator.py": "intelligence",
    "src/llm_client.py": "intelligence",
    "src/skeleton_parser.py": "intelligence",
    "src/prompt_utils.py": "intelligence",
    "src/llm_errors.py": "intelligence",
    "src/llm_providers/__init__.py": "intelligence",
    "src/test_plan.py": "intelligence",
    "src/user_story_parser.py": "intelligence",
    "src/analyzer.py": "intelligence",
    "src/config.py": "intelligence",
    # Context
    "src/scraper.py": "context",
    "src/stateful_scraper.py": "context",
    "src/journey_scraper.py": "context",
    "src/semantic_candidate_ranker.py": "context",
    # Refinement
    "src/placeholder_orchestrator.py": "refinement",
    "src/placeholder_resolver.py": "refinement",
    "src/page_object_builder.py": "refinement",
    "src/code_validator.py": "refinement",
    "src/code_postprocessor.py": "refinement",
    "src/locator_scorer.py": "refinement",
    "src/locator_fallback.py": "refinement",
    # Output
    "src/report_utils.py": "output",
    "src/report_builder.py": "output",
    "src/report_formatters.py": "output",
    "src/evidence_report.py": "output",
    "src/evidence_tracker.py": "output",
    # Utility
    "src/file_utils.py": "utility",
    "src/run_utils.py": "utility",
    "src/pytest_output_parser.py": "utility",
    "src/coverage_utils.py": "utility",
    "src/gantt_utils.py": "utility",
    "src/heatmap_utils.py": "utility",
    "src/url_utils.py": "utility",
    "src/__init__.py": "utility",
}

###############################################################################
# 2. ALL PROJECT FILES — scan for real files
###############################################################################
ALL_FILES = set()
SKIP_DIRS = {
    ".venv",
    "__pycache__",
    "node_modules",
    ".git",
    "screenshots",
    "htmlcov",
    "pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "playwright",
    "test-results",
    "playwright-report",
    "blob-report",
    "scratch",
    ".uv-cache",
    ".pytest_cache",
    ".tmp",
    ".streamlit",
    ".cache",
    "cline-mcp-memory-bank",
    "memory-bank",
    "evidence",
}
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
    for f in files:
        full = os.path.join(root, f)
        rel = full.replace("\\", "/")
        if f.startswith("."):
            continue
        skip_ext = (
            ".pyc",
            ".pyo",
            ".so",
            ".dll",
            ".exe",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".woff",
            ".ttf",
            ".woff2",
            ".map",
            ".lock",
            ".tag",
            ".met",
            ".wheel",
        )
        if f.endswith(skip_ext):
            continue
        ALL_FILES.add(rel)

ROOT_CONFIG_FILES = [
    ".clinerules",
    ".clineignore",
    ".dockerignore",
    ".gitignore",
    ".env.example",
    ".python-version",
    "pyproject.toml",
    "pytest.ini",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
    "LICENSE",
    "fix.sh",
    "launch_ui.sh",
    "launch_dev.sh",
]
for f in ROOT_CONFIG_FILES:
    if os.path.exists(f):
        ALL_FILES.add("./" + f)

for subdir in ["cli", "src", "tests", "docs", "docs/plans", "scripts"]:
    if os.path.isdir(subdir):
        for f in os.listdir(subdir):
            full = "./" + subdir + "/" + f
            if f.endswith(".py") or f.endswith(".md"):
                ALL_FILES.add(full)
        for root2, _dirs2, files2 in os.walk(subdir):
            for f in files2:
                if f.endswith(".py") or f.endswith(".md"):
                    full = "./" + os.path.join(root2, f).replace("\\", "/")
                    ALL_FILES.add(full)

# Filters
ALL_FILES = {f for f in ALL_FILES if not f.endswith((".xml", ".lock"))}
ALL_FILES = {f for f in ALL_FILES if "mock_insurance_site" not in f and "cart.html" not in f}
ALL_FILES = {f for f in ALL_FILES if "cline-mcp-memory-bank" not in f}
ALL_FILES = {f for f in ALL_FILES if not f.endswith((".txt", ".log", ".err")) or f in (".env.example",)}
ALL_FILES = {
    f
    for f in ALL_FILES
    if f not in ("3d_map_data.json", "nodes.csv", "links.csv")
    and f not in ("./3d_map_data.json", "./nodes.csv", "./links.csv")
    and f not in ("docs/3d_map_data.json", "docs/nodes.csv", "docs/links.csv")
}

###############################################################################
# 3. SMART DOC LINKS
###############################################################################
DOC_REFS = {
    "AGENTS.md": [
        "streamlit_app.py",
        "cli/main.py",
        "src/test_generator.py",
        "src/llm_client.py",
        "src/orchestrator.py",
        "src/placeholder_resolver.py",
        "src/skeleton_parser.py",
        "src/scraper.py",
        "src/page_object_builder.py",
        "src/semantic_candidate_ranker.py",
        "src/pipeline_report_service.py",
        "src/pipeline_run_service.py",
        "src/pipeline_writer.py",
        "src/file_utils.py",
        "src/stateful_scraper.py",
        "src/code_validator.py",
        "src/run_utils.py",
        "src/gantt_utils.py",
        "src/heatmap_utils.py",
        "main.py",
        "README.md",
        "BACKLOG.md",
        "src/prompt_utils.py",
        "src/spec_analyzer.py",
        "src/pipeline_models.py",
        "tests/test_spec_analyzer.py",
        "tests/test_test_plan.py",
        "tests/test_evidence_tracker.py",
        "tests/test_gantt_utils.py",
        "tests/test_heatmap_utils.py",
        "generated_tests/conftest.py",
    ],
    "docs/ARCHITECTURE.md": [
        "src/orchestrator.py",
        "src/test_generator.py",
        "src/llm_client.py",
        "src/scraper.py",
        "src/placeholder_resolver.py",
        "src/skeleton_parser.py",
        "src/page_object_builder.py",
        "src/pipeline_writer.py",
        "src/pipeline_report_service.py",
        "streamlit_app.py",
        "cli/main.py",
        "src/prompt_utils.py",
    ],
    "BACKLOG.md": [
        "src/prompt_utils.py",
        "src/evidence_tracker.py",
        "src/orchestrator.py",
        "tests/conftest.py",
    ],
    "CHANGELOG.md": [
        "streamlit_app.py",
        "src/orchestrator.py",
        "src/test_generator.py",
        "src/scraper.py",
        "src/placeholder_resolver.py",
        "src/skeleton_parser.py",
        "src/page_object_builder.py",
        "src/pipeline_writer.py",
    ],
    "CONTRIBUTING.md": [
        "streamlit_app.py",
        "cli/main.py",
        "src/test_generator.py",
        "src/llm_client.py",
        "src/orchestrator.py",
        "pytest.ini",
        "pyproject.toml",
    ],
    "docs/DEMO_GUIDE.md": [
        "streamlit_app.py",
        "launch_ui.sh",
        "launch_dev.sh",
        "src/scraper.py",
        "src/test_generator.py",
    ],
    "docs/FEATURE_SPEC_AI009_phase_b.md": [
        "streamlit_app.py",
        "src/llm_client.py",
        "src/test_generator.py",
        "main.py",
        "fix.sh",
    ],
    "docs/specs/FEATURE_SPEC_intelligent_scraping_pipeline.md": [
        "streamlit_app.py",
        "src/prompt_utils.py",
        "src/skeleton_parser.py",
        "src/page_object_builder.py",
        "src/placeholder_resolver.py",
    ],
    "docs/specs/FEATURE_SPEC_multi_page_scraping.md": [
        "src/scraper.py",
        "src/stateful_scraper.py",
        "src/page_context_scraper.py",
        "src/orchestrator.py",
        "src/test_generator.py",
        "src/placeholder_resolver.py",
        "src/page_object_builder.py",
        "streamlit_app.py",
    ],
    "docs/specs/FEATURE_SPEC_multi_provider_llm.md": [
        "src/llm_client.py",
        "src/test_generator.py",
        "main.py",
        "src/llm_providers/__init__.py",
        "streamlit_app.py",
    ],
    "docs/specs/FEATURE_SPEC_page_context_scraper.md": [
        "src/scraper.py",
        "src/stateful_scraper.py",
        "src/orchestrator.py",
        "src/test_generator.py",
        "src/placeholder_resolver.py",
        "src/page_object_builder.py",
        "streamlit_app.py",
    ],
    "docs/specs/FEATURE_SPEC_run_results.md": [
        "src/pipeline_report_service.py",
        "src/report_utils.py",
        "src/pytest_output_parser.py",
        "src/coverage_utils.py",
        "streamlit_app.py",
        "src/pipeline_writer.py",
    ],
    "docs/session_02_placeholder_resolver.md": [
        "src/scraper.py",
        "src/placeholder_resolver.py",
        "src/orchestrator.py",
        "src/skeleton_parser.py",
    ],
    "docs/session_03_orchestrator.md": [
        "src/orchestrator.py",
        "src/scraper.py",
        "src/placeholder_resolver.py",
    ],
    "docs/session_04_final_polish.md": ["src/orchestrator.py"],
    "docs/session_05_pipeline_rebuild_plan.md": [
        "docs/specs/FEATURE_SPEC_intelligent_scraping_pipeline.md",
        "src/pipeline_models.py",
        "src/skeleton_parser.py",
        "src/page_object_builder.py",
        "src/placeholder_resolver.py",
        "src/test_generator.py",
        "src/scraper.py",
        "streamlit_app.py",
    ],
    "docs/test_suite_audit_2026-04-08.md": [
        "tests/test_orchestrator.py",
        "tests/test_skeleton_parser.py",
        "tests/test_placeholder_resolver.py",
        "tests/test_scraper.py",
        "tests/test_page_object_builder.py",
        "tests/test_pipeline_models.py",
        "tests/test_pipeline_writer.py",
        "tests/test_pipeline_run_service.py",
        "tests/test_pipeline_report_service.py",
        "tests/test_pytest_output_parser.py",
        "tests/test_run_utils.py",
        "tests/test_coverage_utils.py",
        "tests/test_user_story_parser.py",
        "tests/test_code_validator.py",
        "tests/test_test_generator.py",
        "tests/test_llm_client.py",
        "tests/test_llm_errors.py",
        "tests/test_cli_smoke.py",
        "tests/test_cli_test_orchestrator.py",
        "src/orchestrator.py",
        "src/skeleton_parser.py",
        "src/placeholder_resolver.py",
        "src/scraper.py",
        "src/page_object_builder.py",
        "src/pipeline_models.py",
        "src/pipeline_writer.py",
        "src/pipeline_run_service.py",
        "src/pipeline_report_service.py",
        "src/pytest_output_parser.py",
        "src/run_utils.py",
        "src/coverage_utils.py",
        "src/user_story_parser.py",
        "src/code_validator.py",
        "src/test_generator.py",
        "src/llm_client.py",
        "src/llm_errors.py",
    ],
    "docs/plans/AI-016_plan.md": [
        "src/spec_analyzer.py",
        "tests/test_spec_analyzer.py",
        "streamlit_app.py",
        "src/prompt_utils.py",
    ],
    "docs/plans/AI-017_plan.md": [
        "src/test_plan.py",
        "tests/test_test_plan.py",
        "streamlit_app.py",
    ],
    "docs/plans/AI-018_plan.md": [
        "src/evidence_tracker.py",
        "tests/test_evidence_tracker.py",
        "generated_tests/conftest.py",
        "./.gitignore",
    ],
    "docs/plans/AI-019_plan.md": [
        "src/prompt_utils.py",
        "src/llm_client.py",
        "src/test_generator.py",
    ],
    "docs/plans/AI-020_plan.md": ["src/report_utils.py", "streamlit_app.py"],
    "docs/plans/AI-021_plan.md": [
        "src/gantt_utils.py",
        "tests/test_gantt_utils.py",
        "streamlit_app.py",
    ],
    "docs/plans/AI-022_plan.md": [
        "src/heatmap_utils.py",
        "tests/test_heatmap_utils.py",
        "streamlit_app.py",
    ],
    "docs/plans/AI0IS9_section1_audit.md": [
        "tests/conftest.py",
        "src/prompt_utils.py",
        "src/orchestrator.py",
    ],
    "docs/plans/AI019_section1_audit.md": [
        "tests/conftest.py",
        "src/prompt_utils.py",
        "src/orchestrator.py",
    ],
    "docs/plans/AI019_section2_prompts.md": ["src/prompt_utils.py"],
    "docs/plans/AI019_section3_validation.md": [
        "src/test_generator.py",
        "src/orchestrator.py",
    ],
    "docs/plans/FEATURE_COMPLETION_CHECKLIST.md": [
        "docs/plans/AI-016_plan.md",
        "docs/plans/AI-017_plan.md",
        "docs/plans/AI-018_plan.md",
        "docs/plans/AI-019_plan.md",
        "docs/plans/AI019_section1_audit.md",
        "docs/plans/AI019_section2_prompts.md",
        "docs/plans/AI019_section3_validation.md",
        "docs/plans/AI-020_plan.md",
        "docs/plans/AI-021_plan.md",
        "docs/plans/AI-022_plan.md",
        "docs/archived/session_05_pipeline_rebuild_plan.md",
        "src/test_plan.py",
        "streamlit_app.py",
        "src/page_object_builder.py",
        "src/placeholder_resolver.py",
    ],
    "docs/plans/PK_CLEANUP_section1_audit.md": [
        "docs/PROJECT_KNOWLEDGE.md",
        "AGENTS.md",
        "./.clinerules",
    ],
    "SECURITY.md": ["README.md", "CONTRIBUTING.md"],
    "docs/plans/FEATURE_PLAN_keyword_based_url_resolution.md": [
        "src/orchestrator.py",
        "src/url_utils.py",
        "src/placeholder_orchestrator.py",
    ],
    "docs/plans/FEATURE_PLAN_pom_with_evidence_tracker.md": [
        "src/page_object_builder.py",
        "src/evidence_tracker.py",
        "src/pipeline_writer.py",
    ],
    "docs/plans/FEATURE_PLAN_test_prerequisite_injection.md": [
        "src/orchestrator.py",
        "src/prerequisite_injector.py",
        "src/pipeline_writer.py",
    ],
    "docs/specs/FEATURE_SPEC_AI023_locator_repair.md": [
        "src/code_postprocessor.py",
        "src/placeholder_resolver.py",
        "src/locator_scorer.py",
    ],
    "docs/specs/FEATURE_SPEC_AI024_accessibility_tree_enrichment.md": [
        "src/scraper.py",
        "src/accessibility_enricher.py",
        "src/placeholder_resolver.py",
    ],
    "docs/specs/FEATURE_SPEC_AI026_persist_generated_tests.md": [
        "src/pipeline_writer.py",
        "src/file_utils.py",
        "src/pipeline_run_service.py",
    ],
    # Scripts README — proximity to scripts it documents
    "scripts/README.md": [
        "scripts/3d map/generate_3d_map.py",
        "scripts/3d map/audit_3d_map.py",
        "scripts/debug/debug_all.py",
        "scripts/debug/debug_pipeline.py",
        "scripts/uat/uat_automationexercise.py",
    ],
}

###############################################################################
# 4. GROUP COLORS
###############################################################################
GROUP_COLORS = {
    "interface": "#FF6B6B",
    "orchestration": "#4ECDC4",
    "intelligence": "#45B7D1",
    "context": "#96CEB4",
    "refinement": "#FFEAA7",
    "output": "#DDA0DD",
    "utility": "#98D8C8",
    "Documentation": "#F7DC6F",
    "Configuration": "#BB8FCE",
    "Other": "#AEB6BF",
}

###############################################################################
# 5. BUILD NODE LIST
###############################################################################
NODES = []
for fpath in sorted(ALL_FILES):
    fpath_clean = fpath
    if fpath_clean.startswith("./"):
        fpath_clean = fpath_clean[2:]

    if fpath.endswith(".md"):
        group = "Documentation"
    elif fpath.endswith(".py"):
        group = LAYER_MAP.get(fpath_clean, "utility")
    elif fpath_clean in (
        ".clinerules",
        ".dockerignore",
        ".gitignore",
        "docker-compose.yml",
        "Dockerfile",
        ".env",
        ".env.example",
        ".python-version",
        ".clineignore",
        "pyproject.toml",
        "pytest.ini",
        "requirements.txt",
        "SECURITY.md",
        "LICENSE",
        "fix.sh",
        "launch_ui.sh",
        "launch_dev.sh",
    ):
        group = "Configuration"
    elif fpath.endswith((".sh", ".yml")):
        group = "Configuration"
    else:
        group = "Other"

    if fpath.endswith(".md"):
        ftype = "doc"
    elif fpath.endswith(".py") and fpath_clean.startswith("tests/"):
        ftype = "test"
    elif fpath.endswith(".py"):
        ftype = "src"
    else:
        ftype = "other"

    try:
        with open(fpath, encoding="utf-8", errors="ignore") as fh:
            size = sum(1 for _ in fh)
    except Exception:
        size = 0

    NODES.append((fpath, group, size, ftype))

###############################################################################
# 6. BUILD LINKS
###############################################################################
LINKS = set()
valid_labels = {n[0] for n in NODES}


def normalize_label(label):
    """Normalize a label to match a node format."""
    if label in valid_labels:
        return label
    if "./" + label in valid_labels:
        return "./" + label
    if label.startswith("./") and label[2:] in valid_labels:
        return label[2:]
    return label


def add_link(source, target, link_type):
    """Add a link only if both source and target exist as nodes."""
    src = normalize_label(source)
    tgt = normalize_label(target)
    if src in valid_labels and tgt in valid_labels:
        LINKS.add((src, tgt, link_type))


def module_to_path(module_name: str) -> str:
    """Convert a Python module name to a file path.
    e.g. 'src.orchestrator' -> 'src/orchestrator.py'
         'cli.config' -> 'cli/config.py'
    """
    return module_name.replace(".", "/") + ".py"


def extract_imports(filepath):
    """Extract import module paths from a Python file using AST parsing."""
    imports = []
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as fh:
            source = fh.read()
        tree = ast.parse(source, filename=filepath)
    except SyntaxError, ValueError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            # from src.module import ...
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                # import src.module
                imports.append(alias.name)
    return imports


# 6a. Dynamic import scanning — scan all .py files for actual imports
for fpath in sorted(ALL_FILES):
    if not fpath.endswith(".py"):
        continue
    raw_path = fpath.lstrip("./")
    imports = extract_imports(fpath)
    for mod in imports:
        target_path = module_to_path(mod)
        add_link(raw_path, target_path, "import")

# 6b. Dynamic test detection — test files importing src/ or cli/ modules
# (already covered by 6a, but also detect by file pattern for edge cases)
# No extra step needed since AST scanning catches all imports.

# 6c. Smart doc links — .md → referenced files
for md_file, refs in DOC_REFS.items():
    for ref in refs:
        ref_clean = ref.lstrip("./")
        if os.path.exists(md_file) or md_file in ALL_FILES:
            add_link(md_file, ref_clean, "references")

# 6d. Proximity links — .md in docs/ → related src/ files
for md_file in sorted(ALL_FILES):
    if not md_file.endswith(".md"):
        continue
    md_clean = md_file.lstrip("./")
    if md_clean.startswith("docs/"):
        for core in ["src/orchestrator.py", "src/test_generator.py", "src/scraper.py", "src/llm_client.py"]:
            add_link(md_file, core, "proximity")
        if md_clean.startswith("docs/plans/"):
            for pipe in [
                "src/pipeline_writer.py",
                "src/pipeline_report_service.py",
                "src/pipeline_run_service.py",
                "src/pipeline_models.py",
            ]:
                add_link(md_file, pipe, "proximity")

###############################################################################
# 7. WRITE nodes.csv
###############################################################################
with open("docs/nodes.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["label", "group", "size", "color"])
    for fpath, group, size, _ftype in NODES:
        w.writerow([fpath, group, size, GROUP_COLORS.get(group, "#AEB6BF")])

###############################################################################
# 8. WRITE links.csv
###############################################################################
with open("docs/links.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["source", "target", "type"])
    for s, t, v in sorted(LINKS):
        w.writerow([s, t, v])

print(f"docs/nodes.csv: {len(NODES)} nodes")
print(f"docs/links.csv: {len(LINKS)} links")

gc = Counter(n[1] for n in NODES)
print("Group breakdown:", dict(gc))
vt = Counter(link[2] for link in LINKS)
print("Link types:", dict(vt))

###############################################################################
# 9. WRITE 3d_map_data.json
###############################################################################
nodes_json = []
for i, (fpath, group, size, ftype) in enumerate(NODES):
    nodes_json.append(
        {
            "id": i,
            "label": fpath,
            "group": group,
            "type": ftype,
            "size": size,
            "color": GROUP_COLORS.get(group, "#AEB6BF"),
        }
    )

label_to_id = {n["label"]: n["id"] for n in nodes_json}

links_json = []
for i, (s, t, v) in enumerate(sorted(LINKS)):
    src_id = label_to_id.get(s)
    tgt_id = label_to_id.get(t)
    if src_id is not None and tgt_id is not None:
        links_json.append(
            {
                "id": i,
                "source": src_id,
                "target": tgt_id,
                "type": v,
            }
        )

map_data = {
    "metadata": {
        "generated_at": "auto",
        "total_nodes": len(nodes_json),
        "total_links": len(links_json),
        "groups": list(GROUP_COLORS.keys()),
    },
    "nodes": nodes_json,
    "links": links_json,
}

with open("scripts/3d_map_data.json", "w", encoding="utf-8") as f:
    json.dump(map_data, f, indent=2)

print(f"scripts/3d_map_data.json: {len(nodes_json)} nodes, {len(links_json)} links written")
