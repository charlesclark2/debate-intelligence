"""The bold and size a run inherits, as Word shows them (`v1-e31-t24`).

`v1-e31-t19`'s item (7): two tags typed with nothing set, in a file whose document defaults make
every run bold at 13 pt. Word shows ordinary bold tags; the reader, which reads what a run says,
saw an unbolded line of no size. The package now keeps the document's defaults and each style's own
bold and size, and :func:`as_word_shows_it` fills a run that says nothing from them. The parser does
not call it.

Every file is invented and every expectation written by hand from it (working agreement 6).
"""

from __future__ import annotations

from debate_core.evidence.style_classifier import ParagraphDescription, RunDescription
from debate_core.integrations.docx_parser.package import InheritedRunProperties, open_debate_docx
from debate_core.integrations.docx_parser.runs import as_word_shows_it, defaults_make_text_bold
from debate_core.testing.docx_builder import W_NAMESPACE, build_docx, paragraph_xml, run_xml


def styles(*, defaults: str = "", definitions: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W_NAMESPACE}">{defaults}{definitions}</w:styles>'
    )


def run_defaults(properties: str) -> str:
    return f"<w:docDefaults><w:rPrDefault><w:rPr>{properties}</w:rPr></w:rPrDefault></w:docDefaults>"


def style(
    style_id: str, kind: str, *, properties: str = "", based_on: str = "", default: bool = False
) -> str:
    flag = ' w:default="1"' if default else ""
    based = f'<w:basedOn w:val="{based_on}"/>' if based_on else ""
    run_properties = f"<w:rPr>{properties}</w:rPr>" if properties else ""
    return (
        f'<w:style w:type="{kind}" w:styleId="{style_id}"{flag}>'
        f'<w:name w:val="{style_id}"/>{based}{run_properties}</w:style>'
    )


BOLD_THIRTEEN_POINT = '<w:b w:val="1"/><w:sz w:val="26"/>'

#: (7)'s file, as its defaults have it: every run bold at 13 pt unless it says otherwise, and a
#: default paragraph style that says nothing of either.
SEVEN = styles(
    defaults=run_defaults(BOLD_THIRTEEN_POINT),
    definitions=style("Normal", "paragraph", default=True)
    + style("Heading4", "paragraph", based_on="Normal"),
)


class TestThePackageKeepsWhatARunInherits:
    def test_the_document_defaults_bold_and_size(self) -> None:
        package = open_debate_docx(build_docx(paragraph_xml(run_xml("A line")), styles_xml=SEVEN))
        assert package.run_defaults == InheritedRunProperties(bold=True, half_points=26)

    def test_a_style_s_own_bold_and_size_and_which_style_is_the_default(self) -> None:
        package = open_debate_docx(
            build_docx(
                paragraph_xml(run_xml("A line")),
                styles_xml=styles(
                    definitions=style("Normal", "paragraph", default=True, properties='<w:sz w:val="22"/>')
                    + style("Plain", "paragraph", based_on="Normal", properties='<w:b w:val="0"/>')
                ),
            )
        )
        assert package.styles["Normal"].is_default
        assert package.styles["Normal"].run_properties == InheritedRunProperties(bold=None, half_points=22)
        assert not package.styles["Plain"].is_default
        assert package.styles["Plain"].run_properties == InheritedRunProperties(bold=False, half_points=None)

    def test_off_is_spelled_three_ways_and_a_bare_element_is_on(self) -> None:
        for spelling in ("0", "false", "off"):
            package = open_debate_docx(
                build_docx(
                    paragraph_xml(run_xml("A line")),
                    styles_xml=styles(defaults=run_defaults(f'<w:b w:val="{spelling}"/>')),
                )
            )
            assert package.run_defaults.bold is False
        package = open_debate_docx(
            build_docx(paragraph_xml(run_xml("A line")), styles_xml=styles(defaults=run_defaults("<w:b/>")))
        )
        assert package.run_defaults.bold is True

    def test_a_size_that_is_not_a_positive_number_is_none(self) -> None:
        for size in ("", "big", "0"):
            package = open_debate_docx(
                build_docx(
                    paragraph_xml(run_xml("A line")),
                    styles_xml=styles(defaults=run_defaults(f'<w:sz w:val="{size}"/>')),
                )
            )
            assert package.run_defaults.half_points is None

    def test_a_file_with_no_defaults_inherits_nothing(self) -> None:
        package = open_debate_docx(build_docx(paragraph_xml(run_xml("A line"))))
        assert package.run_defaults == InheritedRunProperties()


