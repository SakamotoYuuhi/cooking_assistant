#!/bin/bash
# =============================================================================
# ローカル → EC2 デプロイスクリプト
# 実行方法: ./deploy/deploy.sh
# 事前準備:
#   1. deploy/config.sh に EC2_HOST と KEY_PATH を設定
#   2. EC2で setup_ec2.sh を一度実行済みであること
# =============================================================================

set -e

# ------------------------------------------------------------------------------
# 設定読み込み
# ------------------------------------------------------------------------------
CONFIG_FILE="$(dirname "$0")/config.sh"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "エラー: deploy/config.sh が見つかりません"
    echo "  cp deploy/config.sh.example deploy/config.sh を実行して設定してください"
    exit 1
fi

source "$CONFIG_FILE"

# 必須変数チェック
if [ -z "$EC2_HOST" ] || [ -z "$KEY_PATH" ]; then
    echo "エラー: config.sh に EC2_HOST と KEY_PATH を設定してください"
    exit 1
fi

EC2_USER="${EC2_USER:-ec2-user}"
APP_DIR="/opt/cooking_assistant"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo " AI料理アシスタント デプロイ開始"
echo "  接続先: ${EC2_USER}@${EC2_HOST}"
echo "  送信元: ${PROJECT_DIR}"
echo "=========================================="

# ------------------------------------------------------------------------------
# 1. 設定ファイルをEC2に転送（初回セットアップ用）
# ------------------------------------------------------------------------------
echo "[1/5] セットアップファイルを転送..."

scp -i "$KEY_PATH" -o StrictHostKeyChecking=no \
    "$SCRIPT_DIR/cooking-backend.service" \
    "$SCRIPT_DIR/cooking-frontend.service" \
    "$SCRIPT_DIR/cooking-assistant.conf" \
    "$SCRIPT_DIR/setup_ec2.sh" \
    "${EC2_USER}@${EC2_HOST}:/tmp/"

echo "[1/5] 完了"

# ------------------------------------------------------------------------------
# 2. アプリコードをEC2に転送（.env・キャッシュは除外）
# ------------------------------------------------------------------------------
echo "[2/5] アプリコードを転送..."

rsync -avz \
    --exclude='.env' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='data/index/' \
    --exclude='data/s3_recipes/' \
    --exclude='data/business_index/' \
    --exclude='deploy/' \
    -e "ssh -i $KEY_PATH -o StrictHostKeyChecking=no" \
    "$PROJECT_DIR/" \
    "${EC2_USER}@${EC2_HOST}:${APP_DIR}/"

echo "[2/5] 完了"

# ------------------------------------------------------------------------------
# 3. EC2上でパッケージインストール
# ------------------------------------------------------------------------------
echo "[3/5] 依存パッケージをインストール..."

ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no "${EC2_USER}@${EC2_HOST}" << 'REMOTE'
    sudo chown -R ec2-user:ec2-user /opt/cooking_assistant
    sudo chmod 600 /opt/cooking_assistant/.env
    /opt/cooking_assistant/venv/bin/pip install -q --upgrade pip
    /opt/cooking_assistant/venv/bin/pip install -q -r /opt/cooking_assistant/requirements.txt
    echo "  → パッケージインストール完了"
REMOTE

echo "[3/5] 完了"

# ------------------------------------------------------------------------------
# 4. サービス再起動
# ------------------------------------------------------------------------------
echo "[4/5] サービスを再起動..."

ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no "${EC2_USER}@${EC2_HOST}" << 'REMOTE'
    sudo systemctl restart cooking-backend
    sleep 3
    sudo systemctl restart cooking-frontend
    sleep 3
    echo "--- サービス状態 ---"
    sudo systemctl is-active cooking-backend  && echo "  backend:  稼働中" || echo "  backend:  停止"
    sudo systemctl is-active cooking-frontend && echo "  frontend: 稼働中" || echo "  frontend: 停止"
    sudo systemctl is-active nginx            && echo "  nginx:    稼働中" || echo "  nginx:    停止"
REMOTE

echo "[4/5] 完了"

# ------------------------------------------------------------------------------
# 5. 完了メッセージ
# ------------------------------------------------------------------------------
echo "[5/5] デプロイ完了"

echo ""
echo "=========================================="
echo " デプロイ完了！"
echo "=========================================="
echo ""
echo "  スマホ・ブラウザでアクセス:"
echo "  http://${EC2_HOST}"
echo ""
echo "  ログを確認する場合:"
echo "    ssh -i $KEY_PATH ${EC2_USER}@${EC2_HOST}"
echo "    sudo journalctl -u cooking-backend -f"
echo "    sudo journalctl -u cooking-frontend -f"
echo ""
