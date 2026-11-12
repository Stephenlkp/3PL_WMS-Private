# Architecture

The system is a modular monolith. HTTP handlers stay thin. Stock rules live in `app/domain/ledger.py` and the only writer of `inventory_transactions` is `app/services/inventory.py`.

## Tenancy

`customers` is the tenant. Warehouse users have a null `customer_id`. Customer users carry their tenant on the user row. The access token identifies the user. Role and tenant are read from the database on every request, so a role change applies before the access token expires.

`scoped_customer_id` forces a customer user onto their own id. A request for another tenant returns 404. Staff may pass `customer_id` to narrow a list. Product barcodes are unique across the building so a scan does not have to ask which customer the label belongs to. SKUs are unique per customer.

## Ledger

Quantities are signed integers.

- `INBOUND` is positive and requires a location.
- `OUTBOUND` is negative and requires a location.
- `MOVE` is a pair of rows that share a `correlation_id`.
- `ADJUSTMENT` is signed, requires a note, and is limited to admin and supervisor.
- `RESERVED` has no location. It is a pool reservation for the customer and SKU.

A posting is accepted only when every location stays at zero or above, reserved stays at zero or above, and physical stock still covers reserved stock. A move is checked after both legs, so stock can leave one bin and enter another in the same posting. A shipment releases the reservation and posts the outbound together, so other orders' reservations are not treated as still covering the units that just left.

Pick lists allocate free quantity at each location. Free quantity is physical stock minus quantities already sitting on open pick lists. The walk order is zone, then rack, then level.

Picked and packed quantities are workflow progress. They are not stock. Stock changes on receive, move, adjustment, and dispatch.

## Authentication

Passwords are hashed with Argon2. Access tokens last 15 minutes. Refresh tokens are random, stored as SHA-256, and rotated. Presenting a revoked refresh token revokes the rest of that user's sessions.

Login is limited to 10 requests a minute. Other routes share a default limit of 240 a minute when rate limiting is on. Redis is the shared store in Docker. A missing Redis does not take the API down. The low-stock snapshot in Redis is a cache. The dashboard still computes from the ledger.

## Files

Airway bills are JPEG, PNG, or PDF, capped at 10 MB, and checked against their file signature. Docker stores them in MinIO. Local runs store them under `backend/storage`. Customer files are visible only to that customer and to warehouse staff. Rack photos have no customer and can be shown to anyone signed in.

## Background work

Celery refreshes the low-stock Redis key `wms:low_stock` every hour. Report downloads are synchronous so a picker is not waiting on a worker to get a CSV.

## What is deliberately not in this version

Marketplace order import is an interface only. Billing is a rate card plus a report, not an invoice run. Storage fees use a snapshot of current on-hand units times the days in the range. The aging report is company-level FIFO and ignores moves, because a move does not change the age of the unit.
