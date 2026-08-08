"""H-Zero — Webhook Routes (standalone)."""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

WEBHOOK_SECRETS = {
    "pubmed": "pubmed-webhook-secret-dev",
    "github": "github-webhook-secret-dev",
    "ci_cd": "ci-cd-webhook-secret-dev",
}


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


@router.post("/{source}")
async def receive_webhook(
    source: str,
    request: Request,
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
):
    if source not in WEBHOOK_SECRETS:
        raise HTTPException(404, f"Unknown webhook source: {source}")

    payload = await request.body()
    secret = WEBHOOK_SECRETS[source]

    if x_hub_signature_256:
        if not verify_signature(payload, x_hub_signature_256, secret):
            raise HTTPException(401, "Invalid webhook signature")

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON payload")

    event_id = str(uuid.uuid4())
    return {
        "event_id": event_id, "source": source, "status": "accepted",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/status")
async def webhook_status():
    return {"configured_sources": list(WEBHOOK_SECRETS.keys()), "status": "active"}
