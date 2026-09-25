"""B-095 — the eval harness must import THIS checkout's ``src/``, not another one.

Found 2026-09-24 (Session 10/11): running ``python scripts/eval/eval_harness.py``
from a worktree left ``sys.path[0]`` at ``scripts/eval``, so the deferred
``from src...`` imports resolved through the site-packages editable install back
to the MAIN checkout. A worktree fix was invisible to the harness unless
``PYTHONPATH`` was exported.

The proof builds a throwaway "checkout" with a sentinel ``src/``, runs the real
harness/resolver script body against it with a decoy checkout on ``PYTHONPATH``,
and checks which ``src/`` won. The second leg strips the guard from the copied
script and asserts the decoy wins — i.e. the test genuinely detects the bug it
guards, instead of passing unconditionally.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"

_GUARD_LINE = "    sys.path.insert(0, str(_PROJECT_ROOT))"

# Both entry points that carry the B-095 guard.
_ENTRY_POINTS = ("eval_harness.py", "eval_resolver.py")


def _make_checkout(root: Path, marker: str) -> Path:
    """Create a minimal checkout whose ``src/`` is identifiable by ``marker``."""
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "__init__.py").write_text(f"MARKER = {marker!r}\n", encoding="utf-8")
    return root


def _copy_entry_points(checkout: Path, *, strip_guard: bool) -> None:
    """Copy the real eval entry points into ``checkout/scripts/eval``.

    ``strip_guard=True`` removes the B-095 sys.path insert so the control leg can
    prove the probe would have detected the original bug.
    """
    dest = checkout / "scripts" / "eval"
    dest.mkdir(parents=True, exist_ok=True)
    for name in _ENTRY_POINTS:
        source = (_EVAL_DIR / name).read_text(encoding="utf-8")
        if strip_guard:
            assert _GUARD_LINE in source, f"guard line not found in {name}"
            source = source.replace(_GUARD_LINE, "    pass")
        (dest / name).write_text(source, encoding="utf-8")


def _import_src_file(
    script: Path,
    checkout: Path,
    decoy: Path,
) -> str:
    """Run ``script`` the way ``python script.py`` would, then report ``src.__file__``.

    ``sys.path[0]`` is set to the script's own directory (the original defect),
    the decoy checkout is exposed through ``PYTHONPATH`` (the "other" checkout),
    and the module body is exec'd with ``__name__ != "__main__"`` so the CLI does
    not run.
    """
    probe = textwrap.dedent(
        f"""
        import pathlib
        import sys

        sys.path.insert(0, {str(script.parent)!r})
        exec(
            compile(
                open({str(script)!r}, encoding="utf-8").read(),
                {str(script)!r},
                "exec",
            ),
            {{"__name__": "b095_probe", "__file__": {str(script)!r}}},
        )
        import src

        print("SRC=" + (src.__file__ or ""))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(decoy)},
    )
    if result.returncode != 0:
        return f"IMPORT_FAILED: {result.stderr.strip().splitlines()[-1] if result.stderr else ''}"
    for line in result.stdout.splitlines():
        if line.startswith("SRC="):
            return line[len("SRC=") :]
    return ""


def _assert_checkout_wins(tmp_path: Path, *, strip_guard: bool) -> None:
    checkout = _make_checkout(tmp_path / "checkout", "checkout-local")
    decoy = _make_checkout(tmp_path / "decoy", "decoy-other")
    _copy_entry_points(checkout, strip_guard=strip_guard)

    for name in _ENTRY_POINTS:
        script = checkout / "scripts" / "eval" / name
        src_file = _import_src_file(script, checkout, decoy)
        checkout_prefix = str(checkout)
        if strip_guard:
            assert not src_file.startswith(checkout_prefix), (
                f"{name}: guard was stripped but the checkout src still won: {src_file!r}"
            )
        else:
            assert src_file.startswith(checkout_prefix), (
                f"{name}: imported src from outside its own checkout: {src_file!r}"
            )


def test_eval_entry_points_use_their_own_checkout_src(tmp_path: Path) -> None:
    """With the guard, both entry points import the checkout they run from."""
    _assert_checkout_wins(tmp_path, strip_guard=False)


def test_probe_detects_a_missing_guard(tmp_path: Path) -> None:
    """Control: without the guard the probe resolves the decoy — so the test has teeth."""
    _assert_checkout_wins(tmp_path, strip_guard=True)
