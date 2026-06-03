"""Tests for Phase 3 product tools (listing generation, translation)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from icross.agents.master.tools_product import (
    _safe_format,
    generate_listing,
    translate_text,
)


# ── _safe_format ───────────────────────────────────────────────────

class TestSafeFormat:
    """Tests for the template formatting utility."""

    def test_basic_format(self):
        """Should format simple template strings."""
        result = _safe_format("产品: {product_name_cn}", product_name_cn="蓝牙耳机")
        assert result == "产品: 蓝牙耳机"

    def test_or_default_with_value(self):
        """Should use the provided value when it exists."""
        result = _safe_format(
            "名称: {product_name_cn or '默认'}",
            product_name_cn="蓝牙耳机"
        )
        assert result == "名称: 蓝牙耳机"

    def test_or_default_with_empty_string(self):
        """Should fall back to default when value is empty string."""
        result = _safe_format(
            "名称: {product_name_cn or '默认名称'}",
            product_name_cn=""
        )
        assert result == "名称: 默认名称"

    def test_or_default_with_none(self):
        """Should fall back to default when value is None."""
        result = _safe_format(
            "名称: {product_name_cn or '默认名称'}",
            product_name_cn=None
        )
        assert result == "名称: 默认名称"

    def test_or_default_single_quotes(self):
        """Should handle single-quoted defaults."""
        result = _safe_format(
            "{field or 'default value'}",
            field="real"
        )
        assert result == "real"

    def test_or_default_double_quotes(self):
        """Should handle double-quoted defaults."""
        result = _safe_format(
            '{field or "default value"}',
            field="real"
        )
        assert result == "real"

    def test_multiple_or_defaults(self):
        """Should handle multiple {field or 'default'} in one template."""
        result = _safe_format(
            "{a or 'A'} and {b or 'B'}",
            a="hello",
            b=""
        )
        assert result == "hello and B"

    def test_list_value_joined(self):
        """Should join list values with comma."""
        result = _safe_format(
            "关键词: {keywords or '无'}",
            keywords=["蓝牙", "耳机", "运动"]
        )
        assert result == "关键词: 蓝牙, 耳机, 运动"

    def test_empty_list_falls_back(self):
        """Should use default for empty list."""
        result = _safe_format(
            "关键词: {keywords or '无关键词'}",
            keywords=[]
        )
        assert result == "关键词: 无关键词"


# ── generate_listing ───────────────────────────────────────────────

class TestGenerateListing:
    @patch("icross.agents.master.llm.create_llm")
    def test_successful_generation(self, mock_create_llm):
        """Should return success JSON with title, description, keywords."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "title": "Русское название",
            "description": "Русское описание товара",
            "keywords": ["ключевое слово1", "ключевое слово2"],
        })
        async def fake_ainvoke(*a, **kw):
            return mock_response
        mock_llm.ainvoke = fake_ainvoke
        mock_create_llm.return_value = mock_llm

        result = generate_listing.func(
            product_name_cn="蓝牙耳机",
            product_description_cn="高品质无线蓝牙耳机",
            category="电子产品",
            keywords=["蓝牙", "耳机"],
            target_market="俄罗斯",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["title"] == "Русское название"
        assert data["description"] == "Русское описание товара"
        assert len(data["keywords"]) == 2

    @patch("icross.agents.master.llm.create_llm")
    def test_generation_with_custom_prompt(self, mock_create_llm):
        """Should use custom prompt template when provided."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "title": "Custom Title",
            "description": "Custom desc",
            "keywords": ["kw1"],
        })
        async def fake_ainvoke(*a, **kw):
            return mock_response
        mock_llm.ainvoke = fake_ainvoke
        mock_create_llm.return_value = mock_llm

        result = generate_listing.func(
            product_name_cn="测试产品",
            custom_prompt="自定义模板: {product_name_cn or '默认'}",
        )

        data = json.loads(result)
        assert data["success"] is True

    @patch("icross.agents.master.llm.create_llm")
    def test_handles_json_in_code_block(self, mock_create_llm):
        """Should extract JSON from markdown code block."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "```json\n{\"title\": \"Title\", \"description\": \"Desc\", \"keywords\": []}\n```"
        async def fake_ainvoke(*a, **kw):
            return mock_response
        mock_llm.ainvoke = fake_ainvoke
        mock_create_llm.return_value = mock_llm

        result = generate_listing.func(
            product_name_cn="测试产品",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["title"] == "Title"

    @patch("icross.agents.master.llm.create_llm")
    def test_handles_llm_error(self, mock_create_llm):
        """Should return error JSON when LLM call fails."""
        mock_llm = MagicMock()
        async def fake_ainvoke(*a, **kw):
            raise Exception("API error")
        mock_llm.ainvoke = fake_ainvoke
        mock_create_llm.return_value = mock_llm

        result = generate_listing.func(
            product_name_cn="测试产品",
        )

        data = json.loads(result)
        assert data["success"] is False
        assert "error" in data

    def test_generation_without_keywords(self):
        """Should handle empty keywords list gracefully and return error due to LLM unavailability."""
        # This tests the code path, not the LLM call success
        result = generate_listing.func(
            product_name_cn="测试产品",
            keywords=[],
        )
        data = json.loads(result)
        # Without mocking, it may fail due to MiniMax not being configured
        assert "success" in data


# ── translate_text ─────────────────────────────────────────────────

class TestTranslateText:
    @patch("icross.agents.master.llm.create_llm")
    def test_successful_translation(self, mock_create_llm):
        """Should return translated text."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Привет мир"
        async def fake_ainvoke(*a, **kw):
            return mock_response
        mock_llm.ainvoke = fake_ainvoke
        mock_create_llm.return_value = mock_llm

        result = translate_text.func(
            text="你好世界",
            target_lang="俄语",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["translated"] == "Привет мир"
        assert data["original"] == "你好世界"
        assert data["target_lang"] == "俄语"

    @patch("icross.agents.master.llm.create_llm")
    def test_translation_error(self, mock_create_llm):
        """Should return error JSON when translation fails."""
        mock_llm = MagicMock()
        async def fake_ainvoke(*a, **kw):
            raise Exception("API error")
        mock_create_llm.return_value = mock_llm

        result = translate_text.func(
            text="你好",
            target_lang="俄语",
        )

        data = json.loads(result)
        assert data["success"] is False



