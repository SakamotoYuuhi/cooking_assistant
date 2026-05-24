from fastapi import APIRouter, HTTPException
from typing import Dict, List
from ..models.schemas import ChatRequest, ChatResponse, ClearRequest, Message
from ..services.bedrock import chat_with_bedrock

router = APIRouter(prefix="/chat", tags=["chat"])

# セッションIDをキーにした会話履歴のインメモリストア
# 本番ではDynamoDBやRedisに置き換える
session_store: Dict[str, List[Message]] = {}


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """ユーザーのメッセージを受け取り、Bedrockに投げて返答を返す"""
    session_id = request.session_id

    if session_id not in session_store:
        session_store[session_id] = []

    history = session_store[session_id]

    try:
        reply = chat_with_bedrock(history, request.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bedrock呼び出しエラー: {str(e)}")

    # 履歴を更新
    history.append(Message(role="user", content=request.message))
    history.append(Message(role="assistant", content=reply))
    session_store[session_id] = history

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        history=history,
    )


@router.post("/clear")
async def clear_history(request: ClearRequest):
    """指定セッションの会話履歴をリセットする"""
    session_store.pop(request.session_id, None)
    return {"message": "会話履歴をリセットしました", "session_id": request.session_id}


@router.get("/history/{session_id}", response_model=List[Message])
async def get_history(session_id: str):
    """指定セッションの会話履歴を取得する"""
    return session_store.get(session_id, [])
