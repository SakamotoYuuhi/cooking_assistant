import faiss
import numpy as np
import json
from pathlib import Path
from typing import List
from .embedding import embed_text

INDEX_FILE = Path(__file__).resolve().parents[2] / "data" / "index" / "recipes.faiss"
METADATA_FILE = Path(__file__).resolve().parents[2] / "data" / "index" / "recipes_metadata.json"

# 起動時に一度だけロード（毎リクエストで読み込まないようにキャッシュ）
_index = None
_metadata: List[dict] = []


def _load_index():
    global _index, _metadata
    if _index is None:
        if not INDEX_FILE.exists():
            raise FileNotFoundError(
                "FAISSインデックスが見つかりません。"
                "先に `python3 scripts/build_index.py` を実行してください。"
            )
        _index = faiss.read_index(str(INDEX_FILE))
        _metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))


def search_recipes(query: str, top_k: int = 3) -> List[dict]:
    """
    クエリに意味的に近いレシピをFAISSで検索して返す。

    Returns:
        [{"title": ..., "content": ..., "score": ...}, ...]
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


def build_rag_context(retrieved: List[dict]) -> str:
    """検索されたレシピをプロンプトに埋め込む形式に整形する"""
    if not retrieved:
        return ""

    context_parts = ["【参考レシピ（あなたのレシピ集より）】\n"]
    for i, recipe in enumerate(retrieved, 1):
        context_parts.append(f"--- 参考レシピ {i}: {recipe['title']} ---")
        context_parts.append(recipe["content"])
        context_parts.append("")

    return "\n".join(context_parts)
