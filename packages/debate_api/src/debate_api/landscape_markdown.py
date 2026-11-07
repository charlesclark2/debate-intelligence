"""A landscape bundle as the pilot's landscape pages show it (`v1-e39-t17`).

The Markdown cut and render are :mod:`debate_core.arguments.landscape.pages`, moved there unchanged
by `v1-e32-t57` so that the report's page-size check measures the bytes these pages send (the PM's
ruling of 2026-11-07, Q4). What is left here is :func:`render_bundle`, the
:class:`~debate_core.application.tub.landscape_pages.LandscapeShelf`'s `prepare`: both files of a
bundle, rendered once, held until the shelf reads the bucket again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from debate_core.application.tub.landscape_pages import LandscapeBundle
from debate_core.arguments.landscape.pages import (
    RenderedReport,
    RenderedSchoolView,
    render_report,
    render_school_view,
)

__all__ = ["RenderedBundle", "render_bundle"]


@dataclass(frozen=True, slots=True)
class RenderedBundle:
    caselist: str
    snapshot: date
    report: RenderedReport
    school_view: RenderedSchoolView | None


def render_bundle(bundle: LandscapeBundle) -> RenderedBundle:
    """Both files of `bundle` as the pages show them: :class:`LandscapeShelf`'s `prepare`."""
    return RenderedBundle(
        caselist=bundle.caselist,
        snapshot=bundle.snapshot,
        report=render_report(bundle.report_markdown, bundle.caselist),
        school_view=(
            None
            if bundle.school_view_markdown is None
            else render_school_view(bundle.school_view_markdown, bundle.caselist)
        ),
    )
