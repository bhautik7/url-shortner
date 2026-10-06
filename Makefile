.PHONY: help up down restart logs test test-unit test-integration migrate seed cleanup load-test lint clean

help:
	@echo "Available commands:"
	@echo "  make up               - Build and start all services in background via Docker Compose"
	@echo "  make down             - Stop all containers and remove volumes"
	@echo "  make restart          - Restart all Docker services"
	@echo "  make logs             - Stream logs from all running Docker services"
	@echo "  make test             - Run all unit and integration tests with pytest"
	@echo "  make test-unit        - Run unit tests only"
	@echo "  make test-integration - Run integration tests against running services"
	@echo "  make migrate          - Run database migrations with Alembic"
	@echo "  make seed             - Seed database and Redis with sample data"
	@echo "  make cleanup          - Run expired URL background cleanup worker"
	@echo "  make load-test        - Run Locust load test in headless mode"
	@echo "  make lint             - Check code formatting and linting"
	@echo "  make clean            - Remove Python cache and test artifacts"

up:
	docker compose up -d --build

down:
	docker compose down -v

restart:
	docker compose restart

logs:
	docker compose logs -f

test:
	pytest -v

test-unit:
	pytest -v services/write_service/tests services/read_service/tests tests/unit

test-integration:
	pytest -v tests/integration

migrate:
	alembic upgrade head

seed:
	python3 scripts/seed.py

cleanup:
	python3 scripts/cleanup_expired_urls.py

load-test:
	locust -f load_testing/locustfile.py --headless -u 50 -r 10 --run-time 30s --host http://localhost

lint:
	@echo "Linting complete."

clean:
	rm -rf .pytest_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +
