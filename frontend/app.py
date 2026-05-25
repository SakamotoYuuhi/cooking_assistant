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

# セッションIDの初期化
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = []

# ---- サイドバー ----
with st.sidebar:
    st.title("🍳 AI料理アシスタント")
    st.markdown("---")

    mode = st.radio(
        "モードを選択",
        ["💬 料理チャット（RAG）", "🍳 料理エージェント"],
        key="mode_selector",
        help=(
            "料理チャット: RAGでレシピ集を参照して回答\n"
            "料理エージェント: 複数ツールを自律的に組み合わせて回答"
        ),
    )

    st.markdown("---")

    if mode == "💬 料理チャット（RAG）":
        st.markdown("### 例文")
        examples = [
            "鶏肉・玉ねぎ・にんじんがあります",
            "20分以内で作れる夕食を提案して",
            "タンパク質多めのレシピがほしい",
            "昨日の残り物のご飯でできる料理は？",
        ]
        for ex in examples:
            if st.button(ex, use_container_width=True, key=f"chat_{ex}"):
                st.session_state.pending_message = ex

        if st.button("会話をリセット", use_container_width=True, type="secondary"):
            requests.post(f"{BACKEND_URL}/chat/clear", json={"session_id": st.session_state.session_id})
            st.session_state.messages = []
            st.rerun()

    else:
        st.markdown("### エージェント例文")
        agent_examples = [
            "鶏肉と豆腐がある。今日の夕食を提案して",
            "今週3日分の献立と買い物リストを作って。鶏肉・卵・玉ねぎはある",
            "昨日の夕食は唐揚げだった。栄養バランスを分析して改善案も教えて",
            "冷蔵庫に鮭・ほうれん草・豆腐がある。献立と不足食材リストを出して",
        ]
        for ex in agent_examples:
            if st.button(ex, use_container_width=True, key=f"agent_{ex}"):
                st.session_state.pending_agent_message = ex

        if st.button("エージェント履歴をリセット", use_container_width=True, type="secondary"):
            requests.post(f"{BACKEND_URL}/agent/clear", json={"session_id": st.session_state.session_id})
            st.session_state.agent_messages = []
            st.rerun()

    st.markdown("---")
    st.caption(f"セッションID: `{st.session_state.session_id[:8]}...`")


# ---- 料理チャットモード（RAG） ----
if mode == "💬 料理チャット（RAG）":
    st.title("💬 料理チャット（RAG）")
    st.caption("食材を伝えると、レシピ集を参照して献立・レシピを提案します")

    for msg in st.session_state.messages:
        with st.chat_message("🧑" if msg["role"] == "user" else "🍳"):
            st.markdown(msg["content"])

    pending = st.session_state.pop("pending_message", None)
    user_input = st.chat_input("食材や条件を入力してください")
    message_to_send = user_input or pending

    if message_to_send:
        st.session_state.messages.append({"role": "user", "content": message_to_send})
        with st.chat_message("🧑"):
            st.markdown(message_to_send)

        with st.chat_message("🍳"):
            with st.spinner("レシピを検索中..."):
                try:
                    response = requests.post(
                        f"{BACKEND_URL}/chat",
                        json={"session_id": st.session_state.session_id, "message": message_to_send},
                        timeout=30,
                    )
                    response.raise_for_status()
                    reply = response.json()["reply"]
                except requests.exceptions.ConnectionError:
                    reply = "バックエンドに接続できません。uvicornが起動しているか確認してください。"
                except Exception as e:
                    reply = f"エラー: {str(e)}"
            st.markdown(reply)

        st.session_state.messages.append({"role": "assistant", "content": reply})


# ---- 料理エージェントモード ----
else:
    st.title("🍳 料理エージェント")
    st.caption("複数のツール（レシピ検索・献立作成・買い物リスト・栄養分析）を自律的に組み合わせて回答します")

    for msg in st.session_state.agent_messages:
        with st.chat_message("🧑" if msg["role"] == "user" else "🍳"):
            st.markdown(msg["content"])
            if msg.get("tools_used"):
                with st.expander(f"🔧 使用ツール（{len(msg['tools_used'])}個）"):
                    for t in msg["tools_used"]:
                        st.markdown(f"**{t['tool']}**")
                        st.json(t["input"])

    pending_agent = st.session_state.pop("pending_agent_message", None)
    agent_input = st.chat_input("複雑な要望を入力してください（例: 今週の献立と買い物リストを作って）")
    agent_message = agent_input or pending_agent

    if agent_message:
        st.session_state.agent_messages.append({"role": "user", "content": agent_message})
        with st.chat_message("🧑"):
            st.markdown(agent_message)

        with st.chat_message("🍳"):
            with st.spinner("エージェントが考え中...（ツールを使って処理しています）"):
                try:
                    response = requests.post(
                        f"{BACKEND_URL}/agent",
                        json={"session_id": st.session_state.session_id, "message": agent_message},
                        timeout=60,
                    )
                    response.raise_for_status()
                    data = response.json()
                    reply = data["reply"]
                    tools_used = data.get("tools_used", [])
                except requests.exceptions.ConnectionError:
                    reply = "バックエンドに接続できません。"
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
