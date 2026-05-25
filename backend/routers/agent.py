from fastapi import APIRouter, HTTPException
from typing import Dict, List
from ..models.schemas import AgentRequest, AgentResponse, ClearRequest, Message
from ..services.agent import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])

# エージェント用セッションストア（chatとは別管理）
agent_session_store: Dict[str, List[Message]] = {}


@router.post("", response_model=AgentResponse)
async def agent_chat(request: AgentRequest):
    """
    エージェントモードのエンドポイント。
    Claudeが自律的にツールを選択・実行して回答を生成する。
    """
    session_id = request.session_id

    if session_id not in agent_session_store:
        agent_session_store[session_id] = []

    history = agent_session_store[session_id]

    try:
        reply, tools_used = run_agent(history, request.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"エージェント実行エラー: {str(e)}")

    history.append(Message(role="user", content=request.message))
    history.append(Message(role="assistant", content=reply))
    agent_session_store[session_id] = history

    return AgentResponse(
        session_id=session_id,
        reply=reply,
        tools_used=tools_used,
        history=history,
    )


@router.post("/clear")
async def clear_agent_history(request: ClearRequest):
    """エージェントセッションの会話履歴をリセット"""
    agent_session_store.pop(request.session_id, None)
    return {"message": "エージェント履歴をリセットしました", "session_id": request.session_id}
