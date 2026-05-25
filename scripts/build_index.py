"""
レシピMarkdownファイルを読み込み、FAISSインデックスを構築するスクリプト。
初回セットアップ時と、レシピを追加・更新したときに実行する。

実行方法:
    cd cooking_assistant
    python3 scripts/build_index.py
"""

import os
import sys
import faiss
import numpy as np
import json
from pathlib import Path
from dotenv import load_dotenv

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root.parent))

load_dotenv(dotenv_path=project_root / ".env")

from cooking_assistant.backend.services.embedding import embed_text

RECIPES_DIR = project_root / "data" / "recipes"
INDEX_DIR = project_root / "data" / "index"
INDEX_FILE = INDEX_DIR / "recipes.faiss"
METADATA_FILE = INDEX_DIR / "recipes_metadata.json"


def load_recipes(recipes_dir: Path) -> list[dict]:
    """Markdownレシピファイルをすべて読み込む"""
    recipes = []
    for md_file in sorted(recipes_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        recipes.append({
            "filename": md_file.name,
            "title": md_file.stem.replace("_", " "),
            "content": text,
        })
        print(f"  読み込み: {md_file.name}")
    return recipes


def build_faiss_index(recipes: list[dict]) -> tuple:
    """レシピをEmbedding化してFAISSインデックスを構築する"""
    print("\n[2] Embeddingを生成中...")
    embeddings = []
    for i, recipe in enumerate(recipes):
        print(f"  ({i+1}/{len(recipes)}) {recipe['filename']} をEmbedding化...")
        vector = embed_text(recipe["content"])
        embeddings.append(vector)

    vectors = np.array(embeddings, dtype=np.float32)
    dim = vectors.shape[1]

    # IndexFlatIPは内積（コサイン類似度に相当）で検索する最もシンプルなインデックス
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)

    return index, vectors


def main():
    print("=" * 50)
    print("FAISSインデックス構築スクリプト")
    print("=" * 50)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n[1] レシピを読み込み中: {RECIPES_DIR}")
    recipes = load_recipes(RECIPES_DIR)
    print(f"  合計 {len(recipes)} 件のレシピを読み込みました")

    index, _ = build_faiss_index(recipes)

    print("\n[3] インデックスを保存中...")
    faiss.write_index(index, str(INDEX_FILE))

    # メタデータ（ファイル名・タイトル・本文）をJSONで保存
    metadata = [
        {"filename": r["filename"], "title": r["title"], "content": r["content"]}
        for r in recipes
    ]
    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  インデックス保存先: {INDEX_FILE}")
    print(f"  メタデータ保存先: {METADATA_FILE}")
    print(f"\n完了！ {len(recipes)} 件のレシピをインデックス化しました。")
    print("=" * 50)


if __name__ == "__main__":
    main()
