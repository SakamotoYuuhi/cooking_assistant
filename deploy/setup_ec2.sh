#!/bin/bash
# =============================================================================
# EC2 初期セットアップスクリプト
# 対象OS: Amazon Linux 2023 / Ubuntu 22.04
# 実行方法: EC2にSSH接続後に実行
#   chmod +x setup_ec2.sh && sudo ./setup_ec2.sh
# =============================================================================

set -e

echo "=========================================="
echo " AI料理アシスタント EC2セットアップ開始"
echo "=========================================="

# ------------------------------------------------------------------------------
# 1. システムアップデートと基本パッケージのインストール
# ------------------------------------------------------------------------------
echo "[1/7] システムアップデート..."

# OS判定
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
fi

if [ "$OS" = "ubuntu" ]; then
    apt-get update -y
    apt-get install -y python3 python3-pip python3-venv nginx git curl
else
    # Amazon Linux 2023
    dnf update -y
    dnf install -y python3 python3-pip nginx git curl
fi

echo "[1/7] 完了"

# ------------------------------------------------------------------------------
# 2. アプリ用ユーザー作成
# ------------------------------------------------------------------------------
echo "[2/7] アプリ用ユーザー作成..."

if ! id "appuser" &>/dev/null; then
    useradd -m -s /bin/bash appuser
    echo "  → ユーザー 'appuser' を作成しました"
else
    echo "  → ユーザー 'appuser' は既に存在します"
fi

# アプリディレクトリ作成
mkdir -p /opt/cooking_assistant
chown appuser:appuser /opt/cooking_assistant

echo "[2/7] 完了"

# ------------------------------------------------------------------------------
# 3. Python仮想環境のセットアップ
# ------------------------------------------------------------------------------
echo "[3/7] Python仮想環境のセットアップ..."

su - appuser -c "python3 -m venv /opt/cooking_assistant/venv"

echo "[3/7] 完了"

# ------------------------------------------------------------------------------
# 4. systemdサービスの配置
# ------------------------------------------------------------------------------
echo "[4/7] systemdサービスの配置..."

cp /tmp/cooking-backend.service /etc/systemd/system/cooking-backend.service
cp /tmp/cooking-frontend.service /etc/systemd/system/cooking-frontend.service

systemctl daemon-reload
systemctl enable cooking-backend
systemctl enable cooking-frontend

echo "[4/7] 完了"

# ------------------------------------------------------------------------------
# 5. Nginx設定
# ------------------------------------------------------------------------------
echo "[5/7] Nginx設定..."

cp /tmp/cooking-assistant.conf /etc/nginx/conf.d/cooking-assistant.conf

# デフォルト設定を無効化（競合防止）
if [ -f /etc/nginx/sites-enabled/default ]; then
    rm /etc/nginx/sites-enabled/default
fi

nginx -t && echo "  → Nginx設定ファイルのシンタックスOK"

systemctl enable nginx
systemctl restart nginx

echo "[5/7] 完了"

# ------------------------------------------------------------------------------
# 6. ファイアウォール設定（ポート80のみ開放）
# ------------------------------------------------------------------------------
echo "[6/7] ファイアウォール設定..."

# セキュリティグループでの設定を想定（AWSコンソールで設定）
# 念のためOS側のfirewallも確認
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-service=http
    firewall-cmd --reload
    echo "  → firewalld: ポート80を開放しました"
else
    echo "  → ファイアウォールはAWSセキュリティグループで管理してください"
fi

echo "[6/7] 完了"

# ------------------------------------------------------------------------------
# 7. 完了メッセージ
# ------------------------------------------------------------------------------
echo "[7/7] セットアップ完了"

echo ""
echo "=========================================="
echo " セットアップ完了！"
echo "=========================================="
echo ""
echo "次のステップ："
echo "  1. ローカルから deploy.sh を実行してコードをデプロイ"
echo "  2. EC2の /opt/cooking_assistant/ に .env ファイルを作成"
echo "  3. サービスを起動:"
echo "       sudo systemctl start cooking-backend"
echo "       sudo systemctl start cooking-frontend"
echo "  4. ブラウザで http://<EC2のパブリックIP> にアクセス"
echo ""
