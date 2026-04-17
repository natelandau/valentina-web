# Valentina Web

Server-rendered Flask app consuming the valentina-python-client API. HTMX for interactivity — no SPA.

**Workflow:** Never commit working documents in `docs/superpowers/` to git. Work on branches, not worktrees.

## Quick Reference

```bash
uv run vweb           # Dev server (127.0.0.1:8089)
uv run pytest tests/  # Tests
duty lint             # ruff, ty, typos, pre-commit
duty test             # Tests with coverage
duty run              # Flask + Tailwind watcher
duty css              # Build CSS (production, minified)
```

## Stack

- Flask 3.1+, Python 3.13, JinjaX (on Jinja2), HTMX + AlpineJS (CDN)
- Tailwind v4 + daisyUI v5 via `@tailwindcss/cli` (npm)
- pydantic-settings (`VWEB_` prefix, reads `.env.secret`) — use lazy `get_settings()`, never a module-level `settings`
- Flask-Talisman (CSP/HSTS), flask-wtf CSRF, Authlib OAuth
- API: valentina-python-client (`SyncVClient`)

### CSP / No inline JS

Production CSP blocks `onclick`, `onchange`, inline `<script>`. Use Alpine `@click`/`@change`/`x-data` directives; add `x-data` directly for elements not already in an Alpine scope: `<button x-data @click="...">`. `'unsafe-eval'` is enabled (Alpine needs it). When adding CDN sources, update the CSP dict in `create_app()`.

## Route-Centric Structure

Each route is a self-contained package under `routes/<name>/` co-locating views, services, handlers, and templates. Business logic lives next to its route — **there is no top-level `services/`.** Cross-cutting infrastructure lives in `lib/`.

Character routes split into `character_view`, `character_trait_edit` (spend types: `NO_COST`/`STARTING_POINTS`/`XP`), and `character_create`. Shared character services: `lib/character_sheet.py`, `lib/character_profile.py`.

### Conventions

- **`MethodView` only**, not decorated functions. Register via `bp.add_url_rule("/path", view_func=MyView.as_view("name"))`. Always pass `methods=` when handling more than GET.
- Render templates via `catalog.render("namespace.ComponentName", **kwargs)` — never `render_template()` except for shared partials in `templates/partials/`.

## Key Helpers

- **VClient:** `SyncVClient` is created in `create_app()` with a default `company_id`. Just call `sync_*` service factories — `sync_companies_service().list_all()`.
- **Data access:** `lib/api.get_character_and_campaign(character_id)` (reads `g.global_context`, no API call). Campaigns via `g.global_context.campaigns`. Requesting user via `g.requesting_user`.
- **Permission guards (`lib/guards.py`):** `is_admin`, `is_storyteller`, `is_self`, `can_manage_campaign`, `can_grant_experience`, `can_edit_traits_free`, `can_edit_character`, etc. **Never inline `g.requesting_user.role in (...)` or ownership checks — always call a guard** (Python and templates). Don't pass a guard result as a prop if the child already has the parent object in scope. New check? Add to `lib/guards.py`, register in `app.py`'s `jinja_globals`, test in `tests/test_guards.py`.

### Caching

`RedisCache` in prod, `SimpleCache` in dev — all cached values must be picklable. Keys/TTLs in `extensions.py` and `lib/*_cache.py`. Blueprint traits (`lib/blueprint_cache.py`) and API enumerations (`lib/options_cache.py`) are 1-hour shared caches; `get_options()` is a Jinja global (`get_options().characters.character_class`).

**`GlobalContext` gotcha:** `characters_by_campaign` and `characters` contain ALL characters including other players'. **Routes must filter before rendering.** The `inject_global_context` before_request hook populates `g.global_context` and resolves `g.requesting_user` from `session["user_id"]`. Call `clear_global_context_cache()` after local mutations.

### Auth (OAuth)

Authlib with Discord/GitHub/Google. All resolve via `routes/auth/services.py` (provider ID → email → create UNAPPROVED). `require_auth` before_request hook redirects unauthenticated → landing, UNAPPROVED → `/pending-approval`. 30-day permanent sessions in Redis, keyed by `session["user_id"]`.

### Scanner Block Hook (`lib/hooks.py`)

`_hook_block_scanner_probes` runs before auth and 404s known scanner paths — also the **intentional-404 mechanism** for non-routes like `/sitemap.xml` that would otherwise get auth's 302 redirect. For publicly accessible paths (like `/robots.txt`), add to `_PUBLIC_PATH_PREFIXES` instead.

## Templates (JinjaX)

