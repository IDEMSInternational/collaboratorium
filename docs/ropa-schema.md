# The ROPA schema, in config

A config-only draft of the Records of Processing Activities register, in
`examples/ropa/config/`. It is a separate deployment on the same framework —
separate server, schema and database — so it defines its own organisations,
agreements and people rather than sharing Collaboratorium's. The modelling
reasoning is in [data-protection-model.md](data-protection-model.md); this
records what that model looks like once it is written down as tables and forms,
and, more usefully, what the config dialect could not say.

No Python was written. That was the point: a gap here is an argument for a
capability in core, not for a plugin.

## What is in it

A star schema. `processing_records` is the fact, at the decided grain
`(scope, field, purpose, recipient, data subject category)`; every other table
is a dimension it points at.

    scopes ────────────────┐
    data_fields ───────────┤
    purposes ──────────────┼──> processing_records
    data_subject_categories┤          │
    organisations ─────────┘          ├─> agreements ──> organisations
                                      ├─> assessments ─> justifications x3
                                      └─> justifications  (consent mechanism,
                                                           retention, transfer,
                                                           security measures)

- **`scopes`** is a tree, via a single `parent_scope` column rather than a link
  table: a node has at most one parent, and a link table would permit the shape
  to say otherwise. `level` — product / deployment / program / cohort — is
  stored as well as implied by depth.
- **`data_fields`** hang off a product-level scope, so a field is defined once
  and applies to everything below it.
- **`justifications`** is one table with a `kind`, not one table per kind,
  because the deduplication the register needs is the same mechanism for a
  balancing test, a security description and a transfer safeguard.
- **`assessments`** bind one purpose, necessity and balancing justification into
  the combination that was actually reviewed. Records cite the assessment.
- Two link tables: `organisation_people_links`, and
  `record_security_measure_links` because Art. 30(1)(g) expects measures,
  plural.

The lawful basis drives six conditional branches, and `disposition` drives one
more: a row saying "this scope does not process this" clears every other answer
to NULL and asks only why.

## What the config dialect could not express

In rough order of how much it cost.

**1. No group with a shared `relevant:`.** Every element below `disposition`
has to repeat `${disposition} != 'removed'` in its own condition — twenty-odd
copies of one clause, each of which has to be edited if the rule changes. ODK,
whose conventions this dialect borrows, has `begin group` with its own
`relevant:`. `relevant:` on a `subform` is explicitly rejected, so the existing
grouping construct is not a way round it. Needed: a container element, or a
form-level `relevant:` map, whose condition conjoins onto its children.

**2. A condition cannot read across a link.** `data_fields` already records
whether a field is special category, and `organisations` already records its
transfer standing. The processing record has to ask both again, because
`${x}` resolves only to elements of the same form. So the register holds the
same fact twice and nothing stops the two copies disagreeing. Needed: either a
reference that dereferences a link (`${data_field.special_category}`), or a
`default:` that can be pulled from the selected row.

**3. A `select_one` cannot filter its source table.** Three places want it and
none can have it: `data_fields.product` should offer only product-level scopes,
the justification dropdowns should offer only the matching `kind`, and
`agreement` should offer only agreements with the chosen recipient. The result
is dropdowns that will be long and mostly wrong. Needed: a `filter:` on
`parameters`, ideally in the same expression language so it can reference other
answers.

**4. Version-pinned citations are not expressible.** The design record requires
links to carry `(id, version)`. `links:` maps one column to one column, and
nothing in the form engine offers you the version of the row you just picked, so
`assessments` carries `purpose_justification_version` as a plain integer beside
the foreign key — a pin that is typed by hand and unenforced. Needed: composite
link mappings, and a `select_one` that can write a second column.

**5. No derived or templated column.** A five-dimensional fact has no natural
name, but both the graph label and every dropdown that cites the row read a
single column, so `processing_records.name` is typed by hand and will drift from
the dimensions it describes. Needed: a `label_template` on the table, or a
computed column.

**6. `store:` cannot stamp a constant on a link row.** The link insert writes
only id, version, timestamp, status, the two endpoints and `created_by`; the
`type` column is left NULL and no config can set it. So two elements citing
justifications in different roles cannot share one link table — hence a
`record_security_measure_links` table that exists only to be distinguishable.

**7. No uniqueness or referential constraint.** Nothing stops two rows at the
same grain, an orphaned `parent_scope`, or a `data_field` whose product is not
an ancestor of the record's scope. `init_db` emits a composite primary key on
`(id, version)` and no foreign keys at all. For a fact table whose whole meaning
is its grain, "two rows for the same tuple" is a real failure mode.

**8. `boolean` renders without its label.** `component_factory` returns a bare
`dcc.Checklist` for a boolean — no label, no required asterisk, no wrapper. Every
yes/no in this config is a `select_one` over a two-item list instead, which is
arguably better for a register anyway but is not a choice that was made freely.

**9. YAML anchors do not cross files.** A merged config directory is merged
after parsing, so a shared fragment — the status element, the meta block, a
yes/no list — has to be repeated once per file. Nothing serious, but it caps how
finely the config can be split.

## Judgement calls the design record did not settle

- **Scope tree as a parent column, not a link table.** A tree has one parent;
  the self-link table pattern used for initiatives permits many.
- **`level` stored, not derived.** Denormalised so a form can condition on it
  and a report can say "all deployments" without walking the tree.
- **"Removed" is a row, not the absence of one.** Absence has to mean
  "inherited", since inheritance is what makes the row count tractable. So a
  scope that switched a feature off states it, with a reason. `disposition` is
  `declared | overridden | removed`.
- **Recipient role on the record, not on the organisation or the link.** The
  same body is a processor on one flow and a separate controller on another.
- **`internal` is a recipient role, not a null recipient.** It makes "not
  disclosed" an answer rather than an omission, and it is what the transfer and
  agreement questions hang off.
- **One counterparty per agreement.** A multi-party arrangement is entered as
  one agreement per counterparty, because the record cites exactly one agreement
  and a link table would make "which of them governs this flow" ambiguous.
- **Retention as trigger + number + unit.** "Held longer than five years" has to
  be a query, and "three years" is meaningless without "from what".
- **Transfer standing on the organisation, transfer questions on the record.**
  Adequacy is a property of where the organisation sits; whether this particular
  flow crosses a border is a property of the flow.
- **Special category asked on both `data_fields` and the record.** Forced by
  gap 2 above, and the duplication is a known defect rather than a design.
