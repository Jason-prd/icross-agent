"""Ozon platform rules knowledge base service.

Indexes and searches PDF documents from the Ozon平台规则 directory.
"""

import json
import os
import re
from pathlib import Path
from typing import Any

RULES_DIR = Path(__file__).parent.parent.parent.parent / "Ozon平台规则"
INDEX_FILE = Path(__file__).parent.parent.parent.parent / "data" / "ozon_rules_index.json"


def _make_id(title: str, index: int = 0) -> str:
    """Create a unique document ID from the title.

    Preserves Chinese characters. Falls back to a numeric ID if needed.
    """
    # Remove characters that are unsafe for URL/file paths
    # Keep word chars, Chinese chars (U+4E00-U+9FFF), spaces, dashes
    safe = title
    for ch in ['"', "'", '*', '/', '\\', '?', '%', '#', '@', '!', '&', '(', ')', '=', '+', ',', '.', ':', ';', '<', '>', '|', '~', '`', '{', '}', '[', ']', '^']:
        safe = safe.replace(ch, "")
    safe = re.sub(r"\s+", "-", safe.strip())[:60]
    if not safe:
        safe = f"doc-{index}"
    return safe


class OzonRuleKB:
    """Knowledge base for Ozon platform rules.

    Builds an index of all PDF documents in the Ozon平台规则 directory,
    then provides full-text search over their content.
    """

    def __init__(self):
        self._entries: list[dict[str, Any]] | None = None

    # ── Index building ──────────────────────────────────────────

    def build_index(self) -> dict:
        """Scan all PDFs, extract text, build search index.

        Returns a summary dict with counts per category.
        """
        import pypdf

        if not RULES_DIR.exists():
            return {"error": f"Rules directory not found: {RULES_DIR}"}

        entries = []
        category_counts: dict[str, int] = {}

        # Walk directories (1/, 2/, 3/, ...)
        for cat_dir in sorted(RULES_DIR.iterdir()):
            if not cat_dir.is_dir():
                continue

            category = cat_dir.name
            category_counts[category] = 0

            for pdf_path in sorted(cat_dir.iterdir()):
                if pdf_path.suffix.lower() != ".pdf":
                    continue

                title = pdf_path.stem
                # Strip " _ Ozon Help" suffix
                clean_title = re.sub(r"\s*_ Ozon Help$", "", title).strip()

                text = self._extract_text(pdf_path)
                if not text.strip():
                    continue

                entry = {
                    "id": _make_id(clean_title, len(entries)),
                    "category": category,
                    "title": clean_title,
                    "filename": pdf_path.name,
                    "path": str(pdf_path.relative_to(RULES_DIR.parent)),
                    "content": text.strip(),
                    "word_count": len(text.split()),
                }
                entries.append(entry)
                category_counts[category] += 1

        self._entries = entries
        self._save_index(entries)

        return {
            "total_docs": len(entries),
            "categories": category_counts,
        }

    def _extract_text(self, pdf_path: Path) -> str:
        """Extract text from a PDF file using pypdf."""
        import pypdf

        try:
            reader = pypdf.PdfReader(str(pdf_path))
            texts = []
            for page in reader.pages:
                t = page.extract_text()
                if t and t.strip():
                    texts.append(t.strip())
            return "\n\n".join(texts)
        except Exception:
            return ""

    def _save_index(self, entries: list[dict]) -> None:
        INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    # ── Loading / Querying ──────────────────────────────────────

    def _load_index(self) -> list[dict]:
        if self._entries is not None:
            return self._entries
        if INDEX_FILE.exists():
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                self._entries = json.load(f)
        else:
            self._entries = []
        return self._entries

    def search(
        self,
        query: str,
        category: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search the knowledge base by keyword.

        Implements simple TF-style search: scores documents by
        the number of query term occurrences in title and content.
        """
        entries = self._load_index()
        if not entries:
            return []

        query_lower = query.lower()

        # Build search terms: for CJK content without spaces, we need
        # to match individual characters as well as bigrams
        terms = set()
        # 1. Full query as a substring
        terms.add(query_lower)
        # 2. Whitespace-separated words
        for part in query_lower.split():
            terms.add(part)
        # 3. Character-level for Chinese: each Chinese char + bigrams
        cjk_chars = [c for c in query_lower if ord(c) > 127]
        for ch in cjk_chars:
            terms.add(ch)
        for i in range(len(cjk_chars) - 1):
            terms.add(cjk_chars[i] + cjk_chars[i + 1])
        # 4. Remove empty
        terms.discard("")

        results = []
        for entry in entries:
            if category and entry.get("category") != category:
                continue

            title_lower = entry.get("title", "").lower()
            content_lower = entry.get("content", "").lower()

            score = 0
            for term in terms:
                cnt = title_lower.count(term) * 5 + content_lower.count(term)
                score += cnt

            if score > 0:
                results.append({
                    "id": entry["id"],
                    "category": entry["category"],
                    "title": entry["title"],
                    "score": score,
                    "snippet": self._make_snippet(content_lower, list(terms), entry.get("content", "")),
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    def _make_snippet(self, content_lower: str, terms: list[str], original: str) -> str:
        """Extract a text snippet around the first matching term."""
        for term in terms:
            idx = content_lower.find(term)
            if idx != -1:
                start = max(0, idx - 60)
                end = min(len(original), idx + 200)
                prefix = "…" if start > 0 else ""
                suffix = "…" if end < len(original) else ""
                return f"{prefix}{original[start:end].strip()}{suffix}"
        return original[:200]

    def get_categories(self) -> list[dict]:
        """Get list of categories with document counts."""
        entries = self._load_index()
        counts: dict[str, int] = {}
        for e in entries:
            cat = e.get("category", "?")
            counts[cat] = counts.get(cat, 0) + 1

        return [
            {"id": k, "name": f"第{k}类", "count": v}
            for k, v in sorted(counts.items())
        ]

    def get_document(self, doc_id: str) -> dict | None:
        """Get a single document by its ID."""
        entries = self._load_index()
        for e in entries:
            if e["id"] == doc_id:
                return e
        return None

    def get_stats(self) -> dict:
        """Get knowledge base statistics."""
        entries = self._load_index()
        cats: dict[str, int] = {}
        total_words = 0
        for e in entries:
            cat = e.get("category", "?")
            cats[cat] = cats.get(cat, 0) + 1
            total_words += e.get("word_count", 0)
        return {
            "total_docs": len(entries),
            "total_words": total_words,
            "categories": cats,
        }
