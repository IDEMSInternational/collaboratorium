"""
`{base_url}`: a report whose links still work once the markdown is elsewhere.

The shipped report does not use it. Its `{actions}` are affordances of this
app — edit, add — and the copy button deliberately hands over the document
without them, which is what belongs in a published activity report.

What this is for is reuse: a deployment that would rather hand out a report
people can click back from, to go and revise the records behind a figure, can
write `{base_url}#edit/...` into its own templates and set `PUBLIC_URL`. That
was how the report worked before the actions existed, and it is worth keeping
available rather than deleting.
"""
import pandas as pd
import pytest

from pantograph import settings
from pantograph.provenance import SUGGESTED, record
from pantograph.report_generator import generate_markdown_report

LINKED_CFG = {"name": "Register", "hierarchy": [
    {"type": "initiatives", "template": "## {name} [source]({base_url}#edit/initiatives/{id})\n"}]}


SUGGESTION = record(SUGGESTED, origin="run-4", confidence=0.82)


def nodes(**properties):
    data = {"id": 7, "version": 1, "name": "n", **properties}
    return [{"data": {"id": f"initiatives-{data['id']}", "label": data["name"],
                      "type": "initiatives", "properties": data}}]


@pytest.fixture
def public_url():
    """Set the configured address for one test, restoring whatever was there."""
    before = settings.get_settings().public_url_override

    def set_to(value):
        settings.configure(public_url_override=value)

    yield set_to
    settings.configure(public_url_override=before)


