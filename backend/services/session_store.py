"""
DynamoDB を使ったセッション（会話履歴）の永続化サービス。

テーブル設計:
  テーブル名 : ${DYNAMODB_TABLE_NAME}（デフォルト: cooking-assistant-sessions）
  パーティションキー: session_id (String)
    - chat セッション  : "chat_{session_id}"
    - agent セッション : "agent_{session_id}"
  TTL属性    : ttl (Number / Unix秒)  ← DynamoDBコンソールでTTLを有効化すること

AWS コンソールでの事前作業:
  1. DynamoDB → テーブルの作成
       テーブル名       : cooking-assistant-sessions
       パーティションキー: session_id（文字列）
  2. 「追加設定」タブ → TTL → 属性名 "ttl" で有効化
  3. EC2インスタンスのIAMロールに AmazonDynamoDBFullAccess をアタッチ
"""

import boto3
import json
import os
import time
from datetime import datetime, timezone
from typing import List

from ..models.schemas import Message

SESSION_TTL_DAYS = 7  # セッションの有効期限（日）


def _get_client():
    return boto3.client(
        "dynamodb",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1"),
    )


def _table_name() -> str:
    return os.getenv("DYNAMODB_TABLE_NAME", "cooking-assistant-sessions")


def _session_key(session_id: str, prefix: str) -> str:
    """DynamoDB上のキーを生成する（例: "chat_abc-123"）"""
    return f"{prefix}_{session_id}"


def get_session(session_id: str, prefix: str) -> List[Message]:
    """
    DynamoDBから会話履歴を取得する。
    セッションが存在しない場合は空リストを返す。

    Args:
        session_id: フロントエンドのセッションID
        prefix:     "chat" または "agent"
    """
    try:
        client = _get_client()
        response = client.get_item(
            TableName=_table_name(),
            Key={"session_id": {"S": _session_key(session_id, prefix)}},
        )
        item = response.get("Item")
        if not item:
            return []
        history_data = json.loads(item["history"]["S"])
        return [Message(role=m["role"], content=m["content"]) for m in history_data]
    except Exception:
        # DynamoDB未設定・接続エラー時は空リストを返してフォールバック
        return []


def save_session(session_id: str, prefix: str, history: List[Message]) -> None:
    """
    会話履歴をDynamoDBに保存する。
    既存のアイテムは上書きされる。TTLは保存のたびにリセットされる。
    DynamoDB未設定・権限不足・接続エラー時はスキップして処理を続行する。

    Args:
        session_id: フロントエンドのセッションID
        prefix:     "chat" または "agent"
        history:    保存する会話履歴
    """
    try:
        client = _get_client()
        ttl = int(time.time()) + SESSION_TTL_DAYS * 24 * 60 * 60
        history_data = [{"role": m.role, "content": m.content} for m in history]
        client.put_item(
            TableName=_table_name(),
            Item={
                "session_id": {"S": _session_key(session_id, prefix)},
                "history": {"S": json.dumps(history_data, ensure_ascii=False)},
                "ttl": {"N": str(ttl)},
                "updated_at": {"S": datetime.now(timezone.utc).isoformat()},
            },
        )
    except Exception:
        # DynamoDB未設定・権限不足・接続エラー時はスキップ（会話は続行）
        pass


def delete_session(session_id: str, prefix: str) -> None:
    """
    会話履歴をDynamoDBから削除する。
    DynamoDB未設定・権限不足・接続エラー時はスキップして処理を続行する。

    Args:
        session_id: フロントエンドのセッションID
        prefix:     "chat" または "agent"
    """
    try:
        client = _get_client()
        client.delete_item(
            TableName=_table_name(),
            Key={"session_id": {"S": _session_key(session_id, prefix)}},
        )
    except Exception:
        pass
