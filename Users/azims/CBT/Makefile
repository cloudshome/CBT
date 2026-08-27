.PHONY: install run test docker-build docker-up clean

install:
	pip install -r requirements.txt

run:
	uvicorn app:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest tests/ -v

docker-build:
	docker compose build

docker-up:
	docker compose up -d

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
