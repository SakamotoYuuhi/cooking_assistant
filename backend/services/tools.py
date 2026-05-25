"""
エージェントが呼び出せるツール定義。

各ツールは2つの要素で構成される：
1. TOOL_DEFINITIONS  - Claudeに渡すツールのスキーマ（何ができるかの説明）
2. execute_tool()    - 実際の処理を行う関数
"""

import json
from typing import Any
from .rag import search_recipes


# ---- ツールの定義（ClaudeのTool Use用スキーマ） ----

TOOL_DEFINITIONS = [
    {
        "name": "search_recipe",
        "description": (
            "ユーザーの食材・条件からレシピ集を検索し、関連するレシピを返す。"
            "食材名・料理ジャンル・調理時間などをキーワードに使える。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "検索クエリ（例: 鶏肉を使った和食、20分以内の簡単レシピ）",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "plan_meals",
        "description": (
            "指定した日数分の献立プランを作成する。"
            "食材リストと日数を受け取り、栄養バランスを考慮した献立を提案する。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ingredients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "利用可能な食材のリスト",
                },
                "days": {
                    "type": "integer",
                    "description": "献立を作る日数（1〜7）",
                },
            },
            "required": ["ingredients", "days"],
        },
    },
    {
        "name": "generate_shopping_list",
        "description": (
            "献立プランをもとに買い物リストを生成する。"
            "すでに持っている食材を差し引いた不足分のみリストアップする。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "meal_plan": {
                    "type": "string",
                    "description": "献立プランのテキスト",
                },
                "have_ingredients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "すでに持っている食材のリスト",
                },
            },
            "required": ["meal_plan", "have_ingredients"],
        },
    },
    {
        "name": "analyze_nutrition",
        "description": (
            "料理・食材・献立の栄養バランスを分析する。"
            "PFC（タンパク質・脂質・炭水化物）バランス、不足栄養素、改善提案を返す。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "meal_description": {
                    "type": "string",
                    "description": "分析する料理または献立の説明",
                }
            },
            "required": ["meal_description"],
        },
    },
]


# ---- ツールの実装（実際の処理） ----

def _tool_search_recipe(query: str) -> str:
    """レシピ集からRAG検索を実行する"""
    try:
        results = search_recipes(query, top_k=3)
        if not results:
            return "該当するレシピが見つかりませんでした。"

        output = []
        for i, r in enumerate(results, 1):
            output.append(f"=== レシピ {i}: {r['title']} (類似度: {r['score']:.2f}) ===")
            output.append(r["content"])
            output.append("")
        return "\n".join(output)
    except FileNotFoundError:
        return "レシピインデックスが未構築です。build_index.py を実行してください。"


def _tool_plan_meals(ingredients: list[str], days: int) -> str:
    """献立プランを生成する（LLMへの委任はagent.pyで行う）"""
    ingredients_str = "・".join(ingredients)
    return (
        f"[献立プラン生成リクエスト]\n"
        f"利用可能な食材: {ingredients_str}\n"
        f"プラン日数: {days}日分\n"
        f"→ 上記の情報をもとに栄養バランスを考慮した{days}日分の献立を提案してください。"
    )


def _tool_generate_shopping_list(meal_plan: str, have_ingredients: list[str]) -> str:
    """買い物リスト生成リクエストを整形する"""
    have_str = "・".join(have_ingredients) if have_ingredients else "なし"
    return (
        f"[買い物リスト生成リクエスト]\n"
        f"献立プラン:\n{meal_plan}\n\n"
        f"すでに持っている食材: {have_str}\n"
        f"→ 上記の献立に必要な食材から、すでに持っているものを除いた買い物リストを作成してください。"
    )


def _tool_analyze_nutrition(meal_description: str) -> str:
    """栄養分析リクエストを整形する"""
    return (
        f"[栄養分析リクエスト]\n"
        f"分析対象: {meal_description}\n"
        f"→ PFCバランス・不足しがちな栄養素・改善提案を分析してください。"
    )


def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """ツール名と入力を受け取り、対応する関数を実行して結果を返す"""
    if tool_name == "search_recipe":
        return _tool_search_recipe(tool_input["query"])
    elif tool_name == "plan_meals":
        return _tool_plan_meals(tool_input["ingredients"], tool_input["days"])
    elif tool_name == "generate_shopping_list":
        return _tool_generate_shopping_list(
            tool_input["meal_plan"], tool_input.get("have_ingredients", [])
        )
    elif tool_name == "analyze_nutrition":
        return _tool_analyze_nutrition(tool_input["meal_description"])
    else:
        return f"未定義のツール: {tool_name}"
