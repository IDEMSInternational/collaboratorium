"""
scopes.py
Scope resolution: what a register actually says about one deployment.

Scope is a tree — `Product → Deployment → Program → …` — and a processing
record attaches at any level and applies to everything beneath it. Only the
divergences are stored, so a product with ~200 fields across a dozen
deployments holds a few hundred rows rather than the five figures the grain
implies.

The grain of a record is `(scope, field, purpose, recipient, data subject
category)`. Resolution runs along the **scope** dimension only: the other four
form the key that decides whether a record beneath overrides one above, and are
otherwise opaque here — `recipient` and `data_subject_category` are link ids,
and this module never looks inside them.

Three divergence kinds are named in the model. Only one of them is stored:

- **removed** must be written down, because "this deployment does not collect
  this" is not derivable from an absence — an absence is what inheritance is
  for. It is a tombstone: a record carrying `status: "removed"` and no payload.
- **added** and **overridden** are the same stored thing — a record declared at
  this scope — and differ only in whether an ancestor already declared that
  key. Asking the author to classify their own edit invites a register whose
  labels disagree with its rows, so `divergences` derives the label instead.

Removal is the direction that costs credibility: a register claiming a
deployment processes biometrics when the feature is switched off is worse than
one that omits the field.

Depth is not fixed anywhere in here. Nothing counts levels or names them, so a
fourth level — region, cohort — is a row in the scope table and no code change.

This module is a pure library: no database, no Dash, no config. It is handed a
scope tree and a bag of records and answers questions about them.
"""

# The three divergence kinds from docs/data-protection-model.md. Only REMOVED
# is ever stored; see the module docstring.
ADDED = "added"
REMOVED = "removed"
OVERRIDDEN = "overridden"

# The dimensions of the grain other than scope, in the order they key on.
GRAIN_DIMENSIONS = ("field", "purpose", "recipient", "data_subject_category")


class ScopeError(Exception):
    """Raised for a scope tree or a record set that cannot be resolved."""


# --------------------------------------------------------------------------
# The tree
# --------------------------------------------------------------------------

class ScopeTree:
    """
    A parent-pointer forest over scope ids.

    Built from dicts — `{"id": "kenya", "parent": "parentapp"}` — because that
    is the shape a scope table hands back. A root is a scope whose parent is
    absent, `None` or `""`.

    Several roots are allowed: an organisation runs more than one product, and
    forcing a synthetic "everything" node above them would invite a record
    attached to it, which would then be inherited by products that share
    nothing.
    """

    def __init__(self, scopes):
        self._parent = {}
        self._children = {}

        for scope in scopes:
            scope_id = scope["id"] if isinstance(scope, dict) else scope[0]
            if scope_id in self._parent:
                raise ScopeError(f"Duplicate scope id {scope_id!r}.")
            parent = scope.get("parent") if isinstance(scope, dict) else scope[1]
            self._parent[scope_id] = parent or None
            self._children.setdefault(scope_id, [])

        for scope_id, parent in self._parent.items():
            if parent is None:
                continue
            if parent not in self._parent:
                raise ScopeError(
                    f"Scope {scope_id!r} names parent {parent!r}, which is not a scope."
                )
            self._children[parent].append(scope_id)

        # Walking ancestry is the core operation and would hang on a cycle, so
        # pay for the check once at construction rather than defending every
        # walk.
        for scope_id in self._parent:
            self._check_acyclic(scope_id)

    def _check_acyclic(self, scope_id):
        seen = set()
        current = scope_id
        while current is not None:
            if current in seen:
                raise ScopeError(
                    f"Scope {scope_id!r} is its own ancestor, via {sorted(seen)}."
                )
            seen.add(current)
            current = self._parent[current]

    def __contains__(self, scope_id):
        return scope_id in self._parent

    def __iter__(self):
        """Pre-order: every scope appears after its parent."""
        for root in self.roots():
            yield from self._preorder(root)

    def _preorder(self, scope_id):
        yield scope_id
        for child in self._children[scope_id]:
            yield from self._preorder(child)

    def require(self, scope_id):
        """Raise unless this scope exists. Asking about a scope that is not in
        the tree is a caller bug, not an empty answer."""
        if scope_id not in self._parent:
            raise ScopeError(f"Unknown scope {scope_id!r}.")

    def roots(self):
        return [s for s, parent in self._parent.items() if parent is None]

    def parent(self, scope_id):
        self.require(scope_id)
        return self._parent[scope_id]

    def children(self, scope_id):
        self.require(scope_id)
        return list(self._children[scope_id])

    def ancestry(self, scope_id):
        """Root first, `scope_id` last — the order records must be applied in."""
        self.require(scope_id)
        line = []
        current = scope_id
        while current is not None:
            line.append(current)
            current = self._parent[current]
        line.reverse()
        return line

    def descendants(self, scope_id):
        """Everything beneath `scope_id`, pre-order, excluding itself."""
        self.require(scope_id)
        return list(self._preorder(scope_id))[1:]

    def depth(self, scope_id):
        """0 for a root. Reported, never branched on."""
        return len(self.ancestry(scope_id)) - 1


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------

