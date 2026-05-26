"""
レシピ管理エンドポイント。

POST /recipes/convert  - 生テキストをBedrockでMarkdown形式に変換
POST /recipes/upload   - レシピをS3に保存してFAISSインデックスを再構築
GET  /recipes          - S3上のレシピ一覧を返す
GET  /recipes/{filename} - 指定レシピの内容を返す
"""

import subprocess
import sys
import json
import os
import boto3
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.s3_storage import upload_recipe, list_recipes, get_recipe
from ..services.rag import reload_index

router = APIRouter(prefix="/recipes", tags=["recipes"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_index.py"


class RecipeConvertRequest(BaseModel):
    raw_text: str


class RecipeConvertResponse(BaseModel):
    markdown: str
    suggested_title: str
    suggested_filename: str


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

CONVERT_MODEL_ID = "jp.anthropic.claude-haiku-4-5-20251001-v1:0"

CONVERT_SYSTEM_PROMPT = """あなたはレシピ整形の専門家です。
ユーザーが貼り付けた料理に関するテキスト（ChatGPTの回答・ブログ記事・メモなど）を、
以下のMarkdown形式に変換してください。

---
# レシピ名

## 基本情報
- 調理時間: XX分
- 人数: X人分
- カテゴリ: （主菜・和食 / 主菜・洋食 / 主菜・中華 / 副菜 / 汁物 / ご飯・麺 / デザート など）
- 難易度: （簡単 / 普通 / 難しい）

## 材料
- 材料名: 分量
- ...

## 手順
1. 手順1
2. 手順2
...

## ポイント
- コツや注意点
- ...
---

ルール：
- 元テキストに記載のない情報（調理時間・カテゴリなど）は内容から推測して補完する
- 絵文字・装飾文字（■①→等）は除去してシンプルなMarkdownにする
- 会話文・解説文・アレンジ提案など、レシピ本体以外の内容は除外する
- 材料は「- 食材名: 分量」の形式に統一する
- 手順は番号付きリスト（1. 2. 3.）にする
- 計量単位は「小さじ」「大さじ」「カップ」などを正確にそのまま表記すること（省略・誤字厳禁）
- `~` や `~~` はMarkdown記法として特殊な意味を持つため、テキスト中に一切使用しないこと
- 出力はMarkdownのみ。説明文は不要。

また、最後の行に以下を追記してください（Markdownの外）：
TITLE: レシピ名
FILENAME: ファイル名（英数字とアンダースコアのみ、拡張子なし）
"""


def _convert_with_bedrock(raw_text: str) -> RecipeConvertResponse:
    """Bedrockを使って生テキストをMarkdownレシピに変換する"""
    client = boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 3000,
        "system": CONVERT_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": raw_text}],
    }

    response = client.invoke_model(
        modelId=CONVERT_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )

    full_text = json.loads(response["body"].read())["content"][0]["text"]

    # TITLE: / FILENAME: を末尾から抽出してMarkdown本体と分離
    lines = full_text.strip().splitlines()
    title = ""
    filename = ""
    markdown_lines = []

    for line in lines:
        if line.startswith("TITLE:"):
            title = line.removeprefix("TITLE:").strip()
        elif line.startswith("FILENAME:"):
            filename = line.removeprefix("FILENAME:").strip()
        else:
            markdown_lines.append(line)

    markdown = "\n".join(markdown_lines).strip()

    # フォールバック: 1行目の # レシピ名 から取得
    if not title:
        for line in markdown_lines:
            if line.startswith("# "):
                title = line.lstrip("# ").strip()
                break

    if not filename:
        import re
        filename = re.sub(r"[^\w]", "_", title.lower())[:40].strip("_") or "recipe"

    return RecipeConvertResponse(
        markdown=markdown,
        suggested_title=title,
        suggested_filename=filename,
    )

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

@router.post("/convert", response_model=RecipeConvertResponse)
async def convert_recipe(request: RecipeConvertRequest):
    """
    生テキスト（ChatGPT回答・ブログ記事など）をBedrockでMarkdownレシピ形式に変換する。
    変換結果のプレビュー・編集後に /upload で保存する想定。
    """
    if not request.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text が空です")
    try:
        return _convert_with_bedrock(request.raw_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bedrock変換エラー: {e}")


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
