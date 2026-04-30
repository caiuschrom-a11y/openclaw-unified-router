"""Fulfillment dispatcher.

Each `fulfillment_kind` has a different post-purchase flow:
- api_key: generate a per-customer API token + email it
- license_key: generate a license string + email it (for self-host bundles)
- concierge_email: drop the order in a ready/ queue + email the operator
- subscription_only: just track; no provisioning
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import emailer

DATA_DIR = Path(os.environ.get("PRODUCTS_DATA_DIR", r"C:\openclaw-products\_shared\data"))
OPERATOR_EMAIL = os.environ.get("OPERATOR_EMAIL", "oahudaddy@duck.com")


def _gen_api_key() -> str:
    return "ock_" + secrets.token_urlsafe(28)


def _gen_license() -> str:
    raw = secrets.token_hex(12).upper()
    return f"{raw[:6]}-{raw[6:14]}-{raw[14:24]}"


def _persist_order(product_slug: str, order: dict[str, Any], subdir: str) -> Path:
    dst = DATA_DIR / product_slug / subdir
    dst.mkdir(parents=True, exist_ok=True)
    fp = dst / f"{order['session_id']}.json"
    fp.write_text(json.dumps(order, indent=2, default=str), encoding="utf-8")
    return fp


def handle_checkout_completed(session: dict[str, Any]) -> None:
    """checkout.session.completed — fulfill based on metadata.fulfillment_kind."""
    md = session.get("metadata") or {}
    product_slug = md.get("product_slug", "unknown")
    fulfillment_kind = md.get("fulfillment_kind", "subscription_only")
    customer_email = session.get("customer_details", {}).get("email") or session.get("customer_email")

    base_order: dict[str, Any] = {
        "session_id": session.get("id"),
        "stripe_customer_id": session.get("customer"),
        "stripe_subscription_id": session.get("subscription"),
        "amount_total_cents": session.get("amount_total"),
        "customer_email": customer_email,
        "product_slug": product_slug,
        "fulfillment_kind": fulfillment_kind,
        "metadata": md,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    portal_url: str | None = None
    if base_order.get("stripe_customer_id"):
        try:
            import stripe as _stripe
            if not _stripe.api_key:
                _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
            site = os.environ.get("PORTFOLIO_SITE_URL", "https://portfolio-site-beta-swart-35.vercel.app")
            sess = _stripe.billing_portal.Session.create(
                customer=base_order["stripe_customer_id"],
                return_url=site,
            )
            portal_url = sess.url
        except Exception as e:  # noqa: BLE001
            print(f"[fulfill] portal session create failed: {e}")

    if fulfillment_kind == "api_key":
        api_key = _gen_api_key()
        base_order["api_key"] = api_key
        _persist_order(product_slug, base_order, "issued")
        # Attach the api_key to the Stripe customer so the gateway (in
        # gateway.py) can validate buyer requests via Stripe Search even
        # when the router's local filesystem is ephemeral (Vercel).
        try:
            import stripe as _stripe
            if not _stripe.api_key:
                _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
            if base_order.get("stripe_customer_id"):
                _stripe.Customer.modify(
                    base_order["stripe_customer_id"],
                    metadata={
                        "openclaw_api_key": api_key,
                        "product_slug": product_slug,
                        "monthly_quota": str(md.get("monthly_quota", "")),
                        "plan": md.get("plan", ""),
                        "calls_this_month": "0",
                        "status": "active",
                    },
                )
        except Exception as e:  # noqa: BLE001
            print(f"[fulfill] attach api_key to Stripe customer failed: {e}")
        if customer_email:
            portal_block = f"\nManage your subscription (cancel, update card):\n    {portal_url}\n" if portal_url else ""
            body = (
                f"Thanks for your purchase of {product_slug}.\n\n"
                f"Your API key:\n\n    {api_key}\n\n"
                f"Use it as the Bearer token against the openclaw API gateway:\n\n"
                f"    curl -X POST -H \"Authorization: Bearer {api_key}\" \\\n"
                f"         -H \"Content-Type: application/json\" \\\n"
                f"         -d '{{\"<see /v1/{product_slug}/info>\"}}' \\\n"
                f"         https://unified-router.vercel.app/v1/{product_slug}/run\n\n"
                f"Quota: {md.get('monthly_quota', 'unlimited')} calls/month on the {md.get('plan', 'standard')} plan.\n"
                f"{portal_block}\n"
                f"Questions: reply to this email.\n"
            )
            emailer.send(
                to=customer_email,
                subject=f"Your openclaw API key for {product_slug}",
                body_text=body,
            )
        print(f"[fulfill] api_key issued for {product_slug} -> {customer_email}")
    elif fulfillment_kind == "license_key":
        license_key = _gen_license()
        base_order["license_key"] = license_key
        _persist_order(product_slug, base_order, "issued")
        if customer_email:
            body = (
                f"Thanks for your purchase of {product_slug}.\n\n"
                f"Your license key:\n\n    {license_key}\n\n"
                f"Source + install instructions:\n"
                f"    https://github.com/caiuschrom-a11y/{product_slug}\n\n"
                f"Activate the license inside the tool when prompted, or set:\n"
                f"    OPENCLAW_LICENSE={license_key}\n\n"
                f"Lifetime entitlement — no recurring charge. Questions: reply here.\n"
            )
            emailer.send(
                to=customer_email,
                subject=f"Your openclaw license key for {product_slug}",
                body_text=body,
            )
        print(f"[fulfill] license_key {license_key} issued for {product_slug} -> {customer_email}")
    elif fulfillment_kind == "concierge_email":
        _persist_order(product_slug, base_order, "ready")
        if customer_email:
            emailer.send(
                to=customer_email,
                subject=f"Your {product_slug} order is queued",
                body_text=(
                    f"Got your order for {product_slug}. We'll be in touch within 24 hours\n"
                    f"to gather requirements and start work.\n\n"
                    f"Order ref: {session.get('id')}\n"
                ),
            )
        emailer.send(
            to=OPERATOR_EMAIL,
            subject=f"[concierge] new order: {product_slug}",
            body_text=(
                f"product: {product_slug}\n"
                f"customer: {customer_email}\n"
                f"session: {session.get('id')}\n"
                f"amount_cents: {session.get('amount_total')}\n"
                f"metadata: {json.dumps(md, indent=2)}\n"
            ),
        )
        print(f"[fulfill] order queued for concierge fulfillment: {product_slug} from {customer_email}")
    elif fulfillment_kind == "subscription_only":
        _persist_order(product_slug, base_order, "subscriptions")
        print(f"[fulfill] subscription recorded for {product_slug} ({customer_email})")


def handle_subscription_canceled(subscription: dict[str, Any]) -> None:
    sub_id = subscription.get("id")
    md = subscription.get("metadata") or {}
    product_slug = md.get("product_slug", "unknown")

    # Walk the issued/ folder for matching subscription_id and mark canceled
    issued_dir = DATA_DIR / product_slug / "issued"
    if not issued_dir.exists():
        return
    for f in issued_dir.glob("*.json"):
        try:
            order = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if order.get("stripe_subscription_id") == sub_id:
            order["status"] = "canceled"
            order["canceled_at"] = datetime.now(timezone.utc).isoformat()
            f.write_text(json.dumps(order, indent=2, default=str), encoding="utf-8")
            print(f"[fulfill] canceled subscription for {product_slug} session {f.stem}")


def handle_subscription_updated(subscription: dict[str, Any]) -> None:
    """No-op for now; could update plan tier or quotas."""
    pass
