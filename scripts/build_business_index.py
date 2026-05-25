"""
業務文書をEmbedding化してFAISSインデックスを構築するスクリプト。
build_index.py（レシピ用）と全く同じ構造で、対象ディレクトリだけ異なる。

実行方法:
    cd cooking_assistant
    python3 scripts/build_business_index.py
"""

import os
import sys
import faiss
import numpy as np
import json
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root.parent))

load_dotenv(dotenv_path=project_root / ".env")

from cooking_assistant.backend.services.embedding import embed_text

DOCS_DIR = project_root / "data" / "business_docs"
INDEX_DIR = project_root / "data" / "business_index"
INDEX_FILE = INDEX_DIR / "docs.faiss"
METADATA_FILE = INDEX_DIR / "docs_metadata.json"


def load_docs(docs_dir: Path) -> list[dict]:
    docs = []
    for md_file in sorted(docs_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        docs.append({
            "filename": md_file.name,
            "title": md_file.stem.replace("_", " "),
            "content": text,
        })
        print(f"  読み込み: {md_file.name}")
    return docs


def main():
    print("=" * 50)
    print("業務ナレッジ FAISSインデックス構築")
    print("=" * 50)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n[1] 業務文書を読み込み中: {DOCS_DIR}")
    docs = load_docs(DOCS_DIR)
    print(f"  合計 {len(docs)} 件の文書を読み込みました")

    print("\n[2] Embeddingを生成中...")
    embeddings = []
    for i, doc in enumerate(docs):
        print(f"  ({i+1}/{len(docs)}) {doc['filename']} をEmbedding化...")
        vector = embed_text(doc["content"])
        embeddings.append(vector)

    vectors = np.array(embeddings, dtype=np.float32)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)

    print("\n[3] インデックスを保存中...")
    faiss.write_index(index, str(INDEX_FILE))
    metadata = [{"filename": d["filename"], "title": d["title"], "content": d["content"]} for d in docs]
    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  保存先: {INDEX_DIR}")
    print(f"\n完了！ {len(docs)} 件の業務文書をインデックス化しました。")
    print("=" * 50)


if __name__ == "__main__":
    main()
