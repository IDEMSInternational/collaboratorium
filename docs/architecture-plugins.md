# Pantograph: core + plugins

## Why

The tool was built to be repurposed, and the configuration layer largely
delivers on that: schema, forms, links, filters, views and graph styling are all
driven from `config.yaml`, and `db.py`, `component_factory.py` and `form_gen.py`
name no table of ours anywhere.

Two things have since broken that promise from opposite directions.

The Dashboard (#53) is a page whose *questions* are specific — "initiatives with
no activity", "activities not linked to an initiative", "people near your work"
— and it answers them with 655 lines of SQL that name `initiatives`,
`activities`, `people`, `tag_groups` and the link tables literally. It is a good
page. It is not configurable, and pretending otherwise would either cripple it
or add a config dialect nobody can read.

The GDPR / Better Deal 4 Data records-of-processing use case pulls the other
way. A Record of Processing Activity is a guided checklist: the lawful basis you
pick determines which further questions you are legally required to answer.
Selecting "Legitimate Interest" makes Collection Purpose, Collection Necessity
and Collection Balance mandatory; selecting "Consent" makes a different set
mandatory. That is conditional form logic, and the core has none.

So the answer is not "make everything generic". It is to say plainly which code
is allowed to know about a specific domain, put that code in a plugin, and grow
the core only where the capability is genuinely shared.

## Decisions taken

- The core is named **Pantograph** — a linkage that traces an outline and
  reproduces it: trace the schema, get the application. Collaboratorium is the
  name of one deployment built on it, not of the engine.
- **Monorepo.** Core and all in-repo plugins live here, under `src/`. Plugins
  are discovered through the `pantograph.plugins` entry point group, so moving
  one into its own distribution later is a packaging change and nothing else.
- **Option (b), declared requirements**, for plugins that assume a schema shape.
- The **LLM static-analysis pipeline is a separate project coupled by data**,
  not a plugin and not an importer of core. See "The producer interface" below.
- Collaboratorium and the GDPR register are **not expected to share a
  deployment**. The plugin system is therefore a build-time seam that lets one
  codebase produce two products, not a runtime composition system — which is why
  it needs no isolation guarantees, sandboxing, or frozen public API.

## The split

**Core** owns everything that must never name a table:

- config load, merge and validation
- the versioned-record database layer (`db.py`) and link-table read/write
- form element types (`component_factory.py`) and the generic add/edit/submit
  cycle (`form_gen.py`)
- the editor container (modal / offcanvas / inline) and its open/close routing
- auth, session, person resolution, analytics
- the plugin loader, the page navigation and the shared `dcc.Store` contract

**A plugin** is allowed to be specific. It may ship its own SQL, its own layout,
its own tables and its own vocabulary. That permission is the whole point of the
split: it is what stops domain knowledge leaking into core as ever-more-abstract
configuration.

Initial plugins:

| id | what it is |
| --- | --- |
| `explore` | today's graph/spreadsheet/report page |
| `dashboard` | today's Dashboard, moved verbatim |
| `gdpr_ropa` | new: guided records-of-processing checklists |

Explore is listed as a plugin even though it is close to core, because a GDPR
deployment may well not want a force-directed network graph as its front door,
and "which pages exist" should be one decision in one place.

## Plugin interface

Formalises what the view modules already do:

```python
class Plugin:
    id: str                       # namespace for every component id it creates
    label: str                    # nav button text
    requires_tables: tuple[str]   # checked at startup, fails loudly
    def layout(self, config): ...        # -> the page's Dash component tree
    def register(self, app, config): ... # -> None, registers callbacks
    def stores(self): ...                # -> plugin-private dcc.Stores
    def header_items(self, config): ...  # -> app-header controls, e.g. quick-add
```

`id` is deployment-facing: the nav button is `nav-<id>`, the page container is
`<id>-container`, and it is the value of the shared `page-store`. Naming the two
existing pages `dashboard` and `explore` therefore reproduced the previous DOM
ids exactly, which kept the existing browser tests a real safety net through the
restructure.

Declared in config:

```yaml
plugins:
  - id: dashboard
    landing: true
  - id: explore
```

An entry may also carry `label:` to rename the nav button, `config:` for the
plugin's own options, and `class: "package.module:ClassName"` to point at an
implementation directly. The `id` from config wins over the class default, so
one implementation can be mounted under a deployment's own name.

`pantograph/app.py` then reduces to: load config, init db, build the nav from the
plugin list, mount each plugin's layout in its own display-toggled container,
register each plugin's callbacks.

The `+ Activity` / `+ Initiative` quick-adds became `header_items` on the
dashboard plugin rather than a config list. They are global to the app but not
generic — the dashboard is what wires their clicks, prefills the new record and
hides them while an admin views someone else's page read-only — so the plugin
that owns the behaviour also owns the rendering. The catch-all "Add other…",
which works against any schema, stayed in core.

Two rules keep plugins from colliding:

1. **Every component id a plugin creates is prefixed with its plugin id.**
   Dash silently stops dispatching pattern-matching callbacks on duplicate ids,
   and that failure mode is miserable to debug.
2. **A short list of stores is core contract**, shared deliberately:
   `current-person-id`, `form-prefill`, `form-refresh`, `page-store`,
   `intermediary-loaded`. Everything else is plugin-private.

### On the Dashboard's SQL

Two options were considered for `dashboard_data.py`:

- **(a) Role mapping.** The plugin declares `roles: {container: initiatives,
  item: activities, actor: people}` and its SQL is templated over those names.
- **(b) Declared requirements.** The plugin keeps its SQL as-is and declares
  `requires_tables`, failing at startup if the deployment doesn't provide them.

**(b)** was chosen, with (a) available later if a second deployment actually
wants the same shape under different names. Option (a) buys reuse that nobody
has asked for yet, at the cost of SQL that reads as `{container}` throughout —
and speculative genericity is what grew `config.yaml` to 1213 lines. A plugin
that is honest about needing an `initiatives` table is easier to fork than a
plugin that is abstract about it.

## What core must gain for the GDPR plugin

These are the load-bearing additions, and none of them belongs in the plugin —
they are ODK-standard form capabilities that every deployment can use.

**1. Relevance.** `relevant: "${lawful_basis} = 'legitimate_interest'"` on an
element, evaluated against current form state, toggling that element's
container. Needs a small expression evaluator (equality, membership, and/or/not
over `${element}` references — deliberately not a Python `eval`) plus one
pattern-matching callback per form. This is the single biggest core change and
the one everything else depends on.

**2. Dynamic required.** `required` is currently read once at callback
registration and frozen into `validate_required_fields`. It must become
state-dependent: a field is required only when relevant. This also resolves
TODO item B — once the required set is computed per-render, the disabled submit
button can name the fields it is waiting on instead of saying nothing.

**3. Constraints.** Validation beyond emptiness, with a per-element message.
Retention periods, date ordering, "if you claim an exemption you must cite it".

**4. Multi-page forms.** A ROPA record is long enough that one scrolling page is
the wrong shape. A `pages` grouping over `elements`, with next/back and per-page
validation, is generic and Explore's forms would benefit too.

**5. A prefill provider seam.** `generate_form_layout` already takes
`initial_values` — the Dashboard uses it to hand off a pre-linked activity
([form_gen.py:29](../src/pantograph/form_gen.py:29)). Formalise it as a
provider a plugin can register:

```python
provider(table_name, context) -> {element_name: value}, {element_name: provenance}
```

This is where the LLM static-code-analysis results land: a field's value arrives
with `provenance: {source: "static-analysis", run: ..., confidence: ...}`.

**6. Suggested-vs-confirmed field state.** Prefilled values must render visibly
distinct from human-entered ones, and require an explicit confirm before they
count as answered. For a compliance record this is not a UX nicety — a ROPA that
cannot distinguish "a model inferred this purpose" from "the data controller
asserted this purpose" is not a defensible record. Store the provenance
alongside the value and surface it in the report.

## Config layout

`config.yaml` is now a merged directory:

```
config/
  core.yaml          # title, editor_layout, plugins list
  schema.yaml        # tables, links, default_forms
  forms.yaml         # form definitions
  explore.yaml       # node_tables, network_vis, filter_registry, views, reports
  dashboard.yaml     # the dashboard plugin block
  gdpr.yaml          # ROPA tables, forms and checklist definitions
```

Files are merged on their top-level keys in filename order. Two files may
contribute to the same top-level *mapping* — `gdpr.yaml` adding its own `tables:`
alongside `schema.yaml`'s is the motivating case, and it is what lets a plugin
ship a schema without either file knowing about the other. Defining the same
sub-key twice is an error naming both files, because silent last-one-wins would
make the winner depend on filenames. A duplicated scalar or list is an error
outright: concatenating `plugins:` across files would be a guess, and its order
is meaningful.

A single file still loads, so `config_gen`'s output works unchanged and a small
deployment need not split anything.

## Migration order

1. ~~**Plugin loader + nav registry.**~~ **Done.** Core moved to
   `src/pantograph/`, Explore and the Dashboard to `src/pantograph_explore/` and
   `src/pantograph_dashboard/`, discovered through entry points. The package is
   now importable as a library: internal imports are absolute, and the database
   paths that were module globals monkeypatched by the test suite are now
   `pantograph.settings`, read at call time.
2. ~~**Decouple the editor from Explore.**~~ **Done.** Core hosted the editor
   but took its inputs from `cyto`, the Explore graph. It now listens to a
   shared `editor-request` store that any page publishes to
   (`pantograph/editor.py`), and the graph's node-versus-edge disambiguation
   moved to `pantograph_explore/editor_bridge.py`. Core names no Explore
   component, and a test asserts it stays that way.
3. ~~**Config split**~~ **Done.** The 1213-line `config.yaml` became the
   directory above; the split was verified to be a pure reorganisation by
   comparing the merged result against the original.
4. **Relevance, dynamic required, constraints** in core forms. Ships a real
   improvement to existing forms (TODO B) independently of the GDPR work.
5. **Multi-page forms**, then `pantograph_gdpr_ropa` — schema, checklist forms,
   completeness view — built using only core features. If it needs something
   core can't do, that is the signal to add it to core, not to the plugin.
6. **Prefill provider + provenance**, then wire in the static-analysis output.

## The editor seam

Core hosts one editor and knows nothing about what might open it. A page
publishes a request to the shared `editor-request` store:

```python
{"mode": "edit",    "table": str, "id": int,                  "token": ...}
{"mode": "add",     "table": str, "values": {...}, "title": str | None, "token": ...}
{"mode": "message", "text": str,                              "token": ...}
```

`token` carries the source event's timestamp so a request identifies the event
that raised it. It is belt-and-braces rather than load-bearing: dash-renderer
re-dispatches downstream callbacks when a Store's `data` is reassigned even to
an equal value, so a repeat tap reopens the editor either way. It is kept
because depending on that is depending on a renderer implementation detail, and
because a unique request is much easier to read in devtools.

`message` exists so a page that has decided something is not editable can say so
in its own words — core has no better wording for "this edge is drawn from a
column, there is no record behind it".

Before this, core's form callbacks read `cyto` directly, so core named a
plugin's component and no other page could open the editor without pretending to
be the graph. The tap-to-request translation is now a set of plain functions in
`pantograph_explore/editor_bridge.py`, which is also the first time that path
has had any test coverage.

## Open questions

- **Cross-plugin data.** Does the GDPR plugin want to link a processing activity
  to an Explore `contracts` record? Probably yes, given the partnership
  agreements framing — which means plugins share a schema namespace, not just a
  page slot. Worth settling before the GDPR plugin's schema is written.
- **Round-tripping to the producer.** The pipeline needs to see what is already
  recorded, so it does not re-suggest what a human has answered or rejected.
  Either export current records alongside the schema, or make rejection sticky
  by `source_ref`. Awkward to retrofit, so decide before the format is fixed.
