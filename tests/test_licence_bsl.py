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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LICENSE = ROOT / "LICENSE"
NOTICE = ROOT / "NOTICE"
README = ROOT / "README.md"

#: The record's SPDX id for the product, compared with pyproject (t-1397).
PRODUCT_SPDX = "BUSL-1.1"

#: Each parameter's ENTIRE value. Equality, not substring: a swap must fail.
EXPECTED_PARAMETERS = {
    "Licensor": "Louis Cattano, trading as TanCat",
    "Licensed Work": ("TanCat version 0.1.0 or later. The Licensed Work is (c) 2026 Louis Cattano, trading as TanCat."),
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


def _flat(text: str) -> str:
    """Collapse whitespace: assertions must not depend on where a file wraps."""
    return re.sub(r"\s+", " ", text).strip()


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
