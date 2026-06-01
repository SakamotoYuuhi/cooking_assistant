"""
AWS Systems Manager Parameter Store から設定値を取得するユーティリティ。

優先順位:
  1. 環境変数（ローカル開発 / .env）
  2. SSM Parameter Store（本番EC2 / IAMロール経由で認証）

この設計により:
  - ローカル: .env に書いた値がそのまま使われる
  - EC2本番: .env なし・IAMロールで自動認証・SSMから安全に取得
"""

import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# SSM のパラメータパスプレフィックス
_SSM_PREFIX = "/cooking-assistant"

# 環境変数名 → SSM パラメータパス のマッピング
_ENV_TO_SSM: dict[str, str] = {
    "LANGFUSE_PUBLIC_KEY": f"{_SSM_PREFIX}/langfuse/public-key",
    "LANGFUSE_SECRET_KEY": f"{_SSM_PREFIX}/langfuse/secret-key",
    "LANGFUSE_HOST":       f"{_SSM_PREFIX}/langfuse/host",
    "REBUILD_API_KEY":     f"{_SSM_PREFIX}/rebuild-api-key",
}


@lru_cache(maxsize=None)
def _get_ssm_client():
    """SSMクライアントを生成（キャッシュして再利用）"""
    import boto3
    return boto3.client("ssm", region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1"))


def get_config(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    設定値を取得する。環境変数 → SSM の順で探す。

    Args:
        key:     環境変数名（例: "LANGFUSE_SECRET_KEY"）
        default: どちらにも見つからない場合のデフォルト値

    Returns:
        設定値の文字列、または default
    """
    # 1. 環境変数を優先
    env_val = os.getenv(key)
    if env_val:
        return env_val

    # 2. SSM から取得（マッピングにある場合のみ）
    ssm_path = _ENV_TO_SSM.get(key)
    if not ssm_path:
        return default

    try:
        client = _get_ssm_client()
        resp = client.get_parameter(Name=ssm_path, WithDecryption=True)
        value = resp["Parameter"]["Value"]
        # 取得した値を環境変数にキャッシュ（同一プロセス内での再取得を防ぐ）
        os.environ[key] = value
        logger.info("SSM から設定を取得しました: %s", ssm_path)
        return value
    except Exception as e:
        logger.warning("SSM からの取得に失敗しました (key=%s, path=%s): %s", key, ssm_path, e)
        return default
