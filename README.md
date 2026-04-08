# Valentina Web

Valentina Web is a server-rendered web app for running [Vampire: The Masquerade](https://www.worldofdarkness.com/vampire-the-masquerade) chronicles with the [Valentina Noir API](https://github.com/natelandau/valentina-noir). Players manage character sheets, spend experience, roll dice,and track inventory; storytellers run campaigns, grant XP, etc. The stack is Flask, HTMX, and AlpineJS, so there's no JavaScript build pipeline to fight with.

## Features

- Character sheets with traits, disciplines, inventory, and notes
- Experience tracking and trait editing with multiple spend modes
- Campaign and chronicle management for storytellers
- Role-based permissions for players, storytellers, and admins
- OAuth login via Discord, GitHub, or Google
- Server-rendered HTML with HTMX for interactivity, no SPA build step

## Tech Stack

- Flask 3.1+ on Python 3.13
- JinjaX templates on top of Jinja2
- HTMX and AlpineJS (loaded from a CDN)
- Tailwind CSS v4 and daisyUI v5
- Redis for caching and sessions
- Authlib for OAuth
- valentina-python-client for API access (see the [API docs](https://docs.valentina-noir.com/))

## Prerequisites

Before you install, make sure you have:

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Node.js (for the Tailwind CLI)
- A running Redis instance
- Access to the [Valentina Noir API](https://docs.valentina-noir.com/), along with an API key

## Quick Start

Clone the repo and install dependencies:

```bash
git clone https://github.com/natelandau/valentina-web.git
cd valentina-web
uv sync
```

Copy the example env file and fill in your values:

```bash
cp .env.example .env.secret
```

At a minimum, set `VWEB_SECRET_KEY`, the `VWEB_API__*` block, and (for production) `VWEB_REDIS__URL`. See [Configuration](#configuration) for details.

Start the dev server:

```bash
uv run vweb
```

The app runs at <http://127.0.0.1:8089>.

To run Flask alongside the Tailwind watcher so CSS rebuilds on change:

```bash
duty run
```

## Configuration

Configuration is handled by [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/). Every variable uses the `VWEB_` prefix, and nested settings use double underscores (for example, `VWEB_API__BASE_URL`). Secrets are read from `.env.secret` in the project root.

The most important variables:

| Variable                             | Description                                                                                 |
| ------------------------------------ | ------------------------------------------------------------------------------------------- |
| `VWEB_ENV`                           | `development` or `production`. Production mode enforces Redis and a non-default secret key. |
| `VWEB_SECRET_KEY`                    | Flask session secret. Must be changed for production.                                       |
| `VWEB_API__BASE_URL`                 | URL of the Valentina API.                                                                   |
| `VWEB_API__API_KEY`                  | API key for the Valentina API.                                                              |
| `VWEB_API__DEFAULT_COMPANY_ID`       | Default company ID used by the API client.                                                  |
| `VWEB_API__SERVER_ADMIN_USER_ID`     | API user ID used as `requesting_user_id` when creating accounts via OAuth.                  |
| `VWEB_REDIS__URL`                    | Redis connection URL.                                                                       |
| `VWEB_OAUTH__DISCORD__CLIENT_ID`     | Discord OAuth client ID.                                                                    |
| `VWEB_OAUTH__DISCORD__CLIENT_SECRET` | Discord OAuth client secret.                                                                |
| `VWEB_OAUTH__GITHUB__CLIENT_ID`      | GitHub OAuth client ID.                                                                     |
| `VWEB_OAUTH__GITHUB__CLIENT_SECRET`  | GitHub OAuth client secret.                                                                 |
| `VWEB_OAUTH__GOOGLE__CLIENT_ID`      | Google OAuth client ID.                                                                     |
| `VWEB_OAUTH__GOOGLE__CLIENT_SECRET`  | Google OAuth client secret.                                                                 |

`.env.example` documents every available setting (timeouts, retries, logging, Docker runtime, etc.). See `src/vweb/config.py` for the full schema.

## Authentication

Valentina Web supports Discord, GitHub, and Google OAuth. Provider-specific setup guides live in `docs/`:

- [Discord OAuth setup](docs/oauth-discord.md)
- [GitHub OAuth setup](docs/oauth-github.md)
- [Google OAuth setup](docs/oauth-google.md)

New accounts register as `UNAPPROVED` and can't access the app until an admin approves them.

## Development

Common commands:

```bash
uv run vweb           # Start the dev server on 127.0.0.1:8089
duty run              # Flask + Tailwind watcher
duty test             # Run the test suite with coverage
duty lint             # Run ruff, ty, typos, and pre-commit
duty css              # Build production (minified) CSS
uv run pytest tests/  # Run tests directly
```

Run `duty lint` and `duty test` before opening a pull request.

## Contributing

Issues and pull requests are welcome. For anything non-trivial, please open an issue first so we can agree on the approach before you write code.

## License

Released under the [MIT License](LICENSE).

## Legal

_Vampire: The Masquerade_, _World of Darkness_, and related marks are trademarks of Paradox Interactive AB. Valentina Web is an unofficial fan project and is not affiliated with, endorsed by, or sponsored by Paradox Interactive or White Wolf Entertainment. No copyrighted game content is distributed with this software.
