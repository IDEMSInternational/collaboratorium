# Benchmarking the writing style of generated descriptions

How the style guide's instructions for initiative and activity descriptions were
tested, so that a later change to them can be measured against the same thing.
Run on 2026-11-06 and 07 against the guide as of commit `e1ee1b5`.

The question is not "can a reader tell it is machine-written". It is: **what, in
a generated description, differs from what IDEMS's careful writers produce, and
is the difference a defect we can instruct away or a limit of the input?**

**Where the texts are.** The real entries and the generated ones are not in this
repository. The real ones come from IDEMS's internal working documents, and the
generated ones are drawn from internal Drive documents, so both stay out of a
public repository. The side-by-side page is a private artifact owned by the
person who ran this: <https://claude.ai/artifact/5je9gH13ZeKidK44kxUTbH>. To
rebuild the real set, see "The real set" below.

## What was compared

**Real (answer key).** Seven initiative-level entries from the IDEMS Activities
2022 working document, all in the ParentApp / ParentText family, written by
Elena, Esmee and Chiara. Headings and authors:

| id | Heading | Author |
| --- | --- | --- |
| P01 | Global Parenting Initiative (includes ParentApp, ParentText, FacilitatorApp, Parenting for Responsibility, PerinatalApp, ParentApp for Kids) | Elena |
| P02 | FacilitatorApp | Elena |
| P03 | WASHApp | Elena |
| P04 | ParentApp | Esmee |
| P05 | ParentText/RapidPro authoring/editing pipelines | Chiara |
| P06 | Sexual reproductive health chatbot Jamaica | Chiara |
| P07 | ParentText for contracts outside of GPI (Myanmar, Cambodia, China) | Chiara |

These were chosen by the "report-style" research session under the same
attribution rule as `report-style-findings.md`, which also supplies the sizing
the guide uses. Entries quoted in the style guide were excluded from the answer
key, because the generator had seen them.

**Generated.** One Sonnet session given only the handoff zip and told to write
those seven initiatives as they stood on 31 December 2022, from GitHub
(IDEMSInternational) and Google Drive material that existed by then.

## Procedure

1. **Build the bundle** from a copy of the live database, never the live file
   (`sqlite3.connect("file:...?mode=ro", uri=True)` then `.backup()`), with the
   tag vocabulary inserted. Blank the `description` of every initiative that
   could be one of the seven, so the generator cannot copy what is already
   there. `handoff.zip_bytes(config)` writes the zip.
2. **Start a fresh session** with no memory of this work, on a cheaper model
   (Sonnet), in an empty folder that holds only `downloads/<bundle>.zip`. If the
   session starts inside a repository, tell it not to read it, and move the
   answer-key files out of that repository first.
3. **Brief** (essentially verbatim): unzip the bundle and read the instructions,
   the format page and the style guide in full; propose exactly these seven
   initiatives, with these exact names, as they stood on 31 December 2022;
   evidence is GitHub, Drive and the Forgejo instance, read-only, limited to what
   existed by that date; do **not** open any "IDEMS Activities <year>" document,
   annual report or CIC report, or any other year-summary of IDEMS's work, and do
   not use descriptions already in the snapshot; write `my-work.yaml` with only
   an `initiatives:` list; report which sources were read.
4. **Check the generator did not read the key.** Search its transcript for the
   titles of the activity reports and for the answer-key path. The only hits
   should be the style guide's own attribution lines.
5. **Pair and shuffle.** `benchmark/make_pairs.py REAL.json GENERATED.yaml OUT`
   writes `pairs-raw.json` and `pairs-flat.json` (layout stripped) for the blind
   agent and `pairs-key.json` for you. For each initiative the order of the real
   and generated text is shuffled, seed 11.
6. **Blind agents.** Two fresh agents, one on `pairs-raw`, one on `pairs-flat`,
   each told: this file has 7 items, each with two descriptions of one
   initiative, one written by staff for an annual report and one drafted by an AI
   agent from the code and documents of the time; read only this file; no web, no
   Drive, no other file; give a verdict and confidence per item, then the
   consistent checkable tells of each side, and which verdicts rest on layout or
   length alone.
