# Deployment

## Docker Compose

From `wms/`:

```bash
docker compose up --build
```

| Service | URL |
| --- | --- |
| Web | http://localhost:3000 |
| API and OpenAPI | http://localhost:8000/docs |
| Postgres | localhost:5433 (user `wms`, password `wms`, database `wms`) |
| Redis | localhost:6379 |
| MinIO | http://localhost:9000 , console http://localhost:9001 |

The API entrypoint waits for Postgres, runs `alembic upgrade head`, and seeds the demo warehouse when `SEED_ON_START=true`. The worker and beat process start after the API health check passes, so they see the migrated schema.

## Production checklist

Set these before `ENV=production`. The process refuses to boot when the JWT secret is still the development value, or when MinIO is still using `minioadmin`.

- `ENV=production`
- `JWT_SECRET` at least 32 random characters
- `DATABASE_URL=postgresql+psycopg://...`
- `REDIS_URL` and `RATE_LIMIT_STORAGE` pointing at Redis, so limits are shared across API workers
- `STORAGE_BACKEND=minio` with a private bucket and replaced credentials
- `CORS_ORIGINS` set to the real web origin
- `SEED_ON_START=false`
- `NEXT_PUBLIC_DEMO_HINTS=false` on the web image
- Postgres and MinIO volumes backed up
- TLS terminated in front of the web and API containers

Run more than one API process only behind that proxy. Uvicorn workers do not replace the Celery worker. Keep one beat process.

Access tokens expire after 15 minutes. Refresh tokens last 7 days, are stored hashed, and rotate on use. Put the web app and API on HTTPS so the bearer token is not sent in the clear. Preview URLs for airway bills and barcodes accept the access token as a query parameter so a phone can render an image. The API sends `Referrer-Policy: no-referrer` so that token is not leaked onward.

## Local SQLite

SQLite is for development and the automated tests. The same models and the same view SQL run there. Postgres is the deployment database. Do not point two API processes at one SQLite file.

## Backups

Back up the Postgres volume and the MinIO volume together. The database stores the object key. The bytes live in the bucket. Restoring one without the other leaves airway bills and rack photos missing.

## Operations

- Health: `GET /health` checks Postgres and, when configured, Redis.
- Audit: `GET /api/v1/audit` for admin, supervisor, and the customer's own rows.
- Low stock cache: Celery writes `wms:low_stock` hourly. The dashboard does not depend on it.
- Failed scans are written to the audit log and then the request returns an error, so a wrong barcode does not roll the attempt away.
