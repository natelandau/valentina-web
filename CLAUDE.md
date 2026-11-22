# Valentina Web

Server-rendered Flask app over the Valentina API, through the in-repo client `src/vweb/api_client/`. HTMX for interactivity, no SPA. Never commit specs or plans to this repo.

## Commands

```bash
uv run duty run          # Flask dev server (127.0.0.1:8089) + Tailwind watcher + dev Redis
uv run duty lint         # ruff, format, ty, typos, pre-commit
uv run duty test         # Tests with coverage; scopes under "Running tests"
uv run duty css          # Production CSS build
uv run duty worktree branch=<name>           # Worktree with its own Redis database and port
uv run duty worktree-teardown branch=<name>  # Remove a worktree, flush its Redis database
uv run duty validate_constants company_id=<id>  # Check client constants against a running API
```

- Do feature, fix, and refactor work in a worktree from `duty worktree`, not the main checkout.
- Run checks only through these duties, never the bare tool. They share a pass cache: "already passed on tree ..." or "already passed on paths ..." is a pass. Set `GATE_CACHE_DISABLE=1` only when the user asks or a changed input is invisible to git (ignored file, tool version). Run `gate-cache --skill` before adding or changing a gate in `duties.py`.

## Stack

- Flask 3.1+, Python 3.13, JinjaX, HTMX, AlpineJS (CDN), Tailwind v4 + daisyUI v5 (npm `@tailwindcss/cli`).
- Settings: pydantic-settings, `VWEB_` prefix, reads `.env.secret`. Call `get_settings()`; no module-level `settings`.
- Flask-Talisman CSP, flask-wtf CSRF, Authlib OAuth.
- API client: sync only. Change it in the same PR as the web code that needs it.
- CSP blocks inline JS (`onclick`, `onchange`, inline `<script>`). Use Alpine directives; add `x-data` to elements outside an Alpine scope: `<button x-data @click="...">`. New CDN source: add it to the CSP dict in `lib/security.py`.

## Structure

- Each route is a package `routes/<name>/` holding its views, services, handlers, and templates. No top-level `services/`. Cross-cutting code goes in `lib/`.
- File roles: `views.py` owns `bp` and all URL registration; `handlers.py` holds `CrudHandler` implementations; `services.py` holds stateless logic and API orchestration (no request/response objects, `flash()`, or `redirect()`).
- File over ~300 lines: split into `views_<feature>.py` / `handlers_<feature>.py`. Sibling view modules define classes only; `views.py` imports and registers them. `character_create` pairs `<flow>_views.py` with `<flow>_services.py`.
- Views are `MethodView` classes: `bp.add_url_rule("/path", view_func=MyView.as_view("name"), methods=[...])`. Pass `methods=` for anything beyond GET.
- Render with `catalog.render("namespace.ComponentName", **kwargs)`, never `render_template()`.
- Character routes: `character_view`, `character_trait_edit` (spend types `NO_COST`, `STARTING_POINTS`, `XP`), `character_create`. Shared logic: `lib/character_profile.py`.

## Key helpers

- API services: in request code, call `lib/api_services.py` (`api_services.users()`, `.books(campaign_id)`, `.character_traits(character_id)`, ...). They take company and On-Behalf-Of user from the session and raise `NoRequestScopeError` without them. Never pass `company_id` or `on_behalf_of` by hand. Use the `<name>_service()` factories from `vweb.api_client` only before a session exists or for another company or user (auth flows, company selection, `cache.global_context.load`, and the unscoped `companies_service()`, `system_service()`, `user_lookup_service()`). Read `src/vweb/api_client/` for models, methods, and exceptions.
- Request data: `g.requesting_user`, `g.global_context.campaigns`, `lib/api.get_character_and_campaign(character_id)` (no API call).
- Permissions: call a guard from `lib/guards.py` (`is_admin`, `is_storyteller`, `can_edit_character`, ...) in Python and templates; never inline role or ownership checks. Don't pass a guard result as a prop when the child has the object in scope. New guard: add to `lib/guards.py`, register in `jinja_globals` in `lib/jinja.py`, test in `tests/lib/test_guards.py`.
- Trait rules: `lib/trait_rules.py` (`is_derived_trait`, specialty rules). For a character, call the `character_trait_*` wrappers in `lib/character_profile.py`, never compare trait names or sections inline.
- API errors: show `api_error_message(error, fallback="...")`, or `api_field_errors(...)` for per-field form errors (`lib/api_errors.py`), never a fixed "Failed to ..." string or raw `detail`. Catch `USER_FACING_API_ERRORS` when only user-fixable errors are handled.
- CRUD tables: subclass `CrudTableView` (`lib/crud/view.py`) and implement `CrudHandler` (`lib/crud/handler.py`; `validate` returns field -> message, `"_general"` for non-field errors). Register URLs with `register_crud_table_routes`. Copy an existing subclass.
- Scanner block (`lib/hooks.py`): `_hook_block_scanner_probes` 404s scanner paths before auth; use it for intentional 404s. Public path: add to `_PUBLIC_PATH_PREFIXES`; public file with a blocked suffix: `_PUBLIC_FILE_PATHS`.

## Caching

- API-response caches live in `lib/cache/`. Import the package, call `cache.<domain>.<verb>()`. Build new domains on `cache.base.cached_fetch(key, fetch, strategy)` (single-flight included).
- Values must be picklable (Redis in prod).
- `GlobalContext.characters` and `.characters_by_campaign` include other players' characters. Filter before rendering.
- After a local mutation, call `cache.global_context.clear_current()` (or `clear(company_id, user_id)` outside a session).
- When an API write returns the new state, patch the sheet with `cache.character_sheet.update(character_id, apply)` instead of clearing it.
- Templates use Jinja globals: `get_options()`, `get_all_traits()`, `get_system_health()`, `tracker_actions_for(...)`. Python calls `cache.*` directly.

