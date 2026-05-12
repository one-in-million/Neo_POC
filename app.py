"""
app.py — Worklap GraphRAG Chatbot (Ultra-Clean Text UI)
"""

import streamlit as st
from chatbot import ask
from ingest import run_ingest

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Worklap AI", page_icon="🧠", layout="wide")

# ── Simple Style ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

    .stApp { background: #0d1117; color: #c9d1d9; font-family: 'Inter', sans-serif; }

    .chat-bubble {
        padding: 16px 20px;
        border-radius: 12px;
        margin-bottom: 16px;
        border: 1px solid #21262d;
    }
    .user-bubble {
        background: #161b22;
        border-left: 4px solid #58a6ff;
    }
    .bot-bubble {
        background: #0f1923;
        border-left: 4px solid #3fb950;
    }
    .label {
        font-weight: 600;
        font-size: 0.72rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 10px;
        display: block;
    }
    .user-label { color: #58a6ff; }
    .bot-label  { color: #3fb950; }
    .bot-content {
        line-height: 1.8;
        font-size: 0.92rem;
        color: #e6edf3;
    }
    .bot-content br + br { margin-top: 4px; }
</style>
""", unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Worklap AI")
    if st.button("📥 Refresh Data", use_container_width=True):
        try:
            run_ingest()
            st.success("Synced!")
        except Exception as e:
            st.error(f"Error: {e}")
    
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ── Main UI ───────────────────────────────────────────────────────────────────
st.subheader("Worklap Project Assistant")

# Display history
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(
            f'<div class="chat-bubble user-bubble">'
            f'<span class="label user-label">YOU</span>'
            f'{msg["content"]}'
            f'</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f'<div class="chat-bubble bot-bubble">'
            f'<span class="label bot-label">✦ WORKLAP AI</span>'
            f'<div class="bot-content">{msg["content"]}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
        if msg.get("cypher"):
            with st.expander("🔍 View Cypher Query"):
                st.code(msg["cypher"], language="cypher")

# Input
prompt = st.chat_input("Ask a question...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    try:
        response = ask(prompt)
        st.session_state.messages.append({
            "role": "assistant", 
            "content": response["answer"],
            "cypher": response["cypher"]
        })
    except Exception as e:
        st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})
    
    st.rerun()
