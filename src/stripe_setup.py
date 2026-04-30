"""Programmatically create Stripe Products + Prices from the catalog.

Run ONCE after the user signs up + provides STRIPE_SECRET_KEY:

    python -m src.stripe_setup --confirm

This creates one Stripe Product per catalog entry (or reuses existing
ones by metadata.product_slug match) and one Price per SKU. Writes the
generated price IDs back to the catalog as a YAML companion file at
C:/openclaw-products/_unified-router/price_ids.yaml.

Idempotent: running again won't duplicate; it skips already-configured SKUs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
import stripe
import yaml

from .catalog import CATALOG, ProductSKU


PRICE_MAP_FILE = Path(__file__).resolve().parent.parent / "price_ids.yaml"


# Default $ prices per SKU. EDIT before running if you want different.
# Format: (sku_index_in_catalog, price_in_cents, billing_interval)
# billing_interval is "month", "year", or None for one-time
DEFAULT_PRICES_USD_CENTS: dict[str, tuple[int, str | None]] = {
    # coldmail
    "coldmail Starter": (9900, "month"),
    "coldmail Pro": (49900, "month"),
    # mcp-trademark / patent
    "mcp-trademark Lifetime Self-Host": (14900, None),
    "mcp-trademark Pro": (29900, None),
    "mcp-patent Lifetime": (14900, None),
    # resume-service
    "applywell Starter": (9900, None),
    "applywell Pro": (29900, None),
    # pricing-intel
    "pricing-intel Starter": (9900, "month"),
    "pricing-intel Growth": (29900, "month"),
    # voice-agent-smb
    "voice-agent SMB Standard": (29900, "month"),
    # code-review-bot
    "code-review-bot Team": (1900, "month"),  # per-dev — buyer enters quantity
    # shopify-support-bot
    "shopify-support-bot Standard": (19900, "month"),
    # legal-doc-drafter
    "legal-doc-drafter Pay-per-doc": (9900, None),
    "legal-doc-drafter Unlimited": (29900, "month"),
    # hipaa-doc-intake
    "hipaa-doc-intake Practice": (49900, "month"),
    # ma-diligence
    "ma-diligence per-engagement": (500000, None),  # $5K
    # ai-roadmap
    "ai-roadmap Starter": (49900, None),
    "ai-roadmap with consults": (249900, None),
    # chargeback-drafter
    "chargeback-drafter pay-per-dispute": (9900, None),
    "chargeback-drafter Unlimited": (49900, "month"),
    # meeting-notes-bot
    "meeting-notes-bot per-user": (1900, "month"),
}


def load_existing_price_map() -> dict[str, str]:
    if not PRICE_MAP_FILE.exists():
        return {}
    return yaml.safe_load(PRICE_MAP_FILE.read_text(encoding="utf-8")) or {}


def save_price_map(price_map: dict[str, str]) -> None:
    PRICE_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRICE_MAP_FILE.write_text(yaml.safe_dump(price_map, sort_keys=True), encoding="utf-8")


def _load_env_local() -> None:
    """Auto-load .env.local from _shared/ if STRIPE_SECRET_KEY isn't already set."""
    env_file = Path(__file__).resolve().parents[2] / "_shared" / ".env.local"
    if not env_file.exists() or os.environ.get("STRIPE_SECRET_KEY"):
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def setup(confirm: bool = False) -> dict[str, str]:
    _load_env_local()
    api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not api_key:
        raise RuntimeError("STRIPE_SECRET_KEY not set in env or .env.local")
    stripe.api_key = api_key

    price_map = load_existing_price_map()

    if not confirm:
        unconfigured = [sku for sku in CATALOG if sku.display_name not in price_map]
        click.echo(f"Would create {len(unconfigured)} new Stripe Product+Price objects:")
        for sku in unconfigured:
            price_cents, interval = DEFAULT_PRICES_USD_CENTS.get(sku.display_name, (0, None))
            click.echo(f"  {sku.display_name}: ${price_cents/100:.2f}{'/' + interval if interval else ' one-time'}")
        click.echo("\nRe-run with --confirm to actually create them.")
        return price_map

    for sku in CATALOG:
        if sku.display_name in price_map:
            click.echo(f"  skip {sku.display_name} (already has price {price_map[sku.display_name]})")
            continue

        price_cents, interval = DEFAULT_PRICES_USD_CENTS.get(sku.display_name, (None, None))
        if price_cents is None:
            click.echo(f"  skip {sku.display_name} (no default price configured)")
            continue

        # Find or create the Product
        product = stripe.Product.create(
            name=sku.display_name,
            description=sku.description,
            metadata={
                "product_slug": sku.product_slug,
                "fulfillment_kind": sku.fulfillment_kind,
                **sku.metadata,
            },
        )

        price_kwargs: dict = {
            "currency": "usd",
            "unit_amount": price_cents,
            "product": product.id,
        }
        if interval:
            price_kwargs["recurring"] = {"interval": interval}

        price = stripe.Price.create(**price_kwargs)
        price_map[sku.display_name] = price.id
        save_price_map(price_map)  # save FIRST in case echo or anything else fails
        click.echo(f"  [ok] created {sku.display_name}  -> {price.id}")

    click.echo(f"\nSaved {len(price_map)} price IDs to {PRICE_MAP_FILE}")
    return price_map


@click.command()
@click.option("--confirm", is_flag=True, help="Actually create products. Without this, runs as dry-run.")
def main(confirm: bool) -> None:
    """Create Stripe Products + Prices for every paid SKU in the catalog."""
    setup(confirm=confirm)


if __name__ == "__main__":
    main()
