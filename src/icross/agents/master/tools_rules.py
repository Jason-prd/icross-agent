"""Ozon platform rules knowledge base Agent tools (Phase 4)."""

import json

from langchain_core.tools import tool

from icross.agents.tools import registry


@tool
def search_ozon_rules(
    query: str,
    category: str = "",
    limit: int = 5,
) -> str:
    """搜索 Ozon 平台规则知识库。

    查询 Ozon 官方规则文档，涵盖：商品上架要求、图片视频规范、类目佣金费率、
    物流设置、促销活动、定价规则、订单处理、退货退款、广告推广等。
    适用于：了解平台规则、商品审核要求、合规指引等场景。

    Args:
        query: 搜索关键词（中文或俄语，如 "佣金"、"фото"、"图片要求"）
        category: 分类筛选（可选，如 "1"、"2"、"3"、"4"、"5"、"6"）
        limit: 返回结果数量（1-10）

    Returns:
        JSON字符串，包含匹配的文档列表及摘要
    """
    try:
        from icross.services.ozon_rules import OzonRuleKB

        kb = OzonRuleKB()
        results = kb.search(
            query=query,
            category=category or None,
            limit=min(max(limit, 1), 10),
        )

        if not results:
            return json.dumps({
                "success": True,
                "count": 0,
                "message": f"未找到与「{query}」相关的规则文档，请尝试其他关键词",
                "results": [],
            }, ensure_ascii=False)

        return json.dumps({
            "success": True,
            "count": len(results),
            "query": query,
            "results": results,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


registry.register(search_ozon_rules, toolset="rules")


@tool
def get_ozon_rule_document(doc_id: str) -> str:
    """获取 Ozon 平台规则文档的完整内容。

    Args:
        doc_id: 文档 ID（从 search_ozon_rules 结果中获得）

    Returns:
        JSON字符串，包含文档完整标题、分类和内容
    """
    try:
        from icross.services.ozon_rules import OzonRuleKB

        kb = OzonRuleKB()
        doc = kb.get_document(doc_id)
        if not doc:
            return json.dumps({"success": False, "error": f"文档 {doc_id} 未找到"}, ensure_ascii=False)

        return json.dumps({
            "success": True,
            "title": doc.get("title"),
            "category": doc.get("category"),
            "content": doc.get("content", ""),
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


registry.register(get_ozon_rule_document, toolset="rules")


OZON_RULES_TOOLS = [search_ozon_rules, get_ozon_rule_document]
