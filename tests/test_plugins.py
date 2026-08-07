"""Unit tests for the plugin contract and loader."""
import pytest

from pantograph.plugins import Plugin, PluginError, load_plugins, resolve_plugin_class


class _Fake(Plugin):
    id = "fake"
    label = "Fake"
    requires_tables = ("widgets",)

    def layout(self, config):
        return "layout"


SPEC = f"{__name__}:_Fake"


def _config(plugins, tables=("widgets",)):
    return {"tables": {t: {} for t in tables}, "plugins": plugins}


def test_explicit_class_spec_is_used_before_any_lookup():
    assert resolve_plugin_class("anything", SPEC) is _Fake


def test_entry_points_resolve_the_shipped_plugins():
    # Both live in this repo, but they are found the same way a separately
    # distributed plugin would be.
    assert resolve_plugin_class("explore").id == "explore"
    assert resolve_plugin_class("dashboard").id == "dashboard"


def test_unknown_plugin_names_the_ways_to_provide_it():
    with pytest.raises(PluginError, match="No plugin named 'nope'"):
        resolve_plugin_class("nope")


def test_bad_class_spec_is_rejected():
    with pytest.raises(PluginError, match="module:ClassName"):
        resolve_plugin_class("x", "pantograph.plugins")
    with pytest.raises(PluginError, match="has no attribute"):
        resolve_plugin_class("x", "pantograph.plugins:Missing")


def test_missing_required_table_fails_at_load_not_at_first_click():
    config = _config([{"id": "fake", "class": SPEC}], tables=())
    with pytest.raises(PluginError, match="requires table.*widgets"):
        load_plugins(config)


def test_config_id_overrides_the_class_default():
    """One implementation can be mounted under a deployment's own name."""
    config = _config([{"id": "registry", "class": SPEC, "label": "Registry"}])
    plugins, landing = load_plugins(config)
    assert (plugins[0].id, plugins[0].label, landing) == ("registry", "Registry", "registry")


def test_options_reach_the_plugin_and_deployment_config_does_not():
    config = _config([{"id": "fake", "class": SPEC, "config": {"window": 30}}])
    plugins, _ = load_plugins(config)
    assert plugins[0].options == {"window": 30}


def test_landing_defaults_to_the_first_entry_and_is_overridable():
    two = [{"id": "a", "class": SPEC}, {"id": "b", "class": SPEC}]
    assert load_plugins(_config(two))[1] == "a"
    marked = [{"id": "a", "class": SPEC}, {"id": "b", "class": SPEC, "landing": True}]
    assert load_plugins(_config(marked))[1] == "b"


def test_duplicate_ids_are_rejected():
    """Two pages sharing an id would collide on nav-<id> and <id>-container."""
    dupes = [{"id": "a", "class": SPEC}, {"id": "a", "class": SPEC}]
    with pytest.raises(PluginError, match="Duplicate plugin id"):
        load_plugins(_config(dupes))


def test_a_bare_string_entry_is_shorthand_for_an_id():
    plugins, _ = load_plugins(_config(["explore"], tables=()))
    assert plugins[0].id == "explore"


def test_no_plugins_is_an_error_rather_than_a_blank_page():
    with pytest.raises(PluginError, match="No plugins configured"):
        load_plugins(_config([]))


class _Unlabelled(Plugin):
    def layout(self, config):
        return "layout"


def test_label_falls_back_to_a_readable_form_of_the_id():
    spec = f"{__name__}:_Unlabelled"
    config = _config([{"id": "data_protection", "class": spec}])
    assert load_plugins(config)[0][0].label == "Data Protection"
