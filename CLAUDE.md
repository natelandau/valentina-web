# Valentina Web

Server-rendered Flask app consuming the valentina-python-client API. HTMX for interactivity — no SPA.

## Workflow Rules

- **Never commit plans, designs, or implementation specs in `docs/superpowers/`.** Working documents only.
- **Work on branches, not worktrees.** Unless the user explicitly asks otherwise.

## Quick Reference

```bash
uv run vweb           # Start dev server (127.0.0.1:8089)
uv run pytest tests/  # Run tests
duty lint             # Run all linters (ruff, ty, typos, pre-commit)
duty test             # Run tests with coverage
duty run              # Run Flask + Tailwind watcher
duty css              # Build CSS (production, minified)
```

## Architecture

- **Framework**: Flask 3.1+, Python 3.13 only
- **Templates**: JinjaX (on Jinja2)
- **Frontend**: HTMX and AlpineJS via CDN
- **CSS**: Tailwind v4 + daisyUI v5 via `@tailwindcss/cli` (npm)
- **Config**: pydantic-settings, `VWEB_` env prefix, reads `.env.secret`; lazy singleton via `get_settings()` — never use a module-level `settings`
- **Security**: Flask-Talisman (CSP/HSTS/cookies), flask-wtf CSRF, Authlib OAuth. When adding new CDN sources, update the CSP dict in `create_app()`. **No inline JavaScript** — CSP blocks `onclick`, `onchange`, inline `<script>` tags, etc. in production (`'unsafe-inline'` is only enabled for `script-src` in development). Use Alpine.js `@click`/`@change`/`x-data` directives instead. For elements not already in an Alpine scope, add `x-data` directly: `<button x-data @click="...">`. For Alpine to evaluate expressions it needs `'unsafe-eval'`, which is already in the CSP.
- **API client**: valentina-python-client (`SyncVClient`)

### Route-Centric Structure

Each route is a self-contained package under `routes/<name>/` co-locating views, services, handlers, and templates. Business logic lives alongside its route — there is no top-level `services/`. Cross-cutting infrastructure lives in `lib/`.

**Character routes** are split into three packages: `character_view` (display, image, inventory/notes), `character_trait_edit` (trait value modification with `NO_COST`/`STARTING_POINTS`/`XP` spend types), and `character_create` (picker, autogeneration, manual). Shared character services are in `lib/character_sheet.py` and `lib/character_profile.py`.

### VClient Lifecycle

`SyncVClient` is instantiated in `create_app()` and stored in `app.extensions["vclient"]`, configured with a default `company_id`. `sync_*` service factories take `company_id` as optional — just call them:

```python
from vclient import sync_companies_service

all_companies = sync_companies_service().list_all()
```

### Data-Access Helpers

- `lib/api.get_character_and_campaign(character_id)` — looks up from `g.global_context`, no API call
- For campaign lookups, use `g.global_context.campaigns` directly
- For the requesting user, use `g.requesting_user` (set by a before_request hook)

### Permission Guards (`lib/guards.py`)

Centralized authorization helpers registered as Jinja globals. **Always use these instead of inlining role or ownership checks** — in both Python and templates. See `lib/guards.py` for the current list (`is_admin`, `is_storyteller`, `is_self`, `can_manage_campaign`, `can_grant_experience`, `can_edit_traits_free`, `can_edit_character`, …).

**Rules:**

- Never write `g.requesting_user.role in (...)` or `session.get("user_id") == character.user_player_id` — call the guard.
- Never re-derive a guard in a template: `{% if can_edit_character(character) %}`.
- Don't pass a guard result down as a prop when the child template has the parent object in scope — let the child call the guard.
- If a new permission check is needed and no guard covers it, **add one to `lib/guards.py` first**, register it in `app.py`'s `jinja_globals`, write tests in `tests/test_guards.py`, then use it.

### Caching (`extensions.py`, Flask-Caching)

`RedisCache` in production, `SimpleCache` in dev. All cached values must be picklable. Cache keys and TTLs are defined in `extensions.py` and `lib/*_cache.py`.

