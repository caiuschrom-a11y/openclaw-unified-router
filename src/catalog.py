"""Product catalog → Stripe price-ID registry.

For each paid product in the openclaw-products monorepo, declares the
SKU (Stripe price IDs) and entitlement metadata.

Once the user creates these prices in Stripe and pastes the IDs here,
the router knows how to checkout + provision each product.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ProductSKU:
    product_slug: str            # matches the product directory name
    display_name: str
    description: str
    pricing_model: Literal["one_time", "subscription_monthly", "subscription_annual", "metered"]
    price_id: str | None = None  # Stripe price ID — fill in after creating in Stripe
    success_redirect: str | None = None
    cancel_redirect: str | None = None
    fulfillment_kind: Literal["api_key", "license_key", "concierge_email", "subscription_only"] = "api_key"
    metadata: dict[str, str] = field(default_factory=dict)


# ============================================================
# THE CATALOG: one entry per pricing tier of each paid product.
# Fill price_id values AFTER creating products + prices in Stripe.
# ============================================================

CATALOG: list[ProductSKU] = [
    # ---------- coldmail ----------
    ProductSKU(
        product_slug="coldmail",
        display_name="coldmail Starter",
        description="Cold-email personalization API — 1,000 emails/mo",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "starter", "monthly_quota": "1000"},
    ),
    ProductSKU(
        product_slug="coldmail",
        display_name="coldmail Pro",
        description="Cold-email personalization API — 10,000 emails/mo + 24h SLA",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "pro", "monthly_quota": "10000"},
    ),

    # ---------- mcp-trademark ----------
    ProductSKU(
        product_slug="mcp-trademark",
        display_name="mcp-trademark Lifetime Self-Host",
        description="USPTO Trademark Watcher — MCP + CLI — 5 marks lifetime",
        pricing_model="one_time",
        fulfillment_kind="license_key",
        metadata={"tier": "lifetime", "mark_quota": "5"},
    ),
    ProductSKU(
        product_slug="mcp-trademark",
        display_name="mcp-trademark Pro",
        description="USPTO Trademark Watcher Pro — 25 marks + Claude semantic similarity",
        pricing_model="one_time",
        fulfillment_kind="license_key",
        metadata={"tier": "pro", "mark_quota": "25"},
    ),

    # ---------- mcp-patent ----------
    ProductSKU(
        product_slug="mcp-patent",
        display_name="mcp-patent Lifetime",
        description="USPTO Patent prior-art MCP + CLI — lifetime self-host",
        pricing_model="one_time",
        fulfillment_kind="license_key",
        metadata={"tier": "lifetime"},
    ),

    # ---------- resume-service ----------
    ProductSKU(
        product_slug="resume-service",
        display_name="applywell Starter",
        description="Concierge auto-apply — 100 senior-role applications",
        pricing_model="one_time",
        fulfillment_kind="concierge_email",
        metadata={"apps_quota": "100"},
    ),
    ProductSKU(
        product_slug="resume-service",
        display_name="applywell Pro",
        description="Concierge auto-apply — 300 apps + per-role cover letters",
        pricing_model="one_time",
        fulfillment_kind="concierge_email",
        metadata={"apps_quota": "300"},
    ),

    # ---------- pricing-intel ----------
    ProductSKU(
        product_slug="pricing-intel",
        display_name="pricing-intel Starter",
        description="SMB e-commerce competitor pricing — 50 SKUs tracked",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "starter", "sku_quota": "50"},
    ),
    ProductSKU(
        product_slug="pricing-intel",
        display_name="pricing-intel Growth",
        description="pricing-intel — 250 SKUs tracked + multi-source comp",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "growth", "sku_quota": "250"},
    ),

    # ---------- voice-agent-smb ----------
    ProductSKU(
        product_slug="voice-agent-smb",
        display_name="voice-agent SMB Standard",
        description="24/7 AI receptionist — up to 200 calls/mo, 1 number",
        pricing_model="subscription_monthly",
        fulfillment_kind="concierge_email",
        metadata={"plan": "standard", "monthly_calls": "200"},
    ),

    # ---------- code-review-bot ----------
    ProductSKU(
        product_slug="code-review-bot",
        display_name="code-review-bot Team",
        description="GitHub PR reviewer — 1k reviews/mo, per-dev pricing",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "team", "monthly_reviews": "1000"},
    ),

    # ---------- shopify-support-bot ----------
    ProductSKU(
        product_slug="shopify-support-bot",
        display_name="shopify-support-bot Standard",
        description="Tier-1 support agent — up to 500 tickets/mo",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "standard", "monthly_tickets": "500"},
    ),

    # ---------- legal-doc-drafter ----------
    ProductSKU(
        product_slug="legal-doc-drafter",
        display_name="legal-doc-drafter Pay-per-doc",
        description="One legal document draft (NDA / contractor / ToS / privacy)",
        pricing_model="one_time",
        fulfillment_kind="api_key",
        metadata={"docs_quota": "1"},
    ),
    ProductSKU(
        product_slug="legal-doc-drafter",
        display_name="legal-doc-drafter Unlimited",
        description="Unlimited legal-doc drafts — for founders + agencies",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "unlimited"},
    ),

    # ---------- hipaa-doc-intake ----------
    ProductSKU(
        product_slug="hipaa-doc-intake",
        display_name="hipaa-doc-intake Practice",
        description="HIPAA-compliant medical-intake — single practice, on-prem",
        pricing_model="subscription_monthly",
        fulfillment_kind="concierge_email",
        metadata={"plan": "practice"},
    ),

    # ---------- ma-diligence ----------
    ProductSKU(
        product_slug="ma-diligence",
        display_name="ma-diligence per-engagement",
        description="On-prem M&A diligence Q&A — single deal engagement",
        pricing_model="one_time",
        fulfillment_kind="concierge_email",
        metadata={"engagement_kind": "single_deal"},
    ),

    # ---------- ai-roadmap ----------
    ProductSKU(
        product_slug="ai-roadmap",
        display_name="ai-roadmap Starter",
        description="One-shot AI-adoption roadmap for SMB or mid-market",
        pricing_model="one_time",
        fulfillment_kind="concierge_email",
        metadata={"includes_consult": "false"},
    ),
    ProductSKU(
        product_slug="ai-roadmap",
        display_name="ai-roadmap with consults",
        description="Roadmap + 2 follow-up consult calls",
        pricing_model="one_time",
        fulfillment_kind="concierge_email",
        metadata={"includes_consult": "true"},
    ),

    # ---------- chargeback-drafter ----------
    ProductSKU(
        product_slug="chargeback-drafter",
        display_name="chargeback-drafter pay-per-dispute",
        description="One chargeback dispute draft + evidence checklist",
        pricing_model="one_time",
        fulfillment_kind="api_key",
        metadata={"disputes_quota": "1"},
    ),
    ProductSKU(
        product_slug="chargeback-drafter",
        display_name="chargeback-drafter Unlimited",
        description="Unlimited dispute drafts — single merchant",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "unlimited"},
    ),

    # ---------- meeting-notes-bot ----------
    ProductSKU(
        product_slug="meeting-notes-bot",
        display_name="meeting-notes-bot per-user",
        description="Transcript → action items + follow-ups — single user",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "individual"},
    ),

    # Add more SKUs as you wire them up. The pattern is consistent.
]


def by_slug(slug: str) -> list[ProductSKU]:
    return [p for p in CATALOG if p.product_slug == slug]


def by_price_id(price_id: str) -> ProductSKU | None:
    for p in CATALOG:
        if p.price_id == price_id:
            return p
    return None


def unconfigured() -> list[ProductSKU]:
    """SKUs that don't have a Stripe price_id yet."""
    return [p for p in CATALOG if not p.price_id]
