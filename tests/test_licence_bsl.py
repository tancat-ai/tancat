"""TanCat's own licence is the canonical BSL 1.1, and no surface still says otherwise.

The owner decided on 2026-11-11 to move from Apache-2.0 to the Business Source
License 1.1: the source stays free to read, modify and use - production use for
any internal purpose is allowed - and only offering it as a competing product or
service is restricted. Each version converts to Apache-2.0 on its Change Date,
four years after it is first publicly distributed.

These tests pin three things:

* the LICENSE is the canonical MariaDB text with only its parameter block
  filled - the prose (Terms, Covenants, Notice) is untouched, and no placeholder
  survives;
* nothing that speaks about TanCat's own code calls it Apache-2.0 or open source
  any more - including the pages a customer reads;
* the third-party statements are unchanged: a dependency's Apache-2.0, OFL or
  Artistic election is not TanCat's licence and must not be edited by this rule.

The free-tier promise survives the change and is asserted here too: the tier is
still free, still usable, still readable and modifiable - it is source-available,
not OSI open source, until the Change Date.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LICENSE = ROOT / "LICENSE"
NOTICE = ROOT / "NOTICE"
README = ROOT / "README.md"

#: The record's SPDX id for the product, compared with pyproject (t-1397).
PRODUCT_SPDX = "BUSL-1.1"

#: Each parameter's ENTIRE value. Equality, not substring: a swap must fail.
EXPECTED_PARAMETERS = {
    "Licensor": (
        "Cat Tan Operations Ltd, a company registered in England and Wales (company number 17576111), "
        "whose registered office is at Flat 2, Bournehall, 2 Bourne Close, Bournemouth, BH2 6BW"
    ),
    # t-1407 (j-0299): the author assigned the copyright to the company, so the
    # Licensed Work names the company as holder. The Licensor line already did.
    "Licensed Work": "TanCat version 0.1.0 or later. The Licensed Work is (c) 2026 Cat Tan Operations Ltd.",
    "Change Date": "The fourth anniversary of the date the Licensed Work is first publicly distributed.",
    "Change License": "Apache License, Version 2.0",
}

#: Sentences from the fetched canonical text. If one of these is ever reworded,
#: the licence is no longer the canonical BSL 1.1 and the test should fail.
CANONICAL_PROSE = (
    "Business Source License 1.1",
    "The Licensor hereby grants you the right to copy, modify, create derivative",
    "Effective on the Change Date, or the fourth anniversary of the first publicly",
    "Covenants of Licensor",
    "To specify as the Change License the GPL Version 2.0 or any later version,",
    "Not to modify this License in any other way.",
    "The Business Source License (this document, or the \u201cLicense\u201d) is not an Open",
    "License text copyright (c) 2024 MariaDB plc, All Rights Reserved.",
)

#: Files that speak about TanCat itself to a reader or a customer.
OWN_SURFACES = (
    "README.md",
    "NOTICE",
    "landing/index.html",
    "landing/terms.html",
    "landing/install.html",
    "docs/implementation/tancat-pro-install-and-licence.html",
    # t-1395: these three spoke about the product too - the first two are the
    # licence record a store reviewer reads, and the third ships inside the wheel.
    "docs/licenses/DEPENDENCIES.md",
    "docs/licenses/DOCUMENT_READER_LICENSES.md",
    "src/data/ocr/README.md",
    # t-1399: the site footer on every page - the reviewer found it live.
    "mkdocs.yml",
)

#: Surfaces where the word "Apache" may only appear in a sentence about the Change
#: Licence. The dependency-record files are excluded: they legitimately name
#: dependencies whose own licence is Apache-2.0.
CHANGE_LICENCE_SURFACES = (
    "README.md",
    "NOTICE",
    "landing/index.html",
    "landing/terms.html",
    "landing/install.html",
    "docs/implementation/tancat-pro-install-and-licence.html",
)

#: One of these must be in a line that mentions Apache on those surfaces.
APACHE_CONTEXT = ("converts to", "Change License", "four years", "Apache License, Version 2.0")


def _license_text() -> str:
    return LICENSE.read_text(encoding="utf-8")


class TestTheLicenceText:
    def test_it_is_the_canonical_bsl_1_1(self) -> None:
        """Phrase-based, so a reflow cannot fail it and a reword cannot pass it."""
        flat = _flat(_license_text())
        missing = [phrase for phrase in CANONICAL_PROSE if _flat(phrase) not in flat]
        assert missing == [], f"LICENSE is missing canonical text: {missing}"

    def _value_of(self, label: str) -> str:
        """The label's own value: its line plus its indented continuation lines."""
        lines = _license_text().splitlines()
        start = next((i for i, line in enumerate(lines) if line.startswith(f"{label}:")), None)
        assert start is not None, f"{label}: missing from the parameter block"
        collected = [lines[start].split(":", 1)[1].strip()]
        for line in lines[start + 1 :]:
            if not line.strip() or not line.startswith(" " * 22):
                break
            collected.append(line.strip())
        return " ".join(collected)

    def test_the_parameters_are_filled(self) -> None:
        """Each label's WHOLE value is compared, so swapping two values fails.

        A substring test passed a swap: with the Licensor and Licensed Work values
        exchanged, each block still contained the other's expected text (t-1397).
        """
        for label, value in EXPECTED_PARAMETERS.items():
            owned = _flat(self._value_of(label))
            assert owned == _flat(value), f"{label}: expected {_flat(value)!r}, found {owned!r}"

    def test_the_record_states_the_same_spdx_id_as_pyproject(self) -> None:
        record = (ROOT / "docs/licenses/DEPENDENCIES.md").read_text(encoding="utf-8")
        stated = re.search(r"^Product licence:\s*\**([^*\s(]+)\**", record, re.MULTILINE)
        assert stated is not None, "the record carries no 'Product licence: <SPDX>' line"
        assert stated.group(1) == PRODUCT_SPDX
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert f'license = "{PRODUCT_SPDX}"' in pyproject

    def test_the_contact_line_is_ours(self) -> None:
        text = _license_text()
        assert "please contact: hello@tancat.dev" in text
        assert "mariadb.com/products" not in text

    def test_the_additional_use_grant_keeps_customers_free_and_blocks_resale(self) -> None:
        grant = _flat(self._value_of("Additional Use Grant"))
        for phrase in (
            "production use",
            "for any internal purpose",
            "competing product or service",
            "substantially the same functionality",
        ):
            assert phrase in grant, f"the grant lost {phrase!r}: {grant!r}"

    def test_the_change_date_is_four_years_after_first_distribution(self) -> None:
        change_date = _flat(self._value_of("Change Date"))
        assert "fourth anniversary" in change_date
        assert "first publicly distributed" in change_date

    def test_it_converts_to_apache_2(self) -> None:
        assert _flat(self._value_of("Change License")) == "Apache License, Version 2.0"

    def test_no_placeholder_or_foreign_parameter_survives(self) -> None:
        text = _license_text()
        for leftover in ("TODO", "<licensor>", "[Licensor", "MariaDB MaxScale", "MariaDB plc\n\nParameters"):
            assert leftover not in text, f"placeholder or foreign value left in LICENSE: {leftover!r}"
        # MariaDB's own copyright line is part of the licence text and must stay;
        # it must not be used as a parameter value.
        assert text.count("MariaDB plc") == 2, "the two MariaDB copyright/trademark lines, and nothing else"

    def test_production_use_is_not_limited_to_non_production(self) -> None:
        """The old non-production-only grant must be gone: production use is permitted."""
        text = _license_text()
        grant = text[text.index("Additional Use Grant:") : text.index("Change Date:")]
        assert "non-production" not in grant


