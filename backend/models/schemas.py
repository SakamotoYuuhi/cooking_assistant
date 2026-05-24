from pydantic import BaseModel
from typing import List


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
