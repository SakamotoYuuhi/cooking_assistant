"""
レシピ管理エンドポイント。

POST /recipes/convert        - 生テキストをBedrockでMarkdown形式に変換
POST /recipes/generate-image - レシピ内容からBedrockで完成画像を生成
POST /recipes/upload         - レシピをS3に保存してFAISSインデックスを再構築
GET  /recipes                - S3上のレシピ一覧を返す
GET  /recipes/{filename}     - 指定レシピの内容を返す
GET  /recipes/{filename}/image - 指定レシピの画像を返す
"""

import base64
import subprocess
import sys
import json
import os
import boto3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..services.s3_storage import (
    upload_recipe, list_recipes, get_recipe,
    upload_recipe_image, get_recipe_image, recipe_image_exists,
    delete_recipe, delete_recipe_image,
)
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
    image_base64: Optional[str] = None
    image_ext: str = "jpg"


class RecipeUploadResponse(BaseModel):
    s3_key: str
    filename: str
    index_rebuilt: bool
    message: str
    image_s3_key: Optional[str] = None


class RecipeUpdateRequest(BaseModel):
    title: str
    content: str
    image_base64: Optional[str] = None
    image_ext: str = "jpg"
    delete_image: bool = False


class RecipeUpdateResponse(BaseModel):
    s3_key: str
    filename: str
    index_rebuilt: bool
    message: str
    image_s3_key: Optional[str] = None
    image_deleted: bool = False


class RecipeImageUpdateRequest(BaseModel):
    image_base64: str
    image_ext: str = "jpg"


class RecipeImageUpdateResponse(BaseModel):
    image_s3_key: str
    message: str


class GenerateImageRequest(BaseModel):
    recipe_title: str
    recipe_content: str


class GenerateImageResponse(BaseModel):
    image_base64: str
    content_type: str


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

IMAGE_MODEL_ID = "stability.stable-image-core-v1:1"
IMAGE_REGION = "us-west-2"


TEXT_MODEL_ID = "jp.anthropic.claude-haiku-4-5-20251001-v1:0"


def _build_image_prompt(recipe_title: str, recipe_content: str) -> str:
    """
    Claudeを使ってレシピ内容から Stable Diffusion 用の英語プロンプトを生成する。
    日本語タイトルをそのまま渡すと誤った画像が生成されるため、
    Claudeに料理の見た目を英語で詳しく描写させる。
    """
    text_client = boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    system = (
        "You are an expert at writing image generation prompts for Stable Diffusion. "
        "Given a Japanese recipe, describe the finished dish in English for a food photography prompt. "
        "Focus on: dish name in English, appearance, color, texture, plating style, bowl/plate type. "
        "Output ONLY the prompt text (under 100 words). No explanation."
    )
    user_msg = f"Recipe title: {recipe_title}\n\nRecipe content:\n{recipe_content[:500]}"

    response = text_client.invoke_model(
        modelId=TEXT_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 150,
            "system": system,
            "messages": [{"role": "user", "content": user_msg}],
        }),
    )
    dish_description = json.loads(response["body"].read())["content"][0]["text"].strip()
    return (
        f"Professional food photography, {dish_description}, "
        f"natural lighting, top-down angle, appetizing, clean background, high resolution"
    )


