"""A hand fix in the Fix Locator teaches the library, at that site only (j-0248, d-0065).

The automatic self-healing path writes a patch lesson (``learn_from_patch``);
the manual Fix Locator button used to read nothing and write nothing, so the
best correction a customer can give was thrown away. The owner's word
(2026-10-30): "manual fix should write, i think it should be specific to the
site rather than general across multiple sites."

What these tests hold to:

* the write goes through the same route the automatic repair uses (one route,
  not two), and lands on the same record type the learned positives already use;
* the row carries the site hash from ``golden_site_hash(site, base_url)`` - the
  function the seed and the scorer share - and an empty / site-agnostic hash is
  refused rather than written as a general lesson;
* ``RAG_LEARNED=0`` (j-0247's switch) writes nothing;
* only an APPLIED fix counts: an abandoned session, a failed session, a session
  that captured no usable locator, or a patch that failed to apply teach
  nothing;
* what is written is what the scorer reads next time: action, description,
  chosen selector, site hash - so a pattern learned on site A earns nothing on
  site B.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src import rag_learn
from src.locator_repair import CodegenOutcome, apply_fix_from_codegen
from src.rag_bundled import golden_site_hash
from src.rag_learn import learn_from_manual_fix
from src.rag_retriever import RAGRetriever
from src.rag_store import LearnedPattern, RAGStore, RetrievedPattern
from src.ui import ui_run_results
from tests.test_locator_repair_codegen import _FakeST, _install_fake_st, _Rerun
from tests.test_rag_retriever import _FakeEmbedder, _InMemoryBackend

_URL_A = "https://www.saucedemo.com/"
_URL_B = "https://www.automationexercise.com/"

_TEST_SOURCE = """from playwright.sync_api import Page


def test_login(page: Page) -> None:
    page.goto("https://www.saucedemo.com/")
    page.locator("#wrong-user").fill("standard_user")
    page.locator("#wrong-pass").fill("secret_sauce")