class TestNoSurfaceSaysOpenSourceOrApache:
    """TanCat's own code is source-available; the Change License is the only Apache mention."""

    def test_the_landing_pages_do_not_call_it_open_source(self) -> None:
        patterns = {
            "landing/index.html": ("Licence (Apache-2.0)",),
            "landing/terms.html": ("the open-source licence", "because it is open source"),
            "landing/install.html": ("open-source core",),
            "docs/implementation/tancat-pro-install-and-licence.html": ("open-source core",),
        }
        for name, forbidden in patterns.items():
            text = (ROOT / name).read_text(encoding="utf-8")
            found = [phrase for phrase in forbidden if phrase in text]
            assert found == [], f"{name} still says {found}"

    def test_the_readme_does_not_call_it_apache(self) -> None:
        text = README.read_text(encoding="utf-8")
        assert "license-Apache_2.0" not in text
        assert "Apache 2.0 — see" not in text
        assert "Business Source License 1.1" in text
        assert "BSL 1.1" in text or "Business Source License" in text

    def test_the_notice_names_the_bsl(self) -> None:
        text = NOTICE.read_text(encoding="utf-8")
        assert "Business Source License 1.1" in text
        assert "Licensed under the Apache License, Version 2.0 (see LICENSE)" not in text

    def test_pyproject_declares_the_bsl(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert 'license = "BUSL-1.1"' in text
        assert 'license = "Apache-2.0"' not in text

    def test_every_apache_mention_is_about_the_change_licence(self) -> None:
        """The gap the reviewer proved: an injected "TanCat is Apache-2.0 licensed." passed."""
        offenders: list[str] = []
        for name in CHANGE_LICENCE_SURFACES:
            for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
                if "apache" not in line.lower():
                    continue
                if not any(context in line for context in APACHE_CONTEXT):
                    offenders.append(f"{name}: {line.strip()[:120]}")
        assert offenders == [], offenders

    def test_the_product_licence_lines_in_the_records_are_bsl(self) -> None:
        forbiddens = {
            "docs/licenses/DEPENDENCIES.md": (
                "TanCat itself is **Apache-2.0**",
                "TanCat's Apache-2.0 licence",
                "shipping Apache-2.0 TanCat",
            ),
            "docs/licenses/DOCUMENT_READER_LICENSES.md": ("The product is Apache-2.0", "an Apache-2.0 product"),
            "src/data/ocr/README.md": ("this Apache-2.0 product",),
        }
        for name, phrases in forbiddens.items():
            text = (ROOT / name).read_text(encoding="utf-8")
            found = [phrase for phrase in phrases if phrase in text]
            assert found == [], f"{name} still says {found}"
            assert "Business Source License 1.1" in text or "TanCat's own licence" in text or "TanCat's licence" in text

    def test_the_notice_artistic_sentence_is_the_reworded_one(self) -> None:
        """The gap the reviewer proved: reverting this sentence passed."""
        text = NOTICE.read_text(encoding="utf-8")
        assert "is permissive and compatible with Apache-2.0" not in text
        assert "is permissive and imposes no restriction of its own" in text

    def test_no_source_docstring_claims_apache_for_our_code(self) -> None:
        offenders: list[str] = []
        for path in list((ROOT / "src").rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r".*(?:repo is|product is|core is).*Apache-2\.0.*", text):
                offenders.append(f"{path.relative_to(ROOT)}: {match.group(0).strip()}")
        assert offenders == [], offenders


class TestTheFreeTierPromiseSurvives:
    def test_the_terms_keep_the_free_tier_and_say_why(self) -> None:
        text = (ROOT / "landing/terms.html").read_text(encoding="utf-8")
        assert "Free Community" in text
        assert "cannot be withdrawn from you" in text
        assert "production use for any internal purpose" in text

    def test_the_readme_says_it_stays_readable_and_modifiable(self) -> None:
        text = README.read_text(encoding="utf-8")
        assert "free to read, modify and use" in text
        assert "competing product or service" in text
        assert "not OSI open source" in text


class TestThirdPartyStatementsAreUnchanged:
    """A dependency's licence is not TanCat's: this rule must not touch those."""

    def test_the_notice_keeps_the_dependency_elections(self) -> None:
        text = NOTICE.read_text(encoding="utf-8")
        for phrase in ("text-unidecode 1.3", "Artistic-1.0", "MPL-2.0", "SIL Open Font License 1.1"):
            assert phrase in text, phrase

    def test_the_egress_audit_keeps_the_vendored_model_licence(self) -> None:
        text = (ROOT / "docs/security/egress-audit.md").read_text(encoding="utf-8")
        assert "Apache-2.0 (Baidu/PaddleOCR)" in text

    def test_the_vendored_models_keep_their_licence_note(self) -> None:
        text = (ROOT / "src/data/ocr/README.md").read_text(encoding="utf-8")
        assert "Apache-2.0" in text


# The word sweep: every tracked text file, not a hand-picked phrase list
# ---------------------------------------------------------------------------

#: Text files the sweep reads: these suffixes, every extensionless file, and the
#: licence filenames - LICENSE and NOTICE were invisible to a suffix whitelist.
SWEEP_SUFFIXES = {".md", ".html", ".yml", ".yaml", ".toml", ".txt", ".py", ".json", ".cfg", ".ini", ".sh"}
LICENCE_FILENAMES = {"LICENSE", "LICENCE", "NOTICE", "COPYING", "COPYRIGHT", "AUTHORS"}

#: The words that must not appear about TanCat itself.
SWEEP_WORDS = (
    re.compile(r"\bapache\b", re.IGNORECASE),
    re.compile(r"\bopen[- ]source\b", re.IGNORECASE),
    re.compile(r"\bOSI\b"),
)

#: Files allowed to carry the words - one by one, each with its reason (t-1403).
#: A DIRECTORY is not an allowance: `docs/licenses/` was one, and a false claim sat
#: in DOCUMENT_READER_LICENSES.md for weeks. A file in this map still may not claim
#: TanCat itself is Apache-2.0 or open source - see `_says_tancat_is_apache`.
RECORD_FILES: dict[str, str] = {
    "LICENSE": "the canonical licence text: its Apache mention IS the Change Licence",
    "docs/licenses/DEPENDENCIES.md": "the dependency licence record: table rows and elections",
    "docs/licenses/DOCUMENT_READER_LICENSES.md": "the PDF/OCR reader's dependency record",
    "scripts/maintenance/licence_record.py": "the generator that emits DEPENDENCIES.md",
    "scripts/maintenance/vendor_ocr_models.py": "the vendoring script: the OCR models are Apache-2.0",
    "src/data/ocr/README.md": "the vendored models' own readme",
    "src/data/ocr/manifest.json": "the vendored models' manifest field",
    "src/ocr_backends.py": "documents the OCR models' provenance",
    "docs/security/egress-audit.md": "its table names the vendored OCR models' licences",
    "tests/test_licence_bsl.py": "this file: the words are its patterns and its attack cases",
}

#: A sentence that says TANCAT ITSELF is Apache-2.0 or open source is a claim about
#: us, and is refused inside an allowed file too. Merely naming both is not enough:
#: "Apache-2.0, compatible with TanCat's licence" is a dependency statement.
OWN_CLAIM_RE = re.compile(
    r"(?:TanCat|this product|our licen[cs]e)(?:['’]s)?\s+(?:is|are|remains|stays)\s+"
    r"(?:licensed under\s+)?(?:the\s+)?(?:apache|open[- ]source)",
    re.IGNORECASE,
)

#: Dated records: what was true when they were written, not claims about today.
DATED_FILES = ("CHANGELOG.md", "BACKLOG.md")
DATED_DIRS = ("docs/sessions/", "docs/specs/", "docs/reviews/", "docs/private/")
#: docs/specs/ cannot reach the public site: mkdocs.yml builds `docs_dir: docs/user`,
#: and pages-deploy runs `mkdocs build` and stages only `site/`.
#: `test_the_specs_cannot_reach_the_public_site` pins that, so widening docs_dir
#: fails the suite before this allowance can go stale (t-1403).

#: Component and licence names that make a line a dependency statement rather than a
#: claim about us. A token alone is not an allowance on a buyer-facing surface.
THIRD_PARTY_TOKENS = (
    "orjson",
    "pypdfium2",
    "pdfium",
    "opencv",
    "torch",
    "rapidocr",
    "PP-OCR",
    "PaddleOCR",
    "Baidu",
    "tiktoken",
    "openai",
    "unsloth",
    "zvec",
    "Laya",
    "Granite-Docling",
    "LightOnOCR",
    "OrangeHRM",
    "text-unidecode",
    "certifi",
    "tqdm",
    "fqdn",
    "pathspec",
    "MPL-2.0",
    "BSD-3-Clause",
    "BSD-2-Clause",
    "MIT",
)

#: A Change-Licence sentence says WHERE it converts and WHEN, in one sentence. The
#: words alone are not enough: 'TanCat converts to Apache-2.0 today, so it is
#: Apache-2.0 now.' passed the old rule, and 'TanCat is Apache-2.0 now; the Change
#: Date is 2030.' was rescued by a date phrase in the next sentence.
CHANGE_WORDING = ("Change License", "Change Licence", "converts to", "Change Date")
CHANGE_DATE_WORDS = ("four years", "fourth anniversary", "Change Date")
OSI_DISCLAIMER = ("not OSI",)

#: A quoted SPDX value is a licence EXPRESSION - a dependency row, an election option,
#: a metadata field - and never a product claim. These surfaces may not use it.
NEVER_A_QUOTED_VALUE = ("landing/", "mkdocs.yml", "README.md", "NOTICE", "docs/user/")

QUOTED_SPDX = re.compile(r"[\"']apache-2\.0[\"']", re.IGNORECASE)
#: "BSD-3-Clause / Apache-2.0" - two licences paired is an expression, not a claim.
LICENCE_PAIR = re.compile(r"(?:[\w.+-]+\s*/\s*apache-2\.0|apache-2\.0\s*/\s*[\w.+-]+)", re.IGNORECASE)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _flat(text: str) -> str:
    """Collapse whitespace: assertions must not depend on where a file wraps."""
    return re.sub(r"\s+", " ", text).strip()


def _tracked_text_files() -> list[str]:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, "git ls-files failed, so the sweep cannot know the tracked tree"
    return [
        name
        for name in result.stdout.split()
        if Path(name).suffix.lower() in SWEEP_SUFFIXES
        or Path(name).suffix == ""
        or Path(name).name in LICENCE_FILENAMES
    ]


def _sweep_hits() -> list[tuple[str, int, str, str]]:
    """Every matching line, with its file's whole text (a sentence can span lines)."""
    hits: list[tuple[str, int, str, str]] = []
    for name in _tracked_text_files():
        path = ROOT / name
        if not path.is_file():
            continue
        document = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(document.splitlines(), 1):
            if any(pattern.search(line) for pattern in SWEEP_WORDS):
                hits.append((name, number, line.strip(), document))
    return hits


def _paragraph(document: str, line: str) -> str:
    """The blank-line-separated block around *line* - a sentence can wrap."""
    index = document.find(line.strip())
    if index < 0:
        return _flat(line)
    start = document.rfind("\n\n", 0, index)
    end = document.find("\n\n", index)
    return _flat(document[(start + 2 if start >= 0 else 0) : (end if end >= 0 else len(document))])


def _sentence_at(paragraph: str, line: str) -> str:
    """The ONE sentence the line belongs to - so one bad sentence cannot blame a neighbour."""
    probe = line.strip()[:60]
    index = paragraph.find(probe)
    if index < 0:
        return line.strip()
    start, end = 0, len(paragraph)
    for match in re.finditer(r"(?<=[.!?])\s+", paragraph):
        if match.end() <= index:
            start = match.end()
        elif match.start() > index:
            end = match.start()
            break
    return paragraph[start:end]


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT.split(_flat(text)) if part.strip()]


