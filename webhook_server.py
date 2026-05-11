"""
webhook_server.py — Worklap GraphRAG Webhook Listener
Run with: uvicorn webhook_server:app --port 8000
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from ingest import WorklapGraphSync
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WorklapWebhook")

app = FastAPI(title="Worklap Graph Sync Webhook")

class WorklapEvent(BaseModel):
    event_type: str        # e.g., "EPIC_CREATED", "STORY_UPDATED"
    project_uuid: str      # The ID of the project that was updated
    timestamp: str         # When it happened

def trigger_graph_sync(project_uuid: str):
    """Background task to sync the graph without blocking the API response."""
    try:
        logger.info(f"Starting background sync for Project: {project_uuid}")
        sync = WorklapGraphSync()
        result = sync.sync_project(project_uuid)
        logger.info(f"Sync complete! {result['total_items']} items updated.")
    except Exception as e:
        logger.error(f"Sync failed for {project_uuid}: {e}")

@app.post("/webhook/worklap")
async def handle_worklap_event(event: WorklapEvent, background_tasks: BackgroundTasks):
    """
    Endpoint for Worklap to send events to.
    It immediately returns a 200 OK so Worklap doesn't hang,
    and runs the graph update in the background.
    """
    if not event.project_uuid:
        raise HTTPException(status_code=400, detail="Missing project_uuid")

    logger.info(f"Received {event.event_type} event for project {event.project_uuid}")
    
    # Send the sync job to the background
    background_tasks.add_task(trigger_graph_sync, event.project_uuid)
    
    return {"status": "success", "message": "Graph sync queued."}

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "Neo4j Sync Webhook"}
