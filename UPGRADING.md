# Upgrading

## To the Pantograph split (core + plugins)

The engine was extracted from `collaboratorium/` into `src/pantograph/`, with
Explore and the Dashboard as plugins. Your **data is unaffected** — the database
schema, file name and location are unchanged, and no migration runs.

Three things change for an existing deployment. All three will stop a container
from starting, so do them together.

### 1. `config.yaml` becomes a `config/` directory

Configuration is now a directory of YAML files merged on their top-level keys.
The quickest upgrade is to keep your existing file as-is inside the new
directory — a single file still loads, and merging is by top-level key, so one
file is simply the degenerate case:

```bash
mkdir config
git mv config.yaml config/config.yaml    # or plain mv, if it isn't tracked
```

Then add the new `plugins:` key, which has no default — a deployment with no
plugins configured renders nothing, and startup fails saying so:

```yaml
plugins:
- id: dashboard
  landing: true
- id: explore
```

Drop `- id: dashboard` if this deployment doesn't want the Collaboratorium
dashboard. It declares the tables it assumes (`activities`, `initiatives`,
`people`, `tag_groups`, and the two link tables); if your schema lacks any of
them, startup now fails naming the missing ones rather than erroring at first
click.

To split further later, see the layout this repository ships in `config/`.

### 2. The Docker bind mount changes

In `docker-compose.yml`:

```diff
-      - ./config.yaml:/app/config.yaml:ro
+      - ./config:/app/config:ro
```

If you miss this, the container exits with
`ConfigError: No config at /app/config …`, which names the mount as the likely
cause.

### 3. The entrypoint changes

Handled for you if you build from this repository's `Dockerfile`. If you run the
app directly, `python ./collaboratorium/main.py` becomes:

```bash
pip install -e .        # once, so the plugin entry points resolve
python -m pantograph
```

### Optional

Paths can now be moved with `PANTOGRAPH_CONFIG`, `PANTOGRAPH_DB`,
`PANTOGRAPH_ANALYTICS_DB` and `PANTOGRAPH_ASSETS` (see `env.example`). They
default to the previous locations, so you need none of them to upgrade.

A stale editable install of the old package may still be present in a
development environment. Remove it so imports resolve unambiguously:

```bash
pip uninstall collaboratorium
```
