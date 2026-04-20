import base64
import pickle
import os
from typing import Dict, Any

from fastapi import FastAPI
from fastapi import Request
from pydantic import BaseModel, Field
from pyicloud import PyiCloudService
from google.cloud import secretmanager
import google.auth

# -----------------------------
# App
# -----------------------------

app = FastAPI()

# -----------------------------
# Config
# -----------------------------

PROJECT_ID = google.auth.default()
if not PROJECT_ID:
    raise RuntimeError("GCP_PROJECT or GOOGLE_CLOUD_PROJECT environment variable is not set")

sm_client = secretmanager.SecretManagerServiceClient()

# -----------------------------
# Helpers
# -----------------------------

def get_secret(secret_id: str) -> str:
    name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
    response = sm_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# -----------------------------
# Business Logic
# -----------------------------

def icloud_photo_bridge(limit: int = 3):
    email = get_secret("icloud_email")
    password = get_secret("icloud_password")
    base64_session = get_secret("icloud_session_token")

    try:
        cookie_bytes = base64.b64decode(base64_session)
        session_cookies = pickle.loads(cookie_bytes)
    except Exception:
        raise Exception("Invalid iCloud session token")

    api = PyiCloudService(email, password)
    api.session.cookies.update(session_cookies)

    if api.requires_2fa:
        raise Exception("iCloud session expired")

    photos = []
    for i, photo in enumerate(api.photos.all):
        if i >= limit:
            break

        photo_data = photo.download("medium").raw.read()
        encoded_image = base64.b64encode(photo_data).decode("utf-8")

        photos.append({
            "filename": photo.filename,
            "data": encoded_image,
            "mime_type": "image/jpeg"
        })

    return photos

# -----------------------------
# MCP Models
# -----------------------------

class ToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

# -----------------------------
# Tool execution (shared)
# -----------------------------

def execute_tool(call: ToolCall):
    if call.name != "icloud_photo_bridge":
        return {
            "content": [
                {"type": "text", "text": f"Unknown tool: {call.name}"}
            ]
        }

    try:
        limit = call.arguments.get("limit", 3)
        photos = icloud_photo_bridge(limit)

        return {
            "content": [
                {
                    "type": "json",
                    "json": {
                        "photos": photos
                    }
                }
            ]
        }

    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error: {str(e)}"
                }
            ]
        }

# -----------------------------
# MCP Endpoints
# -----------------------------

# Tool discovery (manual / optional for Vertex)
@app.post("/v1/tools/list")
def list_tools():
    return {
        "tools": [
            {
                "name": "icloud_photo_bridge",
                "description": "Fetches the most recent iCloud photos using a trusted session",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Number of recent photos",
                            "default": 3
                        }
                    }
                }
            }
        ]
    }

# Tool execution (manual)
@app.post("/v1/tools/call")
async def call_tool(request: Request):
    body = await request.json()
    print("VERTEX TOOL CALL:", body)
    return {"debug": body}

# Vertex MCP entrypoint (IMPORTANT)
@app.post("/")
async def root(request: Request):
    body = await request.json()

    # Try all common MCP shapes
    name = body.get("name") or body.get("tool")
    arguments = body.get("arguments") or body.get("params") or {}

    if name != "icloud_photo_bridge":
        return {
            "content": [
                {"type": "text", "text": f"Unknown tool: {name}"}
            ]
        }

    try:
        limit = arguments.get("limit", 3)
        photos = icloud_photo_bridge(limit)

        return {
            "content": [
                {"type": "json", "json": {"photos": photos}}
            ]
        }

    except Exception as e:
        return {
            "content": [
                {"type": "text", "text": f"Error: {str(e)}"}
            ]
        }

# Health check (useful for Cloud Run)
@app.get("/")
def health():
    return {"status": "ok"}

# -----------------------------
# Local dev entrypoint
# -----------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )