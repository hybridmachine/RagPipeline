"""Setup script for RAG Pipeline."""

from pathlib import Path

from setuptools import find_packages, setup

# Read README
readme_file = Path(__file__).parent / "README.md"
if readme_file.exists():
    long_description = readme_file.read_text(encoding="utf-8")
else:
    long_description = "RAG Pipeline - Retrieval-Augmented Generation system"

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    with open(requirements_file) as f:
        requirements = [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("#")
        ]

setup(
    name="rag-pipeline",
    version="0.1.0",
    description="Production-ready RAG system with HuggingFace embeddings and OpenAI LLM",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="RAG Pipeline Team",
    python_requires=">=3.11",
    packages=find_packages(exclude=["tests", "tests.*"]),
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "rag=cli.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
