"""
S3 → Lambda → EC2 インデックス自動再構築

トリガー: S3 バケットの cooking-assistant/recipes/ に .md ファイルがアップロードされた時
処理    : EC2 の FastAPI /admin/rebuild-index を呼び出してインデックス再構築を開始する

必要な環境変数（Lambda コンソールで設定）:
  EC2_API_URL    : http://<EC2のパブリックIP>/admin/rebuild-index
  REBUILD_API_KEY: EC2 の .env に設定した値と同じキー
"""

import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    api_url = os.environ.get("EC2_API_URL", "")
    api_key = os.environ.get("REBUILD_API_KEY", "")

    if not api_url or not api_key:
        logger.error("EC2_API_URL または REBUILD_API_KEY が未設定です")
        return {"statusCode": 500, "body": "環境変数が未設定です"}

    # S3 イベントからアップロードされたファイル情報を取得してログに記録
    for record in event.get("Records", []):
        bucket = record.get("s3", {}).get("bucket", {}).get("name", "")
        key = record.get("s3", {}).get("object", {}).get("key", "")
        logger.info("S3 イベント受信: s3://%s/%s", bucket, key)

        # .md ファイル以外はスキップ
        if not key.endswith(".md"):
            logger.info("スキップ: .md ファイルではありません (%s)", key)
            continue

        # EC2 の rebuild-index エンドポイントを呼び出す
        try:
            req = urllib.request.Request(
                url=api_url,
                method="POST",
                headers={
                    "X-Api-Key": api_key,
                    "Content-Type": "application/json",
                },
                data=json.dumps({"triggered_by": f"s3://{bucket}/{key}"}).encode(),
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
                logger.info("EC2 応答 (%s): %s", resp.status, body)

        except urllib.error.HTTPError as e:
            logger.error("EC2 呼び出しエラー (HTTP %s): %s", e.code, e.read().decode())
        except Exception as e:
            logger.error("EC2 呼び出し中に例外が発生: %s", e)

    return {"statusCode": 200, "body": "処理完了"}
