from fastapi import APIRouter, HTTPException
from typing import List
from ..models.schemas import ChatRequest, ChatResponse, ClearRequest, Message
from ..services.bedrock import chat_with_bedrock
from ..services.rag import search_recipes, build_rag_context
from ..services.session_store import get_session, save_session, delete_session

router = APIRouter(prefix="/chat", tags=["chat"])

_PREFIX = "chat"


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """ユーザーのメッセージを受け取り、RAGで関連レシピを検索してBedrockに投げて返答を返す"""
    session_id = request.session_id
    history = get_session(session_id, _PREFIX)

    # RAGでレシピ検索（インデックス未構築の場合はスキップしてフォールバック）
    rag_context = ""
    try:
        retrieved = search_recipes(request.message, top_k=3)
        rag_context = build_rag_context(retrieved)
    except FileNotFoundError:
        pass  # インデックス未構築時はRAGなしで回答
    except Exception:
        pass  # RAGエラー時もフォールバック

    # RAGコンテキストをユーザーメッセージに付加
    augmented_message = request.message
    if rag_context:
        augmented_message = f"{rag_context}\n\n【ユーザーの質問】\n{request.message}"

    try:
        reply = chat_with_bedrock(history, augmented_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bedrock呼び出しエラー: {str(e)}")

    # 履歴を更新してDynamoDBに保存
    history.append(Message(role="user", content=request.message))
    history.append(Message(role="assistant", content=reply))
    save_session(session_id, _PREFIX, history)

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        history=history,
    )


@router.post("/clear")
async def clear_history(request: ClearRequest):
    """指定セッションの会話履歴をリセットする"""
    delete_session(request.session_id, _PREFIX)
    return {"message": "会話履歴をリセットしました", "session_id": request.session_id}


@router.get("/history/{session_id}", response_model=List[Message])
async def get_history(session_id: str):
    """指定セッションの会話履歴を取得する"""
    return get_session(session_id, _PREFIX)
