import streamlit as st
import requests
import uuid
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

BACKEND_URL = "http://localhost:8000"

st.set_page_config(
    page_title="AI料理アシスタント",
    page_icon="🍳",
    layout="wide",                    # PC: wide レイアウト（変更なし）
    initial_sidebar_state="auto",     # PC: サイドバー表示 / モバイル: 自動折りたたみ
)

# ==============================================================================
# レスポンシブCSS
#   PC   (min-width: 769px) : 従来どおり wide + サイドバー
#   Mobile (max-width: 768px): centered 幅・縦積みカラム・大きいタップ領域
# ==============================================================================
st.markdown("""
<style>
/* =========================================================
   共通
   ========================================================= */
/* iOSでフォーカス時に自動ズームさせない最小フォントサイズ */
.stTextInput input,
.stTextArea textarea,
.stSelectbox select,
.stNumberInput input {
    font-size: 16px;
}

/* =========================================================
   PC / タブレット レイアウト（431px 以上）: 変更なし
   ========================================================= */

/* =========================================================
   スマホ レイアウト（430px 以下 = iPhone最大幅）
   ========================================================= */
@media (max-width: 430px) {
    /* --- コンテナ幅・余白 --- */
    .block-container {
        max-width: 100% !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        padding-top: 0.5rem !important;
    }

    /* --- PC専用のサイドバーモード選択ラベルを縮小 --- */
    section[data-testid="stSidebar"] {
        min-width: 0 !important;
        width: 260px !important;
    }

    /* --- 2カラムを縦積みに --- */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="stVerticalBlock"] {
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }

    /* --- ボタン: タップしやすい最小高さ 48px --- */
    .stButton > button {
        min-height: 48px !important;
        font-size: 15px !important;
        border-radius: 10px !important;
        padding: 0.4rem 0.8rem !important;
    }
    .stButton > button[kind="primary"] {
        font-size: 16px !important;
        font-weight: bold !important;
    }

    /* --- チャット入力 --- */
    .stChatInput textarea {
        font-size: 16px !important;
    }

    /* --- タブ: 横スクロール対応 --- */
    .stTabs [data-baseweb="tab-list"] {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        gap: 2px !important;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 13px !important;
        padding: 6px 10px !important;
        white-space: nowrap !important;
    }

    /* --- タイトル文字サイズ --- */
    h1 { font-size: 1.4rem !important; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 1.05rem !important; }

    /* expander ヘッダー */
    .streamlit-expanderHeader { font-size: 14px !important; }
}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# セッション初期化
# ==============================================================================
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = []

# ==============================================================================
# サイドバー（PC: 常時表示 / モバイル: ハンバーガーメニューで開く）
# ==============================================================================
with st.sidebar:
    st.title("🍳 AI料理アシスタント")
    st.markdown("---")

    mode = st.radio(
        "モード選択",
        ["🤖 料理エージェント", "📖 レシピを追加"],
        key="mode_selector",
    )

    st.markdown("---")

    if mode == "🤖 料理エージェント":
        st.markdown("### 例文")
        agent_examples = [
            "鶏肉と豆腐がある。今日の夕食を提案して",
            "今週3日分の献立と買い物リストを作って。鶏肉・卵・玉ねぎはある",
            "20分以内でできる夕食レシピを教えて",
            "昨日の夕食は唐揚げだった。栄養バランスを分析して改善案も教えて",
            "冷蔵庫に鮭・ほうれん草・豆腐がある。献立と不足食材リストを出して",
            "タンパク質多めのレシピがほしい",
        ]
        for ex in agent_examples:
            if st.button(ex, use_container_width=True, key=f"agent_{ex}"):
                st.session_state.pending_agent_message = ex

        st.markdown("---")
        if st.button("🗑️ 会話をリセット", use_container_width=True, type="secondary"):
            requests.post(
                f"{BACKEND_URL}/agent/clear",
                json={"session_id": st.session_state.session_id},
            )
            st.session_state.agent_messages = []
            st.rerun()

    st.caption(f"セッションID: `{st.session_state.session_id[:8]}...`")



# ==============================================================================
# 🤖 料理エージェント
# ==============================================================================
if mode == "🤖 料理エージェント":
    st.title("🤖 料理エージェント")
    st.caption("食材・条件を伝えると、レシピ検索・献立作成・買い物リスト・栄養分析を組み合わせて回答します")

    for msg in st.session_state.agent_messages:
        with st.chat_message("🧑" if msg["role"] == "user" else "🍳"):
            st.markdown(msg["content"])
            if msg.get("tools_used"):
                with st.expander(f"🔧 使用ツール（{len(msg['tools_used'])}個）"):
                    for t in msg["tools_used"]:
                        st.markdown(f"**{t['tool']}**")
                        st.json(t["input"])

    pending_agent = st.session_state.pop("pending_agent_message", None)
    agent_input = st.chat_input(
        "食材や要望を入力してください（例: 鶏肉と玉ねぎで20分以内の夕食を提案して）"
    )
    agent_message = agent_input or pending_agent

    if agent_message:
        st.session_state.agent_messages.append({"role": "user", "content": agent_message})
        with st.chat_message("🧑"):
            st.markdown(agent_message)

        with st.chat_message("🍳"):
            with st.spinner("考え中..."):
                try:
                    response = requests.post(
                        f"{BACKEND_URL}/agent",
                        json={
                            "session_id": st.session_state.session_id,
                            "message": agent_message,
                        },
                        timeout=60,
                    )
                    response.raise_for_status()
                    data = response.json()
                    reply = data["reply"]
                    tools_used = data.get("tools_used", [])
                except requests.exceptions.ConnectionError:
                    reply = "バックエンドに接続できません。uvicornが起動しているか確認してください。"
                    tools_used = []
                except Exception as e:
                    reply = f"エラー: {str(e)}"
                    tools_used = []

            st.markdown(reply)
            if tools_used:
                with st.expander(f"🔧 使用ツール（{len(tools_used)}個）"):
                    for t in tools_used:
                        st.markdown(f"**{t['tool']}**")
                        st.json(t["input"])

        st.session_state.agent_messages.append({
            "role": "assistant",
            "content": reply,
            "tools_used": tools_used,
        })


# ==============================================================================
# 📖 レシピを追加
# ==============================================================================
elif mode == "📖 レシピを追加":
    st.title("📖 レシピを追加")
    st.caption("新しいレシピをS3に保存します。保存後はRAG検索の対象として自動的に利用できます。")

    tab_convert, tab_add, tab_list = st.tabs(["🤖 AIでテキスト変換", "✏️ 手動で入力", "📋 登録済みレシピ一覧"])

    # ---------- AIでテキスト変換 ----------
    with tab_convert:
        st.markdown("### ChatGPTなどのレシピテキストをMarkdown形式に変換")
        st.caption("AIの回答・ブログ記事・メモなど、どんな形式のテキストでもOKです。Bedrockが自動でレシピ形式に整形します。")

        raw_text = st.text_area(
            "変換したいテキストを貼り付けてください",
            placeholder="例:\nほうれん草とベーコンのパスタ\n■ 材料\nパスタ 200g\nほうれん草 1束\n...",
            height=280,
            key="convert_raw_text",
        )

        if st.button("🤖 AIで変換する", type="primary", use_container_width=True, key="btn_convert"):
            if not raw_text.strip():
                st.error("テキストを入力してください")
            else:
                with st.spinner("Bedrockがレシピを整形中...（10〜20秒）"):
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/recipes/convert",
                            json={"raw_text": raw_text},
                            timeout=60,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        st.session_state["converted_markdown"] = data["markdown"]
                        st.session_state["converted_title"] = data["suggested_title"]
                        st.session_state["converted_filename"] = data["suggested_filename"]
                        st.success("変換完了！内容を確認・編集してから保存してください。")
                    except requests.exceptions.ConnectionError:
                        st.error("バックエンドに接続できません。uvicornが起動しているか確認してください。")
                    except Exception as e:
                        st.error(f"エラー: {str(e)}")

        if st.session_state.get("converted_markdown"):
            st.markdown("---")
            st.markdown("### 変換結果")

            # PC: 2カラム / モバイル: CSS で縦積みに
            col_l, col_r = st.columns([1, 1])
            with col_l:
                edited_title = st.text_input(
                    "レシピ名",
                    value=st.session_state.get("converted_title", ""),
                    key="conv_title_input",
                )
                edited_filename = st.text_input(
                    "ファイル名（英数字・アンダースコア）",
                    value=st.session_state.get("converted_filename", ""),
                    key="conv_filename_input",
                )
            with col_r:
                st.markdown("**プレビュー（Markdown）**")
                with st.expander("Markdownを表示", expanded=True):
                    st.markdown(st.session_state["converted_markdown"])

            edited_markdown = st.text_area(
                "Markdownを編集（必要に応じて修正できます）",
                value=st.session_state["converted_markdown"],
                height=300,
                key="conv_md_edit",
            )

            st.markdown("---")
            if st.button("💾 S3に保存してインデックスを更新", type="primary", use_container_width=True, key="btn_conv_save"):
                if not edited_title.strip():
                    st.error("レシピ名を入力してください")
                elif not edited_filename.strip():
                    st.error("ファイル名を入力してください")
                else:
                    filename = edited_filename.strip()
                    if not filename.endswith(".md"):
                        filename = f"{filename}.md"

                    with st.spinner("S3に保存してインデックスを再構築中...（30秒ほどかかります）"):
                        try:
                            resp = requests.post(
                                f"{BACKEND_URL}/recipes/upload",
                                json={
                                    "filename": filename,
                                    "title": edited_title,
                                    "content": edited_markdown,
                                },
                                timeout=120,
                            )
                            resp.raise_for_status()
                            data = resp.json()
                            if data["index_rebuilt"]:
                                st.success(
                                    f"✅ {data['message']}\n\n"
                                    f"S3キー: `{data['s3_key']}`"
                                )
                                st.session_state.pop("converted_markdown", None)
                                st.session_state.pop("converted_title", None)
                                st.session_state.pop("converted_filename", None)
                            else:
                                st.warning(data["message"])
                        except requests.exceptions.ConnectionError:
                            st.error("バックエンドに接続できません。uvicornが起動しているか確認してください。")
                        except Exception as e:
                            st.error(f"エラー: {str(e)}")

    # ---------- 手動入力 ----------
    with tab_add:
        st.markdown("### レシピ情報を入力してください")

        # PC: 2カラム / モバイル: CSS で縦積みに
        col1, col2 = st.columns([1, 1])

        with col1:
            recipe_title = st.text_input(
                "レシピ名 *",
                placeholder="例: 鶏の唐揚げ",
                key="recipe_title",
            )
            recipe_filename = st.text_input(
                "ファイル名（英数字・アンダースコア）*",
                placeholder="例: chicken_karaage",
                key="recipe_filename",
            )
            recipe_category = st.selectbox(
                "カテゴリ",
                ["主菜・和食", "主菜・洋食", "主菜・中華", "副菜", "汁物", "ご飯・麺", "デザート", "その他"],
                key="recipe_category",
            )
            recipe_time = st.number_input(
                "調理時間（分）",
                min_value=5, max_value=180, value=30, step=5,
                key="recipe_time",
            )
            recipe_servings = st.number_input(
                "人数",
                min_value=1, max_value=10, value=2,
                key="recipe_servings",
            )

        with col2:
            recipe_ingredients = st.text_area(
                "材料（1行1つ）*",
                placeholder="鶏もも肉: 300g\n醤油: 大さじ2\nにんにく: 1片\n...",
                height=200,
                key="recipe_ingredients",
            )

        recipe_steps = st.text_area(
            "作り方（1行1ステップ）*",
            placeholder="鶏肉を一口大に切る\nにんにくをすりおろす\n調味料と鶏肉を混ぜて15分漬け込む\n...",
            height=150,
            key="recipe_steps",
        )

        recipe_tips = st.text_area(
            "ポイント・メモ（任意）",
            placeholder="冷蔵庫で30分以上漬けるとより美味しくなります",
            height=80,
            key="recipe_tips",
        )

        st.markdown("---")

        if recipe_title and recipe_ingredients and recipe_steps:
            with st.expander("📄 Markdownプレビュー", expanded=False):
                ingredients_md = "\n".join(
                    f"- {line.strip()}"
                    for line in recipe_ingredients.strip().splitlines()
                    if line.strip()
                )
                steps_md = "\n".join(
                    f"{i}. {line.strip()}"
                    for i, line in enumerate(
                        [l for l in recipe_steps.strip().splitlines() if l.strip()], 1
                    )
                )
                tips_md = (
                    f"\n## ポイント\n{recipe_tips.strip()}" if recipe_tips.strip() else ""
                )
                preview = f"""# {recipe_title}

## 基本情報
- 調理時間: {recipe_time}分
- 人数: {recipe_servings}人分
- カテゴリ: {recipe_category}

## 材料
{ingredients_md}

## 手順
{steps_md}{tips_md}
"""
                st.code(preview, language="markdown")

        if st.button("💾 S3に保存してインデックスを更新", type="primary", use_container_width=True):
            if not recipe_title:
                st.error("レシピ名を入力してください")
            elif not recipe_filename:
                st.error("ファイル名を入力してください")
            elif not recipe_ingredients:
                st.error("材料を入力してください")
            elif not recipe_steps:
                st.error("作り方を入力してください")
            else:
                ingredients_md = "\n".join(
                    f"- {line.strip()}"
                    for line in recipe_ingredients.strip().splitlines()
                    if line.strip()
                )
                steps_md = "\n".join(
                    f"{i}. {line.strip()}"
                    for i, line in enumerate(
                        [l for l in recipe_steps.strip().splitlines() if l.strip()], 1
                    )
                )
                tips_section = (
                    f"\n## ポイント\n{recipe_tips.strip()}" if recipe_tips.strip() else ""
                )
                content = f"""# {recipe_title}

## 基本情報
- 調理時間: {recipe_time}分
- 人数: {recipe_servings}人分
- カテゴリ: {recipe_category}

## 材料
{ingredients_md}

## 手順
{steps_md}{tips_section}
"""
                filename = recipe_filename.strip()
                if not filename.endswith(".md"):
                    filename = f"{filename}.md"

                with st.spinner("S3に保存してインデックスを再構築中...（30秒ほどかかります）"):
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/recipes/upload",
                            json={
                                "filename": filename,
                                "title": recipe_title,
                                "content": content,
                            },
                            timeout=120,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        if data["index_rebuilt"]:
                            st.success(
                                f"✅ {data['message']}\n\n"
                                f"S3キー: `{data['s3_key']}`"
                            )
                        else:
                            st.warning(data["message"])
                    except requests.exceptions.ConnectionError:
                        st.error("バックエンドに接続できません。uvicornが起動しているか確認してください。")
                    except Exception as e:
                        st.error(f"エラー: {str(e)}")

    # ---------- 登録済みレシピ一覧 ----------
    with tab_list:
        st.markdown("### S3に登録されているレシピ")

        if st.button("🔄 一覧を更新", key="refresh_list"):
            st.rerun()

        try:
            resp = requests.get(f"{BACKEND_URL}/recipes", timeout=15)
            resp.raise_for_status()
            data = resp.json()
            recipes_list = data.get("recipes", [])

            if not recipes_list:
                st.info("S3にレシピが登録されていません。「AIでテキスト変換」タブから追加してください。")
            else:
                st.markdown(f"**合計 {len(recipes_list)} 件**")
                for recipe in recipes_list:
                    with st.expander(f"📄 {recipe['filename']}"):
                        col_a, col_b = st.columns([2, 1])
                        with col_a:
                            st.markdown(f"**S3キー:** `{recipe['key']}`")
                        with col_b:
                            st.markdown(f"**更新日時:** {recipe['last_modified'][:19]}")
                            st.markdown(f"**サイズ:** {recipe['size_bytes']} bytes")

                        if st.button("内容を表示", key=f"view_{recipe['filename']}"):
                            try:
                                r = requests.get(
                                    f"{BACKEND_URL}/recipes/{recipe['filename']}",
                                    timeout=10,
                                )
                                r.raise_for_status()
                                st.markdown(r.json()["content"])
                            except Exception as e:
                                st.error(f"取得エラー: {e}")

        except requests.exceptions.ConnectionError:
            st.error("バックエンドに接続できません。uvicornが起動しているか確認してください。")
        except Exception as e:
            st.error(f"エラー: {str(e)}")
