# EC2デプロイ手順

スマホ・外部ブラウザからAI料理アシスタントを利用するためのデプロイ手順です。

---

## 構成図

```
[スマホブラウザ]
      ↓ HTTP (ポート80)
[EC2 - Nginx]
  ├── / → Streamlit (127.0.0.1:8501)
  └── /api/ → FastAPI  (127.0.0.1:8000)
                  ↓
         [AWS Bedrock / S3]
```

---

## 必要なもの

- AWS EC2インスタンス（**t3.micro** 推奨、月額$8〜10）
- SSHキーペア（.pem ファイル）
- EC2のセキュリティグループでポート **22（SSH）** と **80（HTTP）** を開放済み

---

## STEP 1: EC2インスタンスの起動（AWSコンソール）

| 項目 | 設定値 |
|---|---|
| AMI | Amazon Linux 2023（または Ubuntu 22.04） |
| インスタンスタイプ | t3.micro |
| ストレージ | 20GB（gp3） |
| セキュリティグループ | SSH(22), HTTP(80) を自分のIPから許可 |

---

## STEP 2: デプロイ設定ファイルの作成

```bash
cd cooking_assistant
cp deploy/config.sh.example deploy/config.sh
```

`deploy/config.sh` を編集：

```bash
EC2_HOST="<Elastic IP>"                       # Elastic IP
KEY_PATH="~/.ssh/cooking-assistant-key.pem"   # SSHキーのパス
EC2_USER="ec2-user"                           # Amazon Linux 2023
```

---

## STEP 3: EC2の初期セットアップ（初回のみ）

EC2にSSH接続してセットアップスクリプトを実行します。

```bash
# SSHキーのパーミッション設定
chmod 400 ~/.ssh/cooking-assistant-key.pem

# EC2に接続
ssh -i ~/.ssh/cooking-assistant-key.pem ec2-user@<Elastic IP>
```

EC2上で実行：

```bash
# セットアップファイルをEC2に転送（ローカルから）
scp -i ~/.ssh/cooking-assistant-key.pem \
    deploy/setup_ec2.sh \
    deploy/cooking-backend.service \
    deploy/cooking-frontend.service \
    deploy/cooking-assistant.conf \
    ec2-user@<Elastic IP>:/tmp/

# EC2上でセットアップ実行
chmod +x /tmp/setup_ec2.sh
sudo /tmp/setup_ec2.sh
```

---

## STEP 4: .envファイルをEC2に作成

```bash
ssh -i ~/.ssh/cooking-assistant-key.pem ec2-user@<Elastic IP>
sudo nano /opt/cooking_assistant/.env
```

以下の内容を入力：

```env
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_DEFAULT_REGION=ap-northeast-1
S3_BUCKET_NAME=your_bucket_name_here
S3_RECIPES_PREFIX=cooking-assistant/recipes/
```

> **セキュリティのヒント**: IAMロールをEC2に付与すればアクセスキーが不要になります（推奨）。

---

## STEP 5: デプロイ実行（ローカルから）

```bash
cd cooking_assistant
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

デプロイスクリプトが以下を自動実行します：
1. コードをEC2に転送（rsync）
2. 依存パッケージをインストール
3. サービスを再起動

---

## STEP 6: 動作確認

スマホ・ブラウザで以下にアクセス：

```
http://<Elastic IP>
```

---

## サービス管理コマンド

SSH接続後に使用できるコマンドです。

```bash
ssh -i ~/.ssh/cooking-assistant-key.pem ec2-user@<Elastic IP>
```

```bash
# サービス状態確認
sudo systemctl status cooking-backend
sudo systemctl status cooking-frontend
sudo systemctl status nginx

# ログリアルタイム確認
sudo journalctl -u cooking-backend -f
sudo journalctl -u cooking-frontend -f

# サービス再起動
sudo systemctl restart cooking-backend
sudo systemctl restart cooking-frontend
```

---

## コード更新時のデプロイ

コードを変更したら、ローカルから再度デプロイするだけです：

```bash
./deploy/deploy.sh
```

---

## deploy/ ディレクトリ構成

```
deploy/
├── README.md                    # この手順書
├── config.sh.example            # デプロイ設定テンプレート
├── config.sh                    # デプロイ設定（.gitignore対象）
├── setup_ec2.sh                 # EC2初期セットアップスクリプト（初回のみ）
├── deploy.sh                    # コードデプロイスクリプト
├── cooking-assistant.conf       # Nginx設定
├── cooking-backend.service      # systemd: FastAPI
└── cooking-frontend.service     # systemd: Streamlit
```
