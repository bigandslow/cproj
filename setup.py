#!/usr/bin/env python3
"""
Setup script for cproj
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text() if readme_path.exists() else ""

setup(
    name="cproj",
    version="1.0.0",
    description="Multi-project CLI with git worktree + uv",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="cproj",
    author_email="",
    url="https://github.com/user/cenv",
    py_modules=["cproj"],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "cproj=cproj:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Tools",
        "Topic :: System :: Systems Administration",
    ],
    keywords="git worktree development workflow cli",
    install_requires=[
        # No external dependencies - uses only stdlib
    ],
    extras_require={
        "dev": [
            "pytest",
            "black",
            "flake8",
            "mypy",
        ],
    },
)