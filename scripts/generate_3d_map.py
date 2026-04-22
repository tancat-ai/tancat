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
    "cli/story_analyzer.py": "interface",
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
    # Context
    "src/scraper.py": "context",
    "src/stateful_scraper.py": "context",
    "src/page_context_scraper.py": "context",
    "src/semantic_candidate_ranker.py": "context",
    # Refinement
    "src/placeholder_resolver.py": "refinement",
    "src/page_object_builder.py": "refinement",
    "src/code_validator.py": "refinement",
    # Output
    "src/report_utils.py": "output",
    "src/evidence_tracker.py": "output",
    # Utility
    "src/file_utils.py": "utility",
    "src/run_utils.py": "utility",
    "src/pytest_output_parser.py": "utility",
    "src/coverage_utils.py": "utility",
    "src/gantt_utils.py": "utility",
    "src/heatmap_utils.py": "utility",
    "src/__init__.py": "utility",
}

###############################################################################
# 2. ALL PROJECT FILES — scan for real files
###############################################################################
ALL_FILES = set()
# Directories to completely skip during scan
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
}
for root, dirs, files in os.walk("."):
    # Filter out skip dirs (modify in-place for os.walk)
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
    for f in files:
        full = os.path.join(root, f)
        rel = full.replace("\\", "/")
        # skip files starting with . (hidden files) except specific ones added later
        if f.startswith("."):
            continue
        # skip binary / generated artifacts
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

# Explicitly add root-level config files we want (with ./ prefix for consistency)
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

# Also explicitly add cli/, src/, tests/ files that os.walk might miss (with ./ prefix)
for subdir in ["cli", "src", "tests", "docs", "docs/plans", "scripts"]:
    if os.path.isdir(subdir):
        for f in os.listdir(subdir):
            full = "./" + subdir + "/" + f
            if f.endswith(".py") or f.endswith(".md"):
                ALL_FILES.add(full)
        # nested dirs
        for root2, _dirs2, files2 in os.walk(subdir):
            for f in files2:
                if f.endswith(".py") or f.endswith(".md"):
                    full = "./" + os.path.join(root2, f).replace("\\", "/")
                    ALL_FILES.add(full)

# Filter out unwanted files — skip generated artifacts, temp files, and external submodules
ALL_FILES = {f for f in ALL_FILES if not f.endswith((".xml", ".lock"))}
ALL_FILES = {f for f in ALL_FILES if "mock_insurance_site" not in f and "cart.html" not in f}
# Skip generated/temp output files
ALL_FILES = {f for f in ALL_FILES if not f.endswith((".txt", ".log", ".err")) or f in (".env.example",)}
# Skip the map generation artifacts themselves (with or without ./ prefix)
ALL_FILES = {
    f
    for f in ALL_FILES
    if f not in ("3d_map_data.json", "nodes.csv", "links.csv")
    and f not in ("./3d_map_data.json", "./nodes.csv", "./links.csv")
    and f not in ("docs/3d_map_data.json", "docs/nodes.csv", "docs/links.csv")
}

