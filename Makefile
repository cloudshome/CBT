.PHONY: install install-all run test test-python test-ts test-all lint backup restore seed docker-build docker-up docker-down clean

install:
	pip install -r requirements.txt

install-all:
	pip install -r requirements.txt
	npm ci
	npm --prefix frontend ci
	npx prisma generate

run:
	uvicorn app:app --host 0.0.0.0 --port 8000 --reload

test: test-all

test-python:
	pytest --tb=short

test-ts:
	npm test

test-all:
	pytest --tb=short
	npm test

lint:
	ruff check core/ tests/
	npm run lint

backup:
	python deploy/backup_databases.py

restore:
	@echo "Usage: python deploy/restore_databases.py --archive <path_to_tar_gz>"

seed:
	python deploy/seed_market_data.py

build:
	npm run build

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

