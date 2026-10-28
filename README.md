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
- Node.js and npm (for building the Tailwind CSS)
- Docker, for the development Redis container (production needs its own Redis instance)
- Access to the [Valentina Noir API](https://docs.valentina-noir.com/), along with an API key

## Quick Start

Clone the repo and install both the Python and Node dependencies:

```bash
git clone https://github.com/natelandau/valentina-web.git
cd valentina-web
uv sync      # Python dependencies
npm install  # Tailwind CSS and daisyUI, used to build the stylesheet
```

Copy the example env file and fill in your values:

```bash
cp .env.example .env.secret
```

At a minimum, set `VWEB_SECRET_KEY`, the `VWEB_API__*` block, and `VWEB_REDIS__URL`. For a local run, also set `VWEB_ENV=development`. Without it, the app defaults to production mode and redirects every request to HTTPS. See [Configuration](#configuration) for details.

For local development, point Redis at the development container that `compose-db.yml` defines:

```bash
VWEB_REDIS__URL=redis://:redispassword@127.0.0.1:6380/0
```

The container listens on port 6380, so it does not collide with a Valentina Noir API that uses Redis on port 6379.

Start Flask and the Tailwind CSS watcher together:

```bash
duty run
```

The app runs at <http://127.0.0.1:8089>. `duty run` starts the development Redis container if it is not running. If `VWEB_REDIS__URL` is unset or points at port 6379, `duty run` stops, so the app never shares the Redis of the Valentina Noir API. It also builds `src/vweb/static/css/style.css` and rebuilds it whenever a template or `input.css` changes. That file is gitignored, so it does not exist on a fresh clone until the first build. If you skip the build, pages load without any styling.

To run Flask on its own, build the stylesheet first:

```bash
duty css     # Build src/vweb/static/css/style.css once
uv run vweb  # Start the dev server without the watcher
```

## Configuration

Configuration is handled by [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/). Every variable uses the `VWEB_` prefix, and nested settings use double underscores (for example, `VWEB_API__BASE_URL`). Secrets are read from `.env.secret` in the project root.

The most important variables:

| Variable                             | Description                                                                                                                                                      |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `VWEB_ENV`                           | `development` or `production`. Defaults to `production`, which requires Redis, a non-default secret key, and HTTPS. Set `development` for local runs.            |
| `VWEB_FORCE_HTTPS`                   | Redirect HTTP requests to HTTPS and mark cookies secure. Defaults to `true` in production. Set `false` to run production mode over plain HTTP with no TLS proxy. |
| `VWEB_SECRET_KEY`                    | Flask session secret. Must be changed for production.                                                                                                            |
| `VWEB_API__BASE_URL`                 | URL of the Valentina API.                                                                                                                                        |
| `VWEB_API__API_KEY`                  | API key for the Valentina API.                                                                                                                                   |
| `VWEB_REDIS__URL`                    | Redis connection URL. For local development, use `redis://:redispassword@127.0.0.1:6380/0`.                                                                      |
| `VWEB_OAUTH__DISCORD__CLIENT_ID`     | Discord OAuth client ID.                                                                                                                                         |
| `VWEB_OAUTH__DISCORD__CLIENT_SECRET` | Discord OAuth client secret.                                                                                                                                     |
| `VWEB_OAUTH__GITHUB__CLIENT_ID`      | GitHub OAuth client ID.                                                                                                                                          |
| `VWEB_OAUTH__GITHUB__CLIENT_SECRET`  | GitHub OAuth client secret.                                                                                                                                      |
| `VWEB_OAUTH__GOOGLE__CLIENT_ID`      | Google OAuth client ID.                                                                                                                                          |
| `VWEB_OAUTH__GOOGLE__CLIENT_SECRET`  | Google OAuth client secret.                                                                                                                                      |
| `VWEB_OAUTH__APPLE__SERVICES_ID`     | Sign in with Apple Services ID (the web client ID).                                                                                                              |
| `VWEB_OAUTH__APPLE__TEAM_ID`         | Apple Developer Team ID.                                                                                                                                         |
| `VWEB_OAUTH__APPLE__KEY_ID`          | Sign in with Apple key ID.                                                                                                                                       |
| `VWEB_OAUTH__APPLE__PRIVATE_KEY`     | Sign in with Apple `.p8` key contents (PEM, newlines escaped as `\n`).                                                                                           |

`.env.example` documents every available setting (timeouts, retries, logging, Docker runtime, etc.). See `src/vweb/config.py` for the full schema.

## Authentication

Valentina Web supports Discord, GitHub, Google, and Apple OAuth. Provider-specific setup guides live in `docs/`:

- [Discord OAuth setup](docs/oauth-discord.md)
- [GitHub OAuth setup](docs/oauth-github.md)
- [Google OAuth setup](docs/oauth-google.md)
- [Sign in with Apple setup](docs/oauth-apple.md)

New accounts register as `UNAPPROVED` and can't access the app until an admin approves them.

## Development

Common commands:

```bash
uv run vweb           # Start the dev server on 127.0.0.1:8089
duty run              # Flask + Tailwind watcher
duty test             # Run the test suite with coverage
duty lint             # Run ruff, ty, typos, and pre-commit
duty css              # Build production (minified) CSS
duty redis-up         # Start the development Redis container
duty redis-down       # Stop the development Redis container and keep its data
duty redis-cli        # Open redis-cli on this checkout's Redis database
uv run pytest tests/  # Run tests directly
```

Run `duty lint` and `duty test` before opening a pull request.

### Develop against a local vclient

To test unreleased changes to [valentina-python-client](https://github.com/natelandau/valentina-python-client), clone it next to this repository and install it as an editable dependency:

```bash
duty vclient-local    # Install vclient from ../valentina-python-client
duty vclient-release  # Go back to the published vclient
```

`duty vclient-local` adds a path override to `pyproject.toml` and `uv.lock`. That path exists only on your machine, so do not commit these two files while the override is on. Commit your other files as usual and leave these two unstaged. The pre-commit hook, the pre-push hook, and CI reject any dependency path outside the repository.

### Work in several worktrees

You can run up to five git worktrees at the same time. Each worktree gets its own Redis database and its own port, so the dev servers do not share cached data or sessions. The numbers below assume that the main checkout uses Redis database 0 and port 8089.

1. In the main checkout, make sure that `VWEB_REDIS__URL` in `.env.secret` points at port 6380.
2. Create the worktree:

    ```bash
    duty worktree branch=my-feature
    ```

    This command creates `.worktrees/my-feature` on the new branch `my-feature`. It copies `.env.secret` and `CLAUDE.local.md` into the worktree, then gives the worktree a Redis database (1 to 5) and a port (8090 to 8094). It also installs the Python and npm dependencies.

3. Start the worktree:

    ```bash
    cd .worktrees/my-feature
    duty run
    ```

4. When you finish, remove the worktree and delete its Redis data:

    ```bash
    duty worktree-teardown branch=my-feature
    ```

    The branch stays. Git refuses to remove a worktree that has uncommitted changes or untracked files.

`duty worktree-prune` deletes the Redis data of worktrees that you removed without `duty worktree-teardown`.

Each worktree port needs its own OAuth callback URL for Discord and Google. The [Discord](docs/oauth-discord.md) and [Google](docs/oauth-google.md) setup guides list the URLs. GitHub accepts the main development callback on every port. Sign in with Apple does not work on a local checkout.

## Contributing

Issues and pull requests are welcome. For anything non-trivial, please open an issue first so we can agree on the approach before you write code.

## License

Released under the [MIT License](LICENSE).

## Legal

_Vampire: The Masquerade_, _World of Darkness_, and related marks are trademarks of Paradox Interactive AB. Valentina Web is an unofficial fan project and is not affiliated with, endorsed by, or sponsored by Paradox Interactive or White Wolf Entertainment. No copyrighted game content is distributed with this software.
