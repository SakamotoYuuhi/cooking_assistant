# 🍳 AI料理アシスタント

AWS Bedrockを活用した「毎日使えるAI料理アシスタント」です。  
食材・条件を伝えると、レシピ検索・献立作成・買い物リスト生成・栄養分析を組み合わせて回答します。  
また、レシピをS3に保存・管理する機能も備えています。

---

## 概要

| 項目 | 内容 |
|---|---|
| 対話形式 | チャット（会話履歴あり） |
| AIモデル | Amazon Bedrock（Anthropic Claude） |
| レシピ検索 | RAG（FAISS + Titan Embeddings V2） |
| レシピ保存先 | Amazon S3 |
| バックエンド | FastAPI |
| フロントエンド | Streamlit |

---

## システム構成

```
cooking_assistant/
├── backend/
│   ├── main.py                   # FastAPIアプリ本体
│   ├── routers/
│   │   ├── agent.py              # エージェントチャットAPI
│   │   ├── chat.py               # RAGチャットAPI
│   │   ├── business.py           # 業務知識API（参考実装）
│   │   └── recipes.py            # レシピ管理API（S3連携・AI変換）
│   ├── services/
│   │   ├── agent.py              # Bedrockエージェント（Tool Use）
│   │   ├── bedrock.py            # Bedrock LLM呼び出し
│   │   ├── embedding.py          # Titan Embeddings V2
│   │   ├── rag.py                # FAISSインデックス検索
│   │   ├── s3_storage.py         # S3レシピ保存・取得
│   │   ├── tools.py              # エージェントツール定義
│   │   └── business_*.py         # 業務知識（参考実装）
│   └── models/
│       └── schemas.py            # Pydanticスキーマ
├── frontend/
│   └── app.py                    # Streamlit UI
├── scripts/
│   ├── build_index.py            # FAISSインデックス構築（S3対応）
│   └── build_business_index.py   # 業務用インデックス構築
├── data/
│   ├── index/                    # FAISSインデックス（.gitignore対象）
│   ├── s3_recipes/               # S3ダウンロードキャッシュ（.gitignore対象）
│   └── business_docs/            # 業務文書サンプル
├── .env                          # 環境変数（.gitignore対象）
├── .env.example                  # 環境変数テンプレート
└── requirements.txt              # 依存パッケージ
```

### アーキテクチャ概要

```
[Streamlit UI]
     ↓ HTTP
[FastAPI]
     ├── /agent  → BedrockエージェントがToolsを自律実行
     │               └── search_recipe / plan_meals / generate_shopping_list / analyze_nutrition
     ├── /chat   → RAGで関連レシピを検索してBedrockに投げる
     └── /recipes → S3保存・一覧取得・AI変換（Bedrock）
                         ↓
                    [Amazon S3]  ← レシピMarkdownを保存
                         ↓
                    [FAISS Index] ← インデックス再構築
                         ↑
               [Amazon Titan Embeddings V2]
```

---

## 機能一覧

### 🤖 料理エージェント
食材・要望を自然言語で入力すると、AIが必要なツールを自律的に選択・組み合わせて回答します。

| ツール | 説明 |
|---|---|
| `search_recipe` | FAISSでレシピ集を意味検索 |
| `plan_meals` | 食材と日数から献立プランを作成 |
| `generate_shopping_list` | 献立から不足食材の買い物リストを生成 |
| `analyze_nutrition` | 食事の栄養バランスを分析 |

**入力例**
- `鶏肉と豆腐がある。今日の夕食を提案して`
- `今週3日分の献立と買い物リストを作って。鶏肉・卵・玉ねぎはある`
- `昨日の夕食は唐揚げだった。栄養バランスを分析して改善案も教えて`

### 📖 レシピを追加

| タブ | 機能 |
|---|---|
| 🤖 AIでテキスト変換 | ChatGPT等の回答テキストをBedrockが自動でMarkdown形式に変換 → S3に保存 |
| ✏️ 手動で入力 | フォームでレシピを直接入力してS3に保存 |
| 📋 登録済みレシピ一覧 | S3に保存されているレシピを一覧表示・内容確認 |

レシピ保存後はFAISSインデックスが自動再構築され、エージェントのRAG検索に即反映されます。

---

## セットアップ

### 1. 前提条件

- Python 3.10 以上
- AWS アカウント（Bedrock モデルアクセス申請済み）
- S3バケット作成済み

### 2. AWS Bedrockのモデルアクセス

AWSコンソール → Amazon Bedrock → モデルアクセス から以下を有効化してください。

- `anthropic.claude-haiku-4-5` （または Sonnet）
- `amazon.titan-embed-text-v2:0`

### 3. S3バケット構成

```
s3://your-bucket-name/
└── cooking-assistant/
    └── recipes/      ← レシピMarkdownファイルの保存先
```

### 4. 依存パッケージのインストール

```bash
cd cooking_assistant
pip install -r requirements.txt
```

### 5. 環境変数の設定

`.env.example` をコピーして `.env` を作成してください。

```bash
cp .env.example .env
```

`.env` を編集：

```env
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_DEFAULT_REGION=ap-northeast-1
S3_BUCKET_NAME=your_bucket_name_here
S3_RECIPES_PREFIX=cooking-assistant/recipes/
```

### 6. FAISSインデックスの構築

S3にレシピファイルがある場合（推奨）：

```bash
python3 scripts/build_index.py
```

ローカルの `data/recipes/` を使う場合：

```bash
python3 scripts/build_index.py --local
```

---

## 起動方法

ターミナルを2つ開いて、それぞれ実行してください。

**バックエンド（FastAPI）**

```bash
cd cooking_assistant
uvicorn backend.main:app --reload --port 8000
```

**フロントエンド（Streamlit）**

```bash
cd cooking_assistant
streamlit run frontend/app.py
```

ブラウザで `http://localhost:8501` にアクセスしてください。

---

## APIエンドポイント一覧

| メソッド | パス | 説明 |
|---|---|---|
| `POST` | `/agent` | エージェントチャット |
| `POST` | `/agent/clear` | エージェント会話履歴リセット |
| `POST` | `/chat` | RAGチャット |
| `POST` | `/chat/clear` | チャット会話履歴リセット |
| `POST` | `/recipes/convert` | 生テキスト→Markdownレシピ変換（Bedrock） |
| `POST` | `/recipes/upload` | レシピをS3に保存＋インデックス再構築 |
| `GET` | `/recipes` | S3上のレシピ一覧取得 |
| `GET` | `/recipes/{filename}` | 指定レシピの内容取得 |
| `GET` | `/health` | ヘルスチェック |

インタラクティブなAPIドキュメントは `http://localhost:8000/docs` で確認できます。

---

## 開発ロードマップ

| フェーズ | 内容 | 状態 |
|---|---|---|
| Phase 1 | コアチャット機能（Bedrock・会話履歴・FastAPI・Streamlit） | ✅ 完了 |
| Phase 2 | RAG導入（Embeddings・FAISS・レシピ検索） | ✅ 完了 |
| Phase 3 | エージェント化（Bedrock Tool Use・複数ツール連携） | ✅ 完了 |
| Phase 4 | S3連携・レシピ管理・AI変換機能 | ✅ 完了 |

---

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| LLM | Amazon Bedrock (Anthropic Claude Haiku / Sonnet) |
| Embedding | Amazon Titan Embeddings V2 |
| ベクトル検索 | FAISS (faiss-cpu) |
| ストレージ | Amazon S3 |
| バックエンド | FastAPI + Uvicorn |
| フロントエンド | Streamlit |
| 言語 | Python 3.10+ |
