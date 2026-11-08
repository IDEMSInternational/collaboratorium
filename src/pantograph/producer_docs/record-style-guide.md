# Writing initiatives, activities and contracts

How a record should read. The [format spec](suggestions-format.md) says what the
file's shape is; this says what belongs in the fields.

**The records already in Collaboratorium are not the standard for descriptions.**
Most are a few words, and a quarter of the initiatives have none. They are what
got entered in a hurry, not what the register is for. The standard comes from
what IDEMS's most careful writers have put in the annual activity reports, and
the numbers below are measured from 120 of those entries. Names, dates and the
activity-or-initiative question are different: for those the existing records
are a fair guide, and the sections say so where it applies.

---

## The one mistake worth naming first

**Do not write a description that persuades. Write one that informs.** The
failure of every tool that drafts records from documents is to copy the
promotional register of the source:

> ❌ A collaboration with CASAS Global on mathematical modelling, specifically the
> PBDM approach. Described as particularly satisfying because it pushes IDEMS to
> engage in cutting-edge mathematical research with direct application, and as
> showing great alignment of purpose and values.

That is 44 words and about four of them are facts. The rest is the author's
feelings about the work, written to impress a reader who is deciding whether
IDEMS is impressive. The careful writers do the opposite. Their entries run to
five or ten or fifteen sentences, and nearly every sentence carries a fact: a
place, a partner, a number, a date, a result, or a problem and what was done
about it.

> ✅ IDEMS collaborated with UoR, the Mozambique National Institute of
> Meteorology (INAM) and the World Food Programme (WFP) Mozambique to evaluate
> five high-resolution gridded rainfall products against gauge measurements from
> six stations. The evaluation assessed total rainfall and the number of rainy
> days on yearly and monthly timescales, to determine how accurate and reliable
> the products are.

So the rule is not "be short". It is: **every sentence earns its place with a
fact, and none of them is an opinion.** The judgements — satisfying, impactful,
challenging, rewarding, seminal — are not facts about the work and have no home
here. If a thing mattered, the numbers and the result will show it.

---

## Names

**A name is what people call the thing, as short as that is.** Median: three
words, for both initiatives and activities.

Real initiative names: `r-instat`, `Tricots`, `Certificator`, `RMS West Africa`,
`Children's Parliament`, `OpenChatBuilder`, `Statistical Literacy`.

Note what is *absent*: no `Development of…`, no `Support for…`, no
`Establishing…`. Only 5 of 153 initiative names begin with a gerund. A source
document will usually name a strand of work as an activity phrase — "Development
of climatic data quality control procedures in R-Instat" — because a report
describes doing things. Strip it back to the thing: that record is `R-Instat`,
and the development is an activity under it.

**Match the existing name exactly when the thing already exists.** This is the
single most valuable thing a producer can get right. `R-Instat` is already
there; `r-instat` is already there. Proposing `Development of R-Instat` creates
a third. Check `snapshot.yaml` before you name anything, and check it for the
links you mean to attach too: a URL an existing record already carries means
the work is already recorded, whatever it is called.

### The `Category:` prefix

A minority convention — 14% of initiatives, 16% of activities — but a real one,
and strongest where a category has many members:

    R Package: carbonr          (12 initiatives use "R Package:")
    Course: Statistical Methods (4 use "Course:")
    Podcast: ISI 2025
    Paper: Turning Challenges into Opportunities
    Joss Paper: Acceptance for exceltoshiny Paper

Use it when the thing is one of a known series — an R package, a course, a
podcast episode, a paper, a conference strand. Do not invent new prefixes; look
at what the snapshot already uses. Most records have no prefix and that is fine.

---

## Initiative descriptions

An initiative's description says what the strand of work *is*: what it does, who
it serves and where, who is involved or pays, and what state it is in. It is a
standing description, not a diary; what happened and when belongs in the
activities under it.

**How long depends on how big the thing is.** The measured median across the
careful writers' entries is six sentences and about 140 words, and nine in ten
of them run to at least three sentences.

| Size of the initiative | Sentences | Words | Paragraphs |
| --- | --- | --- | --- |
| Small: a tool, a single partnership, a course | **4 to 6**; never fewer than 3 | 80 to 140 | 1 |
| Medium: a product with several uses, a programme with a few strands | 6 to 9 | 140 to 220 | 1 to 2 |
| Flagship: ParentText, the Global Parenting Initiative, R-Instat | **10 to 15** | 250 to 400 | 3 or more |

