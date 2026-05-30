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
import logging
from typing import List
from ..models.schemas import Message
from .tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

# Langfuse クライアントの初期化（キーが未設定の場合はトレース無効）
_langfuse = None
try:
    from langfuse import Langfuse
    _lf_public = os.getenv("LANGFUSE_PUBLIC_KEY")
    _lf_secret = os.getenv("LANGFUSE_SECRET_KEY")
    _lf_host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    if _lf_public and _lf_secret:
        _langfuse = Langfuse(
            public_key=_lf_public,
            secret_key=_lf_secret,
            host=_lf_host,
        )
        logger.info("Langfuse トレーシングが有効です")
    else:
        logger.info("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY が未設定のため、トレーシングを無効化します")
except ImportError:
    logger.warning("langfuse パッケージが見つかりません。pip install langfuse でインストールしてください")

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


def run_agent(history: List[Message], user_message: str, session_id: str = "") -> tuple[str, list[dict]]:
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

    # Langfuse トレース開始
    trace = None
    if _langfuse:
        trace = _langfuse.trace(
            name="agent-run",
            input=user_message,
            session_id=session_id or None,
            metadata={"model": MODEL_ID, "history_length": len(history)},
        )

    total_input_tokens = 0
    total_output_tokens = 0

    try:
        for iteration in range(MAX_ITERATIONS):
            # LLM呼び出しのスパンを記録
            generation = None
            if trace:
                generation = trace.generation(
                    name=f"bedrock-invoke-{iteration}",
                    model=MODEL_ID,
                    input=messages,
                )

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

            # トークン使用量を集計
            usage = result.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens

            if generation:
                generation.end(
                    output=_extract_text(content_blocks) or str(content_blocks),
                    usage={"input": input_tokens, "output": output_tokens},
                    metadata={"stop_reason": stop_reason, "iteration": iteration},
                )

            # アシスタントの返答をメッセージ履歴に追加
            messages.append({"role": "assistant", "content": content_blocks})

            # ツール呼び出しがなければ終了
            if stop_reason == "end_turn":
                final_text = _extract_text(content_blocks)
                if trace:
                    trace.update(
                        output=final_text,
                        metadata={
                            "total_input_tokens": total_input_tokens,
                            "total_output_tokens": total_output_tokens,
                            "iterations": iteration + 1,
                            "tools_used": [t["tool"] for t in tool_use_log],
                        },
                    )
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

                    # ツール実行スパンを記録
                    tool_span = None
                    if trace:
                        tool_span = trace.span(
                            name=f"tool-{tool_name}",
                            input=tool_input,
                            metadata={"tool_use_id": tool_use_id},
                        )

                    # ツールを実行
                    tool_output = execute_tool(tool_name, tool_input)

                    if tool_span:
                        tool_span.end(output=tool_output[:500])

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

        if trace:
            trace.update(output="エージェントの最大反復回数に達しました。")
        return "エージェントの最大反復回数に達しました。", tool_use_log

    except Exception as e:
        if trace:
            trace.update(
                output=f"エラー: {str(e)}",
                metadata={"error": str(e)},
                level="ERROR",
            )
        raise
    finally:
        if _langfuse:
            _langfuse.flush()


def _extract_text(content_blocks: list) -> str:
    """content_blocksからテキストブロックだけを結合して返す"""
    texts = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            texts.append(block["text"])
    return "\n".join(texts)


EXTRACT_RECIPE_SYSTEM_PROMPT = """あなたはレシピ整形の専門家です。
以下の会話履歴を読んで、会話の中で最終的に決まった・提案されたレシピを抽出し、以下のMarkdown形式に整形してください。

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
- 会話の中で最終的に「これにしよう」「このレシピで」と決まった料理を優先して抽出する
- 複数のレシピが出てきた場合は、最後に決まったものを1つ抽出する
- 会話に不足している情報（調理時間・カテゴリなど）は内容から推測して補完する
- 絵文字・装飾文字は除去してシンプルなMarkdownにする
- 材料は「- 食材名: 分量」の形式に統一する
- 手順は番号付きリスト（1. 2. 3.）にする
- 計量単位は「小さじ」「大さじ」「カップ」などを正確にそのまま表記すること（省略・誤字厳禁）
- `~` や `~~` はMarkdown記法として特殊な意味を持つため、テキスト中に一切使用しないこと
- 出力はMarkdownのみ。説明文は不要。

また、最後の行に以下を追記してください（Markdownの外）：
TITLE: レシピ名
FILENAME: ファイル名（英数字とアンダースコアのみ、拡張子なし）

会話の中にレシピが見つからない場合は「RECIPE_NOT_FOUND」とだけ出力してください。
"""


def extract_recipe_from_history(history: List[Message]) -> dict:
    """
    会話履歴からレシピを抽出してMarkdown形式に整形する。

    Returns:
        {found, markdown, suggested_title, suggested_filename}
    """
    if not history:
        return {"found": False, "markdown": "", "suggested_title": "", "suggested_filename": ""}

    conversation_text = "\n".join(
        f"{'ユーザー' if msg.role == 'user' else 'アシスタント'}: {msg.content}"
        for msg in history
    )

    # Langfuse トレース
    trace = None
    generation = None
    if _langfuse:
        trace = _langfuse.trace(name="extract-recipe", input=conversation_text[:500])
        generation = trace.generation(
            name="bedrock-extract-recipe",
            model=MODEL_ID,
            input=[{"role": "user", "content": conversation_text}],
        )

    client = get_bedrock_client()
    response = client.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 3000,
            "system": EXTRACT_RECIPE_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": conversation_text}],
        }),
    )

    result_body = json.loads(response["body"].read())
    full_text = result_body["content"][0]["text"].strip()

    if generation:
        usage = result_body.get("usage", {})
        generation.end(
            output=full_text[:500],
            usage={"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)},
        )
    if _langfuse:
        _langfuse.flush()

    if full_text == "RECIPE_NOT_FOUND":
        return {"found": False, "markdown": "", "suggested_title": "", "suggested_filename": ""}

    lines = full_text.splitlines()
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

    if not title:
        for line in markdown_lines:
            if line.startswith("# "):
                title = line.lstrip("# ").strip()
                break

    if not filename:
        import re
        filename = re.sub(r"[^\w]", "_", title.lower())[:40].strip("_") or "recipe"

    return {
        "found": True,
        "markdown": markdown,
        "suggested_title": title,
        "suggested_filename": filename,
    }
