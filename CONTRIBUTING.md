# Contributing to cproj

Thanks for your interest in contributing to cproj! This document outlines the development setup and workflow.

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/bigandslow/cproj.git
   cd cproj
   ```

2. **Install in development mode:**
   ```bash
   make dev-install
   ```
   This will:
   - Install cproj in editable mode with dev dependencies
   - Set up pre-commit hooks automatically

3. **Verify installation:**
   ```bash
   make dev-check
   make smoke-test
   ```

## Development Workflow

### Running Tests
```bash
# Run all tests
make test

# Run specific test
python -m pytest test_cproj.py::TestConfig -v
```

### Code Quality
```bash
# Run linting
make lint

# Format code
make format

# Run pre-commit checks
make pre-commit

# Run all quality checks
make lint && make format && make test
```

### Before Committing
All commits are automatically checked by pre-commit hooks, which run:
- Code formatting (black)
- Linting (flake8)
- Type checking (mypy)
- Security scanning (bandit)
- Basic file checks (trailing whitespace, etc.)

If you need to skip hooks for a commit (not recommended):
```bash
git commit --no-verify -m "message"
```

## Code Standards

- **Python**: 3.8+ compatibility required
- **Line length**: 100 characters (configured in pyproject.toml)
- **Type hints**: Required for all public functions
- **Testing**: All new features must include tests
- **Documentation**: Update docstrings and README as needed

## Pull Request Process

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** and ensure all checks pass:
   ```bash
   make lint && make test
   ```

3. **Commit with descriptive messages:**
   ```bash
   git commit -m "Add feature: description of what it does"
   ```

4. **Push and create a pull request:**
   ```bash
   git push origin feature/your-feature-name
   ```

5. **Wait for CI checks** - all tests and quality checks must pass

## CI/CD Pipeline

Our GitHub Actions workflow automatically:
- Tests on Python 3.8-3.12 on Ubuntu and macOS
- Runs linting and formatting checks
- Performs security scans
- Measures code coverage
- Creates releases for tagged versions

## Release Process

Releases are automated:
1. Update version in `pyproject.toml`
2. Create and push a git tag: `git tag v1.0.0 && git push origin v1.0.0`
3. GitHub Actions will build and publish to PyPI automatically

## Need Help?

- Check existing issues and PRs first
- Open an issue for bugs or feature requests
- For questions, start a discussion in the repository

## Development Tools Used

- **Testing**: pytest
- **Formatting**: black
- **Linting**: flake8, mypy
- **Security**: bandit, safety
- **Pre-commit**: Automated quality checks
- **CI/CD**: GitHub Actions
- **Dependencies**: Dependabot for automated updates