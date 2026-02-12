# CLAUDE.md - Project Guidelines for AI Agents

## Repository Overview
WebIntel MCP is a FastMCP server providing web search and content retrieval tools.
- **Stack:** Python 3.9+, FastMCP, Docker
- **Entry point:** `src/server/mcp_server.py`

## Allowed Actions
- Modify files in `src/` and `tests/`
- Add new tools in `src/core/` with corresponding handlers in `src/server/`
- Update `requirements.txt` for new dependencies
- Update `README.md` to document new features

## Restricted Actions
- **DO NOT** modify `.github/workflows/` without explicit approval
- **DO NOT** modify `Dockerfile` or `docker-compose.yml` without explicit approval
- **DO NOT** commit secrets, API keys, or credentials
- **DO NOT** push directly to `main` — always use feature branches

## Workflow
1. Create feature branch: `git checkout -b feature/<name>`
2. Make changes
3. Run tests: `pytest tests/ -v`
4. Commit with descriptive message
5. Push and create PR

## Testing
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_search.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

## Code Style
- Use type hints for all function signatures
- Follow existing patterns in `src/core/` for new fetchers
- Keep handlers thin — business logic goes in `src/core/`

## Branch Naming
- Features: `feature/<short-description>`
- Bugfixes: `fix/<short-description>`
- Refactors: `refactor/<short-description>`
