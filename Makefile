.PHONY: test seed api web up

test:
	cd backend && .venv/bin/pytest -q

seed:
	cd backend && .venv/bin/alembic upgrade head && .venv/bin/python -m app.seed

api:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

up:
	docker compose up --build
