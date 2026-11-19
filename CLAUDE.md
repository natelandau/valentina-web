# Valentina Web

Server-rendered Flask app consuming the Valentina API through its in-repo client. HTMX for interactivity, no SPA.

Specs and plans are never committed to this repo.

## Quick Reference

```bash
uv run vweb           # Dev server (127.0.0.1:8089)
duty lint             # ruff, ty, typos, pre-commit
duty test             # All tests with coverage (see "Running tests" for scopes)
duty run              # Flask + Tailwind watcher
duty css              # Build CSS (production, minified)
duty redis-up         # Start the dev Redis container (127.0.0.1:6380); `duty run` does this too
duty worktree branch=<name>           # New worktree with its own Redis database and port
duty worktree-teardown branch=<name>  # Remove a worktree and flush its Redis database
uv run duty validate_constants company_id=<id>  # Check client constants against a running API
```

Do feature, fix, and refactor work in a worktree (`duty worktree branch=<name>`), not in the main checkout. It gives the work its own Redis database and dev server port, and keeps the main checkout on `main`.

`duty ruff/format/ty/typos/test` and `duty precommit` run through gate-cache: a gate that already passed on the same files is skipped ("already passed on tree ..."). A skip is a valid pass. Force a rerun with `GATE_CACHE_DISABLE=1`.

## Stack

- Flask 3.1+, Python 3.13, JinjaX (on Jinja2), HTMX + AlpineJS (CDN)
- Tailwind v4 + daisyUI v5 via `@tailwindcss/cli` (npm)
- pydantic-settings (`VWEB_` prefix, reads `.env.secret`) — use lazy `get_settings()`, never a module-level `settings`
- Flask-Talisman (CSP/HSTS), flask-wtf CSRF, Authlib OAuth
- API: in-repo client `src/vweb/api_client/` (sync only). It changes in the same PR as the web code that needs an API change.

### CSP / No inline JS

Production CSP blocks `onclick`, `onchange`, inline `<script>`. Use Alpine `@click`/`@change`/`x-data` directives; add `x-data` directly for elements not already in an Alpine scope: `<button x-data @click="...">`. `'unsafe-eval'` is enabled (Alpine needs it). When adding CDN sources, update the CSP dict in `create_app()`.

## Route-Centric Structure

Each route is a self-contained package under `routes/<name>/` co-locating views, services, handlers, and templates. Business logic lives next to its route — **there is no top-level `services/`.** Cross-cutting infrastructure lives in `lib/`.

Character routes split into `character_view`, `character_trait_edit` (spend types: `NO_COST`/`STARTING_POINTS`/`XP`), and `character_create`. Shared character logic: `lib/character_profile.py`; the cached full sheet lives in the cache package as `cache.character_sheet.get(...)`.

### Conventions

- **`MethodView` only**, not decorated functions. Register via `bp.add_url_rule("/path", view_func=MyView.as_view("name"))`. Always pass `methods=` when handling more than GET.
- Render templates via `catalog.render("namespace.ComponentName", **kwargs)` — `render_template()` is no longer used anywhere.
- **File roles:** `views.py` (MethodViews + all URL registration, owns `bp`), `handlers.py` (CrudHandler implementations), `services.py` (stateless business logic / API orchestration / validation; no request/response objects, no `flash()`/`redirect()`). Split into `views_<feature>.py` / `handlers_<feature>.py` only when a file would exceed ~300 lines (e.g. `auth/views_oauth.py`, `character_view/views_inventory.py`); sibling view modules define classes only, `views.py` imports and registers them. Each character_create flow pairs `<flow>_views.py` + `<flow>_services.py`.
- CRUD table URL registration goes through `register_crud_table_routes` (`lib/crud/routing.py`).
- **Template placement:** `partials/` = rendered from Python via `catalog.render("ns.partials.X", ...)`; `components/` = embedded as JinjaX tags (`<ns.components.X />`). A template used both ways stays in `partials/`.

