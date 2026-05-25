from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path
from .routers import chat, agent, business, recipes

# プロジェクトルートの .env を明示的に読み込む
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(
    title="AI料理アシスタント API",
    description="食材から献立・レシピを提案するAIアシスタントのバックエンド",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番では特定のオリジンに絞る
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(agent.router)
app.include_router(business.router)
app.include_router(recipes.router)


@app.get("/")
async def root():
    return {"message": "AI料理アシスタント APIが起動中です"}


@app.get("/health")
async def health():
    return {"status": "ok"}