Count sentences rather than paragraphs. Bullet lines inflate a paragraph count,
and the entries that run past about 450 words stop being descriptions and
become logs: stop before that.

**Three sentences is the floor, not the aim.** At exactly three sentences the
careful writers' entries are mostly lists of events attended, and they read as
thin. A four-sentence entry that says why, where, what was done and where it
stands beats a twelve-sentence list.

### What a good one contains

Work through this list and include each item you have evidence for:

1. **Why it exists, and what it is.** Open with the need it answers or the
   situation it came out of, then say what it is. "A small Python library that
   sends requests to…" tells a reader what the thing is before they know why they
   should care; "IDEMS needed one way to call several language-model providers,
   so…" does both. The careful writers almost never open with a bare noun phrase
   ("A …", "X is a Y that…").
2. **Who it serves, and where.** A country, an institution, a site; named, not
   "communities".
3. **What IDEMS specifically did**, as opposed to what the project as a whole
   did: "IDEMS built the first prototype in five days", "IDEMS hosts its own
   RapidPro".
4. **What changed, with at least one number**: users, families, countries,
   sessions, a cost per user, a date launched.
5. **Partners and funders**, by name.
6. **Where it stands now**, and what comes next. One closing sentence.
7. **A problem, if there was one, and what was done.** The best entries state
   setbacks plainly: a pilot that did not produce a deployed product; a surge of
   users that forced a suspension. This is a sign of a trustworthy description,
   not of a bad project.

If the source gives you only some of these, write what you have and stop. Do not
pad, and do not guess at the rest; say in `inferred:` which parts you worked out.
An initiative you can only describe in a sentence or two from the evidence you
have should still be proposed with that sentence, and flagged as thin, rather
than dressed up.

### Keep the scan out of the description

A standing description should still read as true in a year. The facts a scanner
trips over first are the ones that go stale or describe the scan rather than the
work, so leave them out of an initiative's description:

