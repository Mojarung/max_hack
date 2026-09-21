# domovoy (backend)

Python-пакет бэкенда «Домовой Кузя». Общее описание, архитектура и запуск в корневом [README](../README.md).

```bash
uv sync
uv run domovoy api      # REST API + SSE, порт 8000
uv run domovoy bot      # бот MAX и эмулятор чата
uv run domovoy worker   # обращения, напоминания, эскалации
uv run domovoy mcp      # MCP-сервер «Жилищный навигатор», порт 8765
uv run pytest           # тесты
uv run ruff check . && uv run mypy src
```
