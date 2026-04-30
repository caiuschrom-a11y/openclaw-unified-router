"""SaaS API gateway: validate ock_xxx tokens and proxy to Anthropic.

Architecture:
    customer pays via Stripe Checkout
        → webhook generates ock_xxx, attaches to Stripe customer metadata
        → email delivers ock_xxx to buyer
    buyer calls /v1/<slug>/<endpoint> with `Authorization: Bearer ock_xxx`
        → this module validates the token via Stripe customer search
        → applies the product-specific prompt/system message
        → proxies to Anthropic with our backend key
        → tracks usage via Stripe customer metadata
        → returns Claude response

Why Stripe-as-DB: Vercel serverless filesystem is ephemeral, and we don't
want to operate a separate database for v1. Stripe Customer + Subscription
metadata is durable, free, and we already query it on every webhook.

Quota: each plan declares `monthly_quota` in its catalog metadata. The
gateway increments `calls_this_month` on the Stripe customer and 429s when
exceeded. The counter resets via a monthly Stripe webhook (TODO).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

import stripe
from fastapi import APIRouter, HTTPException, Header, Request

router = APIRouter()

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Per-product prompt templates. Each entry maps a product slug to a system
# prompt + a function building the user content from the request body. This
# is what makes "coldmail" different from "code-review-bot" — same backend,
# different domain knowledge applied.
PRODUCT_PROMPTS: dict[str, dict[str, Any]] = {
    "coldmail": {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 800,
        "system": (
            "You write cold-emails that get replies. Tone: brief, specific, no fluff. "
            "Open with one observation about the recipient or their company. "
            "Make ONE concrete ask. End with a one-line PS that creates curiosity. "
            "Output only the email body — no subject line, no signature placeholders."
        ),
        "build_user": lambda body: (
            f"Recipient: {body.get('recipient_name', '(unknown)')} at {body.get('recipient_company', '(unknown)')}\n"
            f"Their context: {body.get('context', '')}\n"
            f"My offer / ask: {body.get('offer', '')}\n"
            f"My company: {body.get('sender_company', '')}\n"
            "Write the email."
        ),
    },
    "code-review-bot": {
        "model": "claude-sonnet-4-6",
        "max_tokens": 2000,
        "system": (
            "You review pull requests like a senior engineer. Focus only on issues "
            "that genuinely matter: bugs, race conditions, security, regressions, "
            "test gaps. Skip nits and style unless they obscure logic. "
            "Cite the line you mean. End with VERDICT: APPROVE / REQUEST_CHANGES / COMMENT."
        ),
        "build_user": lambda body: (
            f"PR title: {body.get('pr_title', '')}\n"
            f"PR description: {body.get('pr_description', '')}\n"
            f"Diff:\n```\n{body.get('diff', '')}\n```\n"
            "Review."
        ),
    },
    "pricing-intel": {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1000,
        "system": (
            "You analyze competitor pricing pages. Extract: tier names, monthly "
            "prices, listed features, target segments. Flag anything ambiguous. "
            "Return strict JSON: {tiers: [{name, price_monthly_usd, features: [...], notes}]}"
        ),
        "build_user": lambda body: (
            f"Competitor: {body.get('competitor', '')}\n"
            f"Page text:\n```\n{body.get('page_text', '')}\n```\n"
            "Extract pricing."
        ),
    },
    "shopify-support-bot": {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 600,
        "system": (
            "You answer Shopify-store customer support questions. Be friendly, "
            "concise, and specific. Reference the customer's order if provided. "
            "Never invent shipping dates or refund policies — defer to the operator "
            "if you don't know."
        ),
        "build_user": lambda body: (
            f"Store: {body.get('store_name', '')}\n"
            f"Customer order: {body.get('order_summary', '')}\n"
            f"Customer message: {body.get('customer_message', '')}\n"
            f"Store policies: {body.get('policies', '(none provided)')}\n"
            "Reply."
        ),
    },
    "meeting-notes-bot": {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1500,
        "system": (
            "You produce concise meeting notes from a transcript. Output four "
            "sections: TLDR (1 sentence), DECISIONS (bulleted), ACTION ITEMS "
            "(owner — task — due-date), OPEN QUESTIONS (bulleted)."
        ),
        "build_user": lambda body: (
            f"Meeting: {body.get('meeting_title', '')}\n"
            f"Attendees: {body.get('attendees', '')}\n"
            f"Transcript:\n```\n{body.get('transcript', '')}\n```\n"
            "Notes."
        ),
    },
    "chargeback-drafter": {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1800,
        "system": (
            "You draft chargeback rebuttal letters for SMB merchants. Address the "
            "specific dispute reason. Cite delivery proof, customer agreement, "
            "and any provided communications. Tone: professional, factual."
        ),
        "build_user": lambda body: (
            f"Dispute reason: {body.get('reason_code', '')} - {body.get('reason_text', '')}\n"
            f"Order: {body.get('order_summary', '')}\n"
            f"Evidence available: {body.get('evidence', '')}\n"
            "Draft the rebuttal."
        ),
    },
    "legal-doc-drafter": {
        "model": "claude-sonnet-4-6",
        "max_tokens": 3000,
        "system": (
            "You draft contract templates for SMB founders. Plain English where "
            "possible. Mark every blank to fill with [BRACKETS]. Include a brief "
            "explainer comment for each major clause. End with a JURISDICTION + "
            "REVIEW BY ATTORNEY disclaimer."
        ),
        "build_user": lambda body: (
            f"Document type: {body.get('doc_type', '')}\n"
            f"Parties: {body.get('parties', '')}\n"
            f"Key terms: {body.get('key_terms', '')}\n"
            f"Jurisdiction: {body.get('jurisdiction', 'unspecified')}\n"
            "Draft."
        ),
    },
    "voice-agent-smb": {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 800,
        "system": (
            "You are a phone receptionist for a small business. Answer in one or "
            "two short sentences. Capture: caller name, callback number, reason "
            "for call. If asked about pricing/availability, answer if known else "
            "promise a callback. Do not invent details."
        ),
        "build_user": lambda body: (
            f"Business: {body.get('business_name', '')}\n"
            f"Business hours: {body.get('hours', '')}\n"
            f"Services: {body.get('services', '')}\n"
            f"Caller said: {body.get('caller_input', '')}\n"
            f"Conversation so far: {body.get('history', '')}\n"
            "Respond."
        ),
    },
    "hipaa-doc-intake": {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1500,
        "system": (
            "You extract structured intake fields from patient-facing forms. "
            "Output JSON only. Fields: full_name, dob, mrn, presenting_concern, "
            "medications, allergies, insurance_carrier, insurance_member_id. "
            "Use null if not present. Do NOT invent values."
        ),
        "build_user": lambda body: (
            f"Form text:\n```\n{body.get('form_text', '')}\n```\n"
            "Extract."
        ),
    },
}


def _stripe_key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise HTTPException(500, "STRIPE_SECRET_KEY not set")
    stripe.api_key = key
    return key


def _validate_token(token: str, product_slug: str) -> dict[str, Any]:
    """Validate ock_xxx against Stripe customer metadata. Returns customer obj
    on success. Raises HTTPException on failure."""
    if not token.startswith("ock_"):
        raise HTTPException(401, "invalid token format")
    _stripe_key()
    try:
        results = stripe.Customer.search(
            query=f'metadata["openclaw_api_key"]:"{token}" AND metadata["product_slug"]:"{product_slug}"',
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"auth backend unavailable: {e}")
    customers = list(results.auto_paging_iter()) if hasattr(results, "auto_paging_iter") else results.data
    if not customers:
        raise HTTPException(401, "unknown or revoked token")
    customer = customers[0]
    # Stripe objects don't have .get(); use dict-style access via __getitem__.
    md_obj = customer["metadata"] if "metadata" in customer else None
    # StripeObject metadata is dict-like but `dict(md)` iterates with integer
    # indices and raises KeyError. Convert via the keys() iterator.
    md_dict: dict[str, Any] = {}
    if md_obj is not None:
        try:
            for k in list(md_obj.keys()):
                md_dict[k] = md_obj[k]
        except Exception:  # noqa: BLE001
            md_dict = {}
    if md_dict.get("status") == "canceled":
        raise HTTPException(403, "subscription canceled")
    return {
        "id": customer["id"],
        "email": customer["email"] if "email" in customer else None,
        "metadata": md_dict,
    }


def _bump_quota(customer_id: str, used: int = 1) -> None:
    """Best-effort increment of calls_this_month. Stripe metadata values are
    strings so we have to read-modify-write."""
    try:
        c = stripe.Customer.retrieve(customer_id)
        md = c["metadata"] if "metadata" in c else {}
        prev = int(md["calls_this_month"]) if "calls_this_month" in md and md["calls_this_month"] else 0
        stripe.Customer.modify(
            customer_id,
            metadata={"calls_this_month": str(prev + used)},
        )
    except Exception as e:  # noqa: BLE001
        # Don't fail the user request just because the meter tick failed.
        print(f"[gateway] quota tick failed for {customer_id}: {e}")


def _call_qwen_fallback(system: str, user_content: str, max_tokens: int) -> tuple[bool, str, dict[str, Any] | str]:
    """Fallback to a self-hosted Qwen via Ollama (HTTP). The user runs Ollama
    locally and exposes it via a Cloudflare Tunnel; the public URL goes into
    QWEN_PROXY_URL on the router. Wraps Ollama's response so it looks like
    an Anthropic content block."""
    base = os.environ.get("QWEN_PROXY_URL", "").rstrip("/")
    if not base:
        return (False, "no_qwen", "QWEN_PROXY_URL not set on router")
    model = os.environ.get("QWEN_MODEL", "qwen3-30b")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        # Qwen3 has hybrid thinking; disable it so num_predict isn't burned
        # on internal reasoning the buyer never sees.
        "think": False,
        "options": {"num_predict": max_tokens, "temperature": 0.6},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "openclaw-products/0.1",
    }
    # If the tunnel is protected by a Cloudflare Access token, support it.
    cf_access = os.environ.get("QWEN_PROXY_CF_ACCESS")
    if cf_access:
        headers["CF-Access-Client-Secret"] = cf_access
    try:
        req = urllib.request.Request(f"{base}/api/chat", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        text = d.get("message", {}).get("content", "")
        # Re-shape into an Anthropic-compatible response so the rest of the
        # gateway code doesn't need to branch.
        return (True, "ok_qwen", {"content": [{"type": "text", "text": text}]})
    except urllib.error.HTTPError as e:
        return (False, f"qwen_http_{e.code}", e.read().decode("utf-8", errors="replace")[:400])
    except Exception as e:  # noqa: BLE001
        return (False, "qwen_err", f"{type(e).__name__}: {e}")


def _call_anthropic(system: str, user_content: str, model: str, max_tokens: int) -> tuple[bool, str, dict[str, Any] | str]:
    """One Anthropic call with retry on 429/5xx. Returns (ok, status_label, body).

    Prompt caching: the per-product `system` prompt is static, so we mark it
    with cache_control=ephemeral. After the first call per product, subsequent
    calls in the 5-minute window read the system prompt from cache at 1/10th
    the input-token cost. This is the single biggest token-spend lever.

    On Anthropic insufficient_credit / not configured: falls through to Qwen
    via QWEN_PROXY_URL when set. This keeps SaaS products live during Anthropic
    propagation issues."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    # If operator has set FORCE_QWEN=1, skip Anthropic entirely (useful when
    # we know the Anthropic balance is empty — saves 1-2s on the inevitable
    # 400 response before falling through).
    force_qwen = os.environ.get("FORCE_QWEN", "").strip().lower() in ("1", "true", "yes")
    if force_qwen or not api_key:
        ok, status, body = _call_qwen_fallback(system, user_content, max_tokens)
        if ok:
            return (True, "ok_qwen", body)
        return (False, "qwen_only_path_failed", f"Qwen fallback failed: {body}")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}},
        ],
        "messages": [{"role": "user", "content": user_content}],
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "openclaw-products/0.1",
        # cache_control needs the prompt-caching beta header.
        "anthropic-beta": "prompt-caching-2024-07-31",
    }
    backoff = [0.5, 2.0, 5.0]
    last = ""
    for attempt, sleep_s in enumerate(backoff, start=1):
        req = urllib.request.Request(ANTHROPIC_API, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return (True, "ok", json.loads(resp.read().decode("utf-8")))
        except urllib.error.HTTPError as e:
            code = e.code
            err_body = e.read().decode("utf-8", errors="replace")
            last = f"HTTP {code}: {err_body[:500]}"
            # Special-case: Anthropic credit balance too low → fall through to Qwen
            if "credit balance is too low" in err_body or "insufficient_quota" in err_body:
                ok, qstatus, qbody = _call_qwen_fallback(system, user_content, max_tokens)
                if ok:
                    return (True, "ok_qwen_fallback", qbody)
                # Both upstreams down — surface both errors
                return (False, "anthropic_zero_balance_qwen_fail", f"anthropic: {last} | qwen: {qbody}")
            if 400 <= code < 500 and code != 429:
                return (False, f"http_{code}", last)
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        if attempt < len(backoff):
            time.sleep(sleep_s)
    # All Anthropic retries exhausted — try Qwen as a last resort
    ok, qstatus, qbody = _call_qwen_fallback(system, user_content, max_tokens)
    if ok:
        return (True, "ok_qwen_after_anthropic_retries", qbody)
    return (False, "retry_exhausted", f"{last} | qwen: {qbody}")


@router.post("/v1/{product_slug}/run")
async def run_product(product_slug: str, request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()

    if product_slug not in PRODUCT_PROMPTS:
        raise HTTPException(404, f"unknown product: {product_slug}")

    customer = _validate_token(token, product_slug)
    md = customer.get("metadata", {}) or {}
    quota = int(md.get("monthly_quota", "0") or "0")
    used = int(md.get("calls_this_month", "0") or "0")
    if quota and used >= quota:
        raise HTTPException(429, f"monthly quota exceeded ({used}/{quota})")

    body = await request.json()
    cfg = PRODUCT_PROMPTS[product_slug]
    user_content = cfg["build_user"](body)
    ok, status, response = _call_anthropic(
        system=cfg["system"], user_content=user_content,
        model=cfg["model"], max_tokens=cfg["max_tokens"],
    )
    if not ok:
        # Translate common upstream failures into actionable buyer-facing messages.
        msg = str(response)[:500]
        if "credit balance is too low" in msg or "insufficient_quota" in msg:
            raise HTTPException(503, "service temporarily paused (operator notified). Email support@openclaw.dev for status.")
        if "rate_limit" in msg.lower() or "429" in msg:
            raise HTTPException(429, "rate limit hit. Try again in 30s, or upgrade plan for higher limits.")
        if "api_key" in msg.lower() or "auth" in msg.lower() or "401" in msg:
            raise HTTPException(503, "auth error with upstream LLM (operator notified)")
        raise HTTPException(502, f"upstream LLM failed: {status} | {msg[:200]}")

    _bump_quota(customer["id"])
    # Strip Anthropic's full response, return only the assistant text + meta
    text = ""
    if isinstance(response, dict):
        for block in response.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
    return {
        "product": product_slug,
        "result": text,
        "model": cfg["model"],
        "quota": {"used": used + 1, "limit": quota or None},
    }


PRODUCT_SCHEMAS: dict[str, dict[str, Any]] = {
    "coldmail": {
        "fields": {
            "recipient_name": "string — name of the prospect",
            "recipient_company": "string — their company",
            "context": "string — what you know about them (recent post, role, team size)",
            "offer": "string — your concrete ask in one line",
            "sender_company": "string — your company name",
        },
        "example": {
            "recipient_name": "Sarah Chen",
            "recipient_company": "Acme Robotics",
            "context": "Saw their Series A announcement; they're scaling QA",
            "offer": "30-min walkthrough of how we cut their automated-test runtime 4x",
            "sender_company": "FastTest Co",
        },
    },
    "code-review-bot": {
        "fields": {
            "pr_title": "string",
            "pr_description": "string",
            "diff": "string — unified-diff of the PR",
        },
        "example": {
            "pr_title": "Add caching to user lookup",
            "pr_description": "Reduces p99 by 40%",
            "diff": "--- a/users.py\n+++ b/users.py\n@@\n+from functools import lru_cache\n+@lru_cache(maxsize=1024)\n def lookup(user_id):\n     ...",
        },
    },
    "pricing-intel": {
        "fields": {"competitor": "string", "page_text": "string — pasted pricing-page content"},
        "example": {"competitor": "Stripe", "page_text": "Standard 2.9% + 30¢ per transaction. Pro: custom..."},
    },
    "shopify-support-bot": {
        "fields": {
            "store_name": "string", "order_summary": "string",
            "customer_message": "string", "policies": "string (optional)",
        },
        "example": {
            "store_name": "Bear & Honey",
            "order_summary": "#1234, 1x organic raw honey 16oz, shipped 3 days ago via USPS",
            "customer_message": "I haven't received my order yet, where is it?",
            "policies": "Standard: 5-7 business days. Refund within 30 days if defective.",
        },
    },
    "meeting-notes-bot": {
        "fields": {
            "meeting_title": "string", "attendees": "string",
            "transcript": "string — full meeting transcript",
        },
        "example": {
            "meeting_title": "Q1 product roadmap",
            "attendees": "Alice, Bob, Carol",
            "transcript": "Alice: Should we ship feature X first? Bob: Let's...",
        },
    },
    "chargeback-drafter": {
        "fields": {
            "reason_code": "string e.g. 4855", "reason_text": "string",
            "order_summary": "string", "evidence": "string",
        },
        "example": {
            "reason_code": "4855",
            "reason_text": "Goods/services not received",
            "order_summary": "Order #1234, $89, shipped Jan 5 via UPS 1Z...",
            "evidence": "UPS tracking shows delivered Jan 8. Customer signed.",
        },
    },
    "legal-doc-drafter": {
        "fields": {
            "doc_type": "string (NDA, Contractor Agreement, Mutual NDA, Letter of Intent)",
            "parties": "string — names + roles",
            "key_terms": "string", "jurisdiction": "string e.g. Delaware",
        },
        "example": {
            "doc_type": "Mutual NDA",
            "parties": "Acme Corp (Delaware C-Corp) and Bob Smith (independent consultant)",
            "key_terms": "2-year term, mutual disclosure of trade secrets, standard carve-outs",
            "jurisdiction": "Delaware",
        },
    },
    "voice-agent-smb": {
        "fields": {
            "business_name": "string", "hours": "string", "services": "string",
            "caller_input": "string", "history": "string (optional)",
        },
        "example": {
            "business_name": "Joe's Plumbing",
            "hours": "Mon-Fri 8am-6pm",
            "services": "Drain cleaning, water heater install, leak repair",
            "caller_input": "Hi, my water heater is leaking, can someone come today?",
        },
    },
    "hipaa-doc-intake": {
        "fields": {"form_text": "string — full intake form content"},
        "example": {
            "form_text": "Patient Name: Jane Doe\nDOB: 1985-03-12\nMRN: 100234\nPresenting concern: Persistent cough...",
        },
    },
}


@router.get("/v1/{product_slug}/info")
def product_info(product_slug: str) -> dict[str, Any]:
    """Public — describes the product's expected request body schema."""
    if product_slug not in PRODUCT_PROMPTS:
        raise HTTPException(404, f"unknown product: {product_slug}")
    cfg = PRODUCT_PROMPTS[product_slug]
    schema = PRODUCT_SCHEMAS.get(product_slug, {})
    return {
        "slug": product_slug,
        "model": cfg["model"],
        "max_tokens": cfg["max_tokens"],
        "endpoint": f"POST /v1/{product_slug}/run",
        "auth": "Bearer ock_xxx (your API key)",
        "system_prompt_preview": cfg["system"][:200] + "...",
        "request_fields": schema.get("fields", {}),
        "example_request": schema.get("example", {}),
        "curl": (
            f"curl -X POST -H 'Authorization: Bearer ock_xxx' \\\n"
            f"     -H 'Content-Type: application/json' \\\n"
            f"     -d '{__import__('json').dumps(schema.get('example', {}))}' \\\n"
            f"     https://openclawapi.vercel.app/v1/{product_slug}/run"
        ),
    }
