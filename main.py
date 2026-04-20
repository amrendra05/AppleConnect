import base64
import pickle
import os
import logging
from typing import Dict, Any

from fastapi import FastAPI, Request
from pyicloud import PyiCloudService
from google.cloud import secretmanager
import google.auth

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# -----------------------------
# App
# -----------------------------
app = FastAPI()

# -----------------------------
# Config
# -----------------------------
credentials, PROJECT_ID = google.auth.default()
PROJECT_ID = PROJECT_ID or os.environ.get("GOOGLE_CLOUD_PROJECT")

if not PROJECT_ID:
    raise RuntimeError("Missing GCP project ID")

sm_client = secretmanager.SecretManagerServiceClient()

# -----------------------------
# Secrets
# -----------------------------
def get_secret(secret_id: str) -> str:
    name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
    response = sm_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# -----------------------------
# iCloud logic
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
        encoded = base64.b64encode(photo_data).decode("utf-8")

        photos.append({
            "filename": photo.filename,
            "data": encoded,
            "mime_type": "image/jpeg"
        })

    return photos

# -----------------------------
# MCP TOOL DEFINITIONS
# -----------------------------
TOOLS = [
    {
        "name": "icloud_photo_bridge",
        "description": "Fetch latest iCloud photos",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"}
            }
        }
    }
]

# -----------------------------
# TOOL EXECUTION
# -----------------------------
def execute_tool(name: str, arguments: Dict[str, Any]):
    if name != "icloud_photo_bridge":
        return {"error": f"Unknown tool: {name}"}

    limit = arguments.get("limit", 3)
    photos = icloud_photo_bridge(limit)
    return {"photos": photos}

# -----------------------------
# MCP: initialize (IMPORTANT)
# -----------------------------
@app.post("/")
async def mcp_router(request: Request):
    body = await request.json()
    logger.info(f"MCP: {body}")

    method = body.get("method")

    # 1. INITIALIZE handshake
    if method == "initialize":
       return {
          "protocolVersion": body["params"]["protocolVersion"],
          "capabilities": {
             "tools": {}
          },
          "serverInfo": {
             "name": "icloud-mcp",
             "version": "1.0.0"
          }
        }

    # 2. LIST TOOLS
    if method == "tools/list":
        return {"tools": TOOLS}

    # 3. CALL TOOL
    if method == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})

        return execute_tool(name, args)

    return {"error": f"Unknown method: {method}"}

# -----------------------------
# Health
# -----------------------------
@app.get("/")
def health():
    return {"status": "ok"}

# -----------------------------
# Local run
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))