## Templates (JinjaX)

| Kind                               | Location                                     | Use                                           |
| ---------------------------------- | -------------------------------------------- | --------------------------------------------- |
| Shared                             | `templates/shared/`                          | `<shared.CommonButton>`                       |
| Route page                         | `routes/<name>/templates/<name>/`            | `catalog.render("book.BookDetail")`           |
| Partial (rendered from Python)     | `routes/<name>/templates/<name>/partials/`   | `catalog.render("book.partials.X", ...)`      |
| Component (embedded as a tag)      | `routes/<name>/templates/<name>/components/` | `<chapter.components.ChapterNav />`           |

A template used both ways stays in `partials/`.

- HTMX endpoints that call `flash()` must OOB-swap the flash container: return `htmx_response_with_flash(content)`, `htmx_response(content, *oob)` for extra swaps, or `htmx_flash_only()` when nothing else swaps (`lib/htmx.py`). OOB-capable components take `oob: bool = False`.
- Dynamic props unquoted: `<Comp prop={{ expr }} />`. `prop="{{ x }}"` passes literal text.
- JinjaX tags inside `{% set %}` capture blocks render as literal text. Use raw HTML with daisyUI classes there.
- `<shared.CommonButton>` takes `extra_class`, `extra_attrs` (dynamic HTMX attributes), `btn_type`.
- Static URLs: `static_url(filename)`, not `url_for('static', ...)`.
- djlint rewrites single quotes to double, breaking JinjaX props holding JS strings. Wrap those lines in `{# djlint:off #}` / `{# djlint:on #}`.
- Lazy cards (`templates/shared/cards/`, endpoints in `routes/fragments_shared_cards/`): build URLs with `build_fragment_url(endpoint, **kwargs)`.
- daisyUI theme: `@plugin "daisyui" { themes: name --default; }`, never `@plugin "daisyui/theme" { ... }`.
- Tailwind sees only literal class strings. Safelist runtime-built classes (`"text-" ~ color`) with `@source inline("...")` in `src/vweb/static/css/input.css`.

## Testing

### Running tests

| Changed                                                         | Run                                                     |
| --------------------------------------------------------------- | ------------------------------------------------------- |
| Web code only (`src/vweb/` outside `api_client/`, templates)    | `uv run duty test scope=web`                            |
| `src/vweb/api_client/` or `tests/api_client/`                   | `uv run duty test`                                      |
| Dependencies, `tests/conftest.py`, or about to commit           | `uv run duty test`                                      |
| Iterating on one file or test                                   | `uv run pytest tests/routes/test_book_view.py -k <name>` |

- `scope=client` runs only `tests/api_client/`.
- Extra pytest args (`uv run duty test scope=web -k book`) filter within the scope and bypass the cache. Never pass a file path to `duty test`; it adds targets instead of narrowing. Use bare `uv run pytest <path>`.
- A full `scope=all` run fails below `COVERAGE_FLOOR` in `duties.py`.
- 10-second per-test timeout, `--exitfirst`, warnings are errors. A timeout usually means an infinite loop.

### Writing tests

- Sync pytest. Autouse `_mock_api` blocks real API calls; `_block_network` fails any network connection. `--strict-markers`: register new markers in `pyproject.toml`.
- Constructing `Settings()` directly: pass `_env_file=None`, or `.env.secret` leaks in. The `test_settings` fixture already does this.
- Model data: factories from `vweb.api_client.testing` (`UserFactory`, `CharacterFactory`, ...; `.batch(n)`). Defaults: users PLAYER, characters type PLAYER, company settings storyteller-only. Set the field when a test depends on it.
- Code that calls API services: the `fake_vclient` fixture. `MagicMock()` only for services passed in as arguments, handlers, and cache mocks.

    ```python
    fake_vclient.set_response(Routes.CAMPAIGNS_GET, model=camp1, params={"campaign_id": "c1"})
    fake_vclient.set_error(Routes.USERS_GET, status_code=404)
    fake_vclient.assert_called(Routes.USERS_GET, params=..., json_subset=..., times=1)
    ```

- Assert on recorded requests (`assert_called`, `assert_not_called`, `requests_for`), not on service mocks. Other options (`set_responses`, `set_connection_error`, `invalid_parameters`, paging, `query=` overrides) are documented in `src/vweb/api_client/testing/`. The fake never retries.
- Reuse shared helpers; don't redefine them: `tests/conftest.py` (`mock_global_context`, `use_context`, `get_csrf`, `htmx_post`, `htmx_delete`), `tests/routes/conftest.py` (`set_role`, `storyteller`, `admin_context`, `set_owner`), `tests/helpers.py` (`session_flashes`, `mock_oauth_provider`, `build_specialty`, ...).
- OAuth: patch `oauth`, `lookup_user_companies`, `identify_in_companies` in the module that uses them (`routes.auth.views_oauth` login/callback, `views_identity` link/unlink, `views` company selection). Pre-seed `user_id` with `client.session_transaction()`.

## Code style

- Ruff `select = ["ALL"]`, Google docstrings, line length 100.
- ty ignores: `# ty:ignore[rule-name]`, not `# type: ignore[...]`.
- Import constants and Literal types from `vweb.api_client` (e.g. `CharacterInventoryType`); never redefine them.
- `ty` is the only type checker. Editor `<new-diagnostics>` come from Pyright, which this project does not use. Confirm a Pyright warning with `ty` before acting; never change `ty`-clean code to satisfy Pyright.