## Key Helpers

- **VClient:** `VClient` is created once in `create_app()` and stored in `app.extensions["vclient"]`. In request code, get services from `lib/api_services.py`: `api_services.users()`, `api_services.books(campaign_id)`, `api_services.character_traits(character_id)`, and so on. Each one takes the company and the On-Behalf-Of user from the session, and raises `NoRequestScopeError` when either is missing. Never pass `company_id` or `on_behalf_of` by hand in request code. `options()`, `dictionary()`, and `character_blueprint()` send no On-Behalf-Of user. Use the explicit `<name>_service()` factories from `vweb.api_client` only before a session exists or for another company or user: auth flows, company selection, `cache.global_context.load(company_id, user_id)`, and the unscoped `companies_service()`, `system_service()`, and `user_lookup_service()`. For model shapes, service methods, exceptions, and testing helpers, read `src/vweb/api_client/` (models, services, exceptions, testing) directly.
- **Data access:** `lib/api.get_character_and_campaign(character_id)` (reads `g.global_context`, no API call). Campaigns via `g.global_context.campaigns`. Requesting user via `g.requesting_user`.
- **Permission guards (`lib/guards.py`):** `is_admin`, `is_storyteller`, `is_self`, `can_manage_campaign`, `can_grant_experience`, `can_edit_traits_free`, `can_edit_character`, `can_edit_trackers`, etc. **Never inline `g.requesting_user.role in (...)` or ownership checks — always call a guard** (Python and templates). Don't pass a guard result as a prop if the child already has the parent object in scope. New check? Add to `lib/guards.py`, register in `lib/jinja.py`'s `jinja_globals`, test in `tests/lib/test_guards.py`.
- **Trait rules (`lib/trait_rules.py`):** `is_derived_trait` (V5 Willpower is read-only) and the local mirror of the API's specialty rules (`FIXED_COST` or `RATING_BASED`): `specialty_min_rating`, `accepts_specialties`, `specialty_keep_rating` (below it the API removes specialties), and `next_specialty_cost`. For a character, call the `character_trait_*` wrappers in `lib/character_profile.py`, which resolve the company rules and the concept's favored abilities once per request; `character_trait_accepts_specialties` and `character_trait_specialty_keep_rating` are Jinja globals. Call these instead of comparing trait names or sections inline.
- **API errors (`lib/api_errors.py`):** when an API client call fails, show `api_error_message(error, fallback="...")` (or `api_field_errors(...)` for forms with per-field errors), never a fixed "Failed to ..." string or the raw `detail`. It shows the API's reason for errors a user can fix and the fallback for server errors. Catch `USER_FACING_API_ERRORS` where only user-fixable errors should be handled.

### Caching

`TolerantRedisCache` (`lib/cache/backend.py`) in prod, `SimpleCache` in dev — all cached values must be picklable. Prod keys carry the app version (`vweb:<version>:`), and an entry that fails to unpickle reads as a miss. All API-response caches live in the `lib/cache/` package. Import the package and call `cache.<domain>.<verb>()`:

- `cache.options.get()` — API enumerations (1-hour TTL); returns `ApiOptions` with fields like `.characters.character_class`
- `cache.blueprint.traits()` / `cache.blueprint.trait(trait_id)` — blueprint traits (1-hour TTL)
- `cache.statistics.get(scope_type, scope_id)` — roll statistics (30s TTL)
- `cache.campaign_content.books(campaign_id)` / `cache.campaign_content.chapters(campaign_id, book_id)` — book/chapter lists
- `cache.global_context.load(company_id, user_id)` — per-user global context; `cache.global_context.clear_current()` (session-scoped) to invalidate after local mutations, or `clear(company_id, user_id)` when ids come from elsewhere (e.g. auth flows)
- `cache.character_sheet.update(character_id, apply)` — change the cached full sheet in place when an API write returns the new state (tracker and health taps), instead of clearing it and refetching

