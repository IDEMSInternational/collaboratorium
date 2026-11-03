"""
Links in a report lead back to the record, wherever the report ends up.

Report markdown is copied into other documents so people can go back and revise
what it was built from. A relative `#edit/...` link goes nowhere once pasted, so
templates write `{base_url}#edit/...` and the deployment says what `base_url` is.
The report shown in the app carries the same links: an absolute link to the
origin the reader is already on is still only a change of fragment, so it opens
the editor in place.
"""
import pytest
from dash import dcc
from playwright.sync_api import Page, expect

from pantograph import settings
from pantograph.report_generator import generate_markdown_report
from pantograph_explore.tab_report import register_report_callbacks

LINKED_CFG = {"name": "Register", "hierarchy": [
    {"type": "initiatives", "template": "## {name} [🔗]({base_url}#edit/initiatives/{id})\n"}]}


def nodes(**properties):
    data = {"id": 7, "version": 1, "name": "n", **properties}
    return [{"data": {"id": f"initiatives-{data['id']}", "label": data["name"],
                      "type": "initiatives", "properties": data}}]


@pytest.fixture
def public_url():
    """Set the configured public URL for one test, restoring whatever was there."""
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


def test_an_explicit_public_url_beats_the_oauth_host(no_url_env):
    no_url_env.setenv("OAUTH_REDIRECT_URI", "http://localhost/auth/callback")
    no_url_env.setenv("PUBLIC_URL", "https://reports.example.org")
    assert settings.public_url() == "https://reports.example.org"


def test_configure_overrides_the_environment(no_url_env, public_url):
    no_url_env.setenv("PUBLIC_URL", "https://reports.example.org")
    public_url("http://127.0.0.1:8050")
    assert settings.public_url() == "http://127.0.0.1:8050"

def test_the_override_can_be_handed_back_to_the_environment(no_url_env, public_url):
    """None is a value here, not a missing argument, so a caller that set an
    address can stop deciding - which is what the fixture above does."""
    no_url_env.setenv("PUBLIC_URL", "https://reports.example.org")
    public_url("http://127.0.0.1:8050")
    settings.configure(public_url_override=None)
    assert settings.public_url() == "https://reports.example.org"


def test_a_path_setting_still_ignores_none():
    """The same cannot be said of a database: there is no "no database"."""
    before = settings.get_settings().database_path
    settings.configure(database_path=None)
    assert settings.get_settings().database_path == before


def test_an_address_without_a_scheme_is_refused(no_url_env, caplog):
    """
    "example.org#edit/initiatives/7" is a path relative to whatever document
    the report was pasted into, so it fails exactly where this feature is meant
    to work. DOMAIN in the same .env is deliberately scheme-less, which makes
    this an easy way to write it, so it is refused out loud.
    """
    no_url_env.setenv("PUBLIC_URL", "collaboratorium.example.org")
    assert settings.public_url() == ""
    assert "has no scheme" in caplog.text


def test_a_scheme_less_oauth_uri_is_refused_too(no_url_env):
    no_url_env.setenv("OAUTH_REDIRECT_URI", "localhost:8050/auth/callback")
    assert settings.public_url() == ""


def test_the_oauth_fallback_keeps_the_port(no_url_env):
    """A development server on 8050 is reached on 8050, not on port 80."""
    no_url_env.setenv("OAUTH_REDIRECT_URI", "http://localhost:8050/auth/callback")
    assert settings.public_url() == "http://localhost:8050"


def test_a_deployment_under_a_sub_path_keeps_it(no_url_env):
    no_url_env.setenv("PUBLIC_URL", "https://example.org/collaboratorium/")
    assert settings.public_url() == "https://example.org/collaboratorium"


def test_the_stored_field_does_not_pose_as_the_address():
    """
    What is stored is an override, and None there means "ask the environment".
    Naming it so is the point: a reader reaching for the deployment's address
    through get_settings() finds no field quietly holding None instead.
    """
    assert not hasattr(settings.get_settings(), "public_url")