###############################################################################
# 3. SMART DOC LINKS — filename references extracted from .md files
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
        "PROJECT_KNOWLEDGE.md",
        "FEATURE_SPEC_multi_provider_llm.md",
        "pyproject.toml",
        ".pre-commit-config.yaml",
        "pytest.ini",
        ".env",
        ".env.example",
        ".github/workflows/ci.yml",
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
    "docs/PROJECT_KNOWLEDGE.md": [
        "streamlit_app.py",
        "src/test_generator.py",
        "src/llm_client.py",
        "src/orchestrator.py",
        "src/scraper.py",
        "src/placeholder_resolver.py",
        "AGENTS.md",
        ".clinerules",
        "BACKLOG.md",
        "ARCHITECTURE.md",
    ],
    "docs/PROMPT_EXAMPLES.md": [
        "src/prompt_utils.py",
        "src/test_generator.py",
        "src/skeleton_parser.py",
        "src/placeholder_resolver.py",
        "src/orchestrator.py",
    ],
    "README.md": [
        "streamlit_app.py",
        "cli/main.py",
        "src/test_generator.py",
        "src/llm_client.py",
        "src/orchestrator.py",
        "src/scraper.py",
        "src/placeholder_resolver.py",
        "src/skeleton_parser.py",
        "src/page_object_builder.py",
        "src/pipeline_writer.py",
        "src/pipeline_report_service.py",
        "launch_ui.sh",
        "launch_dev.sh",
        "pyproject.toml",
        "pytest.ini",
        ".env",
        ".env.example",
    ],
    "SECURITY.md": [
        ".env",
        ".gitignore",
        "requirements.txt",
        "pyproject.toml",
    ],
    "docs/walkthrough.md": [
        "streamlit_app.py",
        "src/test_generator.py",
        "src/llm_client.py",
        "src/orchestrator.py",
        "src/scraper.py",
        "src/placeholder_resolver.py",
        "src/skeleton_parser.py",
        "src/page_object_builder.py",
    ],
    "docs/implementation_plan.md": [
        "src/test_generator.py",
        "src/llm_client.py",
        "src/orchestrator.py",
        "src/scraper.py",
        "src/placeholder_resolver.py",
        "src/skeleton_parser.py",
        "src/page_object_builder.py",
        "src/pipeline_writer.py",
        "src/pipeline_report_service.py",
        "streamlit_app.py",
    ],
    # Feature specs
    "docs/FEATURE_SPEC_AI009_phase_b.md": [
        "src/page_context_scraper.py",
        "streamlit_app.py",
        "src/llm_client.py",
        "src/test_generator.py",
        "main.py",
        "fix.sh",
    ],
    "docs/specs/FEATURE_SPEC_intelligent_scraping_pipeline.md": [
        "src/page_context_scraper.py",
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
        "src/page_context_scraper.py",
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
    # Docs
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
    "docs/session_04_final_polish.md": [
        "src/orchestrator.py",
    ],
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
        "tests/test_page_context_scraper.py",
        "tests/uat_pipeline_test.py",
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
        "src/page_context_scraper.py",
    ],
    # Docs/plans
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
        ".gitignore",
    ],
    "docs/plans/AI-019_plan.md": [
        "src/prompt_utils.py",
        "src/llm_client.py",
        "src/test_generator.py",
    ],
    "docs/plans/AI-020_plan.md": [
        "src/report_utils.py",
        "streamlit_app.py",
    ],
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
    "docs/plans/AI019_section2_prompts.md": [
        "src/prompt_utils.py",
    ],
    "docs/plans/AI019_section3_validation.md": [
        "src/test_generator.py",
        "src/orchestrator.py",
    ],
    "docs/plans/FEATURE_COMPLETION_CHECKLIST.md": [
        "docs/session_02_placeholder_resolver.md",
        "docs/session_03_orchestrator.md",
        "docs/session_04_final_polish.md",
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
        "docs/session_05_pipeline_rebuild_plan.md",
        "src/test_plan.py",
        "streamlit_app.py",
        "src/page_object_builder.py",
        "src/placeholder_resolver.py",
    ],
    "docs/plans/PK_CLEANUP_section1_audit.md": [
        "docs/PROJECT_KNOWLEDGE.md",
        "AGENTS.md",
        ".clinerules",
    ],
}

###############################################################################
# 4. GROUP COLORS — palette for all groups
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
# 5. BUILD NODE LIST — all real files
###############################################################################
NODES = []
for fpath in sorted(ALL_FILES):
    # strip ./ prefix for lookups
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

    # determine type
    if fpath.endswith(".md"):
        ftype = "doc"
    elif fpath.endswith(".py") and fpath_clean.startswith("tests/"):
        ftype = "test"
    elif fpath.endswith(".py"):
        ftype = "src"
    else:
        ftype = "other"

    # count lines
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

