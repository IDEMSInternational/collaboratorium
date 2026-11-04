"""
handoff.py
Assembling the bundle a person hands to a local agent.

Four files, because none of them should have to be reconstructed by hand:
the contract (the shape), the snapshot (the contents), the instructions (how to
write a proposal), and the rejections (what not to propose again). See
docs/agentic-ingest.md §2.

Kept separate from the Flask route so the bundle can be built and asserted
about without a request, and so a CLI could write one to disk.

The instructions are generated rather than stored as a file in `assets/`, for
the same reason the contract is derived: a copy drifts. What they point *at* is
version-controlled — the format spec and the design document — and what they
state here is only what this deployment's own numbers make true.
"""
import io
import json
import zipfile
from datetime import datetime, timezone

import yaml

from pantograph import contract, snapshot

BUNDLE_FORMAT = "collaboratorium-handoff/1"

REJECTIONS_FORMAT = "collaboratorium-rejections/1"

# Where a producer reads the format from. Pinned by path rather than by commit
# because the repository is the authority and the hash below is what detects
# drift; a URL with a commit in it goes stale in the opposite direction.
_FORMAT_DOC = "docs/agentic-ingest.md"
_REPO = "https://github.com/IDEMSInternational/collaboratorium"


def _instructions(config, contract_doc, snapshot_doc):
    """The README a producer reads first."""
    counts = snapshot_doc.get("counts", {})
    omitted = snapshot_doc.get("omitted_elements", [])
    # Grouped by reason rather than listed per element: the same sentence
    # repeated once per table reads as five problems instead of one rule.
    by_reason = {}
    for table, table_doc in contract_doc["tables"].items():
        for element_id, element in table_doc["elements"].items():
            if element.get("accepts_suggestions") is False:
                by_reason.setdefault(
                    element["refused_because"], []).append(f"{table}.{element_id}")
    inventory = "\n".join(
        f"| `{name}` | {count} |" for name, count in counts.items()
    )
    refused_list = "\n".join(
        f"- {', '.join('`' + name + '`' for name in sorted(names))}\n  — {reason}"
        for reason, names in sorted(by_reason.items())
    )
    return f"""# Proposing records for {contract_doc.get("deployment") or "this deployment"}

This bundle is everything you need to draft records for a human to review. It
was exported at {contract_doc["exported_at"]} against config
`{contract_doc["config_hash"]}`.

    contract.json     the shape: tables, elements, types, required, choices
    snapshot.yaml     the contents: current records and links, latest version only
    rejections.yaml   proposals a human has already declined
    instructions.md   this file

## What you are producing

One YAML file in the `{contract.SUGGESTIONS_FORMAT}` format. Its shape is
specified in [`{_FORMAT_DOC}`]({_REPO}/blob/main/{_FORMAT_DOC}) §3 — read that
before writing one. The essentials:

- **Nothing you write becomes a record.** Every value you propose arrives
  marked as suggested and unconfirmed, and a person confirms it field by field
  before it is saved. Draft accordingly: a confident guess costs someone a
  correction, and a flagged uncertainty costs them a glance.
- **Never predict an id.** New records refer to each other by a local `key`.
  Ids are allocated on save.
- **Refer to existing records by `{{id, expect}}`**, where `expect` is the
  record's current name. A wrong id then fails validation instead of quietly
  editing something else.
- **Carry a stable `source_ref`** anchored on the evidence — a repository URL,
  a document id — and never on the date you ran. Re-running must produce the
  same refs, or every run duplicates its predecessor and no rejection sticks.
- **Score placement separately from values.** A record's `kind` (activity or
  initiative) and its parents are the things people actually correct, so give
  them their own confidence rather than burying the doubt in a note.
- **Declare your coverage**, and put the explanation in each entry's `note`
  rather than in a YAML comment beside it. Comments do not survive parsing, so
  a caveat written as a comment reaches nobody. A gap nobody mentioned reads as
  an absence of activity. Only a source whose evidence stops before the end of
  the period is reported, so listing one that ran to the last day costs a
  reader nothing and says what you looked at.
- **Write to the target length, not to the top of a range.** The style guide
  gives a target for each description; records half as long again as the ones
  already here read as imported rather than written.
- **Expect the structured part of a source to be the wrong part.** A tidy list
  of "activities" in a report or a changelog is, in practice, usually a list of
  long-running strands — which is the table already full. The activities you are
  here for tend to be sentences inside the prose around it. Read both.
- **Match before you create.** Check every name you would create against
  `snapshot.yaml` first, and propose an `update` or a link instead where it is
  already there under a shorter or differently-phrased name — `R-Instat` rather
  than `Development of R-Instat`. The import flags likely matches, but a
  duplicate that reaches review has already cost someone the comparison.

## This deployment, as exported

| table | current records |
| --- | --- |
{inventory}

Target `activities` and `initiatives`. The other tables are described in the
contract because they exist, not because a proposal should create them: people,
organisations and contracts are identities and agreements that someone
establishes deliberately, so refer to them, do not invent them.

Activities are the sparse table and the reason this path exists. Note from the
counts how much thinner they are than initiatives — and that most of what is
already there has no location and often no dates, so a record you cannot fully
date is not a worse record than the ones already in here.

## What this bundle does not contain

Values omitted from the snapshot: {", ".join(f"`{name}`" for name in omitted) or "none"}.
They are withheld rather than empty, so do not read a missing one as a gap to
fill.

Elements the format refuses, which validation will reject:

{refused_list or "- none"}

## Checking your work before you hand it over

Validate against `contract.json`: every element you set exists, every required
element is present, every `{{id, expect}}` pair matches a record in
`snapshot.yaml`, and no value names a choice that is not in the vocabulary. The
import will check all of this and name what failed, but finding it here costs
nobody else's time.

If the deployment's config has changed since this bundle was exported, the
import warns rather than refusing — the hash above is what makes that possible.
"""


