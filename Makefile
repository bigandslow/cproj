.PHONY: help install dev-install test test-security test-coverage lint format security-scan pre-commit clean docs build publish

# Default target
help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install the package
	uv pip install .

dev-install: ## Install development dependencies
	uv sync --dev

test: ## Run all tests
	uv run pytest

test-security: ## Run only security tests
	uv run pytest tests/test_security_fixes.py tests/test_onepassword_sanitization.py tests/test_review_code_security.py -v

test-coverage: ## Run tests with coverage report
	uv run pytest --cov=cproj --cov=claude_review_agents --cov-report=html --cov-report=term-missing

test-parallel: ## Run tests in parallel
	uv run pytest -n auto

test-integration: ## Run integration tests
	uv run pytest -m integration

lint: ## Run linting checks
	uv run ruff check cproj.py claude_review_agents.py tests/
	uv run mypy cproj.py claude_review_agents.py --ignore-missing-imports

format: ## Format code
	uv run ruff format cproj.py claude_review_agents.py tests/
	uv run ruff check --fix cproj.py claude_review_agents.py tests/

security-scan: ## Run security scans
	uv run bandit -r cproj.py claude_review_agents.py
	uv run safety check

pre-commit: ## Run pre-commit hooks
	pre-commit run --all-files

pre-commit-install: ## Install pre-commit hooks
	pre-commit install

clean: ## Clean up temporary files
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf coverage.json
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/

docs: ## Generate documentation
	@echo "Documentation generation not yet implemented"

build: ## Build the package
	uv build

publish: ## Publish to PyPI (requires authentication)
	uv publish

# Development workflow targets
dev-setup: dev-install pre-commit-install ## Complete development setup

check: lint test-security ## Quick checks before commit
	@echo "✅ All checks passed!"

ci: lint test security-scan ## Run full CI checks locally
	@echo "✅ CI checks completed!"

# Utility targets
version: ## Show version information
	@python -c "import cproj; print(f'cproj version: {getattr(cproj, \"__version__\", \"unknown\")}')"

info: ## Show project information
	@echo "Project: cproj"
	@echo "Python: $(shell python --version)"
	@echo "UV: $(shell uv --version 2>/dev/null || echo 'not installed')"
	@echo "Git: $(shell git --version)"

# Performance targets
bench: ## Run performance benchmarks
	@echo "Running CLI startup benchmark..."
	@time python cproj.py --help > /dev/null
	@echo "Running import time benchmark..."
	@python -c "import time; start=time.time(); import cproj; print(f'Import time: {time.time()-start:.3f}s')"