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
    layout="wide",
)

# セッションIDの初期化（ブラウザセッションごとに一意）
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

# ---- サイドバー ----
with st.sidebar:
    st.title("🍳 AI料理アシスタント")
    st.markdown("---")

    st.markdown("### 使い方")
    st.markdown(
        """
1. 冷蔵庫にある **食材を入力**
2. 希望があれば **調理時間** や **人数** も伝える
3. AIが **献立・レシピ** を提案します
"""
    )

    st.markdown("### 例文")
    example_messages = [
        "鶏肉・玉ねぎ・にんじんがあります",
        "20分以内で作れる夕食を提案して",
        "昨日の残り物のご飯でできる料理は？",
        "タンパク質多めのレシピがほしい",
    ]
    for example in example_messages:
        if st.button(example, use_container_width=True):
            st.session_state.pending_message = example

    st.markdown("---")
    if st.button("会話をリセット", use_container_width=True, type="secondary"):
        requests.post(
            f"{BACKEND_URL}/chat/clear",
            json={"session_id": st.session_state.session_id},
        )
        st.session_state.messages = []
        st.rerun()

    st.caption(f"セッションID: `{st.session_state.session_id[:8]}...`")

# ---- メインエリア ----
st.title("🍳 AI料理アシスタント")
st.caption("食材を伝えると、献立・レシピ・栄養バランスを提案します")

# チャット履歴の表示
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🍳"):
        st.markdown(msg["content"])

# サイドバーの例文ボタン押下時の処理
pending = st.session_state.pop("pending_message", None)

# 入力欄
user_input = st.chat_input("食材や条件を入力してください（例：鶏肉・豆腐・ほうれん草があります）")

# 入力ソースの統合（直接入力 or 例文ボタン）
message_to_send = user_input or pending

if message_to_send:
    # ユーザーメッセージを表示
    st.session_state.messages.append({"role": "user", "content": message_to_send})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(message_to_send)

    # バックエンドへリクエスト
    with st.chat_message("assistant", avatar="🍳"):
        with st.spinner("レシピを考えています..."):
            try:
                response = requests.post(
                    f"{BACKEND_URL}/chat",
                    json={
                        "session_id": st.session_state.session_id,
                        "message": message_to_send,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                reply = data["reply"]
            except requests.exceptions.ConnectionError:
                reply = "バックエンドに接続できません。`uvicorn`が起動しているか確認してください。"
            except Exception as e:
                reply = f"エラーが発生しました: {str(e)}"

        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
