# SearxNG Configuration

This directory contains the default configuration for the bundled SearxNG instance.

## Files

- `settings.yml` — SearxNG settings (JSON API enabled, rate limiter disabled)

## First Run

On first startup, SearxNG may create additional files in this directory (e.g., `uwsgi.ini`). These are auto-generated and can be safely ignored in version control.

## Customization

Edit `settings.yml` to:
- Add/remove search engines
- Adjust search settings

The `secret_key` is set via the `SEARXNG_SECRET` environment variable in `.env` (not in this file). Generate one with `openssl rand -hex 32`.

See [SearxNG documentation](https://docs.searxng.org/admin/settings/index.html) for all options.
