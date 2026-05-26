from pydantic import BaseModel
from typing import List, Any, Optional


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


class ExtractRecipeRequest(BaseModel):
    session_id: str


class ExtractRecipeResponse(BaseModel):
    found: bool
    markdown: str
    suggested_title: str
    suggested_filename: str


class GenerateImageRequest(BaseModel):
    recipe_title: str
    recipe_content: str


class GenerateImageResponse(BaseModel):
    image_base64: str
    content_type: str


class RecipeImageUploadRequest(BaseModel):
    filename_stem: str
    image_base64: str
    image_ext: str = "jpg"


class RecipeUpdateRequest(BaseModel):
    title: str
    content: str
    image_base64: Optional[str] = None
    image_ext: str = "jpg"
    delete_image: bool = False


class RecipeUpdateResponse(BaseModel):
    s3_key: str
    filename: str
    index_rebuilt: bool
    message: str
    image_s3_key: Optional[str] = None
    image_deleted: bool = False


class RecipeImageUpdateRequest(BaseModel):
    image_base64: str
    image_ext: str = "jpg"


class RecipeImageUpdateResponse(BaseModel):
    image_s3_key: str
    message: str
