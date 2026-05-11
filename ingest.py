"""
ingest.py — Worklap GraphRAG
Deterministic ingestion with proper typed nodes:
  Project → HAS_EPIC → Epic → HAS_CHILD → Story → HAS_CHILD → Task/Bug → HAS_CHILD → Subtask
"""

import os
import requests
from dotenv import load_dotenv
from langchain_neo4j import Neo4jGraph

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
API_URL        = os.getenv("WORKLAP_API_URL")
JWT_TOKEN      = os.getenv("WORKLAP_JWT_TOKEN")
PROJECT_UUID   = os.getenv("WORKLAP_PROJECT_UUID")
NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "95ee6f84")

# ── User name mapping (UUID → Name) ───────────────────────────────────────────
# Add all your team member UUIDs and names here.
# Run inspect_api.py to find UUIDs from the raw API data.
USER_MAPPING = {
    "867a7473-77c0-41cc-9c34-ee6925d5df20": "Uday Hiremath",
    "9775ed57-76fb-48f4-af9e-664e3c8d5b20": "Admin User",
}

# ── Step 1: Fetch & Flatten ───────────────────────────────────────────────────
def fetch_work_items() -> dict:
    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "projectUuid": PROJECT_UUID,
        "page": 0, "size": 1000,
        "childPage": 0, "childSize": 1000,
        "viewType": "LIST",
    }
    resp = requests.post(API_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    response_data = resp.json()["response"][0]
    # Try several possible keys for project name
    project_name = (
        response_data.get("projectName")
        or response_data.get("name")
        or response_data.get("project", {}).get("name")
        or "UNasa"
    )
    project_key = (
        response_data.get("projectKey")
        or response_data.get("key")
        or PROJECT_UUID[:8]
    )
    return {
        "items":       response_data["data"],
        "projectName": project_name,
        "projectKey":  project_key,
    }

# ── Step 1: Flatten & Clean ───────────────────────────────────────────────────
def flatten_items(items: list, parent_uuid: str | None = None, result: list | None = None) -> list:
    if result is None:
        result = []
    for item in items:
        children = item.pop("childWorkItems", [])
        item["_parentUuid"] = parent_uuid
        result.append(item)
        if children:
            flatten_items(children, parent_uuid=item.get("workItemUuid"), result=result)
    return result

def clean_item(item: dict, project_uuid: str) -> dict:
    assignee_uuid = item.get("workItemAssigneeAppUserUuid") or ""
    reporter_uuid = item.get("workItemReporterAppUserUuid") or ""
    return {
        "uuid":           item.get("workItemUuid"),
        "projectUuid":    project_uuid,  # Tag for smart deletion
        "parentUuid":     item.get("_parentUuid"),
        "id":             item.get("workItemKey"),
        "title":          item.get("title"),
        "type":           item.get("workTypeName", "Unknown"),
        "category":       item.get("workTypeCategory", "UNKNOWN"),
        "priority":       item.get("workPriority", "MEDIUM"),
        "status":         item.get("workStatusName", "Unknown"),
        "statusCategory": item.get("workStatusCategory", ""),
        "createdDate":    item.get("createdDate"),
        "lastModifiedAt": item.get("lastModifiedAt"),
        "subtaskCount":   item.get("totalSubTasksCount", 0),
        "commentsCount":  item.get("totalCommentsCount", 0),
        "loggedMinutes":  item.get("totalLoggedMinutes", 0),
        "loggedTime":     item.get("totalLoggedTime", "0m"),
        "assigneeUuid":   assignee_uuid,
        "assigneeName":   USER_MAPPING.get(assignee_uuid, "Unknown User") if assignee_uuid else "",
        "reporterUuid":   reporter_uuid,
        "reporterName":   USER_MAPPING.get(reporter_uuid, "Unknown User") if reporter_uuid else "",
    }

# ── Class: WorklapGraphSync ───────────────────────────────────────────────────
class WorklapGraphSync:
    def __init__(self):
        self.api_url = API_URL
        self.jwt = JWT_TOKEN
        self.graph = Neo4jGraph(
            url=NEO4J_URI, username=NEO4J_USERNAME,
            password=NEO4J_PASSWORD, database=NEO4J_DATABASE
        )

    def fetch_api_data(self, project_uuid: str) -> dict:
        headers = {"Authorization": f"Bearer {self.jwt}", "Content-Type": "application/json"}
        payload = {
            "projectUuid": project_uuid,
            "page": 0, "size": 1000,
            "childPage": 0, "childSize": 1000,
            "viewType": "LIST",
        }
        resp = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()["response"][0]
        return {
            "items": data["data"],
            "projectName": data.get("projectName") or data.get("name") or "UNasa",
            "projectKey": data.get("projectKey") or data.get("key") or project_uuid[:8]
        }

    def sync_project(self, project_uuid: str) -> dict:
        """Fast, non-destructive targeted sync for a specific project."""
        print(f"Syncing Project: {project_uuid}...")
        
        # 1. Fetch & Prepare Data
        fetched = self.fetch_api_data(project_uuid)
        flat_data = flatten_items(fetched["items"])
        cleaned = [clean_item(i, project_uuid) for i in flat_data]
        api_uuids = [c["uuid"] for c in cleaned if c.get("uuid")]

        print(f"Fetched {len(cleaned)} items. Updating Graph...")

        # 2. Smart Deletion: Remove items that exist in Graph but not in API anymore
        if api_uuids:
            self.graph.query("""
                MATCH (w) 
                WHERE w.projectUuid = $projectUuid AND NOT w.uuid IN $apiUuids
                DETACH DELETE w
            """, params={"projectUuid": project_uuid, "apiUuids": api_uuids})

        # 3. Upsert Project Node
        self.graph.query("""
            MERGE (p:Project {uuid: $uuid})
            SET p.name = $name, p.key = $key
        """, params={"uuid": project_uuid, "name": fetched["projectName"], "key": fetched["projectKey"]})

        # 4. Upsert Work Items
        TYPE_LABEL_MAP = {
            "Epic": "Epic", "Story": "Story", "Task": "Task", 
            "Bug": "Bug", "Sub Task": "Subtask"
        }
        
        for type_name, label in TYPE_LABEL_MAP.items():
            items = [c for c in cleaned if c["type"] == type_name]
            if not items: continue
            
            self.graph.query(f"""
                UNWIND $data AS row
                MERGE (w:{label} {{uuid: row.uuid}})
                SET w.projectUuid    = row.projectUuid,
                    w.id             = row.id,
                    w.name           = row.title,
                    w.title          = row.title,
                    w.type           = row.type,
                    w.priority       = row.priority,
                    w.status         = row.status,
                    w.statusCategory = row.statusCategory
            """, params={"data": items})

        # 5. Build Hierarchy (Parent -> Child)
        self.graph.query("""
            UNWIND $data AS row
            WITH row WHERE row.parentUuid IS NOT NULL AND row.parentUuid <> ''
            MATCH (child {uuid: row.uuid}), (parent {uuid: row.parentUuid})
            MERGE (parent)-[:HAS_CHILD]->(child)
        """, params={"data": cleaned})

        # 6. Link to Project (Epics get HAS_EPIC, others get HAS_ITEM)
        self.graph.query("""
            UNWIND $data AS row
            WITH row WHERE row.type = 'Epic' AND (row.parentUuid IS NULL OR row.parentUuid = '')
            MATCH (p:Project {uuid: $projectUuid}), (e:Epic {uuid: row.uuid})
            MERGE (p)-[:HAS_EPIC]->(e)
        """, params={"data": cleaned, "projectUuid": project_uuid})

        self.graph.query("""
            UNWIND $data AS row
            WITH row WHERE row.type IN ['Story', 'Task', 'Bug'] AND (row.parentUuid IS NULL OR row.parentUuid = '')
            MATCH (p:Project {uuid: $projectUuid}), (w {uuid: row.uuid})
            MERGE (p)-[:HAS_ITEM]->(w)
        """, params={"data": cleaned, "projectUuid": project_uuid})

        self.graph.refresh_schema()
        print("Sync Complete!")
        return {"total_items": len(cleaned)}

# ── Wrapper for App.py compatibility ──────────────────────────────────────────
def run_ingest():
    sync = WorklapGraphSync()
    return sync.sync_project(PROJECT_UUID)

if __name__ == "__main__":
    run_ingest()
