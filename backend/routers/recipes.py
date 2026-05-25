"""
レシピ管理エンドポイント。

POST /recipes/upload   - レシピをS3に保存してFAISSインデックスを再構築
GET  /recipes          - S3上のレシピ一覧を返す
GET  /recipes/{filename} - 指定レシピの内容を返す
"""

import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.s3_storage import upload_recipe, list_recipes, get_recipe
from ..services.rag import reload_index

router = APIRouter(prefix="/recipes", tags=["recipes"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_index.py"


class RecipeUploadRequest(BaseModel):
    filename: str
    title: str
    content: str


class RecipeUploadResponse(BaseModel):
    s3_key: str
    filename: str
    index_rebuilt: bool
    message: str


# ---- ヘルパー ----

def _rebuild_index() -> bool:
    """
    build_index.py をサブプロセスで実行してFAISSインデックスを再構築する。
    成功すると rag.py のキャッシュも再読み込みする。
    """
    result = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"インデックス再構築に失敗しました:\n{result.stderr}"
        )
    reload_index()
    return True


# ---- エンドポイント ----

@router.post("/upload", response_model=RecipeUploadResponse)
async def upload(request: RecipeUploadRequest):
    """
    レシピをS3に保存し、FAISSインデックスを自動再構築する。
    filenameはスペースなし英数字＋アンダースコア推奨（例: my_recipe.md）。
    """
    filename = request.filename
    if not filename.endswith(".md"):
        filename = f"{filename}.md"

    try:
        s3_key = upload_recipe(filename, request.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3アップロードエラー: {e}")

    index_rebuilt = False
    try:
        index_rebuilt = _rebuild_index()
    except RuntimeError as e:
        return RecipeUploadResponse(
            s3_key=s3_key,
            filename=filename,
            index_rebuilt=False,
            message=f"S3への保存は成功しましたが、インデックス再構築に失敗しました: {e}",
        )

    return RecipeUploadResponse(
        s3_key=s3_key,
        filename=filename,
        index_rebuilt=index_rebuilt,
        message=f"レシピ「{request.title}」をS3に保存し、インデックスを更新しました",
    )


@router.get("")
async def get_recipes():
    """S3上のレシピ一覧を返す"""
    try:
        recipes = list_recipes()
        return {"recipes": recipes, "count": len(recipes)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3取得エラー: {e}")


@router.get("/{filename}")
async def get_recipe_content(filename: str):
    """指定ファイル名のレシピ内容を返す"""
    try:
        content = get_recipe(filename)
        return {"filename": filename, "content": content}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"レシピが見つかりません: {e}")
