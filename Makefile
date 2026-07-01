# Makefile for GitHub OSINT Agent

.PHONY: help install dev install-frontend run test lint clean build docker-up docker-down

help:
	@echo "GitHub OSINT Agent - Available commands:"
	@echo ""
	@echo "  install        Install Python dependencies"
	@echo "  dev            Install development dependencies"
	@echo "  install-frontend Install frontend dependencies"
	@echo "  run            Start the backend server"
	@echo "  run-frontend   Start the frontend dev server"
	@echo "  test           Run all tests"
	@echo "  lint           Run code linting"
	@echo "  clean          Clean up generated files"
	@echo "  build          Build Python package"
	@echo "  docker-up      Start Docker containers"
	@echo "  docker-down    Stop Docker containers"
	@echo ""

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio pytest-cov ruff black

install-frontend:
	cd frontend && npm install

run:
	python run.py

run-frontend:
	cd frontend && npm run dev

test:
	pytest tests/ -v --cov=app --cov-report=term-missing

lint:
	ruff check app/
	black --check app/ || true

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ *.egg-info 2>/dev/null || true
	cd frontend && rm -rf dist/ node_modules/.vite 2>/dev/null || true

build:
	python -m build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

# Quick start for development
quickstart: docker-up install install-frontend run
	@echo "Server started at http://localhost:8000"