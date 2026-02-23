# Feature Workflow Settings

## Task Guidelines

- Tasks should include unit tests for the code being added
- Dependencies should be added in the tasks that require them, not as separate tasks
- Prefer larger tasks that complete a full vertical slice over small atomic changes
- Each task should update relevant documentation

## Coding Guidelines

Use modern type hint best practise:
- Use built-in generics instead of the aliases from typing, where possible. list instead of List, dict instead of Dict, etc
- Use shorthand syntax for unions instead of Union or Optional
- For arguments, prefer protocols and abstract types (Mapping, Sequence, Iterable, etc.). If an argument accepts literally any value, use object instead of Any.
- For return values, prefer concrete types (list, dict, etc.) for concrete implementations. The return values of protocols and abstract base classes must be judged on a case-by-case basis.
- Use float instead of int | float. Use None instead of Literal[None].

## Commands

### Testing
- All tests: uv run pytest
- With coverage: uv run pytest --cov=casual_mcp --cov-report=html
- Specific file: uv run pytest tests/classifiers/test_pipeline.py -v

### Code quality
- Format: uv run black src/ tests/ examples/
- Lint: uv run ruff check src/ tests/ examples/
- Type Check: uv run mypy src/casual_mcp/