"""Loading and merging configuration from a file or a directory of files."""
import pytest
import yaml

from pantograph.config import Config, ConfigError, load_config

LINKS = {"links": {"a_links": {"mappings": []}}}


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# The shipped config still loads
# --------------------------------------------------------------------------

def test_the_repository_config_directory_loads():
    config = load_config("config")
    assert config["title"] == "Collaboratorium"
    assert {"tables", "links", "forms", "default_forms", "plugins"} <= set(config)
    assert isinstance(config, Config) and config.fk_map


# --------------------------------------------------------------------------
# Single file, still supported
# --------------------------------------------------------------------------

def test_a_single_file_is_still_a_valid_config():
    """config_gen emits one file, and a small deployment has no reason to split."""
    assert load_config("config/schema.yaml")["tables"]


def test_a_single_file_path_is_not_treated_as_a_directory(tmp_path):
    path = _write(tmp_path, "everything.yaml", {"title": "T", **LINKS})
    assert load_config(path)["title"] == "T"


# --------------------------------------------------------------------------
# Directory merge
# --------------------------------------------------------------------------

def test_top_level_keys_from_every_file_are_merged(tmp_path):
    _write(tmp_path, "core.yaml", {"title": "T", **LINKS})
    _write(tmp_path, "schema.yaml", {"tables": {"a": {}}})
    config = load_config(tmp_path)
    assert config["title"] == "T" and config["tables"] == {"a": {}}


def test_two_files_may_contribute_to_the_same_mapping(tmp_path):
    """
    The motivating case: a plugin adds its own tables alongside the deployment's
    without either file having to know about the other.
    """
    _write(tmp_path, "schema.yaml", {"tables": {"people": {}}, **LINKS})
    _write(tmp_path, "gdpr.yaml", {"tables": {"processing_activities": {}}})
    assert set(load_config(tmp_path)["tables"]) == {"people", "processing_activities"}


def test_the_same_sub_key_in_two_files_names_both(tmp_path):
    """
    Silent last-one-wins would make the winner depend on filenames, which is not
    something anyone should have to reason about.
    """
    _write(tmp_path, "schema.yaml", {"tables": {"people": {"fields": {}}}, **LINKS})
    _write(tmp_path, "other.yaml", {"tables": {"people": {"fields": {"x": "y"}}}})
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)
    assert "tables.people" in str(exc.value)
    assert "schema.yaml" in str(exc.value) and "other.yaml" in str(exc.value)


def test_a_duplicated_scalar_is_an_error_not_a_merge(tmp_path):
    _write(tmp_path, "a.yaml", {"title": "One", **LINKS})
    _write(tmp_path, "b.yaml", {"title": "Two"})
    with pytest.raises(ConfigError, match="Only mappings can be spread"):
        load_config(tmp_path)


def test_a_duplicated_list_is_an_error_too(tmp_path):
    """Concatenating would be a guess; ordering matters for `plugins`."""
    _write(tmp_path, "a.yaml", {"plugins": ["explore"], **LINKS})
    _write(tmp_path, "b.yaml", {"plugins": ["dashboard"]})
    with pytest.raises(ConfigError, match="Only mappings can be spread"):
        load_config(tmp_path)


def test_merge_order_is_by_filename_so_it_does_not_depend_on_the_filesystem(tmp_path):
    for name in ["z.yaml", "a.yaml", "m.yaml"]:
        _write(tmp_path, name, {name.split(".")[0]: {}})
    _write(tmp_path, "links.yaml", LINKS)
    assert list(load_config(tmp_path)) == ["a", "links", "m", "z"]


# --------------------------------------------------------------------------
# Failure modes that would otherwise surface much later
# --------------------------------------------------------------------------

def test_an_empty_config_directory_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="No .yaml files"):
        load_config(tmp_path)


def test_non_yaml_files_are_ignored(tmp_path):
    (tmp_path / "notes.md").write_text("not config", encoding="utf-8")
    (tmp_path / ".hidden.yaml").write_text("title: hidden", encoding="utf-8")
    _write(tmp_path, "core.yaml", {"title": "T", **LINKS})
    assert load_config(tmp_path)["title"] == "T"


def test_yml_is_accepted_as_well_as_yaml(tmp_path):
    _write(tmp_path, "core.yml", {"title": "T", **LINKS})
    assert load_config(tmp_path)["title"] == "T"


def test_a_file_that_is_not_a_mapping_says_which_one(tmp_path):
    (tmp_path / "bad.yaml").write_text("- just\n- a list\n", encoding="utf-8")
    _write(tmp_path, "core.yaml", {"title": "T", **LINKS})
    with pytest.raises(ConfigError, match="bad.yaml must contain a mapping"):
        load_config(tmp_path)
