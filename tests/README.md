# Testing Guide

This directory contains tests for the search application using pytest.

## Running Tests

Install pytest:
```bash
pip install pytest pytest-asyncio
```

Run all tests:
```bash
pytest tests/
```

Run with verbose output:
```bash
pytest tests/ -v
```

Run a specific test file:
```bash
pytest tests/test_search.py
```

## Test Files

Each `test_*.py` file in this directory covers the matching module in
`src/`; see the module docstring at the top of each test file for scope.