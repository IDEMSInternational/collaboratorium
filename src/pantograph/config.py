"""
config.py
Loading and merging deployment configuration.

A deployment's config may be a single YAML file or a directory of them. The
directory form exists because one file mixing the graph stylesheet with the
field inventory was already uncomfortable at 1200 lines, and a records-of-
processing deployment's inventory is larger still.

Files are merged on their top-level keys, in filename order. Two files may
contribute to the same top-level mapping — a plugin adding its own `tables` to
the ones in `schema.yaml` is the motivating case — but defining the *same*
sub-key twice is an error rather than a silent last-one-wins, because which file
won would then depend on filenames.
"""
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Raised for configuration that cannot be loaded or merged coherently."""


class Config(dict):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fk_map = self.build_reference_index()

    def build_reference_index(self):
        """Build mappings of foreign key relationships."""
        fk_map = {}  # (child_table, child_column) -> (parent_table, parent_column)
        for link, link_dict in self["links"].items():
            for mapping in link_dict["mappings"]:
                child = (link, mapping["link_col"])
                parent = (mapping["target_table"], mapping["target_col"])
                fk_map[child] = parent
        return fk_map


def _merge_into(merged, origins, section, source_name):
    """
    Merge one file's top-level keys, recording where each came from so a clash
    can name both files rather than just complaining about a key.
    """
    if not isinstance(section, dict):
        raise ConfigError(f"{source_name} must contain a mapping at the top level")

    for key, value in section.items():
        if key not in merged:
            merged[key] = value
            origins[key] = {None: source_name}
            continue

        existing = merged[key]
        if not (isinstance(existing, dict) and isinstance(value, dict)):
            raise ConfigError(
                f"{key!r} is defined in both {origins[key][None]} and {source_name}. "
                f"Only mappings can be spread across files."
            )

        for sub_key, sub_value in value.items():
            if sub_key in existing:
                first = origins[key].get(sub_key, origins[key][None])
                raise ConfigError(
                    f"{key}.{sub_key} is defined in both {first} and {source_name}"
                )
            existing[sub_key] = sub_value
            origins[key][sub_key] = source_name


def load_config(filepath):
    """
    Load a config from a YAML file, or from a directory of them.

    Returns a Config. Raises ConfigError for a directory with no YAML in it,
    which is otherwise a confusing failure much later at the first missing key.
    """
    path = Path(filepath)

    if not path.is_dir():
        with open(path, "r") as f:
            return Config(yaml.safe_load(f))

    sources = sorted(
        p for p in path.iterdir()
        if p.suffix in (".yaml", ".yml") and not p.name.startswith(".")
    )
    if not sources:
        raise ConfigError(f"No .yaml files in config directory {path}")

    merged, origins = {}, {}
    for source in sources:
        with open(source, "r") as f:
            _merge_into(merged, origins, yaml.safe_load(f), source.name)

    return Config(merged)
