"""
handoff_routes.py
The page a person uses to hand this deployment's shape and contents to an agent.

`login_required` and nothing more. The decision and its reasoning are in
docs/agentic-ingest.md §2.4: access to the whole application is already
restricted by email domain, and the Explore spreadsheet already builds a grid
column from every column of every node table, so gating this by role would gate
data the same user reads a click away. What is new is that a bundle *leaves*,
and the answer to that is minimisation — the snapshot withholds email
addresses — plus saying so on the page.

Deliberately a Flask route rather than a Dash page: it serves a file and a
paragraph, it needs no callbacks, and `/admin/maintenance` already establishes
the pattern for "an authenticated page that hands you a download".
"""
from flask import render_template_string, send_file, session
import io

from pantograph import contract, handoff, snapshot
from pantograph.auth import login_required
from pantograph.config import load_config
from pantograph.settings import get_settings

_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Agent handoff</title>
  <style>
    body { font-family: "Segoe UI", sans-serif; margin: 40px; background: #f4f6f8; color: #212529; }
    .card { background: #fff; padding: 25px; border-radius: 8px; border: 1px solid #dee2e6; max-width: 720px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .btn { background: #f28b20; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: bold; }
    .btn:hover { background: #d97b1a; }
    code, pre { background: #f1f3f5; border-radius: 4px; }
    code { padding: 2px 5px; }
    pre { padding: 12px; overflow-x: auto; border: 1px solid #dee2e6; }
    .notice { border-left: 4px solid #f28b20; background: #fff8ef; padding: 12px 15px; margin: 20px 0; }
    table { border-collapse: collapse; margin: 10px 0; }
    td, th { border: 1px solid #dee2e6; padding: 5px 12px; text-align: left; }
    hr { border: 0; border-top: 1px solid #dee2e6; margin: 22px 0; }
    .muted { color: #6c757d; font-size: 0.9em; }
  </style>
</head>
<body>
  <div class="card">
    <h2>Agent handoff</h2>
    <p>Hand this deployment's shape and current contents to a local agent, so it
    can draft records from evidence this site cannot see &mdash; your repository
    activity, your documents, your notes. You review what it proposes, then
    bring the result back to Import.</p>
    <p class="muted">Signed in as <strong>{{ email }}</strong>.</p>

    <hr>

    <h3>1. Download the bundle</h3>
    <p>Four files: the contract (what the forms accept), a snapshot of current
    records, the instructions an agent reads first, and the list of proposals
    already declined.</p>
    <p><a href="/handoff/bundle" class="btn">Download {{ filename }}</a></p>
    <table>
      <tr><th>Records</th><th></th></tr>
      {% for name, count in counts.items() %}<tr><td><code>{{ name }}</code></td><td>{{ count }}</td></tr>
      {% endfor %}
    </table>
    <p class="muted">Config <code>{{ config_hash }}</code>. A proposal drafted
    against this bundle stays checkable after the forms change.</p>

    <h3>2. Start your agent with this</h3>
    <p>Unzip the bundle, then give your local session one line:</p>
    <pre>Read instructions.md in this folder, then propose Collaboratorium records for my work since &lt;date&gt;.</pre>
    <p>The instructions in the bundle are the authority on the format; they
    point back to this repository for the full specification.</p>

    <h3>3. Review, then import</h3>
    <p>Read the YAML it writes and correct it &mdash; renaming, re-parenting and
    promoting an activity to an initiative are all far easier there than here.
    Then paste it into Import, which validates before anything is staged, and
    confirm the values field by field.</p>

    <div class="notice">
      <strong>A bundle is a copy that leaves.</strong> It holds your colleagues'
      names and what they worked on, as of now, and once downloaded this site
      can neither see it nor withdraw it. Email addresses are left out, because
      an agent needs to identify a person and never to contact one. Everything
      else in it is what you can already read on the Explore page &mdash; but on
      your laptop, and in whatever you show it.
    </div>

    <hr>
    <a href="/" style="color: #6c757d; text-decoration: none;">&larr; Back to Application</a>
  </div>
</body>
</html>
"""


def register_handoff_routes(server):

    @server.route("/handoff")
    @login_required
    def handoff_page():
        user = session.get("user") or {}
        config = load_config(get_settings().config_path)
        # Recomputed rather than cached: the counts and the hash on the page
        # have to be the ones the download will carry, and building them again
        # is cheaper than holding a bundle nobody may ask for.
        return render_template_string(
            _PAGE,
            email=user.get("email"),
            filename=handoff.filename(config),
            config_hash=contract.config_hash(config),
            counts=snapshot.build(config)["counts"],
        )

    @server.route("/handoff/bundle")
    @login_required
    def handoff_bundle():
        config = load_config(get_settings().config_path)
        return send_file(
            io.BytesIO(handoff.zip_bytes(config)),
            mimetype="application/zip",
            as_attachment=True,
            download_name=handoff.filename(config),
        )
