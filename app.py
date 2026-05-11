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
    .stApp { background: #0d1117; color: #c9d1d9; font-family: sans-serif; }
    .chat-bubble {
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
        border: 1px solid #30363d;
    }
    .user-bubble { background: #161b22; border-left: 4px solid #58a6ff; }
    .bot-bubble { background: #161b22; border-left: 4px solid #238636; }
    .label { font-weight: bold; font-size: 0.8rem; margin-bottom: 5px; display: block; }
    .user-label { color: #58a6ff; }
    .bot-label { color: #238636; }
    .cypher-label { color: #8b949e; margin-top: 10px; font-size: 0.75rem; font-family: monospace; }
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
        st.markdown(f"""<div class="chat-bubble user-bubble"><span class="label user-label">YOU</span>{msg['content']}</div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""<div class="chat-bubble bot-bubble"><span class="label bot-label">AI</span>{msg['content']}</div>""", unsafe_allow_html=True)
        if msg.get("cypher"):
            with st.expander("🔍 View Technical Logic"):
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
