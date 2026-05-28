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
@media (min-width: 431px) {
    .block-container {
        padding-top: 1rem !important;
    }
}

/* =========================================================
   スマホ レイアウト（430px 以下 = iPhone最大幅）
   ========================================================= */
@media (max-width: 430px) {
    /* --- コンテナ幅・余白 --- */
    /* padding-top を大きめに取り、固定ヘッダー(ハンバーガーメニュー行)との重なりを防ぐ */
    .block-container {
        max-width: 100% !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        padding-top: 4.5rem !important;
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
# ユーティリティ
# ==============================================================================
import re as _re

def _safe_md(content: str) -> str:
    """
    Markdownとしてレンダリングする前に ~ をエスケープする。
    AIが誤って ~~ (strikethrough) や ~ (subscript) を生成すると
    「小さじ」→「弱じ」のように文字が消える問題を防ぐ。
    レシピMarkdownでは ~ を意図的に使う場面がないため全てエスケープして安全。
    """
    return _re.sub(r"~", r"\\~", content)


def _image_ui(key_prefix: str, recipe_title: str = "", recipe_content: str = "") -> str | None:
    """
    画像アップロード＋AI生成UIを表示し、選択・生成された画像のbase64文字列を返す。
    画像がない場合は None を返す。

    Args:
        key_prefix:      Streamlit widget key の重複防止用プレフィックス
        recipe_title:    AI画像生成に使うレシピ名
        recipe_content:  AI画像生成に使うレシピ内容
    """
    st.markdown("##### 完成画像（任意）")
    col_up, col_gen = st.columns([1, 1])

    with col_up:
        uploaded = st.file_uploader(
            "画像をアップロード",
            type=["jpg", "jpeg", "png"],
            key=f"{key_prefix}_file_uploader",
            label_visibility="collapsed",
        )
        if uploaded:
            import base64 as _b64
            img_bytes = uploaded.read()
            img_b64 = _b64.b64encode(img_bytes).decode()
            ext = uploaded.name.rsplit(".", 1)[-1].lower()
            st.session_state[f"{key_prefix}_image_b64"] = img_b64
            st.session_state[f"{key_prefix}_image_ext"] = ext
            st.image(img_bytes, caption="アップロード画像", use_container_width=True)

    with col_gen:
        btn_disabled = not bool(recipe_title.strip())
        if st.button(
            "🎨 AIで画像を生成",
            key=f"{key_prefix}_gen_btn",
            use_container_width=True,
            disabled=btn_disabled,
            help="レシピ名を入力してから押してください" if btn_disabled else "",
        ):
            with st.spinner("Bedrockで画像を生成中...（20〜40秒）"):
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/recipes/generate-image",
                        json={"recipe_title": recipe_title, "recipe_content": recipe_content},
                        timeout=120,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    st.session_state[f"{key_prefix}_image_b64"] = data["image_base64"]
                    st.session_state[f"{key_prefix}_image_ext"] = "jpg"
                    st.rerun()
                except requests.exceptions.ConnectionError:
                    st.error("バックエンドに接続できません。")
                except Exception as e:
                    st.error(f"画像生成エラー: {str(e)}")

    # 生成済み・アップロード済み画像のプレビューと削除ボタン
    b64 = st.session_state.get(f"{key_prefix}_image_b64")
    if b64 and not uploaded:
        import base64 as _b64
        img_bytes = _b64.b64decode(b64)
        st.image(img_bytes, caption="生成された画像", use_container_width=True)
        if st.button("🗑️ 画像を削除", key=f"{key_prefix}_del_btn"):
            st.session_state.pop(f"{key_prefix}_image_b64", None)
            st.session_state.pop(f"{key_prefix}_image_ext", None)
            st.rerun()

    return st.session_state.get(f"{key_prefix}_image_b64")


# ==============================================================================
# セッション初期化
# ==============================================================================
# session_id をURLパラメータで永続化する
# リロード後もURLに ?session_id=xxx が残るため同じ履歴を復元できる
_restored_from_url = False
if "session_id" not in st.session_state:
    params = st.query_params
    if "session_id" in params:
        st.session_state.session_id = params["session_id"]
        _restored_from_url = True
    else:
        st.session_state.session_id = str(uuid.uuid4())
st.query_params["session_id"] = st.session_state.session_id

if "agent_messages" not in st.session_state:
    # URLからsession_idを復元した場合はDynamoDBから会話履歴を取得して復元する
    if _restored_from_url:
        try:
            _hist_resp = requests.get(
                f"{BACKEND_URL}/agent/history/{st.session_state.session_id}",
                timeout=10,
            )
            if _hist_resp.ok:
                _hist_data = _hist_resp.json()
                st.session_state.agent_messages = [
                    {"role": m["role"], "content": m["content"]}
                    for m in _hist_data
                ]
            else:
                st.session_state.agent_messages = []
        except Exception:
            st.session_state.agent_messages = []
    else:
        st.session_state.agent_messages = []
if "editing_recipe" not in st.session_state:
    st.session_state.editing_recipe = None   # 編集中レシピのファイル名
if "editing_content" not in st.session_state:
    st.session_state.editing_content = ""
if "editing_has_image" not in st.session_state:
    st.session_state.editing_has_image = False

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
            "昨日の夕食は唐揚げだった。栄養バランスを分析して改善点も教えて",
            "冷蔵庫に鮭・ほうれん草・豆腐がある。献立と不足食材リストを出して",
            "タンパク質多めのレシピがほしい",
        ]
        for ex in agent_examples:
            if st.button(ex, use_container_width=True, key=f"agent_{ex}"):
                st.session_state.pending_agent_message = ex

        st.markdown("---")
        if st.button("💾 この会話のレシピを登録", use_container_width=True, type="primary"):
            if not st.session_state.agent_messages:
                st.warning("会話履歴がありません")
            else:
                with st.spinner("会話からレシピを抽出中..."):
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/agent/extract-recipe",
                            json={"session_id": st.session_state.session_id},
                            timeout=60,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        if data["found"]:
                            st.session_state["extracted_markdown"] = data["markdown"]
                            st.session_state["extracted_title"] = data["suggested_title"]
                            st.session_state["extracted_filename"] = data["suggested_filename"]
                        else:
                            st.warning("会話の中にレシピが見つかりませんでした。\nもう少し具体的なレシピが決まってから試してください。")
                    except requests.exceptions.ConnectionError:
                        st.error("バックエンドに接続できません。")
                    except Exception as e:
                        st.error(f"エラー: {str(e)}")

        st.markdown("---")
        if st.button("🗑️ 会話をリセット", use_container_width=True, type="secondary"):
            requests.post(
                f"{BACKEND_URL}/agent/clear",
                json={"session_id": st.session_state.session_id},
            )
            st.session_state.agent_messages = []
            st.session_state.pop("extracted_markdown", None)
            st.session_state.pop("extracted_title", None)
            st.session_state.pop("extracted_filename", None)
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


# ---- 会話から抽出したレシピの登録エリア ----
if mode == "🤖 料理エージェント" and st.session_state.get("extracted_markdown"):
    st.markdown("---")
    st.markdown("### 💾 抽出されたレシピを登録")
    st.caption("会話から抽出したレシピです。内容を確認・編集してからS3に保存してください。")

    col_l, col_r = st.columns([1, 1])
    with col_l:
        ext_title = st.text_input(
            "レシピ名",
            value=st.session_state.get("extracted_title", ""),
            key="ext_title_input",
        )
        ext_filename = st.text_input(
            "ファイル名（英数字・アンダースコア）",
            value=st.session_state.get("extracted_filename", ""),
            key="ext_filename_input",
        )
    with col_r:
        st.markdown("**プレビュー**")
        with st.expander("Markdownを表示", expanded=True):
                    st.markdown(_safe_md(st.session_state["extracted_markdown"]))

    ext_markdown = st.text_area(
        "Markdownを編集（必要に応じて修正できます）",
        value=st.session_state["extracted_markdown"],
        height=300,
        key="ext_md_edit",
    )

    st.markdown("---")
    _image_ui("ext", recipe_title=ext_title, recipe_content=ext_markdown)

    col_save, col_cancel = st.columns([3, 1])
    with col_save:
        if st.button("💾 S3に保存してインデックスを更新", type="primary", use_container_width=True, key="btn_ext_save"):
            if not ext_title.strip():
                st.error("レシピ名を入力してください")
            elif not ext_filename.strip():
                st.error("ファイル名を入力してください")
            else:
                filename = ext_filename.strip()
                if not filename.endswith(".md"):
                    filename = f"{filename}.md"
                with st.spinner("S3に保存してインデックスを再構築中...（30秒ほどかかります）"):
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/recipes/upload",
                            json={
                                "filename": filename,
                                "title": ext_title,
                                "content": ext_markdown,
                                "image_base64": st.session_state.get("ext_image_b64"),
                                "image_ext": st.session_state.get("ext_image_ext", "jpg"),
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
                            st.session_state.pop("extracted_markdown", None)
                            st.session_state.pop("extracted_title", None)
                            st.session_state.pop("extracted_filename", None)
                            st.session_state.pop("ext_image_b64", None)
                            st.session_state.pop("ext_image_ext", None)
                            st.rerun()
                        else:
                            st.warning(data["message"])
                    except requests.exceptions.ConnectionError:
                        st.error("バックエンドに接続できません。")
                    except Exception as e:
                        st.error(f"エラー: {str(e)}")
    with col_cancel:
        if st.button("キャンセル", use_container_width=True, key="btn_ext_cancel"):
            st.session_state.pop("extracted_markdown", None)
            st.session_state.pop("extracted_title", None)
            st.session_state.pop("extracted_filename", None)
            st.session_state.pop("ext_image_b64", None)
            st.session_state.pop("ext_image_ext", None)
            st.rerun()


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
                    st.markdown(_safe_md(st.session_state["converted_markdown"]))

            edited_markdown = st.text_area(
                "Markdownを編集（必要に応じて修正できます）",
                value=st.session_state["converted_markdown"],
                height=300,
                key="conv_md_edit",
            )

            st.markdown("---")
            _image_ui("conv", recipe_title=edited_title, recipe_content=edited_markdown)

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
                                    "image_base64": st.session_state.get("conv_image_b64"),
                                    "image_ext": st.session_state.get("conv_image_ext", "jpg"),
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
                                st.session_state.pop("conv_image_b64", None)
                                st.session_state.pop("conv_image_ext", None)
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

        _image_ui("manual", recipe_title=recipe_title, recipe_content="")

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
                                "image_base64": st.session_state.get("manual_image_b64"),
                                "image_ext": st.session_state.get("manual_image_ext", "jpg"),
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
                            st.session_state.pop("manual_image_b64", None)
                            st.session_state.pop("manual_image_ext", None)
                        else:
                            st.warning(data["message"])
                    except requests.exceptions.ConnectionError:
                        st.error("バックエンドに接続できません。uvicornが起動しているか確認してください。")
                    except Exception as e:
                        st.error(f"エラー: {str(e)}")

    # ---------- 登録済みレシピ一覧 ----------
    with tab_list:

        # ============================================================
        # 編集モード: 特定レシピを編集中の場合はフォームを全面表示
        # ============================================================
        if st.session_state.editing_recipe:
            _editing_filename = st.session_state.editing_recipe
            _editing_stem = _editing_filename.removesuffix(".md")

            st.markdown(f"### ✏️ レシピを編集: `{_editing_filename}`")
            st.caption("内容を編集してから「更新して保存」を押してください。画像の追加・差し替え・削除もここで行えます。")

            # タイトル入力
            _edit_title = st.text_input(
                "レシピ名 *",
                value=st.session_state.get("editing_title", _editing_stem.replace("_", " ")),
                key="edit_title_input",
            )

            # Markdown エディタ（左）＋ プレビュー（右）
            col_edit_l, col_edit_r = st.columns([1, 1])
            with col_edit_l:
                _edit_content = st.text_area(
                    "Markdownを編集 *",
                    value=st.session_state.editing_content,
                    height=400,
                    key="edit_md_area",
                )
            with col_edit_r:
                st.markdown("**プレビュー**")
                with st.expander("Markdownを表示", expanded=True):
                    st.markdown(_safe_md(_edit_content))

            # 画像セクション
            st.markdown("---")
            st.markdown("##### 完成画像")

            _has_image = st.session_state.editing_has_image
            if _has_image:
                st.info("現在この画像が登録されています。")
                try:
                    img_resp = requests.get(
                        f"{BACKEND_URL}/recipes/{_editing_filename}/image",
                        timeout=15,
                    )
                    if img_resp.ok:
                        import base64 as _b64
                        st.image(img_resp.content, caption="現在の画像", use_container_width=True)
                except Exception:
                    pass

                _delete_image_flag = st.checkbox(
                    "🗑️ 既存画像を削除する",
                    key="edit_delete_image_check",
                )
            else:
                st.caption("この画像はまだ登録されていません。以下から追加できます。")
                _delete_image_flag = False

            # 新しい画像の追加・AI生成
            _new_image_b64 = _image_ui(
                "edit",
                recipe_title=_edit_title,
                recipe_content=_edit_content,
            )

            st.markdown("---")
            col_save_edit, col_cancel_edit = st.columns([3, 1])

            with col_save_edit:
                if st.button(
                    "💾 更新して保存（インデックスも再構築）",
                    type="primary",
                    use_container_width=True,
                    key="btn_edit_save",
                ):
                    if not _edit_title.strip():
                        st.error("レシピ名を入力してください")
                    elif not _edit_content.strip():
                        st.error("Markdownが空です")
                    else:
                        with st.spinner("S3に保存してインデックスを再構築中...（30秒ほどかかります）"):
                            try:
                                resp = requests.put(
                                    f"{BACKEND_URL}/recipes/{_editing_filename}",
                                    json={
                                        "title": _edit_title.strip(),
                                        "content": _edit_content,
                                        "image_base64": _new_image_b64,
                                        "image_ext": st.session_state.get("edit_image_ext", "jpg"),
                                        "delete_image": _delete_image_flag,
                                    },
                                    timeout=120,
                                )
                                resp.raise_for_status()
                                data = resp.json()
                                if data["index_rebuilt"]:
                                    st.success(f"✅ {data['message']}")
                                else:
                                    st.warning(data["message"])
                                # セッション状態をクリアして一覧に戻る
                                st.session_state.editing_recipe = None
                                st.session_state.editing_content = ""
                                st.session_state.editing_has_image = False
                                st.session_state.pop("editing_title", None)
                                st.session_state.pop("edit_image_b64", None)
                                st.session_state.pop("edit_image_ext", None)
                                st.rerun()
                            except requests.exceptions.ConnectionError:
                                st.error("バックエンドに接続できません。")
                            except Exception as e:
                                st.error(f"更新エラー: {str(e)}")

            with col_cancel_edit:
                if st.button("キャンセル", use_container_width=True, key="btn_edit_cancel"):
                    st.session_state.editing_recipe = None
                    st.session_state.editing_content = ""
                    st.session_state.editing_has_image = False
                    st.session_state.pop("editing_title", None)
                    st.session_state.pop("edit_image_b64", None)
                    st.session_state.pop("edit_image_ext", None)
                    st.rerun()

        # ============================================================
        # 通常モード: レシピ一覧表示
        # ============================================================
        else:
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
                            col_meta_a, col_meta_b = st.columns([2, 1])
                            with col_meta_a:
                                st.markdown(f"**S3キー:** `{recipe['key']}`")
                            with col_meta_b:
                                st.markdown(f"**更新日時:** {recipe['last_modified'][:19]}")
                                st.markdown(f"**サイズ:** {recipe['size_bytes']} bytes")

                            col_btn_view, col_btn_edit, col_btn_del = st.columns([2, 2, 1])

                            with col_btn_view:
                                if st.button("👁️ 内容を表示", key=f"view_{recipe['filename']}"):
                                    try:
                                        r = requests.get(
                                            f"{BACKEND_URL}/recipes/{recipe['filename']}",
                                            timeout=10,
                                        )
                                        r.raise_for_status()
                                        rdata = r.json()
                                        st.markdown(_safe_md(rdata["content"]))
                                        if rdata.get("has_image"):
                                            img_resp = requests.get(
                                                f"{BACKEND_URL}/recipes/{recipe['filename']}/image",
                                                timeout=15,
                                            )
                                            if img_resp.ok:
                                                st.image(img_resp.content, caption="完成画像", use_container_width=True)
                                    except Exception as e:
                                        st.error(f"取得エラー: {e}")

                            with col_btn_edit:
                                if st.button("✏️ 編集", key=f"edit_{recipe['filename']}", use_container_width=True):
                                    try:
                                        r = requests.get(
                                            f"{BACKEND_URL}/recipes/{recipe['filename']}",
                                            timeout=10,
                                        )
                                        r.raise_for_status()
                                        rdata = r.json()
                                        # タイトルを1行目（# レシピ名）から抽出
                                        _lines = rdata["content"].splitlines()
                                        _extracted_title = next(
                                            (l.lstrip("# ").strip() for l in _lines if l.startswith("# ")),
                                            recipe["filename"].removesuffix(".md").replace("_", " "),
                                        )
                                        st.session_state.editing_recipe = recipe["filename"]
                                        st.session_state.editing_content = rdata["content"]
                                        st.session_state.editing_has_image = rdata.get("has_image", False)
                                        st.session_state["editing_title"] = _extracted_title
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"読み込みエラー: {e}")

                            with col_btn_del:
                                if st.button("🗑️", key=f"del_{recipe['filename']}", help="削除", use_container_width=True):
                                    st.session_state[f"confirm_delete_{recipe['filename']}"] = True

                            # 削除確認ダイアログ
                            if st.session_state.get(f"confirm_delete_{recipe['filename']}"):
                                st.warning(f"**「{recipe['filename']}」を削除しますか？** この操作は元に戻せません。")
                                col_yes, col_no = st.columns([1, 1])
                                with col_yes:
                                    if st.button("はい、削除する", key=f"yes_del_{recipe['filename']}", type="primary"):
                                        with st.spinner("削除中..."):
                                            try:
                                                del_resp = requests.delete(
                                                    f"{BACKEND_URL}/recipes/{recipe['filename']}",
                                                    timeout=120,
                                                )
                                                del_resp.raise_for_status()
                                                st.success(f"「{recipe['filename']}」を削除しました")
                                                st.session_state.pop(f"confirm_delete_{recipe['filename']}", None)
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"削除エラー: {e}")
                                with col_no:
                                    if st.button("キャンセル", key=f"no_del_{recipe['filename']}"):
                                        st.session_state.pop(f"confirm_delete_{recipe['filename']}", None)
                                        st.rerun()

            except requests.exceptions.ConnectionError:
                st.error("バックエンドに接続できません。uvicornが起動しているか確認してください。")
            except Exception as e:
                st.error(f"エラー: {str(e)}")
