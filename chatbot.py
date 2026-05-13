import os
from dotenv import load_dotenv
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_cerebras import ChatCerebras
from langchain_core.prompts import PromptTemplate
from prompts import get_cypher_template

load_dotenv()

_chain = None 

def get_chain() -> GraphCypherQAChain:
    global _chain
    if _chain is not None:
        return _chain

    graph = Neo4jGraph(
        url=os.getenv("NEO4J_URI"),
        username=os.getenv("NEO4J_USERNAME"),
        password=os.getenv("NEO4J_PASSWORD"),
        database=os.getenv("NEO4J_DATABASE", "95ee6f84"),
    )
    graph.refresh_schema()

    project_name = os.getenv("WORKLAP_PROJECT_NAME", "UNasa")
    project_uuid = os.getenv("WORKLAP_PROJECT_UUID")

    cypher_template = get_cypher_template(project_uuid=project_uuid, project_name=project_name)
    cypher_prompt = PromptTemplate(input_variables=["schema", "question"], template=cypher_template)


    llm = ChatCerebras(
        model="llama-3.1-8b",
        cerebras_api_key=os.getenv("CEREBRAS_API_KEY"),
        temperature=0,
    )

    _chain = GraphCypherQAChain.from_llm(
        llm=llm,
        graph=graph,
        cypher_prompt=cypher_prompt,
        verbose=True,
        return_intermediate_steps=True,
        return_direct=True,
        allow_dangerous_requests=True,
    )
    return _chain

def _format_context(context: list) -> str:
    """Format Neo4j results into clean output. Handles both lists and aggregates."""
    if not context:
        return "No items found matching your request."

    # Detect if this is a simple aggregate/scalar result (e.g. COUNT, SUM)
    WORK_ITEM_KEYS = {"title", "name", "id", "status", "priority", "type"}
    first = context[0] if context else {}
    is_aggregate = not any(k in first for k in WORK_ITEM_KEYS)

    if is_aggregate:
        # Just print the key-value pairs directly (e.g. "total_workitems: 10")
        lines = []
        for row in context:
            lines.append(", ".join(f"**{k}**: {v}" for k, v in row.items()))
        return "\n".join(lines)

    # Full work item formatting — deduplicate by id to handle multiple graph paths
    seen_ids = set()
    lines = []
    for item in context:
        title    = item.get("title") or item.get("name") or "Untitled"
        item_id  = item.get("id", "")
        itype    = item.get("type", "")
        status   = item.get("status", "")
        priority = item.get("priority", "")
        # Skip duplicates
        dedup_key = item_id or title
        if dedup_key in seen_ids:
            continue
        seen_ids.add(dedup_key)
        parts = [f"**{title}**"]
        if item_id:  parts.append(f"({item_id})")
        if itype:    parts.append(f"| {itype}")
        if status:   parts.append(f"| {status}")
        if priority: parts.append(f"| {priority}")
        lines.append("• " + " ".join(parts))
    return "\n".join(lines)


def ask(question: str) -> dict:
    chain = get_chain()
    result = chain.invoke({"query": question})

    steps  = result.get("intermediate_steps", [])
    cypher = steps[0].get("query", "") if len(steps) > 0 else ""

    # With return_direct=True, raw Neo4j rows are in result["result"] (a list).
    raw = result.get("result", [])
    context = raw if isinstance(raw, list) else steps[1].get("context", []) if len(steps) > 1 else []

    # Print raw context to the terminal for debugging
    print("\n🔍 GENERATED CYPHER:", flush=True)
    print(cypher, flush=True)
    print("\n📦 RAW DATABASE RESULTS:", flush=True)
    print(context, flush=True)
    print("─" * 50, flush=True)

    # Format directly in Python — no QA LLM, no hallucination possible
    answer_html = _format_context(context).replace("\n", "<br>")

    return {
        "answer":  answer_html,
        "cypher":  cypher,
        "context": context,
    }
