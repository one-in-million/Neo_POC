import os
from dotenv import load_dotenv
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_cerebras import ChatCerebras
from langchain_core.prompts import PromptTemplate

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

    # ── Cypher Generation Prompt ──
    # Note: Double curly braces {{ }} for PromptTemplate
    cypher_template = f"""You are an expert Neo4j Cypher query writer for Worklap.

PROJECT CONTEXT:
- Project Name: "{project_name}"
- Project UUID: "{project_uuid}"

GRAPH SCHEMA:
Nodes:
- Project (name, key, uuid)
- Epic, Story, Task, Bug, Subtask (id, name, title, priority, status)
- User (name, uuid)

Relationships:
- (Project)-[:HAS_EPIC]->(Epic)
- (Project)-[:HAS_ITEM]->(Story|Task|Bug)
- (Epic|Story|Task|Bug)-[:HAS_CHILD]->(child)
- (w)-[:ASSIGNED_TO|REPORTED_TO]->(User)

RULES:
1. ALWAYS use toLower() and CONTAINS for status matching. NEVER use exact matches like {{{{status: 'inprogress'}}}}.
   CORRECT EXAMPLE: MATCH (t:Task) WHERE toLower(t.status) CONTAINS toLower('in progress') RETURN t
2. Map these exact phrases: "todo" -> "to do", "inprogress" -> "in progress".
3. To list all items of a type, just match the label: MATCH (b:Bug) RETURN b
4. DO NOT filter items by the Project UUID unless searching for Project specifically.
5. If searching for Project specifically, use: MATCH (p:Project {{{{uuid: "{project_uuid}"}}}})

Schema:
{{schema}}

Question: {{question}}
Cypher Query:"""

    cypher_prompt = PromptTemplate(input_variables=["schema", "question"], template=cypher_template)

    qa_template = """You are a helpful AI Assistant for Worklap.

DATA FROM DATABASE:
{context}

USER QUESTION:
{question}

INSTRUCTIONS:
Provide a direct, concise answer to the user's question based on the data provided.
- If it's a list of items, format it as a clean bulleted list (e.g. "Task Name (ID) - Status").
- DO NOT use headers like "Executive Summary" or "Progress".
- DO NOT use conversational filler like "Based on the data". Just answer the question immediately.
"""

    qa_prompt = PromptTemplate(input_variables=["context", "question"], template=qa_template)

    llm = ChatCerebras(
        model="llama-3.1-8b",
        cerebras_api_key=os.getenv("CEREBRAS_API_KEY"),
        temperature=0,
    )

    _chain = GraphCypherQAChain.from_llm(
        llm=llm,
        graph=graph,
        cypher_prompt=cypher_prompt,
        qa_prompt=qa_prompt,
        verbose=True,
        return_intermediate_steps=True,
        return_direct=False, 
        allow_dangerous_requests=True,
    )
    return _chain

def ask(question: str) -> dict:
    chain = get_chain()
    result = chain.invoke({"query": question})

    steps   = result.get("intermediate_steps", [])
    cypher  = steps[0].get("query", "") if len(steps) > 0 else ""
    context = steps[1].get("context", []) if len(steps) > 1 else []
    answer  = result.get("result", "I couldn't analyze the project data.")

    return {
        "answer":  answer,
        "cypher":  cypher,
        "context": context,
    }
