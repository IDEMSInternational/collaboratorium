"""
suggestions.py
Reading, checking and resolving an uploaded `collaboratorium-suggestions/0.3`
file. The format is specified in docs/suggestions-format.md.

Nothing here writes a record. The output is a `Proposal` — the file's records
with their links resolved to ids, their problems named, and their advisories
attached — which `staging` persists and a person then confirms field by field
through the ordinary editor. The separation is roadmap #69's first rule
("suggestions are never records") and it is also enforced from the other end:
`requirements.rejection_message` refuses a save carrying an unconfirmed answer
to a required question, so an importer that wrote rows directly would be writing
rows the form engine itself would not accept.

Three kinds of finding, and the difference is the whole user interface:

**error** — the record cannot be staged. A link that resolves to nothing, a
`target` whose name disagrees, a date that is not a date. Something is wrong
with the file and a person cannot fix it by thinking harder.

**warning** — the record is staged and something is off. A refused element, a
missing `source_ref`, a contract hash from another config.

**advisory** — the record is staged and is probably about something that already
exists, or is probably the same thing a colleague has also proposed. This is the
one a reviewer acts on, and it is never a refusal: there are no duplicated names
anywhere in the live data, so this exists to catch re-wording, and re-wording
needs a judgement rather than a rule.
"""
import re
from datetime import date, datetime

import yaml

from pantograph import similarity

FORMAT = "collaboratorium-suggestions/0.3"
SUPPORTED_FORMATS = (FORMAT, "collaboratorium-suggestions/0.2")

# The sections of an uploaded file, and the table each one proposes into.
RECORD_SECTIONS = {
    "initiatives": "initiatives",
    "activities": "activities",
    "contracts": "contracts",
}

# How a link element in the file is spelled, per table. The form element it
# writes to is on the right, so a producer writes `people:` and the importer
# knows that means `people_links`.
LINK_ALIASES = {
    "activities": {
        "initiatives": "initiatives_links",
        "people": "people_links",
        "contracts": "contracts_links",
        "parent_activities": "parents",
        "child_activities": "children",
    },
    "initiatives": {
        "parent_initiatives": "parents",
        "child_initiatives": "children",
        "activities": "activities_links",
        "contracts": "contracts_links",
    },
    "contracts": {
        "initiatives": "initiatives_links",
        "activities": "activities_links",
    },
}

# Keys that are about the proposal rather than about the record.
META_KEYS = frozenset((
    "key", "source_ref", "cites", "inferred", "target", "notes",
))

# What a producer naturally writes, against the element it means. `tags` is the
# one that matters: every producer writes it, the element is `tag_groups`, and
# that element is refused — so without this alias a refusal the format
# documents arrives as "no such element", which reads like a different mistake
# and blocks the record instead of dropping one field.
ELEMENT_ALIASES = {
    "tags": "tag_groups",
    "tag_group": "tag_groups",
    "summary": "description",
}

_DATE_ELEMENTS = ("start_date", "end_date")


class Finding:
    """One thing to tell the person who uploaded the file."""

    def __init__(self, severity, message, *, section=None, index=None,
                 element=None, match=None):
        self.severity = severity
        self.message = message
        self.section = section
        self.index = index
        self.element = element
        # For an advisory: (table, id, name, score) of what it resembles, or
        # ("pending", source_ref, name, score) for a colleague's proposal.
        self.match = match

    @property
    def where(self):
        if self.section is None:
            return "file"
        spot = f"{self.section}[{self.index}]"
        return f"{spot}.{self.element}" if self.element else spot

    def __repr__(self):
        return f"<{self.severity} {self.where}: {self.message}>"


class Record:
    """One proposed record, after resolution."""

    def __init__(self, table, section, index, *, key=None, source_ref=None,
                 target=None, values=None, links=None, inferred=None,
                 cites=None):
        self.table = table
        self.section = section
        self.index = index
        self.key = key
        self.source_ref = source_ref
        self.target = target
        self.values = values or {}
        # {form element: [ids]} once resolved; a key not yet allocated an id is
        # held as ("key", handle) and filled in when its record is accepted.
        self.links = links or {}
        self.inferred = inferred or {}
        self.cites = cites or []
        self.findings = []

    @property
    def action(self):
        return "update" if self.target else "create"

    @property
    def name(self):
        return self.values.get("name") or (self.target or {}).get("expect") or ""

    @property
    def blocked(self):
        return any(f.severity == "error" for f in self.findings)

    def __repr__(self):
        return f"<{self.action} {self.table} {self.name!r}>"


