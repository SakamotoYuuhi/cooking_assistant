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
if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = []

# ---- サイドバー ----
with st.sidebar:
    st.title("🍳 AI料理アシスタント")
    st.markdown("---")

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
    if st.button("会話をリセット", use_container_width=True, type="secondary"):
        requests.post(f"{BACKEND_URL}/agent/clear", json={"session_id": st.session_state.session_id})
        st.session_state.agent_messages = []
        st.rerun()

    st.caption(f"セッションID: `{st.session_state.session_id[:8]}...`")


# ---- メイン画面 ----
st.title("🍳 AI料理アシスタント")
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
agent_input = st.chat_input("食材や要望を入力してください（例: 鶏肉と玉ねぎで20分以内の夕食を提案して）")
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
                    json={"session_id": st.session_state.session_id, "message": agent_message},
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