**`GlobalContext` gotcha:** `characters_by_campaign` and `characters` contain ALL characters including other players'. **Routes must filter before rendering.** The `inject_global_context` before_request hook populates `g.global_context` and resolves `g.requesting_user` from `session["user_id"]`. Call `clear_global_context_cache()` after local mutations.

Blueprint traits (`lib/blueprint_cache.py`) and API enumerations (`lib/options_cache.py`) are shared 1-hour caches. `get_options()` is a Jinja global — use as `get_options().characters.character_class`, etc.

### Authentication (OAuth)

Authlib with Discord / GitHub / Google. All three resolve users via `routes/auth/services.py` (provider ID → email → create with UNAPPROVED status). `require_auth` before_request hook redirects unauthenticated users to the landing page and UNAPPROVED users to `/pending-approval`. Sessions are 30-day permanent, stored in Redis, keyed by `session["user_id"]`.

### Scanner Block Hook (`lib/hooks.py`)

`_hook_block_scanner_probes` runs before auth and returns 404 for known scanner paths. **This hook also serves as the intentional-404 mechanism for paths that don't exist but would otherwise get a 302 redirect from the auth hook.** For example, `/sitemap.xml` has no route — without the scanner block, unauthenticated requests would be redirected to the landing page instead of getting a proper 404. When a path should 404 cleanly for bots and crawlers, add it to the blocked suffixes/prefixes in this hook. For paths that should be publicly accessible (like `/robots.txt`), add them to `_PUBLIC_PATH_PREFIXES` instead.

### Route Conventions

- Use `MethodView` (class-based views), not decorated functions. Register via `bp.add_url_rule("/path", view_func=MyView.as_view("name"))`.
- **Always pass `methods=` to `add_url_rule()`** for any MethodView handling more than GET.
- Blueprint instances are named `bp` in each route's `__init__.py` and registered in `create_app()`.
- Routes render **all** templates via `catalog.render("namespace.ComponentName", **kwargs)`, never `render_template()` (except for shared partials in `templates/partials/`).

## Templates (JinjaX)

**Template locations:**

| Category          | Location                                     | Usage                                              |
| ----------------- | -------------------------------------------- | -------------------------------------------------- |
| Shared components | `templates/shared/`                          | `<shared.PageLayout>`, `<shared.CommonButton>`     |
| Shared partials   | `templates/partials/`                        | `render_template("partials/search_bar.html")`      |
| Error pages       | `templates/errors/`                          | Error handler templates                            |
| Route pages       | `routes/<name>/templates/<name>/`            | `catalog.render("book.BookDetail")`                |
| Route partials    | `routes/<name>/templates/<name>/partials/`   | `catalog.render("book.partials.BookContent", ...)` |
| Route components  | `routes/<name>/templates/<name>/components/` | `<chapter.components.ChapterNav>`                  |

The inner `<name>/` directory provides the JinjaX namespace. `render_template()` is permitted **only** for shared partials; everything else goes through `catalog.render()`.

### HTMX OOB + Flash (non-obvious)

Use `htmx_response(content, *oob)` from `vweb.lib.jinja` — never concatenate strings. OOB-capable components accept `oob: bool = False`.

Flask `flash()` messages are rendered inside `<div id="flash-messages">` by `<shared.layout.FlashMessage />`. HTMX partial responses swap only their target, so flashes are silently lost unless you OOB-swap the flash container:

```python
flash("Image uploaded successfully.", "success")
content = catalog.render("character.partials.ImagesContent", ...)
flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
return htmx_response(content, flash_html)
```

**Any HTMX endpoint calling `flash()` must pair it with an OOB `FlashMessage` render.**

### JinjaX Prop Gotchas

- **Pass dynamic values WITHOUT quotes**: `<Comp prop={{ expr }} />`. Quotes pass the literal string. (`prop="{{ x }}"` gives you the text `{{ x }}`, not its value.)
- **`{{ }}` inside quoted props are NOT evaluated.** To pass HTML with dynamic content, build the string with `{% set s = '<tag>' ~ func() ~ '</tag>' %}` then pass as `prop={{ s }}`.
- **JinjaX components inside `{% set %}` capture blocks are NOT processed** — they render as literal HTML. Use raw HTML with equivalent daisyUI classes instead.
- `<shared.CommonButton>` uses `extra_class`, `extra_attrs`, `btn_type` (not `class`/`type` — Python reserved words in JinjaX `{#def}`). For dynamic HTMX attrs, use `extra_attrs` — JinjaX can't parse `{{ var }}` in component tags.
- `static_url(filename)` Jinja global for cache-busted static URLs — use instead of `url_for('static', ...)`.
- **djlint rewrites single quotes to double**, which breaks JinjaX props containing JS strings. Wrap affected lines in `{# djlint:off #}` / `{# djlint:on #}`.

