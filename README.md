# _unified-router — single Stripe billing layer

One FastAPI app that handles checkout + webhooks for every paid product
in the openclaw-products catalog.

## Why this exists

Without it, each of 30+ paid products would need its own Stripe wiring,
webhook handler, deploy, etc. The router consolidates everything into:

- `catalog.py` — declares every paid SKU
- `stripe_setup.py` — creates Stripe Products + Prices once, idempotent
- `app.py` — FastAPI: `/v1/checkout/{slug}/{tier}` + `/webhook/stripe`
- `fulfillment.py` — dispatcher per `fulfillment_kind` (api_key / license / concierge / sub-only)

Once running, every paid product just needs a buy-button that hits
`POST /v1/checkout/<slug>/<tier>` with the customer email.

## Setup (one time, after Stripe signup)

```powershell
cd C:\openclaw-products\_unified-router
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .

$env:STRIPE_SECRET_KEY="sk_test_..."     # test mode first
$env:STRIPE_WEBHOOK_SECRET=""             # blank until next step

# Dry run — see what'd be created
python -m src.stripe_setup

# Actually create Stripe Products + Prices for every catalog SKU
python -m src.stripe_setup --confirm
# → writes price_ids.yaml

# Run the router
uvicorn src.app:app --reload --port 8090
```

## Wiring webhooks (after the router is live somewhere)

In Stripe Dashboard → Developers → Webhooks → Add endpoint:
- URL: `https://your-router-host/webhook/stripe`
- Events: `checkout.session.completed`, `customer.subscription.deleted`,
  `customer.subscription.updated`
- Copy the signing secret → set `STRIPE_WEBHOOK_SECRET` env

## Test

```powershell
# Create a test checkout session
curl -X POST http://localhost:8090/v1/checkout/coldmail/Starter `
   -H "Content-Type: application/json" `
   -d '{"customer_email":"test@example.com"}'

# Trigger a fake webhook (Stripe CLI)
stripe listen --forward-to localhost:8090/webhook/stripe
stripe trigger checkout.session.completed
```

## Deploy

Railway one-click via Dockerfile:

```powershell
railway up
railway env set STRIPE_SECRET_KEY=$env:STRIPE_SECRET_KEY
railway env set STRIPE_WEBHOOK_SECRET=$env:STRIPE_WEBHOOK_SECRET
```

## Catalog summary

The `catalog.py` declares 22 SKUs across 14 products. Add more entries
as you wire up additional paid products from the monorepo.

## Roadmap
- [ ] Email-based fulfillment delivery (Resend / SES)
- [ ] Customer portal redirect (subscription management)
- [ ] Usage metering for the metered SaaS products
- [ ] Coupon / discount-code support
- [ ] Tax handling via Stripe Tax
- [ ] Refund automation for failed-fulfillment cases