# 5a. Import links (from previous analysis)
IMPORT_LINKS = [
    ("streamlit_app.py", "src/orchestrator.py"),
    ("streamlit_app.py", "src/code_validator.py"),
    ("streamlit_app.py", "src/coverage_utils.py"),
    ("streamlit_app.py", "src/gantt_utils.py"),
    ("streamlit_app.py", "src/heatmap_utils.py"),
    ("streamlit_app.py", "src/llm_client.py"),
    ("streamlit_app.py", "src/pipeline_report_service.py"),
    ("streamlit_app.py", "src/pipeline_run_service.py"),
    ("streamlit_app.py", "src/pipeline_writer.py"),
    ("streamlit_app.py", "src/pytest_output_parser.py"),
    ("streamlit_app.py", "src/report_utils.py"),
    ("streamlit_app.py", "src/spec_analyzer.py"),
    ("streamlit_app.py", "src/test_generator.py"),
    ("streamlit_app.py", "src/test_plan.py"),
    ("streamlit_app.py", "src/user_story_parser.py"),
    ("cli/main.py", "cli/config.py"),
    ("cli/main.py", "cli/input_parser.py"),
    ("cli/main.py", "cli/story_analyzer.py"),
    ("cli/main.py", "cli/test_orchestrator.py"),
    ("cli/main.py", "cli/evidence_generator.py"),
    ("cli/main.py", "cli/report_generator.py"),
    ("cli/input_parser.py", "cli/config.py"),
    ("cli/story_analyzer.py", "cli/config.py"),
    ("cli/story_analyzer.py", "cli/input_parser.py"),
    ("cli/test_orchestrator.py", "cli/config.py"),
    ("cli/test_orchestrator.py", "cli/story_analyzer.py"),
    ("cli/test_orchestrator.py", "src/page_context_scraper.py"),
    ("cli/test_orchestrator.py", "src/test_generator.py"),
    ("cli/evidence_generator.py", "cli/config.py"),
    ("cli/evidence_generator.py", "cli/story_analyzer.py"),
    ("cli/report_generator.py", "cli/config.py"),
    ("cli/report_generator.py", "cli/story_analyzer.py"),
    ("src/orchestrator.py", "src/page_object_builder.py"),
    ("src/orchestrator.py", "src/pipeline_models.py"),
    ("src/orchestrator.py", "src/placeholder_resolver.py"),
    ("src/orchestrator.py", "src/scraper.py"),
    ("src/orchestrator.py", "src/semantic_candidate_ranker.py"),
    ("src/orchestrator.py", "src/skeleton_parser.py"),
    ("src/orchestrator.py", "src/stateful_scraper.py"),
    ("src/orchestrator.py", "src/test_generator.py"),
    ("src/pipeline_run_service.py", "src/pytest_output_parser.py"),
    ("src/pipeline_run_service.py", "src/run_utils.py"),
    ("src/pipeline_report_service.py", "src/coverage_utils.py"),
    ("src/pipeline_report_service.py", "src/pytest_output_parser.py"),
    ("src/pipeline_report_service.py", "src/report_utils.py"),
    ("src/spec_analyzer.py", "src/llm_client.py"),
    ("src/test_generator.py", "src/code_validator.py"),
    ("src/test_generator.py", "src/file_utils.py"),
    ("src/test_generator.py", "src/llm_client.py"),
    ("src/test_generator.py", "src/prompt_utils.py"),
    ("src/test_generator.py", "src/skeleton_parser.py"),
    ("src/llm_client.py", "src/llm_providers/__init__.py"),
    ("src/skeleton_parser.py", "src/pipeline_models.py"),
    ("src/stateful_scraper.py", "src/scraper.py"),
    ("src/page_object_builder.py", "src/file_utils.py"),
    ("src/page_object_builder.py", "src/pipeline_models.py"),
    ("src/pipeline_writer.py", "src/code_validator.py"),
    ("src/pipeline_writer.py", "src/file_utils.py"),
    ("src/pipeline_writer.py", "src/pipeline_models.py"),
    ("src/pipeline_writer.py", "src/orchestrator.py"),
    ("src/report_utils.py", "src/pytest_output_parser.py"),
    ("src/test_plan.py", "src/spec_analyzer.py"),
    ("src/file_utils.py", "src/code_validator.py"),
]
for s, t in IMPORT_LINKS:
    LINKS.add((s, t, "import"))

