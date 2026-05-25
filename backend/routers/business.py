from fastapi import APIRouter, HTTPException
from typing import Dict, List
from ..models.schemas import AgentRequest, AgentResponse, ClearRequest, Message
from ..services.business_agent import run_business_agent

router = APIRouter(prefix="/business", tags=["business"])

business_session_store: Dict[str, List[Message]] = {}


@router.post("", response_model=AgentResponse)
async def business_chat(request: AgentRequest):
    """社内ナレッジ検索エージェントのエンドポイント"""
    session_id = request.session_id

    if session_id not in business_session_store:
        business_session_store[session_id] = []

    history = business_session_store[session_id]

    try:
        reply, tools_used = run_business_agent(history, request.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"業務エージェント実行エラー: {str(e)}")

    history.append(Message(role="user", content=request.message))
    history.append(Message(role="assistant", content=reply))
    business_session_store[session_id] = history

    return AgentResponse(
        session_id=session_id,
        reply=reply,
        tools_used=tools_used,
        history=history,
    )


@router.post("/clear")
async def clear_business_history(request: ClearRequest):
    business_session_store.pop(request.session_id, None)
    return {"message": "業務セッション履歴をリセットしました", "session_id": request.session_id}
