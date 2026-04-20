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
logger = logging.getLogger(__name__)

# -----------------------------
# App
# -----------------------------

app = FastAPI()

# -----------------------------
# Config (Cloud Run safe)
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
# Core logic
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
# Tool execution
# -----------------------------

def execute_tool(name: str, arguments: Dict[str, Any]):

    if name != "icloud_photo_bridge":
        return {"error": f"Unknown tool: {name}"}

    try:
        limit = arguments.get("limit", 3)
        photos = icloud_photo_bridge(limit)
        return {"photos": photos}

    except Exception as e:
        logger.exception("Tool execution failed")
        return {"error": str(e)}

# -----------------------------
# Vertex entrypoint (IMPORTANT)
# -----------------------------

@app.post("/")
async def root(request: Request):

    try:
        body = await request.json()
    except Exception:
        raw = (await request.body()).decode("utf-8")
        logger.error(f"Invalid JSON received: {raw}")
        return {"error": "invalid JSON"}

    logger.info(f"Vertex request: {body}")

    # Normalize Vertex tool formats
    name = (
        body.get("name")
        or body.get("tool")
        or (body.get("functionCall") or {}).get("name")
    )

    arguments = (
        body.get("arguments")
        or body.get("params")
        or (body.get("functionCall") or {}).get("args")
        or {}
    )

    if not name:
        return {"error": "missing tool name"}

    return execute_tool(name, arguments)

# -----------------------------
# Health check
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