@pytest.fixture
def no_url_env(monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    monkeypatch.delenv("OAUTH_REDIRECT_URI", raising=False)
    return monkeypatch


# --------------------------------------------------------------------------
# Where the address comes from
# --------------------------------------------------------------------------

def test_an_unconfigured_deployment_keeps_links_relative(no_url_env):
    assert settings.public_url() == ""


def test_public_url_is_read_when_asked_not_at_import(no_url_env):
    """.env is loaded by pantograph.auth, after settings has been imported."""
    no_url_env.setenv("PUBLIC_URL", "https://pantograph.example.org/")
    assert settings.public_url() == "https://pantograph.example.org"


def test_public_url_falls_back_to_the_host_sign_in_returns_to(no_url_env):
    no_url_env.setenv("OAUTH_REDIRECT_URI", "https://pantograph.example.org/auth/callback")
    assert settings.public_url() == "https://pantograph.example.org"


def test_the_oauth_fallback_keeps_the_port(no_url_env):
    """A development server on 8050 is reached on 8050, not on port 80."""
    no_url_env.setenv("OAUTH_REDIRECT_URI", "http://localhost:8050/auth/callback")
    assert settings.public_url() == "http://localhost:8050"


def test_an_explicit_public_url_beats_the_oauth_host(no_url_env):
    no_url_env.setenv("OAUTH_REDIRECT_URI", "http://localhost/auth/callback")
    no_url_env.setenv("PUBLIC_URL", "https://reports.example.org")
    assert settings.public_url() == "https://reports.example.org"


def test_a_deployment_under_a_sub_path_keeps_it(no_url_env):
    no_url_env.setenv("PUBLIC_URL", "https://example.org/collaboratorium/")
    assert settings.public_url() == "https://example.org/collaboratorium"


def test_an_address_without_a_scheme_is_refused(no_url_env, caplog):
    """
    "example.org#edit/initiatives/7" is a path relative to whatever document
    the report was pasted into, so it fails exactly where this is meant to
    work. DOMAIN in the same .env is deliberately scheme-less, which makes this
    an easy way to write it, so it is refused out loud.
    """
    no_url_env.setenv("PUBLIC_URL", "collaboratorium.example.org")
    assert settings.public_url() == ""
    assert "has no scheme" in caplog.text


def test_a_scheme_less_oauth_uri_is_refused_too(no_url_env):
    no_url_env.setenv("OAUTH_REDIRECT_URI", "localhost:8050/auth/callback")
    assert settings.public_url() == ""


# --------------------------------------------------------------------------
# configure()
# --------------------------------------------------------------------------

def test_configure_overrides_the_environment(no_url_env, public_url):
    no_url_env.setenv("PUBLIC_URL", "https://reports.example.org")
    public_url("http://127.0.0.1:8050")
    assert settings.public_url() == "http://127.0.0.1:8050"


def test_the_override_can_be_handed_back_to_the_environment(no_url_env, public_url):
    """None is a value here, not a missing argument, so a caller that set an
    address can stop deciding — which is what the fixture above does."""
    no_url_env.setenv("PUBLIC_URL", "https://reports.example.org")
    public_url("http://127.0.0.1:8050")
    settings.configure(public_url_override=None)
    assert settings.public_url() == "https://reports.example.org"


def test_a_path_setting_still_ignores_none():
    """The same cannot be said of a database: there is no "no database"."""
    before = settings.get_settings().database_path
    settings.configure(database_path=None)
    assert settings.get_settings().database_path == before


def test_configure_still_rejects_unknown_settings():
    with pytest.raises(TypeError):
        settings.configure(public_uri="https://typo.example.org")


def test_the_stored_field_does_not_pose_as_the_address():
    """
    What is stored is an override, and None there means "ask the environment".
    Naming it so is the point: a reader reaching for the deployment's address
    through get_settings() finds no field quietly holding None instead.
    """
    assert not hasattr(settings.get_settings(), "public_url")


# --------------------------------------------------------------------------
# The placeholder
# --------------------------------------------------------------------------

def test_a_template_link_carries_the_deployment_address(public_url):
    public_url("https://pantograph.example.org")
    md = generate_markdown_report(LINKED_CFG, nodes())
    assert "[source](https://pantograph.example.org#edit/initiatives/7)" in md


def test_without_an_address_the_link_is_the_one_it_always_was(public_url):
    public_url("")
    md = generate_markdown_report(LINKED_CFG, nodes())
    assert "[source](#edit/initiatives/7)" in md


def test_a_caller_can_ask_for_relative_links(public_url):
    public_url("https://pantograph.example.org")
    md = generate_markdown_report(LINKED_CFG, nodes(), base_url="")
    assert "[source](#edit/initiatives/7)" in md


def test_a_column_named_base_url_does_not_redirect_the_link(public_url):
    """A schema that happens to have a base_url column must not decide where
    every link in the report points."""
    public_url("https://pantograph.example.org")
    md = generate_markdown_report(LINKED_CFG, nodes(base_url="https://elsewhere.example.com"))
    assert "(https://pantograph.example.org#edit/initiatives/7)" in md
    assert "elsewhere" not in md


def test_the_address_carries_no_provenance_note(public_url):
    """
    Every other substitution can be followed by a note saying who stood behind
    it. Inside a link target that would break the link, so the address is
    answered before that pass - which matters only for a record that really
    does carry provenance under this name, as one with its own base_url column
    would.
    """
    public_url("https://pantograph.example.org")
    context = {
        "people_map": {},
        "act_people_df": pd.DataFrame(columns=["activity_id", "person_id"]),
        "provenance_by_row": {("initiatives", 7, 1): {"base_url": SUGGESTION}},
    }
    md = generate_markdown_report(LINKED_CFG, nodes(), context=context)
    assert "(https://pantograph.example.org#edit/initiatives/7)" in md
    assert "Suggested" not in md


def test_every_level_of_the_hierarchy_can_use_it(public_url):
    public_url("https://pantograph.example.org")
    cfg = {"name": "R", "hierarchy": [{
        "type": "initiatives", "template": "{base_url}#edit/initiatives/{id}\n",
        "children": [{"type": "activities", "template": "{base_url}#edit/activities/{id}\n"}],
    }]}
    elements = nodes() + [
        {"data": {"id": "activities-3", "label": "a", "type": "activities",
                  "properties": {"id": 3, "version": 1, "name": "a"}}},
        {"data": {"source": "initiatives-7", "target": "activities-3"}},
    ]
    md = generate_markdown_report(cfg, elements)
    assert "https://pantograph.example.org#edit/initiatives/7" in md
    assert "https://pantograph.example.org#edit/activities/3" in md


def test_the_shipped_report_leaves_its_links_to_the_actions(app_config):
    """
    Not an accident worth preserving by hand: the shipped templates hold no
    link syntax at all, which is what lets `{actions}` be removed whole for the
    copied document. A template that spelled its own links could only be
    cleaned up by hunting markdown back out of the prose.
    """
    for level in _levels(app_config["reports"]["annual_report"]["hierarchy"]):
        assert "#edit/" not in level["template"]
        assert "#add/" not in level["template"]
        assert "{actions}" in level["template"]


def _levels(hierarchy):
    for level in hierarchy:
        yield level
        yield from _levels(level.get("children", []))
