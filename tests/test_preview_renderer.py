"""Tests for src.utils.preview_renderer._render_preview_html."""

import pytest
from src.utils.preview_renderer import _render_preview_html

pytestmark = pytest.mark.unit


class TestRenderPreviewHtml:
    def test_empty_raw_shows_empty_placeholder(self):
        html = _render_preview_html("some_key", "")
        assert "(empty)" in html

    def test_plain_text_is_escaped_and_rendered(self):
        html = _render_preview_html("some_key", "Hello World")
        assert "Hello World" in html

    def test_html_entities_are_escaped(self):
        html = _render_preview_html("some_key", "Price: <10 & >5")
        assert "&lt;10" in html
        assert "&amp;" in html

    def test_backslash_n_becomes_br(self):
        html = _render_preview_html("some_key", "Line one\\nLine two")
        assert "<br>" in html
        assert "\\n" not in html

    def test_em3_tag_becomes_underline_span(self):
        html = _render_preview_html("some_key", "<EM3>Section Header</EM3>")
        assert "text-decoration:underline" in html
        assert "Section Header" in html

    def test_em4_tag_becomes_bold_blue_span(self):
        html = _render_preview_html("some_key", "<EM4>42 aUEC</EM4>")
        assert "font-weight:bold" in html
        assert "42 aUEC" in html

    def test_mission_token_becomes_grey_italic(self):
        html = _render_preview_html("some_key", "Deliver to ~mission(LocationName)")
        assert "LocationName" in html
        assert "font-style:italic" in html

    def test_mission_token_with_pipe_uses_first_part(self):
        html = _render_preview_html("some_key", "~mission(Foo|bar)")
        assert "Foo" in html

    def test_combined_tokens(self):
        raw = "<EM3>Title</EM3>\\nStat: <EM4>100 hp</EM4>\\nGo to ~mission(Target)"
        html = _render_preview_html("some_key", raw)
        assert "Title" in html
        assert "100 hp" in html
        assert "Target" in html
        assert "<br>" in html

    def test_returns_html_div_wrapper(self):
        html = _render_preview_html("k", "text")
        assert html.startswith("<div")
        assert "font-family" in html
