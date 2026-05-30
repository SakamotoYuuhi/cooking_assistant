import logging
import os

import watchtower
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path
from .routers import chat, agent, business, recipes, admin

# プロジェクトルートの .env を明示的に読み込む
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

# ── ロギング設定 ──────────────────────────────────────────────────────────────
_LOG_GROUP = os.getenv("CLOUDWATCH_LOG_GROUP", "/cooking-assistant/app")
_LOG_STREAM = os.getenv("CLOUDWATCH_LOG_STREAM", "api")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("cooking_assistant")

try:
    _cw_handler = watchtower.CloudWatchLogHandler(
        log_group_name=_LOG_GROUP,
        log_stream_name=_LOG_STREAM,
    )
    _cw_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(_cw_handler)
    logger.info("CloudWatch Logs ハンドラを設定しました (log_group=%s)", _LOG_GROUP)
except Exception as _e:
    logger.warning("CloudWatch Logs ハンドラの設定をスキップしました: %s", _e)
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI料理アシスタント API",
    description="食材から献立・レシピを提案するAIアシスタントのバックエンド",
    version="1.0.0",
)

_allow_origins = os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(agent.router)
app.include_router(business.router)
app.include_router(recipes.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return {"message": "AI料理アシスタント APIが起動中です"}


@app.get("/health")
async def health():
    return {"status": "ok"}
