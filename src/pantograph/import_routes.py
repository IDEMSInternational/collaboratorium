"""
import_routes.py
Uploading a suggestions file, and the queue of what it staged.

Two pages and a deliberate two-step: an upload is **checked and reported on**
before anything is staged, and staging happens only when the person says so.
The report is the product here — a file's errors, its warnings and, above all,
the records that probably name something that already exists.

Nothing on these pages writes a record. A staged suggestion is opened in the
ordinary editor through `#suggest/<id>`, where the values arrive marked
unconfirmed and a person confirms them field by field. See
docs/agentic-ingest.md §4.
"""
import secrets

from flask import render_template_string, request, session, redirect, url_for

from pantograph import contract, staging, suggestions
from pantograph.auth import login_required
from pantograph.config import load_config
from pantograph.db import get_person_id_for_user
from pantograph.settings import get_settings

_STYLE = """
  body { font-family: "Segoe UI", sans-serif; margin: 40px; background: #f4f6f8; color: #212529; }
  .card { background: #fff; padding: 25px; border-radius: 8px; border: 1px solid #dee2e6; max-width: 900px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 20px; }
  .btn { background: #f28b20; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: bold; font-size: 1em; }
  .btn:hover { background: #d97b1a; }
  .btn.secondary { background: #6c757d; }
  .btn.secondary:hover { background: #5a6268; }
  textarea { width: 100%; min-height: 260px; font-family: ui-monospace, Consolas, monospace; font-size: 0.85em; border: 1px solid #ced4da; border-radius: 4px; padding: 10px; }
  code { background: #f1f3f5; padding: 2px 5px; border-radius: 4px; }
  .finding { padding: 10px 14px; border-radius: 4px; margin: 8px 0; border-left: 4px solid; }
  .error { background: #fdf2f2; border-color: #dc3545; }
  .warning { background: #fff8ef; border-color: #f28b20; }
  .advisory { background: #f2f7fd; border-color: #2d7dd2; }
  .where { font-family: ui-monospace, Consolas, monospace; font-size: 0.82em; color: #6c757d; display: block; }
  .count { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.85em; font-weight: bold; margin-right: 8px; }
  .c-error { background: #dc3545; color: #fff; }
  .c-warning { background: #f28b20; color: #fff; }
  .c-advisory { background: #2d7dd2; color: #fff; }
  .c-ok { background: #28a745; color: #fff; }
  table { border-collapse: collapse; width: 100%; margin: 10px 0; }
  td, th { border-bottom: 1px solid #dee2e6; padding: 7px 10px; text-align: left; font-size: 0.92em; vertical-align: top; }
  th { background: #f8f9fa; }
  .muted { color: #6c757d; font-size: 0.9em; }
  .group { border: 1px solid #2d7dd2; border-radius: 6px; padding: 12px; margin: 14px 0; background: #fbfdff; }
  h3 { margin-top: 26px; }
  hr { border: 0; border-top: 1px solid #dee2e6; margin: 22px 0; }
"""

_UPLOAD = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Import suggestions</title><style>""" + _STYLE + """</style></head><body>
<div class="card">
  <h2>Import suggestions</h2>
  <p>Paste the YAML your agent produced, or upload the file. Nothing is saved
  until you have seen what it would do &mdash; and even then, a staged
  suggestion only becomes a record when you confirm its fields in the editor.</p>
  <p class="muted">Format: <code>{{ fmt }}</code> &middot; forms
  <code>{{ config_hash }}</code> &middot;
  <a href="/handoff">get a handoff bundle</a> &middot;
  <a href="/import/queue">review queue{% if pending %} ({{ pending }}){% endif %}</a></p>
  <form method="post" enctype="multipart/form-data">
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    <input type="hidden" name="step" value="check">
    <textarea name="text" placeholder="format: {{ fmt }}&#10;activities:&#10;  - name: ..."></textarea>
    <p><input type="file" name="file" accept=".yaml,.yml,.txt"></p>
    <button type="submit" class="btn">Check it</button>
  </form>
