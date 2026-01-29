# SearxNG Configuration

This directory contains the default configuration for the bundled SearxNG instance.

## Files

- `settings.yml` — SearxNG settings (JSON API enabled, rate limiter disabled)

## First Run

On first startup, SearxNG may create additional files in this directory (e.g., `uwsgi.ini`). These are auto-generated and can be safely ignored in version control.

## Customization

Edit `settings.yml` to:
- Change the `secret_key` (recommended for production)
- Add/remove search engines
- Adjust search settings

See [SearxNG documentation](https://docs.searxng.org/admin/settings/index.html) for all options.