7. **Score** against `pairs-key.json`.
8. **Count surface features** with `benchmark/tells.py` as a cross-check on what
   the agents report.

The same method was first run unpaired, on 13 initiative descriptions from
acceptance run 4 mixed with 14 real entries from other initiatives (27 items,
shuffled, no pairing, no names). That set was topic-confounded and is the weaker
test; the paired one is the benchmark.

## Results

| Test | Result |
| --- | --- |
| Unpaired, 27 items, original guide | 27 of 27 correct |
| Paired, 7 items, raw layout | 7 of 7, confidence 92 to 97 |
| Paired, 7 items, layout stripped | 7 of 7, confidence 85 to 96 |

The generated set is therefore distinguishable. What follows is what separated
the sets, ordered by whether we can do anything about it.

**Defects an instruction can fix (and did, partly).**

- Scan facts in a standing description: commit counts, date ranges, issue and
  version numbers, and phrases like "in what was scanned". The strongest tell in
  the unpaired test (digits per 100 words: 13.9 generated, 3.6 real; "Gabe made N
  commits between…" in 8 of 13). The guide now says to keep them out.
- Absence and "as at" framing: closing lines of the form "had no code", "nothing
  had launched", "by the end of 2022". The same fault in subtler form. Partly
  caused by the brief asking for an end-of-2022 snapshot.
- Opening with a bare noun phrase ("A small library that…"). The guide now says
  to open with why the thing exists. Note that this *introduced* a different tell:
  real entries open with "IDEMS supported…", "We…" or the programme name, not the
  need.

**Differences of voice, which we chose not to chase.**

- Real: organisational "we" and "shall", warm credit to partner organisations,
  signposts ("Of note", "To conclude"), a pointer outward to another report, loose
  dates, several paragraphs or bullets, and lengths from 60 to 600+ words.
- Generated: third-person and documentary, one block of 100 to 230 words, exact
  days and small counts, repository and tool names, and credit to individuals by
  name. Credit by name is kept on purpose.

**Limits of the input.** Real entries contain what only an insider knows: why a
contract was cancelled, how a relationship led to a contract, what the funding
covers. A producer working from code and documents cannot recover it, and
imitating the register without the knowledge would manufacture claims. The
proposed answer is for the producer to say what it could not know and leave it to
the reviewer.

**Not a tell.** Em dashes: none in either set, in any run. Promotional adjectives:
none in the generated set. The punctuation features the guide already controls
are clean.

## Confounds, so the next run is read fairly

- **Genre.** The real entries are year narratives written by insiders; the guide
  asks for a standing description. Some of the gap is the question being
  different, not the writing being worse.
- **Era.** The brief fixed the end of 2022, producing the "end of 2022" framing.
  In real use the vantage point is now.
- **Small n, one generator, one run each.** Seven pairs, one Sonnet session. Do
  not read 7/7 as a rate; read it as "not close to chance".
- **Blind agents are the same family of model.** They may share the generator's
  blind spots, so a tell they miss is not proven absent.
- **Content outweighed style.** Both agents said most verdicts rested on content
  and voice, and survived the removal of layout and length.

## To benchmark a change to the instructions

1. Keep the seven names and rebuild the real set from IDEMS Activities 2022 (the
   headings and authors are above; copy the text verbatim, punctuation and dashes
   kept, Google Docs artefacts stripped).
2. Build a bundle from the **changed** instructions, then run steps 2 to 8.
3. Compare against the table above. A change worked if the surface counts move
   toward the real set and, more usefully, if the agents' named tells shrink to
   ones in the "voice" and "limits" groups. Do not optimise for the verdict
   score going down: it measures how much the text sounds like a person who was
   there, which is not the goal.
4. Re-run the unpaired test as a sanity check on whether the scan-fact tells
   returned.

Scripts are in `benchmark/`. They take the real texts as a local file and do not
store them.
