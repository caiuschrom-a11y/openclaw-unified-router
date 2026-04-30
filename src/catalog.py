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

    # ---------- tiktok-faceless ----------
    ProductSKU(
        product_slug="tiktok-faceless",
        display_name="tiktok-faceless Single",
        description="1 TikTok channel — 30 videos/mo, daily auto-post",
        pricing_model="subscription_monthly",
        fulfillment_kind="concierge_email",
        metadata={"plan": "single", "channels": "1", "videos_per_month": "30"},
    ),
    ProductSKU(
        product_slug="tiktok-faceless",
        display_name="tiktok-faceless Multi",
        description="5 channels, 30 videos each",
        pricing_model="subscription_monthly",
        fulfillment_kind="concierge_email",
        metadata={"plan": "multi", "channels": "5"},
    ),
    ProductSKU(
        product_slug="tiktok-faceless",
        display_name="tiktok-faceless Agency",
        description="25 channels, 30 videos each, white-label",
        pricing_model="subscription_monthly",
        fulfillment_kind="concierge_email",
        metadata={"plan": "agency", "channels": "25"},
    ),

    # ---------- notion-template-pack ----------
    ProductSKU(
        product_slug="notion-template-pack",
        display_name="notion-template-pack Starter",
        description="5 founder Notion templates — markdown",
        pricing_model="one_time",
        fulfillment_kind="license_key",
        metadata={"plan": "starter"},
    ),
    ProductSKU(
        product_slug="notion-template-pack",
        display_name="notion-template-pack Pro",
        description="Starter + JSON for Notion API auto-import + variants",
        pricing_model="one_time",
        fulfillment_kind="license_key",
        metadata={"plan": "pro"},
    ),
    ProductSKU(
        product_slug="notion-template-pack",
        display_name="notion-template-pack Agency",
        description="Pro + underlying YAML schema for fork/remix",
        pricing_model="one_time",
        fulfillment_kind="license_key",
        metadata={"plan": "agency"},
    ),

    # ---------- skills-bundle ----------
    ProductSKU(
        product_slug="skills-bundle",
        display_name="skills-bundle Lifetime",
        description="Claude Code skills bundle — 5 skills, lifetime updates",
        pricing_model="one_time",
        fulfillment_kind="license_key",
        metadata={"plan": "lifetime", "skills_count": "5"},
    ),
    ProductSKU(
        product_slug="skills-bundle",
        display_name="skills-bundle Team",
        description="Lifetime × 5 seats",
        pricing_model="one_time",
        fulfillment_kind="license_key",
        metadata={"plan": "team", "seats": "5"},
    ),

    # ---------- algo-research-newsletter ----------
    ProductSKU(
        product_slug="algo-research-newsletter",
        display_name="algo-research-newsletter Reader",
        description="Weekly backtested-strategy newsletter — read-only",
        pricing_model="subscription_monthly",
        fulfillment_kind="subscription_only",
        metadata={"plan": "reader"},
    ),
    ProductSKU(
        product_slug="algo-research-newsletter",
        display_name="algo-research-newsletter Builder",
        description="Reader + raw vectorbt notebook + Alpaca paper-trade hooks",
        pricing_model="subscription_monthly",
        fulfillment_kind="subscription_only",
        metadata={"plan": "builder"},
    ),
    ProductSKU(
        product_slug="algo-research-newsletter",
        display_name="algo-research-newsletter Firm",
        description="Builder + 4 office-hour calls/yr",
        pricing_model="subscription_monthly",
        fulfillment_kind="concierge_email",
        metadata={"plan": "firm"},
    ),

    # ---------- negotiation-overlay ----------
    ProductSKU(
        product_slug="negotiation-overlay",
        display_name="negotiation-overlay Lifetime",
        description="Chrome ext for car/home/marketplace negotiation — 50 calls/mo",
        pricing_model="one_time",
        fulfillment_kind="api_key",
        metadata={"plan": "lifetime", "monthly_quota": "50"},
    ),
    ProductSKU(
        product_slug="negotiation-overlay",
        display_name="negotiation-overlay Pro",
        description="Unlimited negotiation scripts, 1 device",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "pro", "monthly_quota": "999999"},
    ),
    ProductSKU(
        product_slug="negotiation-overlay",
        display_name="negotiation-overlay Family",
        description="Unlimited, 5 devices",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "family", "monthly_quota": "999999", "device_cap": "5"},
    ),

    # ---------- fda-approvals ----------
    ProductSKU(
        product_slug="fda-approvals",
        display_name="fda-approvals Watcher",
        description="Daily FDA approval digest — 3 saved filters",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "watcher", "filter_count": "3"},
    ),
    ProductSKU(
        product_slug="fda-approvals",
        display_name="fda-approvals Pro",
        description="Daily + intra-day alerts, 10 filters, API access",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "pro", "filter_count": "10", "api_quota": "1000"},
    ),
    ProductSKU(
        product_slug="fda-approvals",
        display_name="fda-approvals Firm",
        description="Pro + team distribution, 20 filters, 10k API/mo",
        pricing_model="subscription_monthly",
        fulfillment_kind="api_key",
        metadata={"plan": "firm", "filter_count": "20", "api_quota": "10000"},
    ),

    # ---------- gdpr-dsar ----------
    ProductSKU(
        product_slug="gdpr-dsar",
        display_name="gdpr-dsar Single",
        description="One Article 15 DSAR response packet — 5-day turnaround",
        pricing_model="one_time",
        fulfillment_kind="concierge_email",
        metadata={"engagement_kind": "single_dsar"},
    ),
    ProductSKU(
        product_slug="gdpr-dsar",
        display_name="gdpr-dsar Monthly",
        description="Unlimited DSARs — up to 10 in flight at any time",
        pricing_model="subscription_monthly",
        fulfillment_kind="concierge_email",
        metadata={"plan": "monthly", "in_flight_cap": "10"},
    ),
    ProductSKU(
        product_slug="gdpr-dsar",
        display_name="gdpr-dsar Annual",
        description="Monthly plan + quarterly preparedness review",
        pricing_model="subscription_annual",
        fulfillment_kind="concierge_email",
        metadata={"plan": "annual", "includes_review": "true"},
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