All domains are built on `cache.base.cached_fetch(key, fetch, strategy)`, which provides single-flight (thundering-herd) protection by default. Freshness strategies: `PureTTL` (pure TTL expiry), `ShortTTL` (same as PureTTL, intent-named for low-TTL eventually-consistent caches), `TimestampValidated` (TTL + external timestamp check for the global context).

**Jinja globals still exist for templates:** `get_options()` (`get_options().characters.character_class`), `get_all_traits()`, `get_system_health()`, `get_all_terms()`, `tracker_actions_for(game_version, tracker_type)` — their dict keys are unchanged. Python code calls `cache.<domain>...` directly.

**`GlobalContext` gotcha:** `characters_by_campaign` and `characters` contain ALL characters including other players'. **Routes must filter before rendering.** The `inject_global_context` before_request hook populates `g.global_context` and resolves `g.requesting_user` from `session["user_id"]`. After local mutations, call `cache.global_context.clear_current()` to invalidate the cached context.

### Auth (OAuth)

Authlib with Discord/GitHub/Google/Apple. Provider authorize/callback views live in `routes/auth/views_oauth.py`, identity link/unlink in `views_identity.py`, logout/company selection (and `bp`) in `views.py`; all resolve via `routes/auth/services.py` (provider ID → email → create UNAPPROVED). `require_auth` before_request hook redirects unauthenticated → landing, UNAPPROVED → `/pending-approval`. 30-day permanent sessions in Redis, keyed by `session["user_id"]`.

### Scanner Block Hook (`lib/hooks.py`)

`_hook_block_scanner_probes` runs before auth and 404s known scanner paths — also the **intentional-404 mechanism** for non-routes like `/sitemap.xml` that would otherwise get auth's 302 redirect. For a public path, add it to `_PUBLIC_PATH_PREFIXES`; for a public file whose suffix the scanner blocks (like `/robots.txt`), add it to `_PUBLIC_FILE_PATHS`.

## Templates (JinjaX)

| Category          | Location                                     | Usage                                              |
| ----------------- | -------------------------------------------- | -------------------------------------------------- |
| Shared components | `templates/shared/`                          | `<shared.PageLayout>`, `<shared.CommonButton>`     |
| Error pages       | `templates/errors/`                          | Error handler templates                            |
| Route pages       | `routes/<name>/templates/<name>/`            | `catalog.render("book.BookDetail")`                |
| Route partials    | `routes/<name>/templates/<name>/partials/`   | `catalog.render("book.partials.BookContent", ...)` |
| Route components  | `routes/<name>/templates/<name>/components/` | `<chapter.components.ChapterNav>`                  |

The inner `<name>/` provides the JinjaX namespace.

### HTMX OOB + Flash

Flask `flash()` messages render inside `<div id="flash-messages">` via `<shared.layout.FlashMessage />`. HTMX partial swaps lose flashes silently — **any HTMX endpoint calling `flash()` must also OOB-swap the flash container**. Use `htmx_response_with_flash(content)` from `vweb.lib.htmx` (or `htmx_response(content, *oob)` when you need to compose additional OOB swaps); When an endpoint flashes but has nothing to swap in, return `htmx_flash_only()`, which sends only the flash container with `HX-Reswap: none`. OOB-capable components accept `oob: bool = False`:

```python
return htmx_response_with_flash(content)
```

### Shared lazy-loaded cards

Reusable HTMX-lazy cards under `templates/shared/cards/` — `<shared.cards.Statistics>` and `<shared.cards.RecentDiceRolls>`. Each wrapper emits an `hx-get` placeholder pointing at `/cards/...`; the endpoints live in `routes/fragments_shared_cards/views.py`. Scope via `campaign_id` / `character_id` / `user_id` props (Statistics: exactly one; Dice rolls: ≥1, combinable). Content partials (endpoint-rendered) live in `templates/shared/cards/partials/`. Wrappers build URLs via the `build_fragment_url(endpoint, **kwargs)` Jinja global, which drops empty/None kwargs. Stats fetches go through `cache.statistics.get(scope_type, scope_id)` (30s TTL).

