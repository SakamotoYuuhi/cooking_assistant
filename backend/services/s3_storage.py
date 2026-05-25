"""
S3へのレシピ保存・取得を担うサービス層。

バケット構造:
  s3://{S3_BUCKET_NAME}/{S3_RECIPES_PREFIX}{filename}.md
  例: s3://ai-agent-dev-sakamoto/cooking-assistant/recipes/chicken_teriyaki.md
"""

import boto3
import os
from typing import List
from pathlib import Path


def _get_s3_client():
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def _bucket() -> str:
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise ValueError("S3_BUCKET_NAME が .env に設定されていません")
    return bucket


def _prefix() -> str:
    return os.getenv("S3_RECIPES_PREFIX", "cooking-assistant/recipes/")


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


def list_recipes() -> List[dict]:
    """
    S3上のレシピ一覧を返す。

    Returns:
        [{"filename": ..., "key": ..., "last_modified": ...}, ...]
    """
    s3 = _get_s3_client()
    prefix = _prefix()
    response = s3.list_objects_v2(Bucket=_bucket(), Prefix=prefix)
    recipes = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        if key == prefix:
            continue
        recipes.append({
            "filename": key.removeprefix(prefix),
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
