"""Contract tests for Spec 002's MDX scanning and preprocessing library."""

from __future__ import annotations

import pytest

import fit.mdx as mdx


MdxDocument = mdx.MdxDocument


def assert_preprocess_error(source: str, pattern: str) -> None:
    """Assert the public preprocessing error without breaking test collection."""
    error_type = getattr(mdx, "MdxPreprocessError", Exception)
    with pytest.raises(error_type, match=pattern):
        MdxDocument(source).preprocess()


class TestPublicSurface:
    def test_public_preprocess_error_is_exposed(self):
        assert hasattr(mdx, "MdxPreprocessError")
        assert issubclass(mdx.MdxPreprocessError, Exception)

    def test_summary_is_empty_until_preprocess_runs(self):
        doc = MdxDocument('<section title="A">x</section>\n')
        assert doc.summary == {}


class TestScan:
    def test_plain_markdown_has_no_findings(self):
        doc = MdxDocument("# Title\n\nJust some text.\n")
        assert doc.structural_tags == {}
        assert doc.content_wrapper_tags == {}
        assert doc.unknown_components == {}
        assert doc.has_structural_tags is False
        assert doc.has_content_wrappers is False
        assert doc.has_unknown_components is False
        assert doc.format_findings() == ""

    def test_counts_opening_tags_and_separates_all_finding_categories(self):
        source = (
            '<section title="A">x</section>\n'
            '<section title="B">y</section>\n'
            "<Tip>z</Tip>\n"
            "<CustomWidget>value</CustomWidget>\n"
        )
        doc = MdxDocument(source)

        assert doc.structural_tags == {"section": 2}
        assert doc.content_wrapper_tags == {"Tip": 1}
        assert doc.unknown_components == {"CustomWidget": 1}
        assert doc.has_structural_tags is True
        assert doc.has_content_wrappers is True
        assert doc.has_unknown_components is True
        assert doc.format_findings() == (
            "Structural:\n"
            "  section: 2\n"
            "Content wrappers:\n"
            "  Tip: 1\n"
            "Unknown JSX:\n"
            "  CustomWidget: 1"
        )

    @pytest.mark.parametrize("fence", ["```", "~~~~"])
    def test_ignores_recognized_and_unknown_jsx_inside_fenced_code(self, fence):
        source = (
            f"{fence}md\n"
            '<section title="Example">\n'
            "<Tip>literal</Tip>\n"
            "<CustomWidget />\n"
            "</section>\n"
            f"{fence}\n"
        )
        doc = MdxDocument(source)

        assert doc.structural_tags == {}
        assert doc.content_wrapper_tags == {}
        assert doc.unknown_components == {}

    def test_ignores_recognized_and_unknown_jsx_inside_code_spans(self):
        source = (
            "Use `<Tip>literal</Tip>` and ``<CustomWidget `mode` />`` as examples.\n"
        )
        doc = MdxDocument(source)

        assert doc.structural_tags == {}
        assert doc.content_wrapper_tags == {}
        assert doc.unknown_components == {}

    @pytest.mark.parametrize(
        "source",
        [
            "Write decisions/<NNN>_<unit>.md for each unit.\n",
            "Write `decisions/<NNN>_<unit>.md` for each unit.\n",
        ],
    )
    def test_all_caps_angle_bracket_placeholder_is_not_unknown_jsx(self, source):
        doc = MdxDocument(source)

        assert doc.unknown_components == {}
        assert doc.format_findings() == ""

    def test_recognizes_multiline_attributes_single_quotes_and_boolean_attribute(self):
        source = (
            "<ParamField\n"
            "  required\n"
            "  type='string'\n"
            "  body='model'\n"
            ">value</ParamField>\n"
        )
        assert MdxDocument(source).content_wrapper_tags == {"ParamField": 1}

    def test_element_names_are_case_sensitive_and_lowercase_html_is_allowed(self):
        source = "<tip>html</tip>\n<details>body</details>\n"
        doc = MdxDocument(source)

        assert doc.structural_tags == {}
        assert doc.content_wrapper_tags == {}
        assert doc.unknown_components == {}

    def test_recognizes_consistently_indented_structural_component(self):
        source = "    <CodeGroup>\n    body\n    </CodeGroup>\n"
        assert MdxDocument(source).structural_tags == {"CodeGroup": 1}


