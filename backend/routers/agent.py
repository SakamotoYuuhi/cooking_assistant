from fastapi import APIRouter, HTTPException
from typing import List
from ..models.schemas import AgentRequest, AgentResponse, ClearRequest, Message, ExtractRecipeRequest, ExtractRecipeResponse
from ..services.agent import run_agent, extract_recipe_from_history
from ..services.session_store import get_session, save_session, delete_session

router = APIRouter(prefix="/agent", tags=["agent"])

_PREFIX = "agent"


@router.post("", response_model=AgentResponse)
async def agent_chat(request: AgentRequest):
    """
    エージェントモードのエンドポイント。
    Claudeが自律的にツールを選択・実行して回答を生成する。
    """
    session_id = request.session_id
    history = get_session(session_id, _PREFIX)

    try:
        reply, tools_used = run_agent(history, request.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"エージェント実行エラー: {str(e)}")

    history.append(Message(role="user", content=request.message))
    history.append(Message(role="assistant", content=reply))
    save_session(session_id, _PREFIX, history)

    return AgentResponse(
        session_id=session_id,
        reply=reply,
        tools_used=tools_used,
        history=history,
    )


@router.post("/clear")
async def clear_agent_history(request: ClearRequest):
    """エージェントセッションの会話履歴をリセット"""
    delete_session(request.session_id, _PREFIX)
    return {"message": "エージェント履歴をリセットしました", "session_id": request.session_id}


@router.get("/history/{session_id}", response_model=List[Message])
async def get_agent_history(session_id: str):
    """指定セッションのエージェント会話履歴を取得する（フロントエンドのリロード復元用）"""
    return get_session(session_id, _PREFIX)


@router.post("/extract-recipe", response_model=ExtractRecipeResponse)
async def extract_recipe(request: ExtractRecipeRequest):
    """
    指定セッションの会話履歴からレシピを抽出してMarkdown形式に返す。
    フロントエンドでプレビュー・編集後に /recipes/upload で保存する想定。
    """
    history = get_session(request.session_id, _PREFIX)

    try:
        result = extract_recipe_from_history(history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"レシピ抽出エラー: {str(e)}")

    return ExtractRecipeResponse(
        found=result["found"],
        markdown=result["markdown"],
        suggested_title=result["suggested_title"],
        suggested_filename=result["suggested_filename"],
    )
