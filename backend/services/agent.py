"""
Bedrock Tool Use（Function Calling）を使ったエージェント実行サービス。

動作フロー:
1. ユーザーメッセージ + ツール定義 を Claude に送る
2. Claude がツールを呼ぶ判断をしたら tool_use ブロックが返る
3. ツールを実行して結果を Claude に返す（tool_result）
4. Claude が最終的な回答を生成するまでループ
"""

import boto3
import json
import os
from typing import List
from ..models.schemas import Message
from .tools import TOOL_DEFINITIONS, execute_tool

MODEL_ID = "jp.anthropic.claude-sonnet-4-5-20250929-v1:0"  # Tool Use対応の高性能モデル
MAX_ITERATIONS = 10  # 無限ループ防止

AGENT_SYSTEM_PROMPT = """あなたは優秀なAI料理アシスタントエージェントです。

ユーザーの要望に応じて、以下のツールを組み合わせて最適な回答を提供してください：

- search_recipe: レシピ集から関連レシピを検索する
- plan_meals: 食材と日数から献立プランを作成する
- generate_shopping_list: 献立から買い物リストを生成する
- analyze_nutrition: 食事の栄養バランスを分析する

複数のツールが必要な場合は、順番に呼び出して総合的な回答を作成してください。
日本語で丁寧に回答してください。
"""


def get_bedrock_client():
    return boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def run_agent(history: List[Message], user_message: str) -> tuple[str, list[dict]]:
    """
    エージェントループを実行する。

    Returns:
        (最終的な回答テキスト, 使用されたツールのログ)
    """
    client = get_bedrock_client()

    # 会話履歴を構築
    messages = [{"role": msg.role, "content": msg.content} for msg in history]
    messages.append({"role": "user", "content": user_message})

    tool_use_log = []  # どのツールが呼ばれたか記録

    for iteration in range(MAX_ITERATIONS):
        response = client.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": AGENT_SYSTEM_PROMPT,
                "tools": TOOL_DEFINITIONS,
                "messages": messages,
            }),
        )

        result = json.loads(response["body"].read())
        stop_reason = result["stop_reason"]
        content_blocks = result["content"]

        # アシスタントの返答をメッセージ履歴に追加
        messages.append({"role": "assistant", "content": content_blocks})

        # ツール呼び出しがなければ終了
        if stop_reason == "end_turn":
            final_text = _extract_text(content_blocks)
            return final_text, tool_use_log

        # ツール呼び出しがある場合
        if stop_reason == "tool_use":
            tool_results = []

            for block in content_blocks:
                if block.get("type") != "tool_use":
                    continue

                tool_name = block["name"]
                tool_input = block["input"]
                tool_use_id = block["id"]

                # ツールを実行
                tool_output = execute_tool(tool_name, tool_input)

                tool_use_log.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "output_preview": tool_output[:100] + "..." if len(tool_output) > 100 else tool_output,
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": tool_output,
                })

            # ツール実行結果をメッセージに追加して次のループへ
            messages.append({"role": "user", "content": tool_results})

    return "エージェントの最大反復回数に達しました。", tool_use_log


def _extract_text(content_blocks: list) -> str:
    """content_blocksからテキストブロックだけを結合して返す"""
    texts = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            texts.append(block["text"])
    return "\n".join(texts)
