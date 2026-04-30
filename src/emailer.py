"""Outbound email sender.

Uses Resend (https://resend.com) when RESEND_API_KEY is set. Falls back
to writing the email to disk under _shared/data/_outbox/ so we never
silently drop a customer-facing message even when no provider is wired.

Why Resend: simplest API, free 3k/mo + 100/day, no DKIM song-and-dance
to get started — they verify a sender domain or you can send from
onboarding@resend.dev for development.

To upgrade later: drop in SES, Postmark, or SendGrid behind the same
`send` signature.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("PRODUCTS_DATA_DIR", r"C:\openclaw-products\_shared\data"))
OUTBOX = DATA_DIR / "_outbox"

DEFAULT_FROM = os.environ.get("EMAIL_FROM", "openclaw <onboarding@resend.dev>")
SUPPORT_FROM = os.environ.get("SUPPORT_EMAIL", "support@openclaw.dev")


def _persist(payload: dict[str, Any], status: str) -> Path:
    OUTBOX.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    fp = OUTBOX / f"{ts}-{status}.json"
    fp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return fp


def _resend_send_once(api_key: str, *, sender: str, to: str, subject: str, body_text: str, body_html: str | None) -> tuple[bool, str, int | None]:
    payload: dict[str, Any] = {
        "from": sender,
        "to": [to],
        "subject": subject,
        "text": body_text,
    }
    if body_html:
        payload["html"] = body_html

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "openclaw-products/0.1 (+https://openclaw.dev)",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")
            return (resp.status < 300, data, resp.status)
    except urllib.error.HTTPError as e:
        return (False, f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}", e.code)
    except Exception as e:  # noqa: BLE001
        return (False, f"{type(e).__name__}: {e}", None)


def _resend_send(api_key: str, **kw: Any) -> tuple[bool, str]:
    """Retry transient failures (network, 5xx, 429) up to 3x with backoff.

    Permanent failures (4xx other than 429) bail immediately so we don't
    burn the rate-limit on guaranteed-bad inputs.
    """
    import time as _time
    backoff = [0.5, 2.0, 5.0]
    last_detail = ""
    for attempt, sleep_s in enumerate(backoff, start=1):
        ok, detail, status = _resend_send_once(api_key, **kw)
        last_detail = detail
        if ok:
            return (True, detail)
        retryable = status is None or status >= 500 or status == 429
        if not retryable:
            return (False, detail)
        if attempt < len(backoff):
            _time.sleep(sleep_s)
    return (False, f"giving up after retries; last: {last_detail}")


def send(*, to: str, subject: str, body_text: str, body_html: str | None = None, sender: str | None = None) -> dict[str, Any]:
    """Send an email. Returns a dict describing what happened.

    Always persists a copy of the message under _outbox/. If RESEND_API_KEY
    is set, attempts the live send; on success the disk record is marked
    `sent`, on failure `failed` (and the operator can re-drive from disk).
    Without an API key, drops to `pending` so the operator can hand-deliver.
    """
    sender = sender or DEFAULT_FROM
    record = {
        "to": to,
        "from": sender,
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        record["status"] = "pending_no_provider"
        record["note"] = "RESEND_API_KEY not set — message persisted to outbox; deliver manually or re-drive once configured"
        path = _persist(record, "pending")
        return {"status": "pending", "outbox_path": str(path)}

    ok, detail = _resend_send(
        api_key,
        sender=sender,
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
    record["resend_response"] = detail[:1000]
    record["status"] = "sent" if ok else "failed"

    # Fallback: when Resend rejects because the account is in test mode and
    # the recipient is not the verified account email, re-route to operator
    # so the message isn't lost. Operator can manually forward to the buyer.
    if not ok and "verify a domain" in detail:
        operator = os.environ.get("OPERATOR_EMAIL", "")
        if operator and operator != to:
            forward_subject = f"[FORWARD TO {to}] {subject}"
            forward_body = (
                f"--- Re-routed because Resend domain not yet verified ---\n"
                f"Original recipient: {to}\n"
                f"Subject: {subject}\n\n"
                f"{body_text}"
            )
            ok2, detail2 = _resend_send(
                api_key,
                sender=sender,
                to=operator,
                subject=forward_subject,
                body_text=forward_body,
                body_html=None,
            )
            record["fallback_to_operator"] = ok2
            record["fallback_detail"] = detail2[:500]
            record["status"] = "rerouted_to_operator" if ok2 else "failed"

    path = _persist(record, record["status"].split("_")[0])
    return {"status": record["status"], "outbox_path": str(path), "detail": detail[:300]}
