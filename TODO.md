# TODO

Follow-up issues surfaced while building the Dashboard page. These concern
shared machinery (the generic form builder, the editor modal, app-wide assets)
rather than the dashboard itself, so they are scoped separately: a change to any
of them affects Explore and any organisation that adapts this tool from its own
schema. Each is written to drop straight into a GitHub issue.

---

## A. Activity form: put the required link fields near the top

**Labels:** enhancement, forms

On `activities_form` the required fields are 1st, 11th and 13th in the form.
The current order is:

    Name*, Summary, Attachments, Location, Start Date, End Date, Tag Groups,
    Status, Parent Activities, Child Activities, Linked Initiatives*,
    Linked Contracts, Linked People*

So to fill the three fields you must supply, you scroll past nine optional ones,
and the two rarely-used self-referential link fields (Parent/Child Activities)
sit *above* Linked Initiatives. Reordering `elements` in `config.yaml` so the
required fields lead would markedly cut the effort of recording an activity —
this is the highest value-per-effort item of the follow-ups.

Kept out of the dashboard change because `activities_form` is the same form
reached from the graph node tap, the spreadsheet Edit link and the report links,
and an adopting organisation inherits whatever order ships. It deserves a
deliberate decision, not a side effect.

**Acceptance:** the fields a user must fill are reachable without scrolling past
optional ones; verify the form still renders and saves from every entry point
(dashboard add, graph tap, spreadsheet Edit).

---

## B. Disabled submit button should name the missing fields

**Labels:** enhancement, forms, ux

While required fields are empty the submit button reads
"Fill Required Fields to Submit" and is disabled, but never says *which* fields —
and they may be off-screen (see A). A user can be left staring at a disabled
button with no cue as to what it wants.

Either name the outstanding fields ("Add a name and a linked person to submit")
or mark the empty required fields visibly. Lives in `form_gen.py`; affects every
form and predates the dashboard.

**Acceptance:** with a required field empty, the UI states which field is
outstanding; the button enables the moment the last one is filled.

---

## C. Editor modal is a dead end after a successful save

**Labels:** enhancement, editor, ux

After submitting, the editor modal stays open showing
"Select a table or click an element to edit." above a success line like
"✅ Created activities record ID 37". The first line reads like an instruction
the user failed to follow; the second exposes a raw database id.

On success the editor should either close, or show a plain-language confirmation
naming what was created and what it was linked to
("Added *Collaboratorium v0.6.0* to Collaboratorium Prototype").

Shared editor behaviour that has always worked this way, but the dashboard makes
adding a record the common path, so a rarely-seen rough edge becomes a
constantly-seen one. Motivated by, but not part of, the dashboard work.

**Acceptance:** after a successful add the user is not left on a modal whose
primary text implies nothing happened; no raw record id is shown as the result.

---

## D. Bootstrap Icons font does not load

**Labels:** bug, assets

`className="bi bi-*"` icons render as nothing throughout the app — the
Bootstrap Icons stylesheet/font is not among the external stylesheets. The
existing "Add Element" button's `bi-plus-circle` has never shown, and it forced
the new dashboard header buttons to use a literal "+" instead of an icon.

Either add the Bootstrap Icons CSS to `external_stylesheets` (self-hosted under
`assets/` to match the offline/CSP posture) or remove the dead `bi` classes.

**Acceptance:** either `bi` icons render, or no component references a `bi` class
that resolves to nothing.

---

## E. No guard against duplicate records

**Labels:** discussion, data-quality

Three activities with the identical name were created in a row with no warning.
This needs a policy decision before any code: duplicate activity names are
plausibly legitimate ("Weekly standup", "Site visit"), so a hard uniqueness
constraint is likely wrong. Options range from doing nothing, through a soft
"an activity with this name already exists — add anyway?" prompt, to
per-table configuration of which fields should warn.

Decide the intended behaviour first; it may resolve as won't-fix.

**Acceptance:** a documented decision on whether/when duplicates are flagged,
and an implementation matching it (which may be "no change").