def _generate_image_with_bedrock(recipe_title: str, recipe_content: str) -> tuple[bytes, str]:
    """
    Stable Image Core (us-west-2) を使って料理の完成画像を生成する。
    ap-northeast-1 にはACTIVEな画像生成モデルがないため us-west-2 を使用。
    プロンプトはClaudeで英語に変換してから渡す。

    Returns:
        (画像バイナリ, content_type)
    """
    prompt = _build_image_prompt(recipe_title, recipe_content)

    image_client = boto3.client(
        "bedrock-runtime",
        region_name=IMAGE_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    body = {
        "prompt": prompt,
        "output_format": "jpeg",
    }

    response = image_client.invoke_model(
        modelId=IMAGE_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )

    result = json.loads(response["body"].read())
    image_base64_str = result["images"][0]
    image_bytes = base64.b64decode(image_base64_str)
    return image_bytes, "image/jpeg"


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


@router.post("/generate-image", response_model=GenerateImageResponse)
async def generate_image(request: GenerateImageRequest):
    """
    レシピ名・内容をもとにBedrock Titan Image Generatorで完成料理の画像を生成する。
    生成結果はbase64で返すのでフロントエンドでプレビュー表示後、/upload に含めて保存する。
    """
    if not request.recipe_title.strip():
        raise HTTPException(status_code=400, detail="recipe_title が空です")
    try:
        image_bytes, content_type = _generate_image_with_bedrock(
            request.recipe_title, request.recipe_content
        )
        return GenerateImageResponse(
            image_base64=base64.b64encode(image_bytes).decode("utf-8"),
            content_type=content_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"画像生成エラー: {e}")


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

    # 画像が添付されている場合はS3に保存
    image_s3_key = None
    if request.image_base64:
        try:
            filename_stem = filename.removesuffix(".md")
            image_bytes = base64.b64decode(request.image_base64)
            image_s3_key = upload_recipe_image(filename_stem, image_bytes, request.image_ext)
        except Exception as e:
            # 画像保存失敗はレシピ保存の失敗扱いにしない（警告のみ）
            image_s3_key = None

    index_rebuilt = False
    try:
        index_rebuilt = _rebuild_index()
    except RuntimeError as e:
        return RecipeUploadResponse(
            s3_key=s3_key,
            filename=filename,
            index_rebuilt=False,
            image_s3_key=image_s3_key,
            message=f"S3への保存は成功しましたが、インデックス再構築に失敗しました: {e}",
        )

    msg = f"レシピ「{request.title}」をS3に保存し、インデックスを更新しました"
    if image_s3_key:
        msg += "（画像も保存しました）"

    return RecipeUploadResponse(
        s3_key=s3_key,
        filename=filename,
        index_rebuilt=index_rebuilt,
        image_s3_key=image_s3_key,
        message=msg,
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
        filename_stem = filename.removesuffix(".md")
        has_image = recipe_image_exists(filename_stem)
        return {"filename": filename, "content": content, "has_image": has_image}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"レシピが見つかりません: {e}")


@router.put("/{filename}", response_model=RecipeUpdateResponse)
async def update_recipe(filename: str, request: RecipeUpdateRequest):
    """
    既存レシピのMarkdown内容を上書き更新する。
    画像を同時に更新・削除することも可能。
    更新後はFAISSインデックスを自動再構築する。

    - delete_image=True の場合、既存画像をS3から削除する
    - image_base64 が指定された場合、画像を新規追加・差し替えする
    """
    if not filename.endswith(".md"):
        filename = f"{filename}.md"

    # レシピ本文の存在確認
    try:
        get_recipe(filename)
    except Exception:
        raise HTTPException(status_code=404, detail=f"レシピ '{filename}' が見つかりません")

    # Markdown を上書き保存
    try:
        s3_key = upload_recipe(filename, request.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3更新エラー: {e}")

    filename_stem = filename.removesuffix(".md")
    image_s3_key = None
    image_deleted = False

    # 画像削除が要求されている場合
    if request.delete_image:
        try:
            image_deleted = delete_recipe_image(filename_stem)
        except Exception:
            pass

    # 新しい画像がある場合はアップロード（削除後でも上書きアップ可能）
    if request.image_base64:
        try:
            image_bytes = base64.b64decode(request.image_base64)
            image_s3_key = upload_recipe_image(filename_stem, image_bytes, request.image_ext)
        except Exception as e:
            image_s3_key = None

    # インデックス再構築
    index_rebuilt = False
    try:
        index_rebuilt = _rebuild_index()
    except RuntimeError as e:
        return RecipeUpdateResponse(
            s3_key=s3_key,
            filename=filename,
            index_rebuilt=False,
            image_s3_key=image_s3_key,
            image_deleted=image_deleted,
            message=f"S3への更新は成功しましたが、インデックス再構築に失敗しました: {e}",
        )

    msg = f"レシピ「{request.title}」を更新し、インデックスを再構築しました"
    if image_s3_key:
        msg += "（画像も更新しました）"
    elif image_deleted:
        msg += "（画像を削除しました）"

    return RecipeUpdateResponse(
        s3_key=s3_key,
        filename=filename,
        index_rebuilt=index_rebuilt,
        image_s3_key=image_s3_key,
        image_deleted=image_deleted,
        message=msg,
    )


@router.post("/{filename}/image", response_model=RecipeImageUpdateResponse)
async def update_recipe_image_endpoint(filename: str, request: RecipeImageUpdateRequest):
    """
    既存レシピに画像を追加・差し替えする。
    レシピ本文の更新は行わず、画像のみ更新する（インデックス再構築不要）。
    """
    if not filename.endswith(".md"):
        filename = f"{filename}.md"

    # レシピ存在確認
    try:
        get_recipe(filename)
    except Exception:
        raise HTTPException(status_code=404, detail=f"レシピ '{filename}' が見つかりません")

    filename_stem = filename.removesuffix(".md")
    try:
        image_bytes = base64.b64decode(request.image_base64)
        image_s3_key = upload_recipe_image(filename_stem, image_bytes, request.image_ext)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"画像アップロードエラー: {e}")

    return RecipeImageUpdateResponse(
        image_s3_key=image_s3_key,
        message=f"レシピ '{filename}' の画像を更新しました",
    )


@router.delete("/{filename}/image")
async def delete_recipe_image_endpoint(filename: str):
    """既存レシピの画像をS3から削除する"""
    filename_stem = filename.removesuffix(".md")
    deleted = delete_recipe_image(filename_stem)
    if not deleted:
        raise HTTPException(status_code=404, detail="画像が見つかりません")
    return {"message": f"レシピ '{filename}' の画像を削除しました"}


@router.delete("/{filename}")
async def delete_recipe_endpoint(filename: str):
    """
    レシピをS3から削除し、FAISSインデックスを再構築する。
    関連する画像も同時に削除する。
    """
    if not filename.endswith(".md"):
        filename = f"{filename}.md"

    # レシピ存在確認
    try:
        get_recipe(filename)
    except Exception:
        raise HTTPException(status_code=404, detail=f"レシピ '{filename}' が見つかりません")

    # レシピ削除
    try:
        delete_recipe(filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3削除エラー: {e}")

    # 画像も削除（存在しない場合はスキップ）
    filename_stem = filename.removesuffix(".md")
    delete_recipe_image(filename_stem)

    # インデックス再構築
    try:
        _rebuild_index()
    except RuntimeError as e:
        return {
            "message": f"レシピ '{filename}' を削除しましたが、インデックス再構築に失敗しました: {e}",
            "index_rebuilt": False,
        }

    return {"message": f"レシピ '{filename}' を削除し、インデックスを更新しました", "index_rebuilt": True}


@router.get("/{filename}/image")
async def get_recipe_image_endpoint(filename: str):
    """指定レシピの完成画像をバイナリで返す"""
    filename_stem = filename.removesuffix(".md")
    result = get_recipe_image(filename_stem)
    if result is None:
        raise HTTPException(status_code=404, detail="画像が見つかりません")
    image_bytes, content_type = result
    return Response(content=image_bytes, media_type=content_type)
