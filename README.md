# Collaboratorium
An environment for collaborative innovation

## Feedback Process

We are excited to hear feedback on this tool!

Please submit reports on how you use this tool and how it's helped you identify connections and understand your collaboration network by going to 
> Issues (in the top left) -> New Issue (top right) -> Use Report

Likewise, you will find templates for bug reports and feature requests.

## Layout

Collaboratorium is one deployment of **Pantograph**, a config-driven database
viewer and form engine. This repository holds both: the engine, and the plugins
that make it a particular product. See
[docs/architecture-plugins.md](docs/architecture-plugins.md).

    src/pantograph/             core — knows no table, no page, no plugin
    src/pantograph_explore/     graph / spreadsheet / report; works on any schema
    src/pantograph_dashboard/   the Collaboratorium dashboard; assumes its tables

Which pages a deployment mounts is the `plugins:` list in `config.yaml`.

## Development

Install once, in editable mode, so the plugin entry points resolve:

```bash
pip install -e .
```

Then run:

```bash
python -m pantograph
```

Paths default to the working directory and can be overridden with
`PANTOGRAPH_CONFIG`, `PANTOGRAPH_DB`, `PANTOGRAPH_ANALYTICS_DB` and
`PANTOGRAPH_ASSETS`. `HOST`, `PORT` and `DEBUG` control the server.

Run the tests with:

```bash
pytest
```

## Hosting
For running in Docker, use the standard `docker compose build` then `docker compose up`

For Auth, register the app in Google Cloud Console and set the redirect URI to `{site_url}/auth/callback`

## Setting up a config.yaml from DBML schema
The config gen script (`src/pantograph/tools/config_gen.py`) can produce a rough config, but work needs to be done to better handle links, I needed to manually add the links for non-link-tables. Some customization to types and appearance eg. using email fields instead of strings can be done in the forms confi