# 5b. Test → source links
TEST_LINKS = [
    ("tests/test_code_validator.py", "src/code_validator.py"),
    ("tests/test_coverage_utils.py", "src/coverage_utils.py"),
    ("tests/test_evidence_tracker.py", "src/evidence_tracker.py"),
    ("tests/test_gantt_utils.py", "src/gantt_utils.py"),
    ("tests/test_heatmap_utils.py", "src/heatmap_utils.py"),
    ("tests/test_llm_client.py", "src/llm_client.py"),
    ("tests/test_llm_client.py", "src/llm_providers/__init__.py"),
    ("tests/test_llm_errors.py", "src/llm_errors.py"),
    ("tests/test_normalise_code_newlines.py", "src/file_utils.py"),
    ("tests/test_orchestrator.py", "src/orchestrator.py"),
    ("tests/test_orchestrator.py", "src/test_generator.py"),
    ("tests/test_orchestrator_dynamic_scrape.py", "src/orchestrator.py"),
    ("tests/test_orchestrator_dynamic_scrape.py", "src/test_generator.py"),
    ("tests/test_page_context_scraper.py", "src/page_context_scraper.py"),
    ("tests/test_page_object_builder.py", "src/page_object_builder.py"),
    ("tests/test_page_object_builder.py", "src/pipeline_models.py"),
    ("tests/test_pipeline_models.py", "src/pipeline_models.py"),
    ("tests/test_pipeline_package_integration.py", "src/orchestrator.py"),
    ("tests/test_pipeline_package_integration.py", "src/pipeline_run_service.py"),
    ("tests/test_pipeline_package_integration.py", "src/pipeline_writer.py"),
    ("tests/test_pipeline_report_service.py", "src/pipeline_report_service.py"),
    ("tests/test_pipeline_report_service.py", "src/pytest_output_parser.py"),
    ("tests/test_pipeline_run_service.py", "src/pipeline_run_service.py"),
    ("tests/test_pipeline_run_service.py", "src/pytest_output_parser.py"),
    ("tests/test_pipeline_writer.py", "src/orchestrator.py"),
    ("tests/test_pipeline_writer.py", "src/pipeline_models.py"),
    ("tests/test_pipeline_writer.py", "src/pipeline_writer.py"),
    ("tests/test_placeholder_resolution_guardrails.py", "src/skeleton_parser.py"),
    ("tests/test_placeholder_resolution_guardrails.py", "src/orchestrator.py"),
    ("tests/test_placeholder_resolver.py", "src/placeholder_resolver.py"),
    ("tests/test_prompt_utils.py", "src/prompt_utils.py"),
    ("tests/test_pytest_output_parser.py", "src/pytest_output_parser.py"),
    ("tests/test_report_utils.py", "src/report_utils.py"),
    ("tests/test_report_utils.py", "src/coverage_utils.py"),
    ("tests/test_report_utils.py", "src/pytest_output_parser.py"),
    ("tests/test_run_utils.py", "src/run_utils.py"),
    ("tests/test_scraper.py", "src/scraper.py"),
    ("tests/test_semantic_candidate_ranker.py", "src/semantic_candidate_ranker.py"),
    ("tests/test_skeleton_parser.py", "src/skeleton_parser.py"),
    ("tests/test_skeleton_parser.py", "src/pipeline_models.py"),
    ("tests/test_spec_analyzer.py", "src/spec_analyzer.py"),
    ("tests/test_stateful_scrape_switch.py", "src/orchestrator.py"),
    ("tests/test_stateful_scrape_switch.py", "src/test_generator.py"),
    ("tests/test_stateful_scraper.py", "src/stateful_scraper.py"),
    ("tests/test_test_generator.py", "src/test_generator.py"),
    ("tests/test_test_plan.py", "src/test_plan.py"),
    ("tests/test_test_plan.py", "src/spec_analyzer.py"),
    ("tests/test_user_story_parser.py", "src/user_story_parser.py"),
    ("tests/test_cli_test_orchestrator.py", "cli/test_orchestrator.py"),
    ("tests/uat_pipeline_test.py", "src/orchestrator.py"),
    ("tests/uat_pipeline_test.py", "src/llm_client.py"),
    ("tests/uat_pipeline_test.py", "src/test_generator.py"),
]
for s, t in TEST_LINKS:
    LINKS.add((s, t, "tests"))

# 5c. Smart doc links — .md → referenced files
for md_file, refs in DOC_REFS.items():
    for ref in refs:
        ref = ref.lstrip("./")
        if os.path.exists(md_file) or md_file in ALL_FILES:
            LINKS.add((md_file, ref, "references"))

# 5d. Proximity links — .md in docs/ → related src/ files
for md_file in sorted(ALL_FILES):
    if not md_file.endswith(".md"):
        continue
    md_clean = md_file.lstrip("./")
    if md_clean.startswith("docs/"):
        for core in ["src/orchestrator.py", "src/test_generator.py", "src/scraper.py", "src/llm_client.py"]:
            LINKS.add((md_file, "./" + core, "proximity"))
        if md_clean.startswith("docs/plans/"):
            for pipe in [
                "src/pipeline_writer.py",
                "src/pipeline_report_service.py",
                "src/pipeline_run_service.py",
                "src/pipeline_models.py",
            ]:
                LINKS.add((md_file, "./" + pipe, "proximity"))

###############################################################################
# 7. WRITE nodes.csv (Cosmograph format: label = id)
###############################################################################
with open("docs/nodes.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["label", "group", "size", "color"])
    for fpath, group, size, _ftype in NODES:
        w.writerow([fpath, group, size, GROUP_COLORS.get(group, "#AEB6BF")])

###############################################################################
# 8. WRITE links.csv (Cosmograph format: source/target = labels)
###############################################################################
# Build a set of valid node labels for normalization
valid_labels = {n[0] for n in NODES}


def normalize_label(label):
    """Normalize a label to match node format (with ./ prefix if needed)."""
    # If already a valid label, return as-is
    if label in valid_labels:
        return label
    # Try adding ./ prefix
    if "./" + label in valid_labels:
        return "./" + label
    # Try without ./ prefix (already normalized)
    if label.startswith("./") and label[2:] in valid_labels:
        return label[2:]
    # Return as-is (might be a valid label without ./)
    return label


with open("docs/links.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["source", "target", "type"])
    for s, t, v in sorted(LINKS):
        w.writerow([normalize_label(s), normalize_label(t), v])

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

# Build label→id lookup for link resolution
label_to_id = {n["label"]: n["id"] for n in nodes_json}

links_json = []
for i, (s, t, v) in enumerate(sorted(LINKS)):
    src_label = normalize_label(s)
    tgt_label = normalize_label(t)
    src_id = label_to_id.get(src_label)
    tgt_id = label_to_id.get(tgt_label)
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
