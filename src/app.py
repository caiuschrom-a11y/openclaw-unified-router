"""Unified Stripe checkout + webhook router for the openclaw-products catalog.

Routes:
    POST /v1/checkout/{product_slug}/{tier_name}   — creates a Checkout session
    POST /webhook/stripe                            — handles Stripe webhooks
    GET  /healthz                                   — liveness
    GET  /v1/products                               — public catalog listing

Per-product fulfillment is dispatched in `fulfillment.py` based on
`fulfillment_kind`:
    api_key          → generate API token, email to customer
    license_key      → generate license key, email
    concierge_email  → drop order in `_shared/data/<product>/ready/` for manual fulfillment
    subscription_only → just store the subscription; no provisioning
"""

from __future__ import annotations

import os
from pathlib import Path

import stripe
import yaml
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import catalog, fulfillment, gateway

app = FastAPI(title="openclaw-products unified router", version="0.1.0")
app.include_router(gateway.router)


def _stripe_key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise HTTPException(500, "STRIPE_SECRET_KEY not set")
    stripe.api_key = key
    return key


def _price_for(display_name: str) -> str:
    price_map_file = Path(__file__).resolve().parent.parent / "price_ids.yaml"
    if not price_map_file.exists():
        raise HTTPException(500, "price_ids.yaml not generated yet — run stripe_setup --confirm")
    price_map = yaml.safe_load(price_map_file.read_text(encoding="utf-8")) or {}
    pid = price_map.get(display_name)
    if not pid:
        raise HTTPException(404, f"no Stripe price for {display_name!r}")
    return pid


# --- public catalog ---

@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/_debug/price")
def debug_price(price_id: str) -> dict:
    """Trace why price-fetch is returning None on the deployed router."""
    import traceback
    info: dict = {"price_id": price_id}
    info["stripe_key_set"] = bool(os.environ.get("STRIPE_SECRET_KEY"))
    price_map_file = Path(__file__).resolve().parent.parent / "price_ids.yaml"
    info["price_yaml_path"] = str(price_map_file)
    info["price_yaml_exists"] = price_map_file.exists()
    if price_map_file.exists():
        try:
            data = yaml.safe_load(price_map_file.read_text(encoding="utf-8"))
            info["yaml_keys_count"] = len(data) if isinstance(data, dict) else 0
        except Exception as e:  # noqa: BLE001
            info["yaml_load_error"] = str(e)
    try:
        _stripe_key()
        p = stripe.Price.retrieve(price_id)
        info["stripe_amount"] = p["unit_amount"] if "unit_amount" in p else None
        info["stripe_currency"] = p["currency"] if "currency" in p else None
        if "recurring" in p and p["recurring"] is not None:
            r = p["recurring"]
            info["stripe_interval"] = r["interval"] if "interval" in r else None
    except Exception as e:  # noqa: BLE001
        info["stripe_error"] = f"{type(e).__name__}: {e}"
        info["traceback"] = traceback.format_exc()[:800]
    return info


_PRICE_CACHE: dict[str, dict] = {}


def _fetch_price_amount(price_id: str) -> tuple[int | None, str | None, str | None]:
    """Returns (amount_cents, currency, recurring_interval) — cached per-process."""
    if price_id in _PRICE_CACHE:
        c = _PRICE_CACHE[price_id]
        return c.get("amount"), c.get("currency"), c.get("interval")
    try:
        _stripe_key()
        p = stripe.Price.retrieve(price_id)
        # StripeObject supports __getitem__ but not .get(); use try/except per field.
        amount = p["unit_amount"] if "unit_amount" in p else None
        currency = p["currency"] if "currency" in p else None
        interval = None
        if "recurring" in p and p["recurring"] is not None:
            recurring = p["recurring"]
            interval = recurring["interval"] if "interval" in recurring else None
        _PRICE_CACHE[price_id] = {"amount": amount, "currency": currency, "interval": interval}
        return amount, currency, interval
    except Exception as e:  # noqa: BLE001
        print(f"[price-fetch] {price_id}: {type(e).__name__}: {e}")
        _PRICE_CACHE[price_id] = {}
        return None, None, None


@app.get("/v1/products")
def list_products() -> dict:
    price_map_file = Path(__file__).resolve().parent.parent / "price_ids.yaml"
    price_map = yaml.safe_load(price_map_file.read_text(encoding="utf-8")) if price_map_file.exists() else {}

    out = []
    for p in catalog.CATALOG:
        pid = price_map.get(p.display_name)
        amount = currency = interval = None
        if pid:
            amount, currency, interval = _fetch_price_amount(pid)
        out.append({
            "slug": p.product_slug,
            "name": p.display_name,
            "description": p.description,
            "pricing_model": p.pricing_model,
            "metadata": p.metadata,
            "configured": pid is not None,
            "price_cents": amount,
            "currency": currency,
            "interval": interval,
        })
    return {"count": len(out), "products": out}


