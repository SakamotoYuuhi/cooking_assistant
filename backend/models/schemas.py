from pydantic import BaseModel
from typing import List, Any


class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    history: List[Message]


class ClearRequest(BaseModel):
    session_id: str


class AgentRequest(BaseModel):
    session_id: str
    message: str


class AgentResponse(BaseModel):
    session_id: str
    reply: str
    tools_used: List[dict]  # 使用されたツールのログ
    history: List[Message]