</div></body></html>
"""

_REPORT = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Import report</title><style>""" + _STYLE + """</style></head><body>
<div class="card">
  <h2>Import report</h2>
  <p>
    {% if errors %}<span class="count c-error">{{ errors|length }} error{{ 's' if errors|length != 1 }}</span>{% endif %}
    {% if warnings %}<span class="count c-warning">{{ warnings|length }} warning{{ 's' if warnings|length != 1 }}</span>{% endif %}
    {% if advisories %}<span class="count c-advisory">{{ advisories|length }} to look at</span>{% endif %}
    <span class="count c-ok">{{ stageable|length }} ready</span>
  </p>
  {% if blocked %}
  <p>{{ blocked|length }} record{{ 's' if blocked|length != 1 }} cannot be staged
  until the file is fixed. The rest can be staged now &mdash; fixing and
  re-uploading will not duplicate them, as long as they carry a
  <code>source_ref</code>.</p>
  {% endif %}

  {% if errors %}<h3>Errors</h3>
    {% for f in errors %}<div class="finding error"><span class="where">{{ f.where }}</span>{{ f.message }}</div>{% endfor %}
  {% endif %}

  {% if advisories %}<h3>Worth a look before you stage</h3>
    {% for f in advisories %}<div class="finding advisory"><span class="where">{{ f.where }}</span>{{ f.message }}</div>{% endfor %}
  {% endif %}

  {% if warnings %}<h3>Warnings</h3>
    {% for f in warnings %}<div class="finding warning"><span class="where">{{ f.where }}</span>{{ f.message }}</div>{% endfor %}
  {% endif %}

  <h3>What would be staged</h3>
  <table>
    <tr><th>Table</th><th>Action</th><th>Name</th><th>Links</th><th>Inferred</th></tr>
    {% for r in stageable %}
    <tr><td>{{ r.table }}</td><td>{{ r.action }}</td><td>{{ r.name }}</td>
      <td class="muted">{% for e, ids in r.links.items() %}{{ e.lstrip('@') }}: {{ ids|length }}<br>{% endfor %}</td>
      <td class="muted">{{ r.inferred.keys()|join(', ') }}</td></tr>
    {% endfor %}
  </table>

  <hr>
  <form method="post">
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    <input type="hidden" name="step" value="stage">
    <button type="submit" class="btn" {{ 'disabled' if not stageable }}>Stage {{ stageable|length }} for review</button>
    <a href="/import" class="btn secondary">Start again</a>
  </form>
</div></body></html>
"""

_STAGED = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Staged</title><style>""" + _STYLE + """</style></head><body>
<div class="card">
  <h2>Staged</h2>
  <p><span class="count c-ok">{{ report.staged|length }} staged</span>
  {% if report.already %}<span class="count c-warning">{{ report.already|length }} already here</span>{% endif %}
  {% if report.declined %}<span class="count c-warning">{{ report.declined|length }} previously declined</span>{% endif %}
  {% if report.grouped %}<span class="count c-advisory">{{ report.grouped|length }} grouped with a colleague's</span>{% endif %}
  </p>
  {% if report.already %}<p class="muted">Records already staged from an earlier
  upload were left alone, which is what makes importing the same file twice
  harmless.</p>{% endif %}
  {% if report.declined %}<p class="muted">Records someone has already turned
  down were dropped rather than re-queued.</p>{% endif %}
  <p><a href="/import/queue" class="btn">Go to the review queue</a>
  <a href="/import" class="btn secondary">Import another</a></p>
</div></body></html>
"""

_QUEUE = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Review queue</title><style>""" + _STYLE + """</style></head><body>
<div class="card">
  <h2>Review queue</h2>
  <p class="muted">{{ total }} awaiting review &middot;
  <a href="/import">import more</a> &middot; <a href="/">back to the app</a></p>
  <p>Opening one puts its values in the ordinary form, marked as not yet stood
  behind. Confirm the fields you accept and save; that save is what creates the
  record.</p>
</div>
{% for key, items in groups.items() %}
<div class="card {{ 'group' if items|length > 1 }}">
  {% if items|length > 1 %}
  <h3 style="margin-top:0">{{ items|length }} people proposed the same thing</h3>
  <p>These arrived from different evidence, so they could not be deduplicated.
  Keep whichever record reads best and decline the others &mdash; then link
  everyone to the survivor. Link lists are added to and never replaced, so
  nobody's contribution is lost by accepting someone else's wording.</p>
  {% endif %}
  <table>
    <tr><th>Name</th><th>Table</th><th>From</th><th>Inferred</th><th></th></tr>
    {% for item in items %}
    <tr>
      <td><strong>{{ item.name }}</strong>
        {% if item.payload.values.description %}
        <div class="muted">{{ item.payload.values.description[:220] }}{{ '…' if item.payload.values.description|length > 220 }}</div>
        {% endif %}
      </td>
      <td>{{ item.table }}<br><span class="muted">{{ item.action }}</span></td>
      <td>{{ item.subject or '—' }}<br><span class="muted">{{ item.run_id or '' }}</span></td>
      <td class="muted">
        {% for element, why in (item.payload.inferred or {}).items() %}<div><code>{{ element }}</code> {{ why }}</div>{% endfor %}
      </td>
      <td style="white-space:nowrap">
        {% if item.waiting %}
        <span class="muted">waiting on
          {% for element, keys in item.waiting.items() %}<code>{{ keys|join(', ') }}</code>{% endfor %}</span><br>
        {% endif %}
        <a class="btn" href="/import/open/{{ item.id }}">Open</a>
        <form method="post" action="/import/decline" style="display:inline">
          <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
          <input type="hidden" name="id" value="{{ item.id }}">
          <button type="submit" class="btn secondary">Decline</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </table>
</div>
{% endfor %}
{% if not groups %}<div class="card"><p>Nothing awaiting review.</p></div>{% endif %}
</body></html>
"""


