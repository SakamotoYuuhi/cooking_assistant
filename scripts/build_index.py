"""
レシピをS3またはローカルから読み込み、FAISSインデックスを構築するスクリプト。
初回セットアップ時と、レシピを追加・更新したときに実行する。

実行方法（S3から読み込む場合）:
    cd cooking_assistant
    python3 scripts/build_index.py

実行方法（ローカルのみで使う場合）:
    cd cooking_assistant
    python3 scripts/build_index.py --local
"""

import os
import sys
import faiss
import numpy as np
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root.parent))

load_dotenv(dotenv_path=project_root / ".env")

from cooking_assistant.backend.services.embedding import embed_text

RECIPES_DIR = project_root / "data" / "recipes"
S3_CACHE_DIR = project_root / "data" / "s3_recipes"
INDEX_DIR = project_root / "data" / "index"
INDEX_FILE = INDEX_DIR / "recipes.faiss"
METADATA_FILE = INDEX_DIR / "recipes_metadata.json"


def load_recipes_from_local(recipes_dir: Path) -> list[dict]:
    """ローカルMarkdownレシピファイルをすべて読み込む"""
    recipes = []
    for md_file in sorted(recipes_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        title_line = next((l for l in text.splitlines() if l.startswith("# ")), None)
        title = title_line.lstrip("# ").strip() if title_line else md_file.stem.replace("_", " ")
        recipes.append({
            "filename": md_file.name,
            "title": title,
            "content": text,
        })
        print(f"  読み込み: {md_file.name}  →  {title}")
    return recipes


def load_recipes_from_s3() -> list[dict]:
    """S3からレシピを取得してローカルにキャッシュし、メタデータを返す"""
    from cooking_assistant.backend.services.s3_storage import download_all_recipes

    print(f"  S3からレシピをダウンロード中... → {S3_CACHE_DIR}")
    saved = download_all_recipes(S3_CACHE_DIR)
    print(f"  S3から {len(saved)} 件のレシピを取得しました")

    recipes = []
    for item in saved:
        local_path = Path(item["local_path"])
        text = local_path.read_text(encoding="utf-8")
        title_line = next((l for l in text.splitlines() if l.startswith("# ")), None)
        title = title_line.lstrip("# ").strip() if title_line else local_path.stem.replace("_", " ")
        recipes.append({
            "filename": item["filename"],
            "title": title,
            "content": text,
        })
        print(f"  読み込み: {item['filename']}  →  {title}")
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--local",
        action="store_true",
        help="S3ではなくローカルの data/recipes/ からレシピを読み込む",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("FAISSインデックス構築スクリプト")
    print("=" * 50)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    if args.local:
        print(f"\n[1] ローカルからレシピを読み込み中: {RECIPES_DIR}")
        recipes = load_recipes_from_local(RECIPES_DIR)
    else:
        print("\n[1] S3からレシピを読み込み中...")
        recipes = load_recipes_from_s3()
        # ローカルレシピも結合（サンプルレシピを含む場合）
        if RECIPES_DIR.exists():
            local_recipes = load_recipes_from_local(RECIPES_DIR)
            existing_filenames = {r["filename"] for r in recipes}
            for lr in local_recipes:
                if lr["filename"] not in existing_filenames:
                    recipes.append(lr)
            if local_recipes:
                print(f"  ローカルから追加: {len(local_recipes)} 件")

    print(f"  合計 {len(recipes)} 件のレシピを読み込みました")

    if not recipes:
        print("  レシピが0件です。処理を中断します。")
        return

    index, _ = build_faiss_index(recipes)

    print("\n[3] インデックスを保存中...")
    faiss.write_index(index, str(INDEX_FILE))

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
