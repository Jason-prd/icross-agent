"""Ozon platform rules knowledge base API endpoints."""

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/ozon-rules", tags=["ozon-rules"])


@router.get("/search")
def search_rules(
    query: str = Query(..., min_length=1, max_length=200),
    category: str = "",
    limit: int = Query(default=5, le=20),
):
    """Search the Ozon platform rules knowledge base."""
    from icross.services.ozon_rules import OzonRuleKB

    kb = OzonRuleKB()
    results = kb.search(query=query, category=category or None, limit=limit)
    return {"success": True, "query": query, "count": len(results), "results": results}


@router.get("/categories")
def list_categories():
    """List all document categories with counts."""
    from icross.services.ozon_rules import OzonRuleKB

    kb = OzonRuleKB()
    return {"categories": kb.get_categories()}


@router.get("/stats")
def get_stats():
    """Get knowledge base statistics."""
    from icross.services.ozon_rules import OzonRuleKB

    kb = OzonRuleKB()
    return kb.get_stats()


@router.get("/documents/{doc_id}")
def get_document(doc_id: str):
    """Get a full document by its ID."""
    from icross.services.ozon_rules import OzonRuleKB

    kb = OzonRuleKB()
    doc = kb.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/rebuild")
def rebuild_index():
    """Rebuild the search index from scratch."""
    from icross.services.ozon_rules import OzonRuleKB

    kb = OzonRuleKB()
    result = kb.build_index()
    return result