### JinjaX Gotchas

- **Dynamic props unquoted**: `<Comp prop={{ expr }} />`. `prop="{{ x }}"` passes the literal text.
- **JinjaX components inside `{% set %}` capture blocks render as literal HTML.** Use raw HTML with equivalent daisyUI classes.
- **`<shared.CommonButton>`** uses `extra_class`, `extra_attrs`, `btn_type` (not `class`/`type` — Python reserved words). Use `extra_attrs` for dynamic HTMX attrs.
- `static_url(filename)` Jinja global for cache-busted static URLs — use instead of `url_for('static', ...)`.
- **djlint rewrites single → double quotes**, breaking JinjaX props with JS strings. Wrap affected lines in `{# djlint:off #}` / `{# djlint:on #}`.

### daisyUI Themes

Use `@plugin "daisyui" { themes: name --default; }`. Do NOT use `@plugin "daisyui/theme" { name: "..." }` — that creates a custom theme with dark defaults.

### Tailwind dynamic classes

Tailwind v4's JIT scanner only sees **literal** class strings in templates at build time. Classes built at runtime (e.g. `"col-span-" ~ col_span`, `"text-" ~ color`) are invisible to the scanner and won't get CSS rules generated — the class lands in the rendered HTML but has no effect. Safelist them in `src/vweb/static/css/input.css` via `@source inline("...")`. Already covered: `col-span-1..4` + `col-span-full` and the daisyUI `link-*` variants.

## CRUD Table Framework (`lib/crud/`)

`CrudTableView` (`lib/crud/view.py`) handles GET/POST/DELETE, sorting, validation, cache invalidation, and refetch-after-mutation for inline CRUD tables. Each route subclasses it (~8 lines) plus a handler implementing `CrudHandler` (`lib/crud/handler.py`) and a form template. `CrudHandler.validate` returns `dict[str, str]` mapping field name → message, with `"_general"` for non-field errors (empty dict when valid). Shared visuals: `templates/shared/crud/CrudTable.jinja` + `CrudForm.jinja`. `CrudTable.jinja` accepts `editable: bool = True`; parents thread `?editable=true/false` on HTMX load URLs. CSRF via `hx-headers` on `<body>` in `PageLayout.jinja`. Copy an existing subclass when adding a new table.

## Testing

### Running tests

Use `uv run duty test` for every check except iterating on a single test. Pick the scope from what you changed:

| You changed                                                                 | Run                                 |
| --------------------------------------------------------------------------- | ----------------------------------- |
| Web code only: `src/vweb/` outside `api_client/`, templates, web tests      | `uv run duty test scope=web`        |
| The API client: `src/vweb/api_client/` or `tests/api_client/`               | `uv run duty test` (web uses the client, so run both) |
| Dependencies, `tests/conftest.py`, or you are about to commit               | `uv run duty test`                  |
| One test file or test while iterating                                       | `uv run pytest tests/routes/test_book_view.py -k <name>` |

- `scope=client` runs only `tests/api_client/`. Use it for a quick check while editing the client, then run `uv run duty test` before you commit.
- Each scope is cached against only the files its tests read. A scope whose files did not change prints "already passed on tree ..." and exits 0. That is a pass, not a skipped check.
- Extra pytest options after the scope (for example `uv run duty test scope=web -k book`) filter within that scope and turn off the cache, so the command always runs. Do not pass a file path to `duty test`: it adds to the scope's targets instead of narrowing them. Use bare `uv run pytest <path>` for that.
- `duty test` runs in parallel (pytest-xdist) and fails a full `scope=all` run below the coverage floor (`COVERAGE_FLOOR` in `duties.py`).
- `pyproject.toml` sets a 10-second per-test timeout, `--exitfirst`, and turns every warning into an error. A timeout failure usually means an infinite loop.

### Writing tests

