"""
plugins.py
The page plugin contract, and the loader that resolves it from config.

A plugin contributes one page: a nav entry, a layout, and a set of callbacks.
Core never names a plugin, and a plugin is explicitly *allowed* to be specific —
to ship its own SQL and assume its own tables. That permission is the point of
the split: it is what stops domain knowledge leaking into core as ever-more
abstract configuration. A plugin declares what it assumes via `requires_tables`
and the deployment fails at startup rather than at first click.

Resolution order for a plugin id, so that a plugin can move between this
repository and its own without any core change:

1. an explicit ``class: "package.module:ClassName"`` in the config entry
2. an installed entry point in the ``pantograph.plugins`` group
3. the in-repo convention ``pantograph_<id>.plugin:Plugin``

(3) exists so a source checkout works without reinstalling after every rename;
(2) is what a separately distributed plugin would use.
"""
from importlib import import_module
from importlib.metadata import entry_points

ENTRY_POINT_GROUP = "pantograph.plugins"


class PluginError(Exception):
    """Raised for a plugin that cannot be resolved, or whose needs are unmet."""


class Plugin:
    """
    Base class for a page plugin.

    `id` is deployment-facing: it appears in the config, in the nav button id
    (``nav-<id>``), in the page container id (``<id>-container``) and as the
    value of the shared ``page-store``. Every other component id a plugin
    creates should be prefixed with it — Dash silently stops dispatching
    pattern-matching callbacks when two components share an id, and that failure
    mode is miserable to debug.
    """

    id = None
    label = None
    requires_tables = ()

    def __init__(self, options=None):
        # The plugin's own block from the config entry, e.g. the dashboard's
        # window sizes. Deployment-wide config is passed to the methods instead.
        self.options = options or {}

    def layout(self, config):
        """Return the page's Dash component tree."""
        raise NotImplementedError

    def register(self, app, config):
        """Register this page's callbacks. Called once, at startup."""

    def stores(self):
        """Plugin-private ``dcc.Store``s to mount alongside the core ones."""
        return []

    def header_items(self, config):
        """
        Controls to place in the app header, e.g. quick-add buttons.

        These are global to the app rather than to the page, so they belong to
        whichever plugin actually wires them up — core cannot know that "add an
        activity" is a useful shortcut for a given deployment.
        """
        return []


def _load_class(spec):
    module_name, _, class_name = spec.partition(":")
    if not class_name:
        raise PluginError(f"Plugin class spec {spec!r} must be 'module:ClassName'")
    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise PluginError(f"Could not import plugin module {module_name!r}: {exc}") from exc
    try:
        return getattr(module, class_name)
    except AttributeError as exc:
        raise PluginError(f"{module_name!r} has no attribute {class_name!r}") from exc


def resolve_plugin_class(plugin_id, explicit_spec=None):
    if explicit_spec:
        return _load_class(explicit_spec)

    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if ep.name == plugin_id:
            return ep.load()

    try:
        return _load_class(f"pantograph_{plugin_id}.plugin:Plugin")
    except PluginError as exc:
        raise PluginError(
            f"No plugin named {plugin_id!r}. Install a distribution providing the "
            f"{ENTRY_POINT_GROUP!r} entry point {plugin_id!r}, add an explicit "
            f"'class:' to its config entry, or provide the module "
            f"pantograph_{plugin_id}.plugin. ({exc})"
        ) from exc


def _check_requirements(plugin, config):
    """
    Fail loudly at startup when a plugin's assumed tables are not in the schema.

    This is the counterpart to letting plugins be specific: a finely tuned
    plugin may hard-code table names, so a deployment that does not define them
    must be told immediately rather than rendering a page of SQL errors.
    """
    tables = set(config.get("tables", {}))
    missing = [t for t in plugin.requires_tables if t not in tables]
    if missing:
        raise PluginError(
            f"Plugin {plugin.id!r} requires table(s) not defined in this "
            f"deployment's config: {', '.join(missing)}"
        )


def load_plugins(config):
    """
    Instantiate the plugins listed in ``config['plugins']``, in order.

    The first entry, or whichever sets ``landing: true``, is the landing page.
    Returns (plugins, landing_id).
    """
    entries = config.get("plugins") or []
    if not entries:
        raise PluginError("No plugins configured: nothing would be rendered.")

    plugins, landing = [], None
    seen = set()
    for entry in entries:
        if isinstance(entry, str):
            entry = {"id": entry}
        plugin_id = entry.get("id")
        if not plugin_id:
            raise PluginError(f"Plugin entry {entry!r} has no 'id'")
        if plugin_id in seen:
            raise PluginError(f"Duplicate plugin id {plugin_id!r}")
        seen.add(plugin_id)

        cls = resolve_plugin_class(plugin_id, entry.get("class"))
        plugin = cls(options=entry.get("config"))
        # The config's id wins, so one implementation can be mounted under a
        # deployment's own name without subclassing it.
        plugin.id = plugin_id
        if entry.get("label"):
            plugin.label = entry["label"]
        plugin.label = plugin.label or plugin_id.replace("_", " ").title()

        _check_requirements(plugin, config)
        plugins.append(plugin)
        if entry.get("landing"):
            landing = plugin_id

    return plugins, landing or plugins[0].id
