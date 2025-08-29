# Makefile for cproj development and installation

.PHONY: help install uninstall test lint format clean dev-install pipx-install

# Default target
help:
	@echo "🚀 cproj - Multi-project CLI with git worktree + uv"
	@echo ""
	@echo "Available commands:"
	@echo "  install      - Install cproj using the standalone installer"
	@echo "  uninstall    - Uninstall cproj"
	@echo "  pipx-install - Install cproj using pipx (recommended for Python users)"
	@echo "  dev-install  - Install in development mode"
	@echo "  test         - Run tests"
	@echo "  lint         - Run linting"
	@echo "  format       - Format code"
	@echo "  clean        - Clean build artifacts"
	@echo ""
	@echo "For first-time users, run: make install"

# Standalone installation (default method)
install:
	@echo "Installing cproj using standalone installer..."
	./install.sh

# Uninstall
uninstall:
	@echo "Uninstalling cproj..."
	./uninstall.sh

# Install via pipx (isolated Python environment)
pipx-install:
	@echo "Installing cproj via pipx..."
	@if ! command -v pipx >/dev/null 2>&1; then \
		echo "❌ pipx not found. Install with: python -m pip install pipx"; \
		exit 1; \
	fi
	pipx install .

# Development installation
dev-install:
	@echo "Installing cproj in development mode..."
	pip install -e .[dev]

# Run tests
test:
	@echo "Running tests..."
	python -m pytest test_cproj.py -v

# Run linting
lint:
	@echo "Running linting..."
	@if command -v flake8 >/dev/null 2>&1; then \
		flake8 cproj.py test_cproj.py; \
	else \
		echo "flake8 not found, install with: pip install flake8"; \
	fi
	@if command -v mypy >/dev/null 2>&1; then \
		mypy cproj.py --ignore-missing-imports; \
	else \
		echo "mypy not found, install with: pip install mypy"; \
	fi

# Format code
format:
	@echo "Formatting code..."
	@if command -v black >/dev/null 2>&1; then \
		black cproj.py test_cproj.py; \
	else \
		echo "black not found, install with: pip install black"; \
	fi

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf .mypy_cache/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

# Check installation
check:
	@echo "Checking cproj installation..."
	@if command -v cproj >/dev/null 2>&1; then \
		echo "✅ cproj is installed and available"; \
		cproj --help | head -5; \
	else \
		echo "❌ cproj not found in PATH"; \
		echo "Run 'make install' to install cproj"; \
	fi

# Development tools check
dev-check:
	@echo "Checking development environment..."
	@echo -n "Python 3.8+: "
	@python3 -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)" && echo "✅" || echo "❌"
	@echo -n "git: "
	@command -v git >/dev/null 2>&1 && echo "✅" || echo "❌"
	@echo -n "gh (GitHub CLI): "
	@command -v gh >/dev/null 2>&1 && echo "✅" || echo "❌ (optional)"
	@echo -n "uv: "
	@command -v uv >/dev/null 2>&1 && echo "✅" || echo "❌ (optional, will fallback to venv)"
	@echo -n "op (1Password CLI): "
	@command -v op >/dev/null 2>&1 && echo "✅" || echo "❌ (optional)"

# Quick test that cproj works
smoke-test:
	@echo "Running smoke test..."
	python3 cproj.py --help >/dev/null && echo "✅ cproj loads successfully" || echo "❌ cproj failed to load"
	python3 cproj.py config --help >/dev/null && echo "✅ cproj config command works" || echo "❌ cproj config failed"