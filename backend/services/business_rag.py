"""
業務ナレッジ検索サービス。

料理アシスタントのRAG（rag.py）と全く同じ構造で、
対象ドキュメントが「レシピ」から「業務文書」に変わっただけ。
これがフェーズ4の本質 ─ 同じアーキテクチャの業務転用。
"""

import faiss
import numpy as np
import json
from pathlib import Path
from typing import List
from .embedding import embed_text

INDEX_FILE = Path(__file__).resolve().parents[2] / "data" / "business_index" / "docs.faiss"
METADATA_FILE = Path(__file__).resolve().parents[2] / "data" / "business_index" / "docs_metadata.json"

_index = None
_metadata: List[dict] = []


def _load_index():
    global _index, _metadata
    if _index is None:
        if not INDEX_FILE.exists():
            raise FileNotFoundError(
                "業務ナレッジのインデックスが見つかりません。"
                "先に `python3 scripts/build_business_index.py` を実行してください。"
            )
        _index = faiss.read_index(str(INDEX_FILE))
        _metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))


def search_business_docs(query: str, top_k: int = 3) -> List[dict]:
    """
    クエリに意味的に近い業務文書をFAISSで検索して返す。
    rag.pyのsearch_recipes()と全く同じ構造。
    """
    _load_index()

    query_vector = np.array([embed_text(query)], dtype=np.float32)
    scores, indices = _index.search(query_vector, top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        meta = _metadata[idx]
        results.append({
            "title": meta["title"],
            "content": meta["content"],
            "score": float(score),
        })

    return results


def build_business_context(retrieved: List[dict]) -> str:
    """検索された業務文書をプロンプトに埋め込む形式に整形する"""
    if not retrieved:
        return ""

    context_parts = ["【参考ドキュメント（社内ナレッジベースより）】\n"]
    for i, doc in enumerate(retrieved, 1):
        context_parts.append(f"--- 参考文書 {i}: {doc['title']} ---")
        context_parts.append(doc["content"])
        context_parts.append("")

    return "\n".join(context_parts)