### daisyUI Themes

Use `@plugin "daisyui" { themes: name --default; }`. Do NOT use `@plugin "daisyui/theme" { name: "..." }` — that creates a custom theme with dark defaults.

## CRUD Table Framework (`lib/crud_view.py`)

Generic inline CRUD tables. `CrudTableView` handles GET/POST/DELETE, sorting, validation, cache invalidation, and refetch-after-mutation. Each route creates thin subclasses. Handlers implement the `CrudHandler` protocol (`lib/crud_handler.py`).

**Adding a new table:**

1. Handler class implementing `CrudHandler` in the route package
2. Form template (JinjaX) in the route's `templates/`
3. ~8-line `CrudTableView` subclass
4. URL rules in the route's view file
5. An `hx-get` div in the parent template

Shared visuals: `templates/shared/crud/CrudTable.jinja` + `CrudForm.jinja`. `CrudTable.jinja` accepts `editable: bool = True`; parents thread `?editable=true/false` on HTMX load URLs. Each table sits in a `<div>` with a unique `table_id`; delete uses a daisyUI modal with `htmx.process()` for the dynamic URL. CSRF is injected via `hx-headers` on `<body>` in `PageLayout.jinja`.

## Testing

- Sync pytest. Mock `sync_*` service factories to avoid real API calls.
- **Always pass `_env_file=None`** when constructing `Settings()` in tests — otherwise pydantic-settings reads `.env.secret` and leaks real config.
- **Always run pytest with a timeout** to catch infinite loops during refactors.
- `conftest.py` builds `Settings` via a `test_settings` fixture passed to `create_app(settings_override=...)` — no env vars needed.
- `--strict-markers` enabled; register new markers in `pyproject.toml`.
- **Use `vclient.testing` factories** (`UserFactory`, `CampaignFactory`, `CharacterFactory`, …) instead of `MagicMock()` for model instances. Customize with kwargs; `Factory.batch(n)` for multiples.
- **`fake_vclient` fixture** (`SyncFakeVClient`): intercepts vclient HTTP calls in-memory. Use `set_response()` / `set_error()` — **never `add_route()`** (deprecated). Import `Routes` from `vclient.testing`.

    ```python
    from vclient.testing import Routes, UserFactory, CampaignFactory

    fake_vclient.set_response(Routes.USERS_GET, model=UserFactory.build(id="test-user-id"))
    fake_vclient.set_response(Routes.CAMPAIGNS_LIST, items=CampaignFactory.batch(3))
    fake_vclient.set_response(Routes.CAMPAIGNS_GET, model=camp1, params={"campaign_id": "camp-1"})
    fake_vclient.set_error(Routes.USERS_GET, status_code=404)
    ```

- **When to use which**: factories for model data; `fake_vclient` for code calling `sync_*` factories directly; `MagicMock()` only for service objects needing `side_effect` or for handler/cache mocks.
- **Shared fixtures in `conftest.py`**: `_mock_api` (autouse) prevents real API calls; `mock_global_context` provides a factory-built `GlobalContext`; `get_csrf(client)` extracts CSRF tokens. Don't duplicate in test files.
- **OAuth tests**: mock `oauth.discord`/`oauth.google` methods and `resolve_or_create_discord_user`. Use `client.session_transaction()` to pre-seed `user_id`.

## Code Style

Ruff `select = ["ALL"]`, Google docstrings, line length 100, double quotes — see `pyproject.toml`. **ty ignore comments use `# ty:ignore[rule-name]`, NOT `# type: ignore[...]`.** Always import types from vclient when available (e.g. `CharacterInventoryType`) — never redefine Literal types locally.