def grain_key(record):
    """
    The part of the grain that is not scope — what makes two records the same
    fact seen at two levels.

    A missing dimension is `None`, which is a key value like any other and not
    a wildcard. A record with no recipient states something about the field
    with no recipient; it is not a default that a recipient-bearing record
    silently overrides. Wildcards would make override order depend on
    specificity as well as depth, and two orderings that can disagree is one
    too many.
    """
    if not record.get("field"):
        raise ScopeError(f"Record {record!r} has no field; the grain requires one.")
    return tuple(record.get(dimension) for dimension in GRAIN_DIMENSIONS)


def is_removal(record):
    return record.get("status") == REMOVED


def _sortable(key):
    """
    Total order over grain keys whose dimensions mix ids, strings and None.

    Output order is part of the contract — a register that reshuffles its rows
    between two identical runs is unreviewable — but the dimensions are opaque
    link values, so they are ordered as text.
    """
    return tuple("" if part is None else str(part) for part in key)


def _by_scope(tree, records):
    """{scope_id: {grain_key: record}}, with the record set validated."""
    grouped = {}
    for record in records:
        scope_id = record.get("scope")
        if scope_id not in tree:
            raise ScopeError(
                f"Record {record!r} attaches to unknown scope {scope_id!r}."
            )
        key = grain_key(record)
        at_scope = grouped.setdefault(scope_id, {})
        if key in at_scope:
            raise ScopeError(
                f"Scope {scope_id!r} declares {key!r} twice. Two records at one "
                f"scope with one grain key have no defined precedence."
            )
        at_scope[key] = record
    return grouped


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

# The contract shared with #82. Absent provenance means "entered", so a record
# resolved at the scope that declared it is returned untouched.
PROVENANCE = "provenance"


def _inherited(record, from_scope):
    """
    A copy of `record` marked as reaching this scope by inheritance.

    Confidence and confirmation are carried across unchanged: they are facts
    about how the record came to be written, and a child scope inheriting it
    does not re-witness them. Only `source` is overwritten, which does lose
    "this was originally suggested by a model" — `from` is the way back to
    that, and duplicating it here would give two places to disagree.
    """
    inherited = dict(record)
    provenance = dict(record.get(PROVENANCE) or {})
    provenance["source"] = "inherited"
    provenance["from"] = from_scope
    provenance.setdefault("confidence", None)
    provenance.setdefault("confirmed_by", None)
    provenance.setdefault("confirmed_at", None)
    inherited[PROVENANCE] = provenance
    return inherited


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------

def resolve(tree, records, scope_id):
    """
    The effective records for one scope: what the register says it processes.

    Ancestry is applied root first, so a record beneath replaces the one it
    diverges from and a tombstone deletes it. A tombstone is not itself
    effective — a removal says nothing is processed — so removals never appear
    in the result; ask `divergences` what a scope chose to drop.

    Records that arrived from an ancestor carry `source: "inherited"` and the
    scope that declared them. Those declared here are returned as given.
    """
    tree.require(scope_id)
    grouped = _by_scope(tree, records)

    effective = {}
    for ancestor in tree.ancestry(scope_id):
        for key, record in grouped.get(ancestor, {}).items():
            if is_removal(record):
                effective.pop(key, None)
            else:
                effective[key] = record

    return _presented(effective, scope_id)


def _presented(effective, scope_id):
    """Grain-key order, with inherited records marked. Shared by both entry points."""
    return [
        record if record.get("scope") == scope_id else _inherited(record, record["scope"])
        for _, record in sorted(effective.items(), key=lambda item: _sortable(item[0]))
    ]


def resolve_all(tree, records):
    """
    `{scope_id: effective records}` for every scope, in one pre-order pass.

    A scope's answer is its parent's plus its own divergences, so resolving the
    whole tree costs one traversal rather than one ancestry walk per scope.
    Worth having because the register's own views — group by recipient across
    every deployment — need all of it at once, and because it is the thing a
    caller would otherwise write badly.
    """
    grouped = _by_scope(tree, records)
    inherited_state = {}
    resolved = {}

    for scope_id in tree:
        parent = tree.parent(scope_id)
        effective = dict(inherited_state[parent]) if parent is not None else {}
        for key, record in grouped.get(scope_id, {}).items():
            if is_removal(record):
                effective.pop(key, None)
            else:
                effective[key] = record
        inherited_state[scope_id] = effective
        resolved[scope_id] = _presented(effective, scope_id)

    return resolved


def divergences(tree, records, scope_id):
    """
    `{grain_key: ADDED | REMOVED | OVERRIDDEN}` for what this scope declares.

    This is the register's divergence view: what did *this* deployment change
    about what it inherited. The label is derived from the tree rather than
    read off the record, so it cannot drift from what the rows actually say —
    and it moves on its own when an ancestor starts declaring the same key,
    which is correct: an addition becomes an override the moment the level
    above acquires it.

    A key re-declared beneath a removal reads as `added`, matching the model's
    definition — a variable the parent scope does not have. The parent, having
    removed it, does not have it.
    """
    tree.require(scope_id)
    grouped = _by_scope(tree, records)

    above = {}
    for ancestor in tree.ancestry(scope_id)[:-1]:
        for key, record in grouped.get(ancestor, {}).items():
            if is_removal(record):
                above.pop(key, None)
            else:
                above[key] = record

    labelled = {}
    for key, record in grouped.get(scope_id, {}).items():
        if is_removal(record):
            labelled[key] = REMOVED
        else:
            labelled[key] = OVERRIDDEN if key in above else ADDED
    return dict(sorted(labelled.items(), key=lambda item: _sortable(item[0])))