def _apache_sentences(text: str) -> list[str]:
    return [sentence for sentence in _sentences(text) if "apache" in sentence.lower()]


def _is_change_sentence(sentence: str) -> bool:
    """Where it converts AND when - in the SAME sentence."""
    return any(word in sentence for word in CHANGE_WORDING) and any(date in sentence for date in CHANGE_DATE_WORDS)


def _says_tancat_is_apache(text: str) -> bool:
    """A sentence that says TanCat itself is Apache-2.0 or open source."""
    return any(OWN_CLAIM_RE.search(sentence) for sentence in _sentences(text))


def _is_licence_value_line(line: str) -> bool:
    """A licence VALUE, not a claim: a row, a map, a bare option, a manifest field."""
    stripped = line.strip()
    if stripped.startswith("|"):
        return True  # a table row
    if re.match(r"^[\"']?[\w.\-]+[\"']?\s*:\s*[\"']", stripped):
        return True  # a mapping / election entry
    if re.fullmatch(r"[\"']apache-2\.0[\"'],?", stripped, re.IGNORECASE):
        return True  # a bare election option
    if "manifest" in line and ("licence" in line or "license" in line):
        return True  # an assertion about a component's manifest field
    return False


def _sweep_allows(name: str, line: str, document: str | None = None) -> bool:
    """Whether this line's mention is legitimate, and why (the reasons live above)."""
    document = document if document is not None else line
    paragraph = _paragraph(document, line)
    sentence = _sentence_at(paragraph, line)
    sentence_is_about_the_change = _is_change_sentence(sentence) or any(phrase in sentence for phrase in OSI_DISCLAIMER)

    if name in ("LICENSE", "tests/test_licence_bsl.py"):
        # The canonical text, and this scanner - which holds the patterns and the
        # attack sentences as fixtures. A claim about TanCat in either would fail the
        # licence tests above, not this sweep.
        # The canonical text itself: "not an Open Source license ... eventually ...
        # under an Open Source License" is MariaDB's wording, and its own tests above
        # verify the text. A false claim here would be a licence change, not a typo.
        return True

    if name in DATED_FILES or name.startswith(DATED_DIRS):
        return True

    if name in RECORD_FILES:
        # The claim rule is per LINE, not per paragraph: a paragraph can be a whole
        # dependency table, and one bad sentence in it must not condemn every row.
        if _says_tancat_is_apache(line):
            return False
        if QUOTED_SPDX.search(line) and any(name.startswith(surface) for surface in NEVER_A_QUOTED_VALUE):
            return False
        if _is_licence_value_line(line) or LICENCE_PAIR.search(line):
            return True
        if "Change Licence" in paragraph or "Change License" in paragraph:
            return True
        if sentence_is_about_the_change:
            return True
        return any(token in paragraph for token in THIRD_PARTY_TOKENS)

    # A surface that speaks to a buyer: only a Change-Licence sentence may name Apache.
    if QUOTED_SPDX.search(line):
        if any(name.startswith(surface) for surface in NEVER_A_QUOTED_VALUE):
            return False
        return _is_licence_value_line(line)
    if "Apache/MIT" in line or "MPL-2.0 AND" in line or LICENCE_PAIR.search(line):
        return True
    if re.search(r"\|\s*apache-2\.0\s*\|", line, re.IGNORECASE):
        return True  # a licence cell inside a quoted table row
    if _says_tancat_is_apache(sentence):
        return False  # a claim about us is not rescued by a date in the same sentence
    # A row can carry the whole conversion clause itself (the terms table does), and
    # the sentence around it may run on into unrelated page furniture.
    return sentence_is_about_the_change or _is_change_sentence(line)