class Proposal:
    """A whole uploaded file, checked."""

    def __init__(self, header=None):
        self.header = header or {}
        self.records = []
        self.findings = []

    @property
    def all_findings(self):
        return self.findings + [f for r in self.records for f in r.findings]

    def by_severity(self, severity):
        return [f for f in self.all_findings if f.severity == severity]

    @property
    def errors(self):
        return self.by_severity("error")

    @property
    def warnings(self):
        return self.by_severity("warning")

    @property
    def advisories(self):
        return self.by_severity("advisory")

    @property
    def stageable(self):
        return [r for r in self.records if not r.blocked]

    @property
    def run_id(self):
        producer = self.header.get("producer") or {}
        if isinstance(producer, dict):
            return producer.get("run_id") or producer.get("name")
        return str(producer) if producer else None

    @property
    def subject(self):
        return self.header.get("subject")


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def parse(text):
    """
    The file as a dict, or a Finding-bearing Proposal if it will not parse.

    Returns `(document, finding)`; exactly one is None.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        # The parser's own message names the line, which is the only useful
        # thing to say about a file that is not YAML.
        return None, Finding("error", f"Not valid YAML: {exc}")
    if document is None:
        return None, Finding("error", "The file is empty.")
    if not isinstance(document, dict):
        return None, Finding(
            "error", "The file must be a mapping with `initiatives:`, "
                     "`activities:` or `contracts:` at the top level.")
    return document, None


# --------------------------------------------------------------------------
# Checking
# --------------------------------------------------------------------------

class Checker:
    """
    Checks a parsed file against the contract and a snapshot of current state.

    `current` is `{table: [(id, name)]}` read at import time — deliberately not
    the snapshot that went out in the bundle, which may be hours old and will
    not contain what a colleague imported this morning.

    `pending` is `[(source_ref, table, name, subject)]` for suggestions already
    staged and not yet resolved, so two people proposing the same work collide
    here rather than silently becoming two records.
    """

    def __init__(self, contract_doc, current, pending=(), threshold=None,
                 vocabulary=None):
        self.contract = contract_doc or {}
        self.current = {table: list(rows) for table, rows in (current or {}).items()}
        self.pending = list(pending)
        self.threshold = (similarity.DEFAULT_THRESHOLD if threshold is None
                          else threshold)
        # `{group_id: key_values}` as the deployment holds them right now. The
        # contract names where the terms live; this is them.
        self.vocabulary = dict(vocabulary or {})

    # -- contract lookups --------------------------------------------------

    def _elements(self, table):
        return ((self.contract.get("tables") or {}).get(table) or {}).get("elements") or {}

    def _refused(self, table):
        return {name for name, element in self._elements(table).items()
                if element.get("accepts_suggestions") is False}

    def _required(self, table):
        return {name for name, element in self._elements(table).items()
                if element.get("required") is True}

    # -- entry point -------------------------------------------------------

    def check(self, document):
        proposal = Proposal(header={k: v for k, v in document.items()
                                    if k not in RECORD_SECTIONS})
        self._check_header(proposal)

        for section, table in RECORD_SECTIONS.items():
            rows = document.get(section)
            if rows is None:
                continue
            if not isinstance(rows, list):
                proposal.findings.append(Finding(
                    "error", f"`{section}:` must be a list of records.",
                    section=section))
                continue
            for index, row in enumerate(rows):
                proposal.records.append(self._record(table, section, index, row))

        self._resolve_keys(proposal)
        self._match(proposal)
        return proposal

    # -- header ------------------------------------------------------------

    def _check_header(self, proposal):
        declared = proposal.header.get("format")
        if not declared:
            proposal.findings.append(Finding(
                "warning", f"No `format:` given; read as {FORMAT}."))
        elif declared not in SUPPORTED_FORMATS:
            proposal.findings.append(Finding(
                "error", f"Unsupported format {declared!r}. "
                         f"This deployment reads {FORMAT}."))

        expected = self.contract.get("config_hash")
        declared_hash = proposal.header.get("contract")
        if expected and declared_hash and declared_hash != expected:
            # A warning and not a refusal: a proposal drafted on Monday against
            # a config edited on Tuesday is usually still good.
            proposal.findings.append(Finding(
                "warning",
                "Drafted against a different version of the forms "
                f"({declared_hash[:19]}…, now {expected[:19]}…). Check any "
                "element that has changed since."))
        elif expected and not declared_hash:
            proposal.findings.append(Finding(
                "warning", "No `contract:` hash, so this cannot be checked "
                           "against the forms it was drafted for."))

        if not proposal.header.get("subject"):
            proposal.findings.append(Finding(
                "warning", "No `subject:`, so these records are not attributed "
                           "to anyone. Activities still need `people:`."))

        # Only a coverage entry that stops *before* the end of the period is a
        # gap. Warning about every entry buries the one that matters: the first
        # real file through here declared six sources, five of which ran to the
        # last day, and the single genuine gap — a notes log that stopped three
        # months earlier — arrived as one line among six identical ones. A
        # warning that fires when nothing is wrong teaches people to skip
        # warnings.
        period_end = self._as_date((proposal.header.get("period") or {}).get("to")) \
            if isinstance(proposal.header.get("period"), dict) else None
        for entry in (proposal.header.get("coverage") or []):
            if not isinstance(entry, dict) or not entry.get("through"):
                continue
            through = self._as_date(entry["through"])
            if period_end and through and through >= period_end:
                continue
            gap = (f" — {(period_end - through).days} days before the end of "
                   f"the period" if period_end and through else "")
            note = f" {entry['note']}" if entry.get("note") else ""
            proposal.findings.append(Finding(
                "warning",
                f"Evidence from {entry.get('source', 'a source')} stops at "
                f"{entry['through']}{gap}. Anything after that rests on the "
                f"other sources.{note}"))

    # -- one record --------------------------------------------------------

    def _record(self, table, section, index, row):
        record = Record(table, section, index)

        if not isinstance(row, dict):
            record.findings.append(Finding(
                "error", "Each record must be a mapping.", section=section,
                index=index))
            return record

        record.key = row.get("key")
        record.source_ref = row.get("source_ref")
        record.cites = row.get("cites") or []
        record.inferred = row.get("inferred") or {}
        if not isinstance(record.inferred, dict):
            record.findings.append(Finding(
                "warning", "`inferred:` should be a mapping of element name to "
                           "the reason. Ignored.", section=section, index=index))
            record.inferred = {}

        self._read_target(record, row)
        self._read_values(record, row)
        self._check_required(record)
        self._check_dates(record)

        if not record.source_ref:
            record.findings.append(Finding(
                "warning", "No `source_ref`, so re-importing this file will "
                           "propose it again and declining it will not stick.",
                section=section, index=index))
        return record

    def _read_target(self, record, row):
        target = row.get("target")
        if target is None:
            return
        if not isinstance(target, dict) or "id" not in target:
            record.findings.append(Finding(
                "error", "`target:` needs an `id` and the record's current "
                         "name as `expect`.", section=record.section,
                index=record.index))
            return

        names = dict(self.current.get(record.table) or [])
        target_id = target["id"]
        if target_id not in names:
            record.findings.append(Finding(
                "error", f"No {record.table} record with id {target_id}.",
                section=record.section, index=record.index))
            return

        expect = target.get("expect")
        if expect is None:
            record.findings.append(Finding(
                "warning", f"`target:` has no `expect`, so a wrong id cannot "
                           f"be caught. It currently names {names[target_id]!r}.",
                section=record.section, index=record.index))
        elif similarity._normalise(expect) != similarity._normalise(names[target_id]):
            record.findings.append(Finding(
                "error",
                f"`target: {{id: {target_id}}}` expected {expect!r} but that "
                f"record is named {names[target_id]!r}. Refusing rather than "
                f"editing a different record.",
                section=record.section, index=record.index))
            return
        record.target = {"id": target_id, "expect": names[target_id]}

    def _read_values(self, record, row):
        elements = self._elements(record.table)
        refused = self._refused(record.table)
        aliases = LINK_ALIASES.get(record.table, {})

        for raw_field, value in row.items():
            if raw_field in META_KEYS:
                continue

            if raw_field in aliases:
                record.links[aliases[raw_field]] = self._as_list(value)
                continue

            # Resolve a spelling to the element it means, but only when the
            # element actually exists here — an alias must not invent one.
            field = raw_field
            if field not in elements and ELEMENT_ALIASES.get(field) in elements:
                field = ELEMENT_ALIASES[field]

            # A tag grouping: proposed by category and term name, resolved
            # against the vocabulary that exists now.
            if ((elements.get(field) or {}).get("subform") or {}).get("kind") == "dynamic":
                resolved = self._read_tags(record, field, value)
                if resolved is not None:
                    record.values[field] = resolved
                continue

            if field in refused:
                named = (f"`{raw_field}` (read as `{field}`)"
                         if field != raw_field else f"`{field}`")
                record.findings.append(Finding(
                    "warning",
                    f"{named} is not accepted and was dropped — "
                    + (elements.get(field) or {}).get(
                        "refused_because", "refused by this deployment"),
                    section=record.section, index=record.index, element=field))
                continue

            if field not in elements:
                record.findings.append(Finding(
                    "error",
                    f"`{field}` is not an element of {record.table}. "
                    f"Check contract.json.",
                    section=record.section, index=record.index, element=field))
                continue

            # A single-valued reference to another table (an initiative's
            # responsible_person) still has to be resolved by name.
            if (elements[field].get("choices") or {}).get("from_table") \
                    and not elements[field].get("link"):
                record.values[field] = value
                record.links.setdefault(f"@{field}", self._as_list(value))
                continue

            record.values[field] = value

        for element in record.inferred:
            if element not in record.values and element not in {
                    v for v in aliases.values()} and element not in aliases:
                record.findings.append(Finding(
                    "warning",
                    f"`inferred:` mentions `{element}`, which this record does "
                    f"not set.", section=record.section, index=record.index,
                    element=element))

    # Soft, because the glossary describes it as forcing hard choices rather
    # than as a limit nobody reaches, and because a person who has a good
    # reason should be able to exceed it. Reported, never refused.
    TAG_CEILING = 6

    def _read_tags(self, record, field, value):
        """
        A proposed `tags:` mapping, as the stored subform value.

        Written by category and term *name* —

            tags:
              impact_area: [Education, Data Science]
              idems_domain: [IDEMS R&D]

        — because that is what a person reviewing the file can read, and the
        same reason links are written by name. Stored keyed by the vocabulary
        row and the option keys, which is what the form loads.

        Returns None when nothing survives, so the element is left unset
        rather than set to an empty shape.
        """
        where = dict(section=record.section, index=record.index, element=field)

        if not self.vocabulary:
            record.findings.append(Finding(
                "warning",
                f"`{field}` was dropped: this deployment has no tag groups "
                f"defined, so there is no vocabulary to choose from.", **where))
            return None

        if not isinstance(value, dict):
            record.findings.append(Finding(
                "error",
                f"`{field}` must be a mapping of category to a list of terms, "
                f"such as `impact_area: [Education]`.", **where))
            return None

        # One group holds the categories. Where a deployment has several, the
        # category name says which, so a proposal never has to know the row id.
        stored, chosen = {}, 0
        for category, terms in value.items():
            group_id, definition = self._category(category)
            if definition is None:
                known = sorted({c for kv in self.vocabulary.values() for c in kv})
                record.findings.append(Finding(
                    "error",
                    f"`{field}.{category}` is not a tag category here. "
                    f"This deployment has: {', '.join(known) or 'none'}.",
                    **where))
                continue

            if definition.get("producer") is False:
                record.findings.append(Finding(
                    "warning",
                    f"`{field}.{category}` was dropped — "
                    + (definition.get("producer_note")
                       or "this deployment does not accept a proposed value "
                          "for that category"),
                    **where))
                continue

            options = definition.get(definition.get("list_name")) or {}
            if not isinstance(options, dict):
                options = {}
            resolved = []
            for term in self._as_list(terms):
                key = self._term_key(options, term)
                if key is None:
                    near = similarity.matches(
                        str(term), list(options.items()),
                        threshold=self.threshold, limit=2)
                    hint = (" Did you mean "
                            + " or ".join(f"{label!r}" for _, label, _ in near)
                            + "?") if near else ""
                    record.findings.append(Finding(
                        "error",
                        f"`{field}.{category}: {term!r}` is not one of its "
                        f"terms.{hint}", **where))
                    continue
                resolved.append(key)
            if resolved:
                stored.setdefault(group_id, {})[category] = resolved
                chosen += len(resolved)

        if chosen > self.TAG_CEILING:
            record.findings.append(Finding(
                "advisory",
                f"{chosen} tags across all categories. The house guidance is "
                f"four to six in total, which is meant to force a choice — "
                f"more than that and the tags stop telling a reader which "
                f"records are unlike each other. Not a rule; override it if "
                f"you have a reason.", **where))

        return stored or None

    def _category(self, category):
        """`(group_id, definition)` for a category name, or `(None, None)`."""
        for group_id, key_values in self.vocabulary.items():
            if category in key_values and isinstance(key_values[category], dict):
                return group_id, key_values[category]
        return None, None

    @staticmethod
    def _term_key(options, term):
        """
        The stored key for a proposed term, by label or by key.

        Matched without case or punctuation, because a producer reads the term
        off a glossary written for people — `IDEMS R&D`, not `idems_rd` — and
        being strict about an ampersand would fail the common case for nothing.
        """
        wanted = similarity._normalise(str(term))
        for key, label in options.items():
            if wanted in (similarity._normalise(key), similarity._normalise(label)):
                return key
        return None

    @staticmethod
    def _as_list(value):
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [v for v in value if v is not None and v != ""]
        return [value]

    def _check_required(self, record):
        if record.action == "update":
            # An update supplies only what it changes; the record already
            # satisfies its own required set.
            return
        for element in sorted(self._required(record.table)):
            if element in record.values and record.values[element] not in (None, ""):
                continue
            if record.links.get(element) or record.links.get(f"@{element}"):
                continue
            label = (self._elements(record.table).get(element) or {}).get(
                "label", element)
            record.findings.append(Finding(
                "error", f"{label} is required and is not set.",
                section=record.section, index=record.index, element=element))

    def _check_dates(self, record):
        parsed = {}
        for element in _DATE_ELEMENTS:
            raw = record.values.get(element)
            if raw in (None, ""):
                continue
            value = self._as_date(raw)
            if value is None:
                record.findings.append(Finding(
                    "error", f"`{element}: {raw!r}` is not a date "
                             f"(use YYYY-MM-DD).",
                    section=record.section, index=record.index, element=element))
                continue
            parsed[element] = value

        if len(parsed) == 2 and parsed["end_date"] < parsed["start_date"]:
            record.findings.append(Finding(
                "error", f"`end_date` {parsed['end_date']} is before "
                         f"`start_date` {parsed['start_date']}.",
                section=record.section, index=record.index, element="end_date"))

        if len(parsed) == 2 and (parsed["end_date"] - parsed["start_date"]).days > 400:
            # The style guide's rule: a thing that ran for years is an
            # initiative, and the activities are what happened inside it.
            record.findings.append(Finding(
                "advisory",
                f"Spans {(parsed['end_date'] - parsed['start_date']).days} days. "
                f"Something running this long is usually an initiative rather "
                f"than an activity.",
                section=record.section, index=record.index))

    @staticmethod
    def _as_date(raw):
        if isinstance(raw, date) and not isinstance(raw, datetime):
            return raw
        if isinstance(raw, datetime):
            return raw.date()
        if not isinstance(raw, str):
            return None
        text = raw.strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    # -- link resolution ---------------------------------------------------

    def _resolve_keys(self, proposal):
        """
        Turn every link name into an id, or into a reference to a `key` in this
        file, or into an error naming what did not resolve.
        """
        keys = {r.key: r for r in proposal.records if r.key}
        by_name = {}
        for table, rows in self.current.items():
            for row_id, name in rows:
                by_name.setdefault(table, {})[similarity._normalise(name)] = row_id

        # Which table each link element points at, from the contract.
        for record in proposal.records:
            elements = self._elements(record.table)
            for element, names in list(record.links.items()):
                bare = element.lstrip("@")
                target_table = ((elements.get(bare) or {}).get("choices")
                                or {}).get("from_table")
                resolved = []
                for name in names:
                    if name in keys:
                        resolved.append(("key", name))
                        continue
                    found = (by_name.get(target_table) or {}).get(
                        similarity._normalise(str(name)))
                    if found is not None:
                        resolved.append(found)
                        continue
                    # A link that resolves to nothing is nearly always a name
                    # written the way the source writes it rather than the way
                    # this deployment does — `ePICSA` for `E-PICSA`. Refusing
                    # without saying so sends someone to the spreadsheet to
                    # look it up, which is work the matcher has already done.
                    near = similarity.matches(
                        str(name), self.current.get(target_table) or [],
                        threshold=self.threshold, limit=2)
                    suggestion = ""
                    if near:
                        options = " or ".join(
                            f"{found_name!r} (#{found_id})"
                            for found_id, found_name, _ in near)
                        suggestion = f" Did you mean {options}?"
                    record.findings.append(Finding(
                        "error",
                        f"`{bare}: {name!r}` names no existing {target_table} "
                        f"and no `key` in this file.{suggestion}",
                        section=record.section, index=record.index,
                        element=bare,
                        match=((target_table, near[0][0], near[0][1], near[0][2])
                               if near else None)))
                record.links[element] = resolved

    # -- matching ----------------------------------------------------------

    def _match(self, proposal):
        """
        Attach an advisory to every `create` that probably already exists, or
        that a colleague has probably also proposed.
        """
        proposed = [r for r in proposal.records if r.action == "create" and r.name]

        for record in proposed:
            live = similarity.matches(
                record.name, self.current.get(record.table) or [],
                threshold=self.threshold)
            for row_id, name, value in live:
                record.findings.append(Finding(
                    "advisory",
                    f"Resembles the existing {record.table} record "
                    f"{name!r} (#{row_id}, {int(value * 100)}% alike). Link to "
                    f"it or update it rather than creating a second.",
                    section=record.section, index=record.index,
                    match=(record.table, row_id, name, value)))

            colliding = similarity.matches(
                record.name,
                [((ref, subject), name) for ref, table, name, subject
                 in self.pending if table == record.table
                 and ref != record.source_ref],
                threshold=self.threshold)
            for (ref, subject), name, value in colliding:
                record.findings.append(Finding(
                    "advisory",
                    f"{subject or 'Someone else'} has already proposed "
                    f"{name!r} ({int(value * 100)}% alike) and it is still "
                    f"awaiting review. These will be grouped so one record "
                    f"survives with both of you linked to it.",
                    section=record.section, index=record.index,
                    match=("pending", ref, name, value)))

            # Initiatives only. An initiative should be named for the thing —
            # `R-Instat`, not `Development of R-Instat` — and only 5 of 153
            # live ones are named any other way. An *activity* is a thing that
            # happened, so describing work is exactly what its name is for, and
            # `Teaching statistical problem solving` is a perfectly good one.
            # This fired on an activity in the first real run, and told the
            # reader a statistic about initiatives to justify it.
            if (record.table == "initiatives"
                    and similarity.looks_like_document_phrasing(record.name)):
                record.findings.append(Finding(
                    "advisory",
                    f"{record.name!r} reads as a description of work rather "
                    f"than the name of a thing. Only 5 of 153 existing "
                    f"initiatives are named this way — consider the thing's "
                    f"own name.",
                    section=record.section, index=record.index, element="name"))

        # Two records in the *same* file naming the same thing.
        for position, record in enumerate(proposed):
            later = [(r.index, r.name) for r in proposed[position + 1:]
                     if r.table == record.table]
            for index, name, value in similarity.matches(
                    record.name, later, threshold=self.threshold):
                record.findings.append(Finding(
                    "advisory",
                    f"Also proposed in this file as {name!r} "
                    f"({record.section}[{index}], {int(value * 100)}% alike).",
                    section=record.section, index=record.index))


def check(text, contract_doc, current, pending=(), threshold=None, vocabulary=None):
    """Parse and check an uploaded file. Always returns a Proposal."""
    document, finding = parse(text)
    if finding is not None:
        proposal = Proposal()
        proposal.findings.append(finding)
        return proposal
    return Checker(contract_doc, current, pending, threshold, vocabulary).check(document)
