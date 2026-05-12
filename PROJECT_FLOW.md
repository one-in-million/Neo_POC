# Worklap GraphRAG Chatbot: Project Flow & Code Walkthrough

This document explains the technical flow of the Worklap AI Chatbot, showing exactly which parts of the code execute at each step of the process.

---

## 1. How the Application Starts (`app.py`)
The application begins in the terminal when you run `streamlit run app.py`. Streamlit reads this file from top to bottom.

First, it sets up the web page and initializes the "memory" (session state) so the chat history persists:

```python
# From app.py
st.set_page_config(page_title="Worklap AI", page_icon="🧠", layout="wide")

# ── Session State ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
```

---

## 2. Getting the Data into the System (`ingest.py`)
In the sidebar of the UI, there is a "Refresh Data" button. When clicked, it triggers the ingestion process:

```python
# From app.py (Sidebar logic)
if st.button("📥 Refresh Data", use_container_width=True):
    try:
        run_ingest()  # This jumps over to ingest.py
        st.success("Synced!")
```

The `run_ingest()` function lives in `ingest.py`. It fetches raw JSON from the Worklap API, cleans it, and uses Cypher to write it directly into the Neo4j database as connected nodes.

```python
# From ingest.py (inside sync_project)
def sync_project(self, project_uuid: str) -> dict:
    # 1. Fetch & Prepare Data from API
    fetched = self.fetch_api_data(project_uuid)
    flat_data = flatten_items(fetched["items"])
    cleaned = [clean_item(i, project_uuid) for i in flat_data]

    # ... skipping smart deletion code ...

    # 3. Upsert Project Node into Neo4j Graph
    self.graph.query("""
        MERGE (p:Project {uuid: $uuid})
        SET p.name = $name, p.key = $key
    """, params={"uuid": project_uuid, "name": fetched["projectName"], "key": fetched["projectKey"]})
```

---

## 3. Asking a Question: The Journey Begins (`app.py`)
At the bottom of the screen, there is a chat input. When the user types a question and hits enter, it is immediately captured.

```python
# From app.py (Main UI)
prompt = st.chat_input("Ask a question...")

if prompt:
    # Save the user's question to memory
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    try:
        # Pass the question to the AI Engine
        response = ask(prompt)
        
        # Save the AI's answer to memory
        st.session_state.messages.append({
            "role": "assistant", 
            "content": response["answer"],
            "cypher": response["cypher"]
        })
```

---

## 4. The Brain of the Operation (`chatbot.py`)
The `ask()` function lives in `chatbot.py`. It uses a LangChain tool called `GraphCypherQAChain` to manage the conversation with the Cerebras AI Model.

```python
# From chatbot.py (The main logic chain)
def ask(question: str) -> dict:
    chain = get_chain()
    
    # This single line does the heavy lifting:
    # 1. AI writes a Cypher query
    # 2. Runs query against Neo4j
    # 3. AI reads the raw data and writes an English answer
    result = chain.invoke({"query": question})

    steps   = result.get("intermediate_steps", [])
    cypher  = steps[0].get("query", "") if len(steps) > 0 else ""
    answer  = result.get("result", "I couldn't analyze the project data.")

    # Convert newlines to HTML so Streamlit renders them perfectly
    answer_html = answer.replace("\n\n", "<br><br>").replace("\n", "<br>")

    return {
        "answer":  answer_html,
        "cypher":  cypher
    }
```

Behind the scenes, `chain.invoke()` uses two specific Prompts to tell the AI exactly how to behave.

**Prompt 1: Generating the Query**
```python
# From chatbot.py (cypher_template)
cypher_template = f"""You are an expert Neo4j Cypher query writer for Worklap.
RULES:
1. ALWAYS use toLower() and CONTAINS for status matching.
2. To list all items of a type, just match the label: MATCH (b:Bug) RETURN b
..."""
```

**Prompt 2: Formatting the Final Answer**
```python
# From chatbot.py (qa_template)
qa_template = """You are a helpful AI Assistant for Worklap.
INSTRUCTIONS:
- For any list of work items, output EACH item on its OWN separate line in this exact format:
  • [Title] ([ID]) | [Type] | [Status] | Priority: [Priority]
..."""
```

---

## 5. Displaying the Answer (`app.py`)
Once `chatbot.py` returns the formatted HTML string, `app.py` loops through the chat memory and draws the beautiful green chat bubbles on the screen.

```python
# From app.py (Display History loop)
for msg in st.session_state.messages:
    if msg["role"] == "user":
        # Draw the Blue User Bubble
        st.markdown(
            f'<div class="chat-bubble user-bubble">'
            f'<span class="label user-label">YOU</span>{msg["content"]}</div>',
            unsafe_allow_html=True
        )
    else:
        # Draw the Green AI Bubble
        st.markdown(
            f'<div class="chat-bubble bot-bubble">'
            f'<span class="label bot-label">✦ WORKLAP AI</span>'
            f'<div class="bot-content">{msg["content"]}</div></div>',
            unsafe_allow_html=True
        )
        
        # Add the dropdown to view the technical query
        if msg.get("cypher"):
            with st.expander("🔍 View Cypher Query"):
                st.code(msg["cypher"], language="cypher")
```