class TestTheWordSweep:
    """One scan over every tracked text file, not a list of phrases someone remembered."""

    def test_no_unrelated_line_mentions_apache_open_source_or_osi(self) -> None:
        offenders = [
            f"{name}:{number}: {text[:120]}"
            for name, number, text, document in _sweep_hits()
            if not _sweep_allows(name, line=text, document=document)
        ]
        assert offenders == [], "line(s) claim a licence TanCat does not have:\n" + "\n".join(offenders[:20])

    def test_the_sweep_covers_the_whole_tracked_tree(self) -> None:
        """Guard against a scan that quietly sees nothing (the class this job exists to stop)."""
        files = _tracked_text_files()
        hits = _sweep_hits()
        assert len(files) > 500, f"only {len(files)} tracked text files seen - the sweep has gone blind"
        assert len(hits) > 50, f"only {len(hits)} lines mention the words - the patterns are not matching"
        assert "LICENSE" in files and "NOTICE" in files, "the extensionless licence files are not being read"

    def test_a_legitimate_dependency_row_passes(self) -> None:
        assert _sweep_allows(
            "docs/licenses/DEPENDENCIES.md",
            "| orjson | 3.11.4 | MPL-2.0 AND (Apache-2.0 OR MIT) | https://github.com/ijl/orjson |",
        )

    def test_a_change_licence_sentence_passes(self) -> None:
        notice = (
            "Licensed under the Business Source License 1.1. It converts to the Apache License, "
            "Version 2.0 four years after each version's first public distribution."
        )
        sentence = (
            "It converts to the Apache License, Version 2.0 four years after each version's first public distribution."
        )
        assert _sweep_allows("NOTICE", sentence, notice)
        assert _sweep_allows("landing/terms.html", "it converts to Apache-2.0 four years after each version's release.")
        assert _sweep_allows(
            "README.md",
            "licence is not OSI open source until it converts to the Apache License, Version 2.0 on that date.",
        )

    def test_converts_to_without_a_date_fails(self) -> None:
        assert not _sweep_allows("README.md", "TanCat converts to Apache-2.0 today, so it is Apache-2.0 now.")

    def test_a_change_date_in_another_sentence_does_not_rescue_the_claim(self) -> None:
        """t-1403: a date phrase anywhere on the line used to be enough."""
        assert not _sweep_allows("README.md", "TanCat is Apache-2.0 now; the Change Date is 2030.")

    def test_a_third_party_name_does_not_rescue_a_claim(self) -> None:
        """t-1403: mentioning a dependency token used to allow any line."""
        assert not _sweep_allows("README.md", "TanCat is Apache-2.0, like Baidu's models.")

    def test_a_claim_inside_an_allowed_record_file_fails(self) -> None:
        """t-1403: docs/licenses/ was a blanket allowance; it is per-file now."""
        assert not _sweep_allows("docs/licenses/DEPENDENCIES.md", "TanCat is licensed under Apache-2.0.")

    def test_a_quoted_spdx_value_on_a_landing_page_fails(self) -> None:
        """A quoted value is an expression, not a product claim - never on a buyer's surface."""
        assert not _sweep_allows("landing/index.html", '<meta name="licence" content="Apache-2.0">')
        assert _sweep_allows("docs/licenses/DEPENDENCIES.md", "| orjson | 3.11.4 | MPL-2.0 AND (Apache-2.0 OR MIT) |")

    def test_an_injected_product_claim_fails(self) -> None:
        assert not _sweep_allows("mkdocs.yml", "copyright: TanCat - Apache-2.0")
        assert not _sweep_allows("landing/index.html", "<p>TanCat is Apache-2.0 licensed.</p>")
        assert not _sweep_allows("README.md", "TanCat is open source.")

    def test_the_specs_cannot_reach_the_public_site(self) -> None:
        """The evidence for keeping the docs/specs/ allowance (t-1403)."""
        mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        assert "docs_dir: docs/user" in mkdocs, "docs_dir changed: re-check the docs/specs allowance"
        deploy = (ROOT / ".github/workflows/pages-deploy.yml").read_text(encoding="utf-8")
        assert "mkdocs build" in deploy, "pages-deploy stopped building with mkdocs: re-check the allowance"
        assert "cp -r site/. _site/docs/" in deploy, "something else is staged now: re-check the allowance"
