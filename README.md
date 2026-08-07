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

Upgrading an existing deployment to this layout: see [UPGRADING.md](UPGRADING.md).
Your data is unaffected, but the config location, the Docker bind mount and the
entrypoint all change.

## Configuration

A deployment is configured by the `config/` directory, whose files are merged on
their top-level keys in filename order:

    config/core.yaml        title, editor layout, and which pages to mount
    config/schema.yaml      tables, links, and which form edits each table
    config/forms.yaml       form definitions
    config/explore.yaml     graph styling, filters and views for the Explore page
    config/dashboard.yaml   the dashboard plugin's options

Two files may contribute to the same top-level mapping — a plugin adding its own
`tables:` alongside the deployment's, say — but defining the same sub-key twice
is an error rather than a silent last-one-wins. A single YAML file still works
too; point `PANTOGRAPH_CONFIG` at it.

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