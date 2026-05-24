import boto3
import json
import os
from typing import List
from ..models.schemas import Message

SYSTEM_PROMPT = """あなたは親切で知識豊富なAI料理アシスタントです。

以下のルールに従って回答してください：

1. ユーザーが食材を伝えたら、その食材を使った献立・レシピを提案する
2. 栄養バランス（タンパク質・炭水化物・脂質・野菜）を考慮した提案を行う
3. 調理時間の目安を必ず記載する
4. ユーザーが調理時間の制限を伝えた場合は、それに合わせたレシピを提案する
5. 手順は番号付きで分かりやすく説明する
6. 日本語で回答する
7. 会話の流れを大切にし、前の質問や条件を踏まえて回答する

レシピ提案の際は以下のフォーマットを使うと読みやすいです：
- 料理名
- 調理時間
- 材料（人数分）
- 手順
- 栄養ポイント（任意）
"""

# 開発・テスト用: Haiku（安価）/ 本番切替: jp.anthropic.claude-sonnet-4-5-20250929-v1:0
MODEL_ID = "jp.anthropic.claude-haiku-4-5-20251001-v1:0"


def get_bedrock_client():
    return boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def chat_with_bedrock(history: List[Message], user_message: str) -> str:
    """会話履歴を含めてBedrockへリクエストを送り、返答を返す"""
    client = get_bedrock_client()

    messages = [{"role": msg.role, "content": msg.content} for msg in history]
    messages.append({"role": "user", "content": user_message})

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "system": SYSTEM_PROMPT,
        "messages": messages,
    }

    response = client.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )

    result = json.loads(response["body"].read())
    return result["content"][0]["text"]