def test_configure_still_rejects_unknown_settings():
    with pytest.raises(TypeError):
        settings.configure(public_uri="https://typo.example.org")


# --------------------------------------------------------------------------
# The placeholder
# --------------------------------------------------------------------------

def test_a_template_link_carries_the_deployment_address(public_url):
    public_url("https://pantograph.example.org")
    md = generate_markdown_report(LINKED_CFG, nodes())
    assert "[🔗](https://pantograph.example.org#edit/initiatives/7)" in md


def test_without_an_address_the_link_is_the_one_it_always_was(public_url):
    public_url("")
    md = generate_markdown_report(LINKED_CFG, nodes())
    assert "[🔗](#edit/initiatives/7)" in md


def test_a_caller_can_ask_for_relative_links(public_url):
    public_url("https://pantograph.example.org")
    md = generate_markdown_report(LINKED_CFG, nodes(), base_url="")
    assert "[🔗](#edit/initiatives/7)" in md


def test_a_column_named_base_url_does_not_redirect_the_link(public_url):
    """A schema that happens to have a base_url column must not decide where
    every link in the report points."""
    public_url("https://pantograph.example.org")
    md = generate_markdown_report(LINKED_CFG, nodes(base_url="https://elsewhere.example.com"))
    assert "(https://pantograph.example.org#edit/initiatives/7)" in md
    assert "elsewhere" not in md


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


def test_the_shipped_report_links_are_absolute(app_config):
    linked = [l for l in _levels(app_config["reports"]["annual_report"]["hierarchy"])
              if "#edit/" in l["template"]]
    # Counted, because "every link is absolute" is also true of no links.
    assert len(linked) == 2
    for level in linked:
        assert "({base_url}#edit/" in level["template"]


def _levels(hierarchy):
    for level in hierarchy:
        yield level
        yield from _levels(level.get("children", []))


# --------------------------------------------------------------------------
# The Report tab
# --------------------------------------------------------------------------

class _CapturingApp:
    def callback(self, *args, **kwargs):
        def keep(fn):
            self.fn = fn
            return fn
        return keep


def _find(component, kind):
    if isinstance(component, kind):
        yield component
    children = getattr(component, "children", None)
    for child in children if isinstance(children, list) else [children]:
        if child is not None and not isinstance(child, str):
            yield from _find(child, kind)


def test_what_is_shown_and_what_is_copied_are_one_report(public_url):
    """
    Rendered once, so the two cannot disagree. Two renders meant two
    independent reads of the database, and a write landing between them left
    the page and the clipboard describing different data.
    """
    public_url("https://pantograph.example.org")
    app = _CapturingApp()
    register_report_callbacks(app, {"reports": {"r": LINKED_CFG}})
    rendered = app.fn(nodes())

    copied = next(_find(rendered, dcc.Clipboard)).content
    shown = next(_find(rendered, dcc.Markdown)).children
    assert "(https://pantograph.example.org#edit/initiatives/7)" in copied
    assert shown == copied


def test_clicking_a_report_link_opens_the_editor_in_place(page: Page, live_server, public_url):
    """
    With the address set to this very server the link is absolute, and still
    opens the editor on the page rather than loading the app again: same
    origin, so following it only changes the fragment. That is what lets the
    shown report carry the same links as the copied one.
    """
    public_url(live_server)
    page.goto("/")
    page.locator("#nav-explore").click()
    page.locator(".nav-link", has_text="Report").click()

    link = page.locator("#report-container a[href*='#edit/']").first
    expect(link).to_be_visible(timeout=20000)
    # Absolute, or this proves nothing about base_url.
    assert link.get_attribute("href").startswith(live_server)
    page.evaluate("() => { window.__notReloaded = true; }")
    link.click()

    expect(page.locator("#editor-popup")).to_be_visible()
    expect(page.locator("#form-heading")).to_contain_text("Edit", timeout=10000)
    assert page.evaluate("() => window.__notReloaded === true")
