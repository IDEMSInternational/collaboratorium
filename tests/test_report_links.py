"""
Links in a report lead back to the record, wherever the report ends up.

Report markdown is copied into other documents so people can go back and revise
what it was built from. A relative `#edit/...` link goes nowhere once pasted, so
templates write `{base_url}#edit/...` and the deployment says what `base_url` is.
Inside the app the shown report keeps relative links, because the editor opens
from a hash change on the current page.
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
    before = settings.get_settings()

    def set_to(value):
        settings.configure(public_url=value)

    yield set_to
    settings._settings = before


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
    for level in _levels(app_config["reports"]["annual_report"]["hierarchy"]):
        if "#edit/" in level["template"]:
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


def test_the_copied_markdown_is_absolute_and_the_shown_one_relative(public_url):
    public_url("https://pantograph.example.org")
    app = _CapturingApp()
    register_report_callbacks(app, {"reports": {"r": LINKED_CFG}})
    rendered = app.fn(nodes())

    copied = next(_find(rendered, dcc.Clipboard)).content
    shown = next(_find(rendered, dcc.Markdown)).children
    assert "(https://pantograph.example.org#edit/initiatives/7)" in copied
    assert "(#edit/initiatives/7)" in shown


def test_clicking_a_report_link_opens_the_editor_in_place(page: Page, live_server, public_url):
    """With the address set to this very server, the link still opens the
    editor on the page rather than loading the app again."""
    public_url(live_server)
    page.goto("/")
    page.locator("#nav-explore").click()
    page.locator(".nav-link", has_text="Report").click()

    link = page.locator("#report-container a[href*='#edit/']").first
    expect(link).to_be_visible(timeout=20000)
    page.evaluate("() => { window.__notReloaded = true; }")
    link.click()

    expect(page.locator("#editor-popup")).to_be_visible()
    expect(page.locator("#form-heading")).to_contain_text("Edit", timeout=10000)
    assert page.evaluate("() => window.__notReloaded === true")