- Sync pytest. `_mock_api` (autouse in `conftest.py`) prevents real API calls, and `_block_network` fails any test that opens a network connection. `--strict-markers`: register new markers in `pyproject.toml`.
- `conftest.py`'s `test_settings` fixture builds `Settings` and passes it to `create_app(settings_override=...)` — no env vars needed. **Always pass `_env_file=None`** when constructing `Settings()` directly or pydantic leaks real config from `.env.secret`.
- **Model data:** use `vweb.api_client.testing` factories (`UserFactory`, `CampaignFactory`, `CharacterFactory`, …). `Factory.batch(n)` for multiples. Factories default users to PLAYER, characters to type PLAYER, and company settings to storyteller-only permissions; set the field when a test depends on it.
- **`fake_vclient` fixture** (`FakeVClient`) intercepts API client HTTP in memory. Use `set_response()` / `set_error()`; `add_route()` is a low-level escape hatch. Import `Routes` from `vweb.api_client.testing`:

    ```python
    fake_vclient.set_response(Routes.USERS_GET, model=UserFactory.build(id="u1"))
    fake_vclient.set_response(Routes.CAMPAIGNS_GET, model=camp1, params={"campaign_id": "c1"})
    fake_vclient.set_error(Routes.USERS_GET, status_code=404)
    ```

- **Assert on the wire, not on service mocks.** The fake records every request. `fake_vclient.assert_called(route, params=..., query=..., json=..., json_subset=..., times=...)` and `assert_not_called(route, ...)` check the route, path ids, query, and body; `requests_for(route)` returns the `RecordedRequest`s for custom checks.
- **More fake responses:** `set_responses(route, [FakeError(status_code=404), FakeResponse(model=user)])` returns one step per call, and the last repeats. `set_connection_error(route)` (or a `FakeConnectionError` step) makes the client raise `APIConnectionError`. `set_response(route, items=..., total=n)` reports more pages than it returns. `set_error(..., invalid_parameters=[{"field": ..., "message": ...}])` fakes a 400 with field errors. `query={...}` on `set_response`/`set_error` narrows an override by query value. The override that pins the most `params` and `query` values wins; a tie goes to the latest. The fake never retries, so a faked 5xx is sent once.
- **When to use which:** factories for data; `fake_vclient` for code that calls API services (`api_services.*()` or `<name>_service()`); `MagicMock()` only for service objects passed in as arguments, or handler and cache mocks.
- Other shared fixtures and helpers: `mock_global_context` (the signed-in player's `GlobalContext`), `mock_context_load`, `use_context(...)` (serve another context, built with `build_global_context` arguments), and in `tests/routes/conftest.py` `set_role`, `storyteller`, `admin_context`, `set_owner`. In `tests/conftest.py`: `get_csrf(client)`, `htmx_post(...)`, `htmx_delete(...)`. In `tests/helpers.py`: `session_flashes(client)`, `mock_oauth_provider(...)`, `build_specialty(...)`. Don't duplicate in test files.
- **OAuth tests:** patch `oauth`, `lookup_user_companies`, and `identify_in_companies` where used (`routes.auth.views_oauth` for login/callback, `views_identity` for link/unlink, `views` for company selection); pre-seed `user_id` via `client.session_transaction()`.

## Code Style

Ruff `select = ["ALL"]`, Google docstrings, line length 100, double quotes — see `pyproject.toml`. **ty ignores use `# ty:ignore[rule-name]`, NOT `# type: ignore[...]`.** Always import types from `vweb.api_client` (constants, models) when available (e.g. `CharacterInventoryType`) — never redefine Literal types locally.

**`ty` (via `duty lint`) is the only authoritative type checker.** Editor `<new-diagnostics>` come from a Pyright LSP plugin this project does NOT use; Pyright ignores `# ty:ignore`, so it flags `ty`-clean lines. A Pyright-only warning is not a failure — confirm with `ty` before acting on it; never "fix" `ty`-clean code to satisfy Pyright.
