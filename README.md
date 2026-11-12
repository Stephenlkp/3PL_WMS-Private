# 3PL Warehouse Management System

Multi-tenant WMS for a fulfillment warehouse. Customers sign in and see only their stock. Warehouse staff receive, locate, pick, pack, and ship. Inventory quantity is never edited. It is the sum of an append-only ledger.

This project lives in `wms/` so it stays separate from the QR AirDrop app in the parent folder.

## Run it locally

The backend on this machine already has a migrated SQLite database with demo data if you have run the seed. From a fresh checkout:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. API docs are at http://localhost:8000/docs.

Demo password for every account: `Wms-demo-123`

| Email | Role |
| --- | --- |
| admin@wms.local | Admin |
| supervisor@wms.local | Warehouse supervisor |
| picker@wms.local | Picker |
| packer@wms.local | Packer |
| ispring@wms.local | iSpring |

Opening stock is the iSpring SKU list. Repeated rows are the quantity: CKC2 starts at 4, WSP50 at 2, and every other SKU at 1. Search `MRO400EU` on the rack map. It sits at **A02-03** with **1** on hand, and the bin has a photo.

## Docker

```bash
docker compose up --build
```

Postgres is published on host port **5433**. The API is on port 8000, the web app on 3000, MinIO on 9000 (console 9001). The API container migrates and seeds on startup. Change `JWT_SECRET` and the MinIO password before any shared deployment. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## How stock works

| Event | Ledger | Physical | Available |
| --- | --- | --- | --- |
| Receive | `INBOUND` positive at a location | up | up |
| Customer creates an order | `RESERVED` positive, no location | unchanged | down |
| Move | `MOVE` negative at the source and positive at the destination | unchanged in total | unchanged |
| Adjustment | signed `ADJUSTMENT` with a required note | changes | changes |
| Dispatch | `OUTBOUND` negative at the picked locations, and the reservation is released | down | stays at the post-reservation figure |

`available = physical − reserved`

There is no balance column to edit. `inventory_balances` and `inventory_balances_by_sku` are SQL views. ORM updates and deletes of `inventory_transactions` are rejected.

Customer A cannot read Customer B's products, balances, orders, or files. The tenant comes from the signed-in user, not from a header the browser can swap.

## Tests

```bash
cd backend && .venv/bin/pytest -q
```

`tests/test_ledger.py` covers the quantity rules and the pick route. `tests/test_wms_flow.py` is the end-to-end API flow: receive, reserve, tenant isolation, wrong-SKU rejection, pick, pack, airway bill, dispatch, and the balance view.

## Layout

```text
backend/app/domain        ledger rules, no database
backend/app/services      application workflows
backend/app/api           FastAPI routes under /api/v1
backend/app/models        SQLAlchemy models
backend/alembic           migration, including the balance views
frontend/src              Next.js warehouse and customer portal
docs                      architecture, ERD, deployment
```

Phase 3 marketplace connectors (Shopee, Lazada, TikTok Shop, Shopify) are a seam in `backend/app/integrations`. They are not connected. Imported orders would still have to go through order creation so the reservation rules stay in one place.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/ERD.md](docs/ERD.md), [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
