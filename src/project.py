"""Project container helpers (t-0510).

The project is the storage workspace promoted to a user-facing concept. Its name
is also the RAG scope (AI-061), so learned patterns follow the project across a
new port or environment for the same project.

Everything here is ignorable: an unset project keeps today's behaviour - the
legacy ``default`` storage workspace and the host[:port] RAG identity - so a
single-environment user sees no change until they name a project.
"""

from __future__ import annotations

import os

from src.rag_learn import RAG_SCOPE_ENV, domain_from_url

#: The legacy storage workspace. An unset project resolves to this directory.
DEFAULT_PROJECT = "default"


def project_display_name(stored: str, first_url: str = "") -> str:
    """The name to show for the project: the stored name, else the host.

    An unset project shows the host of the first story URL (or ``default`` when
    no URL is known), so a single-environment user sees a sensible name that
    matches the environment they are already working against.
    """
    stored = (stored or "").strip()
    if stored:
        return stored
    return domain_from_url(first_url) or DEFAULT_PROJECT


def project_workspace(stored: str) -> str:
    """The storage workspace directory for the project.

    An unset project keeps today's ``default`` workspace, so no data moves
    until the user explicitly names a project.
    """
    return (stored or "").strip() or DEFAULT_PROJECT


def rag_scope_for(stored: str) -> str | None:
    """The RAG scope to apply for the project, or ``None`` to keep host[:port].

    Only a *named* project changes the scope. An unset project returns ``None``
    so :func:`src.rag_learn.effective_site_identity` keeps its legacy host[:port]
    identity - today's behaviour.
    """
    stored = (stored or "").strip()
    if not stored or stored == DEFAULT_PROJECT:
        return None
    return stored


def apply_rag_scope(stored: str) -> str | None:
    """Set (or clear) ``AITEST_RAG_SCOPE`` from the project name.

    Returns the applied scope, or ``None`` when the variable was cleared so the
    host[:port] fallback applies.
    """
    scope = rag_scope_for(stored)
    if scope is None:
        os.environ.pop(RAG_SCOPE_ENV, None)
    else:
        os.environ[RAG_SCOPE_ENV] = scope
    return scope