class TestAsWordShowsIt:
    def test_seven_s_line_is_bold_at_thirteen_points(self) -> None:
        package = open_debate_docx(build_docx(paragraph_xml(run_xml("A line")), styles_xml=SEVEN))
        line = ParagraphDescription(runs=(RunDescription(text="Tag typed with nothing set"),))
        shown = as_word_shows_it(line, package)
        assert shown.runs[0].bold is True
        assert shown.runs[0].half_points == 26
        assert shown.effective_bold
        assert shown.effective_half_points == 26

    def test_what_a_run_says_wins(self) -> None:
        package = open_debate_docx(build_docx(paragraph_xml(run_xml("A line")), styles_xml=SEVEN))
        body = ParagraphDescription(runs=(RunDescription(text="Body text", bold=False, half_points=22),))
        shown = as_word_shows_it(body, package)
        assert (shown.runs[0].bold, shown.runs[0].half_points) == (False, 22)

    def test_the_paragraph_style_comes_before_the_defaults_and_its_ancestors_after_it(self) -> None:
        package = open_debate_docx(
            build_docx(
                paragraph_xml(run_xml("A line")),
                styles_xml=styles(
                    defaults=run_defaults(BOLD_THIRTEEN_POINT),
                    definitions=style("Normal", "paragraph", default=True)
                    + style("Base", "paragraph", properties='<w:sz w:val="20"/>')
                    + style("Plain", "paragraph", based_on="Base", properties='<w:b w:val="0"/>'),
                ),
            )
        )
        line = ParagraphDescription(
            runs=(RunDescription(text="A line"),), style_id="Plain", style_based_on=("Base",)
        )
        shown = as_word_shows_it(line, package)
        assert (shown.runs[0].bold, shown.runs[0].half_points) == (False, 20)

    def test_a_paragraph_that_names_no_style_has_the_default_paragraph_style(self) -> None:
        package = open_debate_docx(
            build_docx(
                paragraph_xml(run_xml("A line")),
                styles_xml=styles(
                    defaults=run_defaults(BOLD_THIRTEEN_POINT),
                    definitions=style("Normal", "paragraph", default=True, properties='<w:b w:val="0"/>'),
                ),
            )
        )
        shown = as_word_shows_it(ParagraphDescription(runs=(RunDescription(text="A line"),)), package)
        assert (shown.runs[0].bold, shown.runs[0].half_points) == (False, 26)

    def test_the_character_style_comes_before_the_paragraph_style(self) -> None:
        package = open_debate_docx(
            build_docx(
                paragraph_xml(run_xml("A line")),
                styles_xml=styles(
                    definitions=style("Normal", "paragraph", default=True, properties='<w:b w:val="0"/>')
                    + style("Strong", "character", properties='<w:b/><w:sz w:val="28"/>'),
                ),
            )
        )
        line = ParagraphDescription(runs=(RunDescription(text="A line", character_style_id="Strong"),))
        shown = as_word_shows_it(line, package)
        assert (shown.runs[0].bold, shown.runs[0].half_points) == (True, 28)

    def test_nothing_anywhere_leaves_the_run_saying_nothing(self) -> None:
        package = open_debate_docx(build_docx(paragraph_xml(run_xml("A line"))))
        line = ParagraphDescription(runs=(RunDescription(text="A line"),))
        assert as_word_shows_it(line, package) == line


class TestDefaultsMakeTextBold:
    def test_seven_s_file(self) -> None:
        assert defaults_make_text_bold(
            open_debate_docx(build_docx(paragraph_xml(run_xml("A")), styles_xml=SEVEN))
        )

    def test_a_default_paragraph_style_that_turns_bold_off(self) -> None:
        package = open_debate_docx(
            build_docx(
                paragraph_xml(run_xml("A")),
                styles_xml=styles(
                    defaults=run_defaults(BOLD_THIRTEEN_POINT),
                    definitions=style("Normal", "paragraph", default=True, properties='<w:b w:val="0"/>'),
                ),
            )
        )
        assert not defaults_make_text_bold(package)

    def test_a_default_paragraph_style_that_is_bold_over_plain_defaults(self) -> None:
        package = open_debate_docx(
            build_docx(
                paragraph_xml(run_xml("A")),
                styles_xml=styles(
                    definitions=style("Normal", "paragraph", default=True, properties="<w:b/>")
                ),
            )
        )
        assert defaults_make_text_bold(package)

    def test_an_ordinary_file(self) -> None:
        assert not defaults_make_text_bold(open_debate_docx(build_docx(paragraph_xml(run_xml("A")))))
