"""Tests for src/gui/markdown_renderer.py — no Qt runtime required."""

from __future__ import annotations

import pytest
from src.gui.markdown_renderer import (
    _convert_markdown_inline,
    _convert_markdown_links,
    create_anchor_id,
    markdown_to_html,
)

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────────────────────────
# create_anchor_id
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateAnchorId:
    def test_basic_spaces(self):
        assert create_anchor_id("Hello World") == "hello-world"

    def test_lowercase(self):
        assert create_anchor_id("UPPERCASE") == "uppercase"

    def test_dots_stripped(self):
        assert create_anchor_id("v1.2.3") == "v123"

    def test_ampersand_to_and(self):
        assert create_anchor_id("Terms & Conditions") == "terms-and-conditions"

    def test_combined(self):
        assert create_anchor_id("Open Strings v1.0.0 & Beyond") == "open-strings-v100-and-beyond"

    def test_already_clean(self):
        assert create_anchor_id("simple") == "simple"


# ─────────────────────────────────────────────────────────────────────────────
# _convert_markdown_links
# ─────────────────────────────────────────────────────────────────────────────


class TestConvertMarkdownLinks:
    def test_basic_link(self):
        result = _convert_markdown_links("[text](https://example.com)")
        assert result == '<a href="https://example.com">text</a>'

    def test_multiple_links(self):
        text = "[foo](https://foo.com) and [bar](https://bar.com)"
        result = _convert_markdown_links(text)
        assert '<a href="https://foo.com">foo</a>' in result
        assert '<a href="https://bar.com">bar</a>' in result

    def test_no_links_unchanged(self):
        text = "plain text with no links"
        assert _convert_markdown_links(text) == text

    def test_relative_link(self):
        result = _convert_markdown_links("[docs](./README.md)")
        assert result == '<a href="./README.md">docs</a>'


# ─────────────────────────────────────────────────────────────────────────────
# _convert_markdown_inline
# ─────────────────────────────────────────────────────────────────────────────


class TestConvertMarkdownInline:
    def test_bold_asterisks(self):
        assert "<strong>bold</strong>" in _convert_markdown_inline("**bold**")

    def test_bold_underscores(self):
        assert "<strong>bold</strong>" in _convert_markdown_inline("__bold__")

    def test_italic_asterisk(self):
        assert "<em>italic</em>" in _convert_markdown_inline("*italic*")

    def test_code_span(self):
        result = _convert_markdown_inline("`code`")
        assert "<code>code</code>" in result

    def test_code_escapes_html(self):
        result = _convert_markdown_inline("`<tag>`")
        assert "<code>&lt;tag&gt;</code>" in result

    def test_code_protects_bold_inside(self):
        result = _convert_markdown_inline("`**not bold**`")
        assert "<strong>" not in result
        assert "**not bold**" in result

    def test_link_inside_inline(self):
        result = _convert_markdown_inline("See [here](https://example.com) for details")
        assert '<a href="https://example.com">here</a>' in result

    def test_plain_text_unchanged(self):
        text = "No markdown here"
        assert _convert_markdown_inline(text) == text

    def test_bold_and_italic_combined(self):
        result = _convert_markdown_inline("**bold** and *italic*")
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_underscore_in_identifier_not_italicized(self):
        # Underscores inside snake_case identifiers must not become <em> tags.
        # The renderer only italicises *single-asterisk* pairs, not bare underscores.
        result = _convert_markdown_inline("vehicle_Name_SCItem")
        assert "<em>" not in result


# ─────────────────────────────────────────────────────────────────────────────
# markdown_to_html
# ─────────────────────────────────────────────────────────────────────────────


class TestMarkdownToHtml:
    def test_returns_full_html(self):
        result = markdown_to_html("hello")
        assert result.startswith("<html>")
        assert "<head>" in result
        assert "<body>" in result
        assert "</html>" in result

    def test_contains_style_block(self):
        result = markdown_to_html("hello")
        assert "<style>" in result

    def test_h1_rendered(self):
        result = markdown_to_html("# Title")
        assert "<h1" in result
        assert "Title" in result

    def test_h2_rendered(self):
        result = markdown_to_html("## Section")
        assert "<h2" in result
        assert "Section" in result

    def test_h3_rendered(self):
        result = markdown_to_html("### Sub")
        assert "<h3" in result
        assert "Sub" in result

    def test_heading_anchor_id(self):
        result = markdown_to_html("# Hello World")
        assert "id='hello-world'" in result

    def test_paragraph_rendered(self):
        result = markdown_to_html("Just a paragraph.")
        assert "<p>" in result
        assert "Just a paragraph." in result

    def test_unordered_list(self):
        result = markdown_to_html("- item one\n- item two")
        assert "<ul>" in result
        assert "<li>item one</li>" in result
        assert "<li>item two</li>" in result

    def test_ordered_list(self):
        result = markdown_to_html("1. first\n2. second")
        assert "<ol>" in result
        assert "<li>first</li>" in result
        assert "<li>second</li>" in result

    def test_code_block(self):
        result = markdown_to_html("```\ncode here\n```")
        assert "<pre>" in result
        assert "code here" in result

    def test_custom_colors_in_style(self):
        result = markdown_to_html("hello", text_color="#ff0000", link_color="#00ff00")
        assert "#ff0000" in result
        assert "#00ff00" in result

    def test_default_colors_present(self):
        result = markdown_to_html("hello")
        # Default colors from function signature
        assert "#000000" in result
        assert "#ffffff" in result
        assert "#0078d7" in result

    def test_atkinson_font_in_style(self):
        result = markdown_to_html("hello")
        assert "Atkinson Hyperlegible" in result

    def test_empty_string(self):
        result = markdown_to_html("")
        assert "<html>" in result
        assert "</html>" in result

    def test_multiline_document(self):
        doc = "# Title\n\nSome paragraph.\n\n## Section\n\n- item\n"
        result = markdown_to_html(doc)
        assert "<h1" in result
        assert "<h2" in result
        assert "<p>" in result
        assert "<li>" in result

    def test_list_closed_when_h1_follows_without_blank_line(self):
        # Exercises the `if in_list: html += f"</{list_type}>"` branch in h1 handler
        doc = "- item one\n- item two\n# Heading"
        result = markdown_to_html(doc)
        assert "</ul>" in result
        assert "<h1" in result

    def test_list_closed_when_h2_follows_without_blank_line(self):
        doc = "- item\n## Sub"
        result = markdown_to_html(doc)
        assert "</ul>" in result
        assert "<h2" in result

    def test_list_closed_when_h3_follows_without_blank_line(self):
        doc = "- item\n### Sub"
        result = markdown_to_html(doc)
        assert "</ul>" in result
        assert "<h3" in result

    def test_ol_closed_when_different_list_starts(self):
        # An ordered list followed immediately by an unordered list should close
        # the ol and open a ul (exercises the `if in_list: html += f"</{list_type}>"` inside ul branch)
        doc = "1. ordered\n- unordered"
        result = markdown_to_html(doc)
        assert "</ol>" in result
        assert "<ul>" in result

    def test_empty_line_sets_prev_blank_when_not_in_list(self):
        # Multiple blank lines between paragraphs — second blank should not add
        # extra <p> (exercises elif not prev_blank: prev_blank = True path)
        doc = "Para one.\n\n\nPara two."
        result = markdown_to_html(doc)
        assert result.count("<p>") == 2

    def test_paragraph_closes_open_list(self):
        # A paragraph immediately after a list (no blank line) closes the list
        doc = "- item\nfollowing paragraph"
        result = markdown_to_html(doc)
        assert "</ul>" in result
        assert "<p>" in result
