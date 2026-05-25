"""
業務ナレッジ検索エージェント。
agent.pyと同じ構造で、システムプロンプトとツールが業務向けに変わっているだけ。
"""

import boto3
import json
import os
from typing import List
from ..models.schemas import Message
from .business_rag import search_business_docs, build_business_context

MODEL_ID = "jp.anthropic.claude-sonnet-4-5-20250929-v1:0"

BUSINESS_SYSTEM_PROMPT = """あなたは社内ナレッジアシスタントです。

社内のFAQ・手順書・障害対応マニュアルをもとに、社員の質問に正確・簡潔に回答してください。

回答のルール：
1. 社内ナレッジに記載がある場合はその内容を優先する
2. 記載がない場合は「社内ドキュメントには記載がありません。担当部署へお問い合わせください」と伝える
3. 手順は番号付きリストで分かりやすく説明する
4. 重要な注意事項は強調（**太字**）で示す
5. 日本語で丁寧に回答する
"""

BUSINESS_TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": "社内ナレッジベース（FAQ・手順書・マニュアル）から関連ドキュメントを検索する",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "検索クエリ（例: 有給休暇の申請方法、本番デプロイ手順、障害対応フロー）",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "ナレッジベースに情報がなく、人間への引き継ぎが必要な場合に使う",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "エスカレーションが必要な理由"},
                "suggested_contact": {"type": "string", "description": "問い合わせ先の推薦（例: 人事部、ITヘルプデスク）"},
            },
            "required": ["reason", "suggested_contact"],
        },
    },
]


def _execute_business_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "search_knowledge_base":
        results = search_business_docs(tool_input["query"], top_k=3)
        return build_business_context(results) if results else "該当するドキュメントが見つかりませんでした。"
    elif tool_name == "escalate_to_human":
        return (
            f"[エスカレーション]\n"
            f"理由: {tool_input['reason']}\n"
            f"推奨連絡先: {tool_input['suggested_contact']}"
        )
    return f"未定義のツール: {tool_name}"


def run_business_agent(history: List[Message], user_message: str) -> tuple[str, list[dict]]:
    """業務ナレッジエージェントを実行する"""
    client = boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    messages = [{"role": msg.role, "content": msg.content} for msg in history]
    messages.append({"role": "user", "content": user_message})
    tool_use_log = []

    for _ in range(10):
        response = client.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": BUSINESS_SYSTEM_PROMPT,
                "tools": BUSINESS_TOOLS,
                "messages": messages,
            }),
        )

        result = json.loads(response["body"].read())
        stop_reason = result["stop_reason"]
        content_blocks = result["content"]
        messages.append({"role": "assistant", "content": content_blocks})

        if stop_reason == "end_turn":
            texts = [b["text"] for b in content_blocks if b.get("type") == "text"]
            return "\n".join(texts), tool_use_log

        if stop_reason == "tool_use":
            tool_results = []
            for block in content_blocks:
                if block.get("type") != "tool_use":
                    continue
                tool_name = block["name"]
                tool_input = block["input"]
                output = _execute_business_tool(tool_name, tool_input)
                tool_use_log.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "output_preview": output[:100] + "..." if len(output) > 100 else output,
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": output,
                })
            messages.append({"role": "user", "content": tool_results})

    return "エージェントの最大反復回数に達しました。", tool_use_log