class TestTransparentAndHeadingComponents:
    def test_plain_markdown_passes_through_byte_identically(self):
        source = "# Title\n\nA paragraph.\n\n## Subhead\n\nMore prose.\n"
        assert MdxDocument(source).preprocess() == source

    def test_standard_raw_html_passes_through_byte_identically(self):
        source = "<details>\n<summary>x</summary>\nbody\n</details>\n"
        assert MdxDocument(source).preprocess() == source

    def test_fenced_jsx_example_passes_through_byte_identically(self):
        source = "```md\n<Tip>literal</Tip>\n<CustomWidget />\n```\n"
        assert MdxDocument(source).preprocess() == source

    @pytest.mark.parametrize("tag", ["CodeGroup", "Tabs", "AccordionGroup", "CardGroup", "Frame"])
    def test_transparent_wrapper_is_removed_and_body_is_exact(self, tag):
        source = f"before\n\n<{tag}>\nbody\n\n- item\n</{tag}>\n\nafter\n"
        expected = "before\n\nbody\n\n- item\n\nafter\n"
        assert MdxDocument(source).preprocess() == expected

    @pytest.mark.parametrize(
        ("opening", "closing"),
        [
            ('<section title="Inner">', "</section>"),
            ('<Tab title="Inner">', "</Tab>"),
            ('<Accordion title="Inner">', "</Accordion>"),
            ('<Card title="Inner">', "</Card>"),
        ],
    )
    def test_heading_wrapper_uses_active_heading_depth(self, opening, closing):
        source = f"## Top\n\n{opening}\nbody\n{closing}\n"
        expected = "## Top\n\n### Inner\n\nbody\n"
        assert MdxDocument(source).preprocess() == expected

    def test_heading_wrapper_defaults_to_h2_without_an_active_heading(self):
        source = '<section title="Inner">\nbody\n</section>\n'
        assert MdxDocument(source).preprocess() == "## Inner\n\nbody\n"

    def test_nested_heading_scope_restores_containing_depth_for_sibling(self):
        source = (
            "# Top\n\n"
            '<section title="Outer">\n'
            '<Accordion title="Nested">n</Accordion>\n'
            "</section>\n"
            '<Card title="Sibling">s</Card>\n'
        )
        expected = (
            "# Top\n\n"
            "## Outer\n\n"
            "### Nested\n\n"
            "n\n"
            "## Sibling\n\n"
            "s\n"
        )
        assert MdxDocument(source).preprocess() == expected

    @pytest.mark.parametrize(
        ("opening", "closing"),
        [
            ('<section title="Inner">', "</section>"),
            ('<Tab title="Inner">', "</Tab>"),
            ('<Accordion title="Inner">', "</Accordion>"),
            ('<Card title="Inner">', "</Card>"),
        ],
    )
    def test_h6_fallback_preserves_title_as_bold_text(self, opening, closing):
        source = f"###### Six\n\n{opening}body{closing}\n"
        expected = "###### Six\n\n**Inner**\n\nbody\n"
        assert MdxDocument(source).preprocess() == expected


