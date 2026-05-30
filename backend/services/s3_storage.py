"""
S3へのレシピ・画像保存・取得を担うサービス層。

バケット構造:
  s3://{S3_BUCKET_NAME}/{S3_RECIPES_PREFIX}{filename}.md
  例: s3://ai-agent-dev-sakamoto/cooking-assistant/recipes/chicken_teriyaki.md

  s3://{S3_BUCKET_NAME}/{S3_IMAGES_PREFIX}{filename_stem}.jpg
  例: s3://ai-agent-dev-sakamoto/cooking-assistant/images/chicken_teriyaki.jpg
"""

import boto3
import os
from typing import List
from pathlib import Path


def _get_s3_client():
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1"),
    )


def _bucket() -> str:
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise ValueError("S3_BUCKET_NAME が .env に設定されていません")
    return bucket


def _prefix() -> str:
    return os.getenv("S3_RECIPES_PREFIX", "cooking-assistant/recipes/")


def _image_prefix() -> str:
    base = os.getenv("S3_RECIPES_PREFIX", "cooking-assistant/recipes/")
    parent = base.rstrip("/").rsplit("/", 1)[0]
    return f"{parent}/images/"


def upload_recipe(filename: str, content: str) -> str:
    """
    レシピMarkdownをS3にアップロードする。

    Args:
        filename: 保存ファイル名（例: my_recipe.md）
        content:  Markdown形式のレシピ本文

    Returns:
        アップロードされたS3オブジェクトのキー
    """
    s3 = _get_s3_client()
    key = f"{_prefix()}{filename}"
    s3.put_object(
        Bucket=_bucket(),
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="text/markdown; charset=utf-8",
    )
    return key


def _extract_title_from_markdown(content: str, fallback: str) -> str:
    """Markdownの先頭 `# タイトル` 行からレシピ名を抽出する。見つからない場合は fallback を返す。"""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def list_recipes() -> List[dict]:
    """
    S3上のレシピ一覧を返す。各ファイルの先頭512バイトを取得してタイトルを抽出する。

    Returns:
        [{"filename": ..., "title": ..., "key": ..., "last_modified": ...}, ...]
    """
    s3 = _get_s3_client()
    prefix = _prefix()
    bucket = _bucket()
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    recipes = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        if key == prefix:
            continue
        filename = key.removeprefix(prefix)
        fallback_title = filename.removesuffix(".md").replace("_", " ")
        # 先頭512バイトだけ取得してタイトル行を探す（コスト・レイテンシ削減）
        try:
            head_resp = s3.get_object(Bucket=bucket, Key=key, Range="bytes=0-511")
            head_content = head_resp["Body"].read().decode("utf-8", errors="replace")
            title = _extract_title_from_markdown(head_content, fallback_title)
        except Exception:
            title = fallback_title
        recipes.append({
            "filename": filename,
            "title": title,
            "key": key,
            "last_modified": obj["LastModified"].isoformat(),
            "size_bytes": obj["Size"],
        })
    return recipes


def get_recipe(filename: str) -> str:
    """
    S3から指定レシピのMarkdown本文を取得する。

    Args:
        filename: ファイル名（例: my_recipe.md）

    Returns:
        Markdown文字列
    """
    s3 = _get_s3_client()
    key = f"{_prefix()}{filename}"
    response = s3.get_object(Bucket=_bucket(), Key=key)
    return response["Body"].read().decode("utf-8")


def upload_recipe_image(filename_stem: str, image_bytes: bytes, ext: str = "jpg") -> str:
    """
    レシピの完成画像をS3にアップロードする。

    Args:
        filename_stem: レシピファイル名から拡張子を除いたもの（例: chicken_karaage）
        image_bytes:   画像バイナリ
        ext:           拡張子（jpg / png）

    Returns:
        アップロードされたS3オブジェクトのキー
    """
    ext = ext.lstrip(".").lower()
    content_type = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    s3 = _get_s3_client()
    key = f"{_image_prefix()}{filename_stem}.{ext}"
    s3.put_object(
        Bucket=_bucket(),
        Key=key,
        Body=image_bytes,
        ContentType=content_type,
    )
    return key


def get_recipe_image(filename_stem: str) -> tuple[bytes, str] | None:
    """
    S3からレシピ画像を取得する。存在しない場合は None を返す。

    Returns:
        (画像バイナリ, content_type) または None
    """
    s3 = _get_s3_client()
    for ext in ("jpg", "jpeg", "png"):
        key = f"{_image_prefix()}{filename_stem}.{ext}"
        try:
            resp = s3.get_object(Bucket=_bucket(), Key=key)
            return resp["Body"].read(), resp["ContentType"]
        except s3.exceptions.NoSuchKey:
            continue
        except Exception:
            continue
    return None


def recipe_image_exists(filename_stem: str) -> bool:
    """レシピ画像がS3に存在するか確認する"""
    s3 = _get_s3_client()
    for ext in ("jpg", "jpeg", "png"):
        key = f"{_image_prefix()}{filename_stem}.{ext}"
        try:
            s3.head_object(Bucket=_bucket(), Key=key)
            return True
        except Exception:
            continue
    return False


def delete_recipe(filename: str) -> bool:
    """
    S3からレシピMarkdownを削除する。

    Args:
        filename: 削除するファイル名（例: my_recipe.md）

    Returns:
        削除成功の場合 True
    """
    s3 = _get_s3_client()
    key = f"{_prefix()}{filename}"
    s3.delete_object(Bucket=_bucket(), Key=key)
    return True


def delete_recipe_image(filename_stem: str) -> bool:
    """
    S3からレシピ画像を削除する。存在する拡張子（jpg/jpeg/png）を全て試行して削除する。

    Args:
        filename_stem: ファイル名から拡張子を除いたもの（例: chicken_karaage）

    Returns:
        1件以上削除された場合 True、存在しなかった場合 False
    """
    s3 = _get_s3_client()
    deleted = False
    for ext in ("jpg", "jpeg", "png"):
        key = f"{_image_prefix()}{filename_stem}.{ext}"
        try:
            s3.head_object(Bucket=_bucket(), Key=key)
            s3.delete_object(Bucket=_bucket(), Key=key)
            deleted = True
        except Exception:
            continue
    return deleted


def download_all_recipes(local_dir: Path) -> List[dict]:
    """
    S3上の全レシピをローカルディレクトリに保存する（インデックス再構築用）。

    Args:
        local_dir: 保存先ディレクトリ（存在しない場合は作成）

    Returns:
        保存されたレシピのメタデータリスト
    """
    local_dir.mkdir(parents=True, exist_ok=True)
    recipes = list_recipes()
    saved = []
    for recipe in recipes:
        content = get_recipe(recipe["filename"])
        local_path = local_dir / recipe["filename"]
        local_path.write_text(content, encoding="utf-8")
        saved.append({**recipe, "local_path": str(local_path)})
    return saved