def _rejections(config):
    """
    Proposals a human has declined, so a producer does not send them again.

    Read from the staging table. Present and empty when nobody has declined
    anything, because an absent file is indistinguishable from "nothing was
    ever rejected".

    The name and table travel with the ref, not just the ref itself. A producer
    that can see *what* was turned down can avoid proposing the same thing
    re-phrased under a new ref, which is the hole a bare list of identifiers
    leaves wide open.
    """
    from pantograph import staging

    return {
        "format": REJECTIONS_FORMAT,
        "config_hash": contract.config_hash(config),
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rejected": staging.rejections(),
        "note": ("Do not propose these again. Each was staged and turned down "
                 "by a person. Re-sending one under the same source_ref is "
                 "dropped rather than re-queued; re-sending the same thing "
                 "under a new ref wastes a reviewer's time."),
    }


def build(config):
    """
    The bundle's files, as `{filename: text}`.

    Returned as text rather than written, so a test can read one and the route
    can zip them without a temporary directory.
    """
    contract_doc = contract.build(config)
    snapshot_doc = snapshot.build(config)
    return {
        "contract.json": json.dumps(contract_doc, indent=2) + "\n",
        "snapshot.yaml": yaml.safe_dump(snapshot_doc, sort_keys=False,
                                        allow_unicode=True,
                                        default_flow_style=False, width=100),
        "rejections.yaml": yaml.safe_dump(_rejections(config), sort_keys=False,
                                          allow_unicode=True),
        "instructions.md": _instructions(config, contract_doc, snapshot_doc),
    }


def short_hash(config):
    """The config hash as it appears in the bundle's filename."""
    return contract.config_hash(config).removeprefix("sha256:")[:12]


def filename(config):
    return f"collaboratorium-handoff-{short_hash(config)}.zip"


def zip_bytes(config):
    """The bundle as a zip, ready to send."""
    buffer = io.BytesIO()
    # A fixed member date rather than "now", so the archive's metadata does not
    # record when someone pressed the button. The files themselves still carry
    # an `exported_at`, so two bundles of identical contents are not identical
    # bytes; the config hash in the filename is what identifies a bundle.
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in build(config).items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()