class TestContainerComponents:
    @pytest.mark.parametrize("tag", ["Tip", "Note", "Warning", "Info", "Danger"])
    def test_admonition_quotes_every_body_line(self, tag):
        source = (
            f"<{tag}>\n"
            "First paragraph.\n\n"
            "```python\n"
            'print("preserved")\n'
            "```\n"
            f"</{tag}>\n"
        )
        expected = (
            f"> **{tag}:**\n"
            ">\n"
            "> First paragraph.\n"
            ">\n"
            "> ```python\n"
            '> print("preserved")\n'
            "> ```\n"
        )
        assert MdxDocument(source).preprocess() == expected

    def test_steps_match_normative_multiline_output(self):
        source = (
            "<Steps>\n"
            '<Step title="Install">\n'
            "Run the command.\n\n"
            "- Keep this nested item.\n"
            "</Step>\n"
            '<Step title="Verify">Check the result.</Step>\n'
            "</Steps>\n"
        )
        expected = (
            "1. **Install**\n\n"
            "   Run the command.\n\n"
            "   - Keep this nested item.\n\n"
            "2. **Verify**\n\n"
            "   Check the result.\n"
        )
        assert MdxDocument(source).preprocess() == expected

    def test_step_counter_resets_for_each_steps_component(self):
        source = (
            "<Steps>\n<Step title='A'>x</Step>\n</Steps>\n\n"
            "<Steps>\n<Step title='B'>y</Step>\n</Steps>\n"
        )
        expected = (
            "1. **A**\n\n   x\n\n"
            "1. **B**\n\n   y\n"
        )
        assert MdxDocument(source).preprocess() == expected

    def test_param_fields_preserve_metadata_and_complete_bodies(self):
        source = (
            '<ParamField body="model" type="string" required>\n'
            "The model name.\n\n"
            "May contain a provider prefix.\n"
            "</ParamField>\n\n"
            '<ParamField type="number" body="temperature">Sampling temperature.</ParamField>\n'
        )
        expected = (
            "- **model** (`string`, required)\n\n"
            "  The model name.\n\n"
            "  May contain a provider prefix.\n\n"
            "- **temperature** (`number`)\n\n"
            "  Sampling temperature.\n"
        )
        assert MdxDocument(source).preprocess() == expected

    def test_response_field_preserves_dotted_name_type_and_body(self):
        source = (
            '<ResponseField type="integer" name="usage.input_tokens">\n'
            "Tokens consumed.\n"
            "</ResponseField>\n"
        )
        expected = (
            "- **usage.input_tokens** (`integer`)\n\n"
            "  Tokens consumed.\n"
        )
        assert MdxDocument(source).preprocess() == expected

    def test_non_field_content_ends_a_field_run(self):
        source = (
            '<ParamField body="a" type="string">A.</ParamField>\n'
            "Intervening prose.\n"
            '<ParamField body="b" type="string">B.</ParamField>\n'
        )
        expected = (
            "- **a** (`string`)\n\n"
            "  A.\n"
            "Intervening prose.\n"
            "- **b** (`string`)\n\n"
            "  B.\n"
        )
        assert MdxDocument(source).preprocess() == expected


class TestIndentationAndPreservation:
    def test_consistently_indented_component_is_deindented_and_transformed(self):
        source = (
            "    <CodeGroup>\n"
            "    ```python\n"
            "    <Tip>literal example</Tip>\n"
            "    ```\n"
            "    </CodeGroup>\n"
        )
        expected = (
            "```python\n"
            "<Tip>literal example</Tip>\n"
            "```\n"
        )
        assert MdxDocument(source).preprocess() == expected

    def test_nested_component_body_order_and_sentinel_text_are_preserved(self):
        source = (
            "<Note>\n"
            "alpha\n"
            '<section title="Nested">beta</section>\n'
            "omega\n"
            "</Note>\n"
        )
        output = MdxDocument(source).preprocess()
        assert output == (
            "> **Note:**\n"
            ">\n"
            "> alpha\n"
            "> ## Nested\n"
            ">\n"
            "> beta\n"
            "> omega\n"
        )
        assert output.index("alpha") < output.index("beta") < output.index("omega")

    def test_preprocessing_is_idempotent(self):
        source = "<Tip>Remember.</Tip>\n"
        once = MdxDocument(source).preprocess()
        assert once == "> **Tip:**\n>\n> Remember.\n"
        assert MdxDocument(once).preprocess() == once

    def test_summary_counts_opening_tags_after_success(self):
        source = '<section title="A">x</section>\n<Tip>y</Tip>\n'
        doc = MdxDocument(source)
        doc.preprocess()
        assert doc.summary["section"] == 1
        assert doc.summary["Tip"] == 1


class TestDiagnostics:
    @pytest.mark.parametrize(
        ("source", "pattern"),
        [
            ("<CustomWidget>body</CustomWidget>\n", "CustomWidget"),
            ('<section title="A">body\n', "unclosed|section"),
            ("<Tabs><Tab title='A'>body</Tabs>\n", "mismatch|Tab"),
            ('<section title={value}>body</section>\n', "JSX|expression"),
            ("<Tip {...props}>body</Tip>\n", "spread|unsupported"),
            ("prose <Tip>body</Tip>\n", "mid-line|unsupported"),
            ('<section title="A" audience="developers">body</section>\n', "audience|attribute"),
            ('<section>body</section>\n', "title|required"),
            ('<ParamField body="x">body</ParamField>\n', "type|required"),
        ],
    )
    def test_unsafe_or_unsupported_input_fails(self, source, pattern):
        assert_preprocess_error(source, pattern)

    def test_mixed_indentation_fails_instead_of_leaving_a_hard_blocker(self):
        source = (
            "    <CodeGroup>\n"
            "    body\n"
            "      </CodeGroup>\n"
        )
        assert_preprocess_error(source, "indent")