"""


@pytest.fixture()
def test_file(tmp_path: Path) -> Path:
    path = tmp_path / "test_login.py"
    path.write_text(_TEST_SOURCE, encoding="utf-8")
    return path


@pytest.fixture()
def store() -> MagicMock:
    fake = MagicMock()
    fake.upsert_pattern.return_value = ("inserted", 1)
    return fake


def _apply(
    test_file: Path,
    store: MagicMock,
    *,
    outcome: CodegenOutcome | None = None,
    original: str = "#wrong-user",
    line: int = 5,
    label: str = "username",
    step_type: str = "fill",
    url: str = _URL_A,
) -> object:
    return apply_fix_from_codegen(
        outcome or CodegenOutcome("captured", locator="#user-name"),
        original_locator=original,
        line_number=line,
        test_file=str(test_file),
        step_label=label,
        step_type=step_type,
        page_url=url,
        store=store,
    )


class TestAnAppliedManualFixWritesOneSiteScopedRow:
    """The good path: the human clicked, the patch landed, one row is learned."""

    def test_an_applied_manual_fix_writes_exactly_one_row_with_that_site_hash(
        self, test_file: Path, store: MagicMock
    ) -> None:
        result = _apply(test_file, store)

        assert result.applied is True  # type: ignore[attr-defined]
        assert store.upsert_pattern.call_count == 1
        pattern: LearnedPattern = store.upsert_pattern.call_args.args[0]
        assert pattern.action_type == "FILL"
        assert pattern.description == "username"
        assert pattern.locator == "#user-name"
        # The same function the seed and the scorer use (j-0248).
        assert pattern.site_hash == golden_site_hash("", _URL_A)
        assert pattern.site_hash == golden_site_hash("saucedemo", _URL_A)
        assert pattern.source == "manual_fix"
        # The human's choice is on disk, and the old locator is gone.
        assert "#user-name" in test_file.read_text(encoding="utf-8")
        assert "#wrong-user" not in test_file.read_text(encoding="utf-8")

    def test_a_click_becomes_a_click_lesson(self, test_file: Path, store: MagicMock) -> None:
        """The step type decides the action - the scorer matches on it."""
        result = _apply(
            test_file,
            store,
            outcome=CodegenOutcome("captured", locator="#login-button"),
            original="#wrong-pass",
            line=6,
            label="Login",
            step_type="click",
            url=_URL_A + "inventory.html",
        )

        assert result.applied is True  # type: ignore[attr-defined]
        pattern: LearnedPattern = store.upsert_pattern.call_args.args[0]
        assert pattern.action_type == "CLICK"
        assert pattern.description == "Login"
        assert pattern.site_hash == golden_site_hash("", _URL_A)

    def test_a_fix_on_site_a_is_not_retrieved_for_a_story_on_site_b(self, test_file: Path, store: MagicMock) -> None:
        _apply(test_file, store)
        pattern: LearnedPattern = store.upsert_pattern.call_args.args[0]
        retrieved = [
            RetrievedPattern(
                description=pattern.description,
                selector=pattern.locator,
                action_type=pattern.action_type,
                confidence=pattern.confidence,
                source="learned",
                site_hash=pattern.site_hash,
            )
        ]
        retriever = RAGRetriever(None)

        assert retriever.scoring_bonus_for({"selector": pattern.locator}, retrieved, site_hash=pattern.site_hash) > 0
        assert (
            retriever.scoring_bonus_for(
                {"selector": pattern.locator}, retrieved, site_hash=golden_site_hash("", _URL_B)
            )
            == 0
        )


class TestOnlyAnAppliedFixCounts:
    """Nothing about a session that did not land may teach the library anything."""

    @pytest.mark.parametrize(
        ("outcome", "reason_part"),
        [
            (CodegenOutcome("no_click", reason="the browser was closed without recording an action"), "closed"),
            (CodegenOutcome("failed", reason="codegen timed out after 120s"), "timed out"),
            (CodegenOutcome("cannot_replay", reason="the saved state is missing"), "missing"),
            (CodegenOutcome("no_click", reason="the recording contains no locator"), "no locator"),
        ],
    )
    def test_an_abandoned_or_failed_session_writes_nothing(
        self, test_file: Path, store: MagicMock, outcome: CodegenOutcome, reason_part: str
    ) -> None:
        before = test_file.read_text(encoding="utf-8")

        result = _apply(test_file, store, outcome=outcome)

        assert result.applied is False  # type: ignore[attr-defined]
        assert reason_part in result.reason  # type: ignore[attr-defined]
        store.upsert_pattern.assert_not_called()
        assert test_file.read_text(encoding="utf-8") == before

    def test_a_patch_that_failed_to_apply_writes_nothing(self, test_file: Path, store: MagicMock) -> None:
        before = test_file.read_text(encoding="utf-8")

        result = _apply(test_file, store, original="#not-in-this-file", line=5)

        assert result.applied is False  # type: ignore[attr-defined]
        assert "could not patch" in result.reason  # type: ignore[attr-defined]
        store.upsert_pattern.assert_not_called()
        assert test_file.read_text(encoding="utf-8") == before

    def test_no_usable_description_writes_nothing(self, test_file: Path, store: MagicMock) -> None:
        """A lesson with no description would match everything - that is the general lesson the owner forbade."""
        result = _apply(test_file, store, label="")

        assert result.applied is True  # type: ignore[attr-defined]  # the fix is still applied
        store.upsert_pattern.assert_not_called()
        assert "description" in result.learned.get("reason", "")  # type: ignore[attr-defined]


class TestLearningSwitchedOff:
    """j-0247's RAG_LEARNED switch: off means write nothing, and say so."""

    def test_learning_switched_off_writes_nothing(
        self, test_file: Path, store: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RAG_LEARNED", "0")

        result = _apply(test_file, store)

        assert result.applied is True  # type: ignore[attr-defined]  # the human's fix still lands
        store.upsert_pattern.assert_not_called()
        assert "off" in result.learned.get("reason", "")  # type: ignore[attr-defined]

    def test_the_switch_module_is_used_when_it_is_present(
        self, test_file: Path, store: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """j-0247 is not merged yet: when ``src.rag_switches`` lands, it is the authority."""
        import sys
        import types

        fake = types.ModuleType("src.rag_switches")
        fake.PART_LEARNED = "learned"  # type: ignore[attr-defined]
        fake.part_enabled = lambda part: False  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "src.rag_switches", fake)

        result = _apply(test_file, store)

        store.upsert_pattern.assert_not_called()
        assert "off" in result.learned.get("reason", "")  # type: ignore[attr-defined]


class TestTheSiteHashIsNeverEmpty:
    """An agnostic lesson is forbidden on this path (the owner's instruction)."""

    def test_an_empty_or_agnostic_site_hash_is_refused(self, test_file: Path, store: MagicMock) -> None:
        result = _apply(test_file, store, url="")

        assert result.applied is True  # type: ignore[attr-defined]  # the human's fix still lands
        store.upsert_pattern.assert_not_called()
        assert "site" in result.learned.get("reason", "")  # type: ignore[attr-defined]

    def test_an_unparseable_url_is_refused(self, test_file: Path, store: MagicMock) -> None:
        result = _apply(test_file, store, url="not a url at all")

        store.upsert_pattern.assert_not_called()
        assert "site" in result.learned.get("reason", "")  # type: ignore[attr-defined]

    def test_the_row_never_carries_an_empty_site_hash(self, test_file: Path, store: MagicMock) -> None:
        _apply(test_file, store)
        pattern: LearnedPattern = store.upsert_pattern.call_args.args[0]
        assert pattern.site_hash
        assert pattern.site_hash == golden_site_hash("", _URL_A)


# ---------------------------------------------------------------------------
# The seams the review found untested (t-1128, j-0248 step 2)
# ---------------------------------------------------------------------------


def _open_repair_panel(monkeypatch: pytest.MonkeyPatch, test_file: Path, *, locator: str, url: str = _URL_A) -> _FakeST:
    """Drive the real Streamlit repair-session function with a fake UI.

    Only the codegen browser is stubbed: everything downstream - the patch, the
    learning call, the session-state message the customer reads - is the real
    code path.
    """
    from types import SimpleNamespace

    fake_st = _FakeST()
    _install_fake_st(monkeypatch, fake_st)
    fake_st.session_state.update(
        {
            "repair_target": SimpleNamespace(failure_url=url, raw_locator="#wrong-user", line_number=5),
            "repair_failure_url": url,
            "repair_test_file": str(test_file),
            "repair_line_number": 5,
            "repair_step_label": "username",
            "repair_step_type": "fill",
        }
    )
    monkeypatch.setattr(
        ui_run_results, "run_codegen_session", lambda *a, **k: CodegenOutcome("captured", locator=locator)
    )
    return fake_st


class TestTheUiSeamActuallyLearns:
    """The panel must call the learn route with the patch it really applied."""

    def test_the_ui_learns_the_chosen_locator_for_this_site(
        self, monkeypatch: pytest.MonkeyPatch, test_file: Path
    ) -> None:
        fake_st = _open_repair_panel(monkeypatch, test_file, locator="#user-name")
        calls: list[dict[str, object]] = []

        def _record(**kw: object) -> dict[str, object]:
            calls.append(kw)
            return {"inserted": 1, "exists": 0, "reason": ""}

        monkeypatch.setattr(rag_learn, "record_learned_locator", _record)

        with pytest.raises(_Rerun):
            ui_run_results._render_repair_browser_session()  # noqa: SLF001

        # The row is keyed on the human's click, not on a default or a fallback.
        assert len(calls) == 1
        assert calls[0]["locator"] == "#user-name"
        assert calls[0]["action_type"] == "FILL"
        assert calls[0]["description"] == "username"
        assert calls[0]["site_digest"] == golden_site_hash("", _URL_A)
        # And it is the same selector that went into the file.
        assert "#user-name" in test_file.read_text(encoding="utf-8")
        assert fake_st.session_state["repair_status"] == "patched"
        assert "Learned for this site only" in fake_st.session_state["repair_message"]

    def test_a_learning_failure_does_not_break_the_repair(
        self, monkeypatch: pytest.MonkeyPatch, test_file: Path
    ) -> None:
        fake_st = _open_repair_panel(monkeypatch, test_file, locator="#user-name")

        def _boom(**_kwargs: object) -> dict[str, object]:
            raise RuntimeError("store on fire")

        monkeypatch.setattr(rag_learn, "record_learned_locator", _boom)

        with pytest.raises(_Rerun):
            ui_run_results._render_repair_browser_session()  # noqa: SLF001

        # The human's fix stands, and the learning failure is reported, not raised.
        assert fake_st.session_state["repair_status"] == "patched"
        assert "#user-name" in test_file.read_text(encoding="utf-8")
        message = fake_st.session_state["repair_message"]
        assert "Learning skipped" in message
        assert "store on fire" in message


class TestTheRetrievalPathKeepsTheLessonOnItsSite:
    """Site scoping, proved through a real store and the real retriever."""

    def test_a_fix_on_site_a_is_not_retrieved_for_site_b(self) -> None:
        store = RAGStore(_InMemoryBackend(dimension=16), _FakeEmbedder(dimension=16))
        learned = learn_from_manual_fix(
            step_type="fill",
            description="username",
            locator="#user-name",
            base_url=_URL_A,
            store=store,
        )
        assert learned["inserted"] == 1

        retriever = RAGRetriever(store)
        patterns = retriever.retrieve("username", action_type="FILL")
        assert patterns, "the real retrieval path did not return the learned row"
        assert any(p.source == "learned" for p in patterns)

        site_a = golden_site_hash("", _URL_A)
        site_b = golden_site_hash("", _URL_B)
        assert retriever.scoring_bonus_for({"selector": "#user-name"}, patterns, site_hash=site_a) > 0
        assert retriever.scoring_bonus_for({"selector": "#user-name"}, patterns, site_hash=site_b) == 0