| Category          | Location                                     | Usage                                              |
| ----------------- | -------------------------------------------- | -------------------------------------------------- |
| Shared components | `templates/shared/`                          | `<shared.PageLayout>`, `<shared.CommonButton>`     |
| Shared partials   | `templates/partials/`                        | `render_template("partials/search_bar.html")`      |
| Error pages       | `templates/errors/`                          | Error handler templates                            |
| Route pages       | `routes/<name>/templates/<name>/`            | `catalog.render("book.BookDetail")`                |
| Route partials    | `routes/<name>/templates/<name>/partials/`   | `catalog.render("book.partials.BookContent", ...)` |
| Route components  | `routes/<name>/templates/<name>/components/` | `<chapter.components.ChapterNav>`                  |

The inner `<name>/` provides the JinjaX namespace. `render_template()` is **only** for shared partials.

### HTMX OOB + Flash

Flask `flash()` messages render inside `<div id="flash-messages">` via `<shared.layout.FlashMessage />`. HTMX partial swaps lose flashes silently — **any HTMX endpoint calling `flash()` must also OOB-swap the flash container**. Use `htmx_response(content, *oob)` from `vweb.lib.jinja`; OOB-capable components accept `oob: bool = False`:

```python
flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
return htmx_response(content, flash_html)
```

### JinjaX Gotchas

- **Dynamic props unquoted**: `<Comp prop={{ expr }} />`. `prop="{{ x }}"` passes the literal text.
- **JinjaX components inside `{% set %}` capture blocks render as literal HTML.** Use raw HTML with equivalent daisyUI classes.
- **`<shared.CommonButton>`** uses `extra_class`, `extra_attrs`, `btn_type` (not `class`/`type` — Python reserved words). Use `extra_attrs` for dynamic HTMX attrs.
- `static_url(filename)` Jinja global for cache-busted static URLs — use instead of `url_for('static', ...)`.
- **djlint rewrites single → double quotes**, breaking JinjaX props with JS strings. Wrap affected lines in `{# djlint:off #}` / `{# djlint:on #}`.

### daisyUI Themes

Use `@plugin "daisyui" { themes: name --default; }`. Do NOT use `@plugin "daisyui/theme" { name: "..." }` — that creates a custom theme with dark defaults.

## CRUD Table Framework (`lib/crud_view.py`)

`CrudTableView` handles GET/POST/DELETE, sorting, validation, cache invalidation, and refetch-after-mutation for inline CRUD tables. Each route subclasses it (~8 lines) plus a handler implementing `CrudHandler` (`lib/crud_handler.py`) and a form template. Shared visuals: `templates/shared/crud/CrudTable.jinja` + `CrudForm.jinja`. `CrudTable.jinja` accepts `editable: bool = True`; parents thread `?editable=true/false` on HTMX load URLs. CSRF via `hx-headers` on `<body>` in `PageLayout.jinja`. Copy an existing subclass when adding a new table.

## Testing

- Sync pytest. `_mock_api` (autouse in `conftest.py`) prevents real API calls. Always run with a timeout to catch infinite loops. `--strict-markers` — register new markers in `pyproject.toml`.
- `conftest.py`'s `test_settings` fixture builds `Settings` and passes it to `create_app(settings_override=...)` — no env vars needed. **Always pass `_env_file=None`** when constructing `Settings()` directly or pydantic leaks real config from `.env.secret`.
- **Model data:** use `vclient.testing` factories (`UserFactory`, `CampaignFactory`, `CharacterFactory`, …). `Factory.batch(n)` for multiples.
- **`fake_vclient` fixture** (`SyncFakeVClient`) intercepts vclient HTTP in-memory — use `set_response()` / `set_error()` (never `add_route()`, deprecated). Import `Routes` from `vclient.testing`:

    ```python
    fake_vclient.set_response(Routes.USERS_GET, model=UserFactory.build(id="u1"))
    fake_vclient.set_response(Routes.CAMPAIGNS_GET, model=camp1, params={"campaign_id": "c1"})
    fake_vclient.set_error(Routes.USERS_GET, status_code=404)
    ```

- **When to use which:** factories for data; `fake_vclient` for code calling `sync_*` factories; `MagicMock()` only for service objects needing `side_effect` or handler/cache mocks.
- Other shared fixtures: `mock_global_context` (factory-built `GlobalContext`), `get_csrf(client)`. Don't duplicate in test files.
- **OAuth tests:** mock `oauth.discord`/`oauth.google` and `resolve_or_create_discord_user`; pre-seed `user_id` via `client.session_transaction()`.

## Code Style

Ruff `select = ["ALL"]`, Google docstrings, line length 100, double quotes — see `pyproject.toml`. **ty ignores use `# ty:ignore[rule-name]`, NOT `# type: ignore[...]`.** Always import types from vclient when available (e.g. `CharacterInventoryType`) — never redefine Literal types locally.
