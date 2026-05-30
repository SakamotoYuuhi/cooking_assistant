"""
管理者用エンドポイント。
Lambda などの内部サービスから呼び出されることを想定。
X-Api-Key ヘッダーで簡易認証する。
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("cooking_assistant")

_PROJECT_DIR = Path(__file__).resolve().parents[2]
_VENV_PYTHON = _PROJECT_DIR / "venv" / "bin" / "python3"
_BUILD_SCRIPT = _PROJECT_DIR / "scripts" / "build_index.py"


def _api_key_valid(api_key: str | None) -> bool:
    expected = os.getenv("REBUILD_API_KEY", "")
    if not expected:
        logger.warning("REBUILD_API_KEY が未設定です。/admin/rebuild-index は無効化されています。")
        return False
    return api_key == expected


def _run_build_index() -> None:
    python = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable
    logger.info("インデックス再構築を開始します: %s", _BUILD_SCRIPT)
    try:
        result = subprocess.run(
            [python, str(_BUILD_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_DIR),
        )
        if result.returncode == 0:
            logger.info("インデックス再構築が完了しました")
            # メモリ上のインデックスをリロード
            from ..services.rag import reload_index
            reload_index()
            logger.info("RAG インデックスをリロードしました")
        else:
            logger.error("インデックス再構築に失敗しました: %s", result.stderr)
    except Exception as e:
        logger.exception("インデックス再構築中に例外が発生しました: %s", e)


@router.post("/rebuild-index", status_code=202)
async def rebuild_index(
    background_tasks: BackgroundTasks,
    x_api_key: str | None = Header(default=None),
):
    """
    S3 → Lambda 経由で呼び出されるインデックス再構築エンドポイント。
    バックグラウンドで build_index.py を実行し、即座に 202 を返す。
    """
    if not _api_key_valid(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    background_tasks.add_task(_run_build_index)
    logger.info("インデックス再構築をキューに追加しました")
    return {"status": "rebuild started"}