# --- checkout ---

class CheckoutIn(BaseModel):
    customer_email: str | None = None  # if absent, Stripe Checkout collects on hosted page
    success_url: str | None = None
    cancel_url: str | None = None
    quantity: int = 1
    metadata: dict[str, str] = {}


class PortalIn(BaseModel):
    customer_email: str
    return_url: str | None = None


@app.post("/v1/portal")
def customer_portal(payload: PortalIn) -> dict:
    """Create a Stripe Customer Portal session so the buyer can manage their
    subscription, update payment method, view invoices, or cancel."""
    _stripe_key()
    customers = stripe.Customer.list(email=payload.customer_email, limit=1)
    if not customers.data:
        raise HTTPException(404, f"no customer found for {payload.customer_email}")
    site = os.environ.get("PORTFOLIO_SITE_URL", "https://portfolio-site-beta-swart-35.vercel.app")
    return_url = payload.return_url or site
    session = stripe.billing_portal.Session.create(
        customer=customers.data[0].id,
        return_url=return_url,
    )
    return {"portal_url": session.url}


@app.post("/v1/checkout/{product_slug}/{tier_name}")
def create_checkout(product_slug: str, tier_name: str, payload: CheckoutIn) -> dict:
    _stripe_key()
    skus = [p for p in catalog.CATALOG if p.product_slug == product_slug]
    if not skus:
        raise HTTPException(404, f"unknown product: {product_slug}")
    matching = [p for p in skus if tier_name.lower() in p.display_name.lower()]
    if not matching:
        raise HTTPException(404, f"no tier matching {tier_name!r} for {product_slug}")
    sku = matching[0]

    price_id = _price_for(sku.display_name)
    mode = "subscription" if sku.pricing_model.startswith("subscription") else "payment"

    site = os.environ.get("PORTFOLIO_SITE_URL", "https://portfolio-site-beta-swart-35.vercel.app")
    success = payload.success_url or f"{site}/success?slug={product_slug}"
    cancel = payload.cancel_url or f"{site}/products/{product_slug}"

    create_kwargs: dict = {
        "mode": mode,
        "line_items": [{"price": price_id, "quantity": payload.quantity}],
        "success_url": success + "&cs_id={CHECKOUT_SESSION_ID}",
        "cancel_url": cancel,
        "metadata": {
            "product_slug": product_slug,
            "fulfillment_kind": sku.fulfillment_kind,
            **payload.metadata,
        },
    }
    if payload.customer_email:
        create_kwargs["customer_email"] = payload.customer_email
    session = stripe.checkout.Session.create(**create_kwargs)
    return {"checkout_url": session.url, "session_id": session.id}


# --- webhook ---

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(default=None)) -> JSONResponse:
    _stripe_key()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(500, "STRIPE_WEBHOOK_SECRET not set")

    body = await request.body()
    try:
        event = stripe.Webhook.construct_event(body, stripe_signature, secret)
    except Exception as e:
        raise HTTPException(400, f"signature failed: {e}")

    handler = {
        "checkout.session.completed": fulfillment.handle_checkout_completed,
        "customer.subscription.deleted": fulfillment.handle_subscription_canceled,
        "customer.subscription.updated": fulfillment.handle_subscription_updated,
    }.get(event["type"])

    if not handler:
        return JSONResponse({"ignored": event["type"]})

    try:
        # stripe.Event -> plain dict so fulfillment code can use .get() etc.
        # Use to_dict_recursive when available (stripe-py StripeObject) so
        # nested structures aren't half-converted.
        import json as _json
        obj = event["data"]["object"]
        if hasattr(obj, "to_dict_recursive"):
            obj_dict = obj.to_dict_recursive()
        elif hasattr(obj, "to_dict"):
            obj_dict = _json.loads(_json.dumps(obj.to_dict(), default=str))
        elif isinstance(obj, dict):
            obj_dict = obj
        else:
            obj_dict = _json.loads(_json.dumps(obj, default=str))
        handler(obj_dict)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[webhook] fulfillment failed: {type(e).__name__}: {e}\n{tb}")
        raise HTTPException(500, f"fulfillment failed: {type(e).__name__}: {e} | tb-tail: {tb.strip().splitlines()[-1] if tb else ''}")

    return JSONResponse({"handled": event["type"]})
