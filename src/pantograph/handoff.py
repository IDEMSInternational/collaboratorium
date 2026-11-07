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
from importlib import resources

import yaml

from pantograph import contract, snapshot

BUNDLE_FORMAT = "collaboratorium-handoff/1"

REJECTIONS_FORMAT = "collaboratorium-rejections/1"

# The two documents a producer must read, shipped *inside* the bundle. They used
# to be linked on GitHub, which fails twice: a producer with no network access to
# the repository (a chat model, say) cannot follow a link at all, and a link to a
# path on `main` is a 404 until the branch that adds it has merged. A bundle that
# has to be supplemented from elsewhere is a bundle that gets used without them.
_PRODUCER_DOCS = ("suggestions-format.md", "record-style-guide.md")


def _producer_docs():
    """`{filename: text}` for the documents that travel with the bundle."""
    root = resources.files("pantograph") / "producer_docs"
    return {name: (root / name).read_text(encoding="utf-8")
            for name in _PRODUCER_DOCS}


def _tag_summary(config):
    """
    The tag categories as they stand, and which of them take a proposal.

    Read from the vocabulary rather than from the contract, because a category
    is only named in the row — the contract can say where the terms live and
    nothing more. Without this a producer would learn that a category refuses
    proposals by having one dropped.
    """
    from pantograph import staging

    vocabulary = staging.tag_vocabulary(config)
    if not vocabulary:
        return ("This deployment has no tag groups, so leave `tags` out "
                "entirely — there is nothing to choose from.")

    lines = []
    for group_id, key_values in sorted(vocabulary.items()):
        for category, definition in (key_values or {}).items():
            if not isinstance(definition, dict):
                continue
            options = definition.get(definition.get("list_name")) or {}
            label = definition.get("label") or category
            count = len(options) if isinstance(options, dict) else 0
            if definition.get("producer") is False:
                why = definition.get("producer_note") or "not open to proposals"
                lines.append(f"- `{category}` — {label}, {count} terms. "
                             f"**Do not set this one**: {why}.")
            else:
                lines.append(f"- `{category}` — {label}, {count} terms.")

    return (
        "\n".join(lines)
        + "\n\nThe terms themselves are in `snapshot.yaml` under the tag-group "
          "rows, as `{key: label}` per category. Write the label. What each "
          "term *means* is in the style guide, and several are not what they "
          "sound like — read the definitions, not the labels."
    )


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
    tag_summary = _tag_summary(config)
    return f"""# Proposing records for {contract_doc.get("deployment") or "this deployment"}

This bundle is everything you need to draft records for a human to review. It
was exported at {contract_doc["exported_at"]} against config
`{contract_doc["config_hash"]}`.

    instructions.md          this file: read it first
    suggestions-format.md    the file you will write: its shape, with an example
    record-style-guide.md    how each field should read, and what every tag means
    contract.json            the shape of the database: tables, elements, required
    snapshot.yaml            the contents: current records and links, latest version
    rejections.yaml          proposals a human has already declined

## What you are producing

One YAML file in the `{contract.SUGGESTIONS_FORMAT}` format, and no other
version: write `format: {contract.SUGGESTIONS_FORMAT}` on its first line. Read
`suggestions-format.md` in this bundle before writing one, and
`record-style-guide.md` before writing any description — both are short and both
are in the folder you were given, so you do not need to look anything up. The
essentials:

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
- **Keep scan facts out of an initiative's description.** Commit counts, date
  ranges, issue and version numbers and phrases like "in what was scanned"
  describe your search, not the work, and go stale. Put them in an activity or in
  `inferred:`/`coverage`.
- **Write descriptions to the length the style guide gives**, which depends on
  how large the initiative is. A thin description is the commonest failure of a
  producer working from commit messages: say what the thing is, who it serves,
  what has been done and where it stands.
- **Tag from the vocabulary in the snapshot, not from memory, and by definition
  rather than by label.** The terms are rows, so they change without this bundle
  changing; read them from `snapshot.yaml` and write the label. Every term is
  defined in `record-style-guide.md`, and several are not what they sound like:
  read the definition before you choose. Four to six across all categories
  together, which is meant to force a choice.
  Propose every category you can, including the strategic one, but declare each
  tag you are not sure of under `inferred: tags:` with your reason — an
  unconfirmed guess a person can correct is useful, and a confident wrong one is
  not.
- **A repository is an initiative. Only its large, overarching issues are
  activities, never every issue.** Someone is ultimately responsible for a
  repository, which is what makes it an initiative. Inside it, a goal-level
  issue or milestone that holds a large body of other issues beneath it is one
  activity of its own; the ordinary issues, pull requests and commits under it
  are the detail of that activity, to be summarised in its description rather
  than listed as records. A repository with forty small issues has a handful of
  activities, not forty. Follow links: an issue that references another
  repository, a project board or a document tells you about work the person is
  connected to that you have not yet looked at.
- **Attach the evidence to an activity.** Each activity can carry `attachments:`,
  a list of `{{name, url}}`: the release, pull request, issue or document it
  summarises. They are added to what is already recorded, never replacing it. An
  activity with sources and no attachments is missing the part a reader opens
  first.
- **Expect the structured part of a source to be the wrong part.** A tidy list
  of "activities" in a report or a changelog is, in practice, usually a list of
  long-running strands — which is the table already full. The activities you are
  here for tend to be sentences inside the prose around it. Read both.
- **Match before you create.** Check every name you would create against
  `snapshot.yaml` first, and propose an `update` or a link instead where it is
  already there under a shorter or differently-phrased name — `R-Instat` rather
  than `Development of R-Instat`. The import flags likely matches, but a
  duplicate that reaches review has already cost someone the comparison.

## Where to look

The person has told you to scan their work; they have not told you where it
lives, and they should not have to. Look in every place you can reach, and say
in `coverage` which ones you did and did not:

- **Code hosts.** Every GitHub organisation and Forgejo/Gitea instance they work
  in (for IDEMS, `github.com/IDEMSInternational` and `git.idems.international`):
  repositories they own or contribute to, their commits and pull requests, the
  issues assigned to or opened by them, milestones, releases and READMEs. Read
  the issues as well as the code; goals and decisions are written there.
- **Shared drive.** Documents they own or edited recently: reports, proposals,
  meeting notes, design documents, spreadsheets. A document's title and opening
  paragraph often name the initiative it belongs to.
- **Publications and media.** Podcast episodes, articles, papers, talks and
  newsletters they appear in or wrote, which are activities and sometimes
  initiatives in their own right.
- **Calendar, email and chat**, if you can reach them: meetings, visits and
  workshops leave no commit, and are exactly the activities a code-only scan
  misses.
- **Anything linked from what you find.** Issues, documents and calendar entries
  point at repositories, boards, folders and other people's work. Follow them
  one step.

Do not stop at the first source that returns something. A scan that found three
documents and no repositories has not scanned; it has sampled. If a source
cannot be reached, say so in `coverage`, with the reason, rather than leaving a
silent gap that reads as an absence of activity.

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

## Tag categories in this deployment

{tag_summary}

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
        **_producer_docs(),
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
