# CLAUDE.md - Instructions for refactoring

## Task
Refactor the scripts in `reference/` into a clean Python package under `src/lark_toolkit/`.

## Source Files (in reference/)
- `lark_common.py` — Core API layer (token management, API calls, messaging)
- `streaming-bridge.py` — Stream OpenClaw session output to Lark cards via CardKit
- `lark-card-builder.py` — Build interactive dashboard cards
- `lark-task-dashboard.py` — Send/update task dashboard cards
- `lark-calendar-create.py` / `lark-calendar-today.py` — Calendar operations
- `lark-todo-manager.py` — Todo/task management
- `lark-oauth-handler.py` — OAuth callback handler
- `lark-chat-names.py` / `lark-lookup-chat.py` — Chat utilities
- `lark-token-refresh.py` — Token refresh utility
- `lark_task.py` — Task-related Lark operations

## Target Package Structure
```
src/lark_toolkit/
  __init__.py          # Public API exports
  client.py            # LarkClient class (token management, API calls)
  messaging.py         # send_message, send_card, send_image, etc.
  cards.py             # Card building utilities (CardKit streaming, interactive cards)
  calendar.py          # Calendar operations
  chat.py              # Chat management (create, lookup, members, rename)
  todo.py              # Todo operations
  oauth.py             # OAuth handler
  types.py             # Shared dataclasses/types
```

## Critical Requirements

1. **NO HARDCODED SECRETS** — All credentials must come from environment variables:
   - `LARK_APP_ID` (required)
   - `LARK_APP_SECRET` (required)
   - `LARK_BASE_URL` (optional, default: `https://open.larksuite.com/open-apis`)
   - User tokens from `LARK_USER_TOKEN_FILE` or passed directly

2. **NO HARDCODED IDs** — Remove all hardcoded open_ids, chat_ids, calendar_ids, wiki space IDs. These should be passed as parameters.

3. **English comments and docstrings** — All code comments and docstrings in English.

4. **LarkClient as central class** — Single client instance manages token lifecycle:
   ```python
   from lark_toolkit import LarkClient
   client = LarkClient()  # reads from env vars
   client.send_message(chat_id, "Hello!")
   ```

5. **Keep all functionality** — Don't drop features. The streaming bridge, card builder, calendar, todo, oauth, chat utilities all need to be preserved.

6. **Remove OpenClaw-specific coupling** — The streaming bridge references OpenClaw session directories. Make it accept a generic "text stream" or callback instead.

7. **Type hints** — Use proper type hints throughout.

8. **Tests** — Write basic tests in `tests/` for at least: client initialization, token caching, message building, card building.

9. **pyproject.toml** — Already exists, update dependencies if needed (keep minimal: no heavy deps).

10. **Delete reference/ when done** — Remove the reference directory after refactoring.

## Don't
- Don't create unnecessary abstractions — keep it practical
- Don't add async unless the original code was async (it's all sync urllib)
- Don't change the Lark API endpoints or behavior
- Don't add external dependencies beyond what's in pyproject.toml (httpx is fine)

## After refactoring
- Run `ruff check src/` and fix any issues
- Run `pytest` and make sure tests pass
- Create a meaningful commit on the `feat/initial-code` branch