def _csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def _check_csrf():
    expected = session.get("csrf_token")
    return bool(expected) and request.form.get("csrf_token") == expected


def _config():
    return load_config(get_settings().config_path)


def _uploaded_text():
    """The pasted text, or the uploaded file's contents if one was given."""
    uploaded = request.files.get("file")
    if uploaded and uploaded.filename:
        raw = uploaded.read()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            # Always UTF-8 and never the platform default, for the reason
            # config.py carries the scar of: a YAML file written on Windows
            # holding an em dash is undecodable as cp1252 elsewhere.
            return raw.decode("utf-8", errors="replace")
    return request.form.get("text") or ""


def register_import_routes(server):

    @server.route("/import", methods=["GET", "POST"])
    @login_required
    def import_page():
        config = _config()

        if request.method == "GET":
            return render_template_string(
                _UPLOAD, csrf_token=_csrf(), fmt=suggestions.FORMAT,
                config_hash=contract.config_hash(config),
                pending=staging.counts().get(staging.PENDING, 0))

        if not _check_csrf():
            return "CSRF token missing or invalid.", 400

        staging_step = request.form.get("step") == "stage"

        # The file is carried between the two steps in the session rather than
        # in a hidden field. A hidden input meant the YAML was escaped into an
        # HTML attribute and read back out, which double-escaped it — Jinja
        # autoescapes what `html.escape` had already escaped — so the staging
        # step re-parsed mangled text and silently staged nothing. There is no
        # safe amount of escaping for a multi-line document in an attribute;
        # the right answer is not to put it there.
        text = session.get("import_text", "") if staging_step else _uploaded_text()
        if not text.strip():
            return redirect(url_for("import_page"))

        proposal = suggestions.check(
            text, contract.build(config), staging.current_names(config),
            staging.pending_rows(), vocabulary=staging.tag_vocabulary(config))

        if staging_step:
            person_id = get_person_id_for_user(session.get("user"))
            report = staging.stage(proposal, person_id)
            session.pop("import_text", None)
            return render_template_string(_STAGED, report=report)

        session["import_text"] = text
        return render_template_string(
            _REPORT, csrf_token=_csrf(),
            errors=proposal.errors, warnings=proposal.warnings,
            advisories=proposal.advisories, stageable=proposal.stageable,
            blocked=[r for r in proposal.records if r.blocked])

    @server.route("/import/queue")
    @login_required
    def import_queue():
        grouped = staging.groups()
        keys = staging.resolved_keys()
        for items in grouped.values():
            for item in items:
                item["waiting"] = staging.unresolved_links(item, keys)

        # Initiatives first, then whatever is ready, then whatever is waiting on
        # something else. An activity cannot be saved without an initiative to
        # link it to, so a queue that offers them in file order sends the
        # reviewer to a form whose submit button will not enable.
        order = {"initiatives": 0, "contracts": 1, "activities": 2}
        ordered = dict(sorted(
            grouped.items(),
            key=lambda entry: (
                any(item["waiting"] for item in entry[1]),
                min(order.get(item["table"], 9) for item in entry[1]),
                -len(entry[1]),
            )))
        return render_template_string(
            _QUEUE, groups=ordered, csrf_token=_csrf(),
            total=sum(len(items) for items in ordered.values()))

    @server.route("/import/open/<int:suggestion_id>")
    @login_required
    def import_open(suggestion_id):
        """
        Hand the reviewer the form for a suggestion, remembering which one.

        The remembering is what lets a successful save mark the suggestion
        answered; see `staging.note_saved`. It is a redirect rather than a link
        straight to the hash so that this happens server-side, where the
        session is.
        """
        item = staging.get(suggestion_id)
        if not item or item["state"] != staging.PENDING:
            return redirect(url_for("import_queue"))
        session["reviewing_suggestion"] = (suggestion_id, item["table"])
        return redirect(f"/#suggest/{suggestion_id}")

    @server.route("/import/decline", methods=["POST"])
    @login_required
    def import_decline():
        if not _check_csrf():
            return "CSRF token missing or invalid.", 400
        try:
            suggestion_id = int(request.form["id"])
        except (KeyError, ValueError):
            return "No suggestion named.", 400
        staging.resolve(suggestion_id, staging.DECLINED,
                        get_person_id_for_user(session.get("user")))
        return redirect(url_for("import_queue"))