- commit counts and the date range they cover ("made 42 commits between 6 August
  and 3 November 2026");
- issue, PR and version numbers, and lists of them ("#524 to #532", "0.4.0 to
  0.10.0");
- language about your own search ("in what was scanned", "when scanned", "no code
  yet", "nothing found").

They belong in an *activity* (where a date range and a link are the point), in a
citation, or under `inferred:` and `coverage`. The careful writers use few
numbers, and the ones they use are about the work's effect, not its bookkeeping:
families reached, a cost per user, a number of countries.

### Voice

Plain, factual, first person plural ("IDEMS", "we"), in the past tense for what
happened and the present for what is ongoing. Concrete over abstract: a number
or a name stands where an adjective would. Expand an acronym the first time
(PICSA, UoR (University of Reading)). The careful writers almost never use a
marketing adjective, and the weakest entries are the ones that do ("comprehensive
support", "enhance capabilities") and omit the figures.

> ✅ **Small (4 sentences, 91 words).** PLH in collaboration with IDEMS designed
> an audio-only chatbot specifically for Rohingya parents and caregivers of
> children aged 2 to 6, living as refugees in Malaysia (released April 2024).
> Piloted with 80 families in collaboration with UNICEF Malaysia, the chatbot
> delivers five lessons over 10 days, offering the ParentText curriculum through
> concise audio messages. The user experience was tailored to the needs of
> Rohingya refugees through co-design workshops. To support illiterate users,
> all features, including a help menu, are audio-led.
>
> — Elena, *Rohingya Text, Malaysia*, IDEMS Activities 2024

A flagship runs in three movements: the year's focus, then what happened in
order (planning, build, deployment), then the outcome and where it stands. Chiara's
2025 ParentText entries are the model, at 9 to 18 sentences each in three
paragraphs, ending on a result: *"By year's end, the research team was analysing
the data, with early findings indicating positive parenting retention at seven
months at a cost of approximately USD 0.86 per user."*

### When you have little

Do not write `No`, `TBD` or a restatement of the name. If the evidence tells you
nothing about what a thing *is*, leave the description out and say so under
`inferred:` or in a note. An empty description is honest and a padded one is not.
Entries left blank in the reports are not a standard to copy: they are mostly
the standing items that were repeated each year and then dropped.

---

## Activity descriptions

An activity is one thing that happened, so its description says what happened,
who was involved, where it landed, and what came next. The careful writers' own
sub-entries (a country deployment, an evaluation, an event) median eight
sentences and about 190 words, but those are pieces of work. A release, a
submitted application or a single meeting is smaller and is fine at two or three
sentences with a link. **Aim for three to five sentences, 60 to 120 words, for an
activity that was a piece of work, and never leave it at a bare title.**

**Cite the artefact.** Link the release, the PR, the paper, the recording or the
document. It is the strongest convention in the existing records, and the
easiest to honour, because a scanner already has the link in hand.

> ✅ Michele and Santiago visited Edinburgh to meet Chris Sangwin and discuss
> the STACK Assistant project. Chris expressed interest but is currently more
> focused on other STACK-related priorities, such as GitSync.
>
> ✅ Application was submitted to the IFS system. Feedback expected by May 2026.

Those read like a colleague telling you what happened: specific nouns, named
people, a date, a link, an outcome where there is one, no adjectives of quality.

What to include when you have it: who was involved, what was produced, where it
landed, what changed, and what happened next. What to leave out: significance,
difficulty, enjoyment, and anything you are inferring about how it was received.

---

## Dates

`start_date` and `end_date` on activities, and they are the field a
document-derived record is worst at. Twenty-two of the 48 existing activities
have no `start_date` at all, so **absent is normal and acceptable**, and a wrong
date is far more expensive than a missing one — nothing downstream can tell a
guessed date from a read one.

- A real date in the source → use it, and do not list it in `inferred:`.
- **A range you derived by grouping evidence is inferred, even though both
  ends are real dates.** If an activity runs from the first commit in a
  cluster you assembled to the last one, the dates are read but the
  *boundary* is your judgement — you decided those commits were one activity.
  Say so. This is the easiest inference to miss, because nothing about either
  date looks like a guess.
- A month → first of that month, and declare it inferred.
- "this year", "towards the end of the year" → you may bracket it to the year,
  declare it inferred, and say what the words were. Consider leaving it out.
- Nothing → leave both out. Do not reach for the document's publication date.

Never span an activity across more than a year. A thing that ran for three years
is an initiative, and the activities are what happened inside it.

---

## Activity or initiative?

The question a producer gets wrong most often, and a source document will
actively mislead you: a report's "Activities" appendix is usually a list of
*initiatives*, because a report describes ongoing work.

**An initiative is a strand of work with no natural end.** A product, a
partnership, a course, a funded programme, a research direction. If it is still
going, or if it ran for years, or if several separable things happened inside
it, it is an initiative.

**An activity is one thing that happened, datable to within a year.** A release,
a conference, a paper submission, a workshop, a visit, a meeting, a recording,
one episode.

Tests that actually work, in order of reliability:

1. **Open-ended in the source → initiative, always.** A date line reading
   "March 2020 – Present" has never once been an activity.
2. **Could it have a parent?** If the thing is plausibly *part of* a bigger
   strand that has its own name, it is an activity under that strand.
3. **Would a colleague look it up to find out what happened, or to find out what
   we do?** What-happened is an activity.
4. **A closed date proves nothing.** Finished initiatives are extremely common —
   a contract that ended, a course that ran its last cohort. Do not promote
   something to an activity because it stopped.

**Code hosts.** A repository you or your team own is an initiative, because
someone is answerable for it. Inside it, an activity is a large, overarching
piece of work: a goal-level issue or milestone that has many other issues
beneath it. Most issues are not activities. They are the detail of one, and
belong in its description ("closed 23 issues, including the export bug") rather
than as records of their own. A useful test: would a colleague look this up to
find out what happened that quarter? A ten-line bug fix would not be.

When genuinely torn, propose it as an **activity under an existing initiative**.
The initiative table is nearly full and the activity table is nearly empty, so a
wrong activity is a small correction and a wrong initiative is a duplicate in
the table people navigate by.

---

## Contracts

`name`, `responsible_person`, and the organisation. A contract is the agreement,
not the work done under it — the work is initiatives and activities, linked to
it. Name it for the counterparty and the subject, briefly: `Nottingham Trent
survey contract`, not `Contract with Nottingham Trent University for the
provision of survey analysis services`.

Do not infer a contract's existence from the fact that work was funded. If the
source does not describe an agreement, there is no contract record to make.

---

## Status

`status: active` unless the source says the thing is finished and you are sure.
`deleted` is not for things that ended; it is for records that should not exist.

---

## Tags

IDEMS tags its work with the same vocabulary it uses for its podcast and
articles. There are three categories, and a record may carry terms from any or
all of them:

    tags:
      impact_area: [Education, Data Science]
      idems_domain: [IDEMS R&D]

Write the term as it reads, not as a key — `IDEMS R&D`, not `idems_rd`. Case
and punctuation do not matter. A term that is not in the vocabulary is refused
and names what is, so there is no value in guessing at one.

### Four to six, in total

**Aim for four to six tags across all three categories together** — not per
category. This is IDEMS's own rule and the glossary is explicit that it will
"require some hard choices". That is the point of it. A record carrying ten
terms is a record the vocabulary is no longer discriminating between, and
filtering by tag stops telling anyone which records are unlike each other.

It is guidance, not a check. The import reports more than six and stages the
record anyway, because a person with a good reason should be able to exceed it.
You are rarely that person: if you are drafting from commit messages, you are
not in a position to know the reason.

If a category does not apply, leave it out. An empty category is the normal
case rather than a failure — in IDEMS's own tagged material, the third category
is absent from roughly 40% of items.

### What you may set

All three categories. They differ in how sure you can be.

**Impact Area** and **IDEMS Domain** are largely a matter of reading what the
work is about, and the definitions below are enough to choose from.

**Sociotechnical Innovation** is the strategic reading of what a piece of work
is *for*: how it moves an expert-built digital tool towards local community
ownership. It is the least settled category (the glossary calls it "still a bit
of an experiment"), and it is the one where a producer working from a repository
is most likely to be wrong. **Propose it anyway, and always say you are unsure**
— write the reason under `inferred: tags:`. A reviewer who sees a low-confidence
guess can correct it in a moment; a reviewer who sees nothing has to work it out
from scratch, and a producer that leaves the whole category blank teaches
nobody anything about what it should have been. Choose the nearest term whose
definition you can defend in a sentence, and write that sentence.

Do not reach for a Sociotechnical term because the work involves software. Most
of IDEMS's work does, and a tag that is true of everything discriminates
nothing. Ask which of the definitions below the work actually advances.

### Impact Area

Pick by what the work is *about*, from the definitions rather than the labels:

| Term | Means |
| --- | --- |
| Education | Education as an area of impact, e.g. STEM education. **Not** research methods, and not training that exists to make a programme usable. |
| Data Science | Data science, statistics, AI. |
| Climate | PICSA, meteorological services, climate data. |
| Public Health | Parenting, sex workers, disease prevention. |
| Agroecology | As it sounds. |
| Biodiversity | CASAS and similar. |
| Labour Exploitation | Innovation for sex workers and other marginalised workers, as an impact area. |
| Responsible Business | Social enterprise, sustainable funding, commercialising impact work. |
| Socio-Technical Innovation | Broad: work that directly explores the meeting of people and novel technology. |

The Education boundary is the one most often got wrong. Research methods
support is **not** Education — the glossary excludes it explicitly — and the
same work is usually Data Science, or IDEMS Evidence of Impact, depending on
what the record is about.

### IDEMS Domain

| Term | Means |
| --- | --- |
| IDEMS Governance | The CIC model, sharing power, collaboration, capacity building, principles. |
| IDEMS Strategy | As it sounds. |
| IDEMS R&D | Getting novel technologies and digital products off the ground. |
| IDEMS Impact Products | Turning R&D into usable, financially sustainable products. |
| IDEMS Revenue & Funding | Who pays, how the work is funded. |
| IDEMS Mission & Vision | As it sounds. |
| IDEMS Evidence of Impact | Case studies, research outcomes. |
| IDEMS Inclusive Innovation | How communities and stakeholders are included. |

Most engineering work is **IDEMS R&D**. Reach for Impact Products only once a
thing is being made sustainable rather than being built.

### Sociotechnical Innovation

The strategy: show that everything IDEMS does is part of one process, taking an
expert-developed digital intervention and handing it over to local community
ownership. Each term names a way a piece of work serves that process. These
definitions are the glossary's and are being refined, so expect to be unsure.

| Term | Means |
| --- | --- |
| Accountable Agentic AI | Making AI answerable to the human communities it affects. About answerability, not about explaining how a model works. |
| Community Ownership | Technology owned and controlled by a community. Rare today, so usually work *moving towards* it. The test for an initiative is whether the work moves that way, not whether anyone discussed it. |
| Data Privacy | Individual data privacy inside a locally governed, accountable system, e.g. for sex workers, or a GDPR conversation and its limits. Not anonymity. |
| Deep Interoperability | IDEMS's IP category: category theory, code as data, the patents, and enabling a locally owned, context-specific application inside one interoperable space. |
| Distributed Governance | How complex systems are governed so they stay accountable to low-resource communities; when power should be central and when distributed. Part social, part technical. |
| Community Retained Value | The economic value that stays with a community because it owns the thing, e.g. a community turning crops into products. |
| Stakeholder Adaptation | Local communities leading the localisation and continued improvement of an application for their own context. The strongest example is FUMA Gaskiya. |
| Contextualised Variants | Expert work on the central, deterministic data core from which local variants are made: the textbooks work, and current GPI/PLH work. Not yet ready to hand to local stakeholders. |
| Responsible Business Models | Beyond IDEMS's own interests: how communities are served by the way work is funded and run. |
| Education & Training | Training that makes local people the keepers of their own applications, such as research-methods support and facilitator training. It is the other half of Impact Area's Education, which excludes exactly this. |
| Local Capacity Building | Building local skills for technology upkeep, e.g. INNODEMS and GHAIDEMS. |

Some of these are closer to the work than others. A library or a tool that
others build on is more likely **Deep Interoperability** or **Contextualised
Variants** than anything about communities; work on training or hand-over is
**Education & Training** or **Local Capacity Building**. When two seem equally
good, choose neither and say what you weighed.

### Do not invent terms

The vocabulary is a published list IDEMS is answerable to, and there is no
technical gate on it — a term that is not in the glossary is visibly not from
the glossary, which is what keeps it honest. If the work you are describing
genuinely has no term, set fewer tags and say so in a note. Nobody is served by
a plausible-looking tag that means nothing.

Two pairs of terms read alike and are not the same: **Responsible Business** is
an Impact Area while **Responsible Business Models** is a Sociotechnical
Innovation term; and **Socio-Technical Innovation** is an Impact Area term while
Sociotechnical Innovation is a whole category. Name the category when you write
a term, and each lands where you meant it.

---

## A worked contrast

The same source sentence, from the 2021 annual report:

> "The major focus of the year for many in the team: developing a new version of
> the Internet of Good Things, a set of websites making life-saving and
> life-improving information on maternal health, hygiene, emergency information
> on diseases, HIV and sexual health advice for adolescents, internet safety and
> more available for free even on low-end devices in over eighty countries."

Written badly — one record, report voice, everything in it:

```yaml
activities:
  - name: Development of Internet of Good Things version 2 for UNICEF
    description: >-
      The major focus of the year for many in the team: developing a new
      version of the Internet of Good Things, a set of websites making
      life-saving and life-improving information available for free even on
      low-end devices in over eighty countries. Challenging, demanding and
      rewarding work, with many lessons learned in establishing a successful
      relationship with UNICEF.
    tags: [social services, open source products]
    start_date: 2021-01-01
    end_date: 2021-12-31
```

Written well — the standing description belongs to the initiative, the dated
thing is the activity, and the guess is declared:

```yaml
initiatives:
  - key: iogt
    name: Internet of Good Things
    description: >-
      The Internet of Good Things is a set of websites that make health and
      safety information freely available, even on low-end devices, in over
      eighty countries. The content covers maternal health, hygiene, emergency
      information on diseases, sexual health advice for adolescents and internet
      safety. Version 2 was developed for UNICEF in 2021.
    status: active

activities:
  - name: IoGT v2 development
    description: >-
      Built version 2 of the Internet of Good Things for UNICEF. It was the
      main focus for many in the team through 2021.
    initiatives: [iogt]
    people: [Gabe Bolton]
    start_date: 2021-01-01
    end_date: 2021-12-31
    status: active
    inferred:
      start_date: source says "this year"; no month given
      end_date: source says "this year"; no month given
```

Note what went: the adjectives, the invented `tags`, and the gerund name. Note what arrived: a parent initiative, a person, and a
declared inference on both dates.
