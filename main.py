import base64
import pickle
import os

from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Dict, Any
from pyicloud import PyiCloudService
from google.cloud import secretmanager

# -----------------------------
# App + clients
# -----------------------------

app = FastAPI()

sm_client = secretmanager.SecretManagerServiceClient()
PROJECT_ID = os.environ.get("GCP_PROJECT")

# -----------------------------
# Helpers
# -----------------------------

def get_secret(secret_id):
    name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
    response = sm_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# -----------------------------
# Your ORIGINAL business logic
# -----------------------------

def icloud_photo_bridge(limit: int = 3):
    email = get_secret("icloud_email")
    password = get_secret("icloud_password")
    base64_session = get_secret("icloud_session_token")

    cookie_bytes = base64.b64decode(base64_session)
    session_cookies = pickle.loads(cookie_bytes)

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
# MCP: Tool discovery
# -----------------------------

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

# -----------------------------
# MCP: Tool execution
# -----------------------------

class ToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

@app.post("/v1/tools/call")
def call_tool(call: ToolCall):
    if call.name != "icloud_photo_bridge":
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Unknown tool: {call.name}"
                }
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
# Local dev entrypoint
# -----------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
