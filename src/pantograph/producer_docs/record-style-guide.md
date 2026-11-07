# Writing initiatives, activities and contracts

How a record should read. The [format spec](suggestions-format.md) says what the
file's shape is; this says what belongs in the fields.

Everything below is measured from the 153 initiatives and 48 activities already
in Collaboratorium, not invented. Where this guide and the existing records
disagree, the records are probably right and this page is out of date.

---

## The one mistake worth naming first

**Do not write annual-report prose.** This is the failure mode of every tool
that drafts records from documents, and it is obvious in a diff:

> ❌ A collaboration with CASAS Global on mathematical modelling, specifically the
> PBDM approach. Described as particularly satisfying because it pushes IDEMS to
> engage in cutting-edge mathematical research with direct application, and as
> showing great alignment of purpose and values.

That is 44 words, and about four of them are facts. It is written to persuade a
reader who is deciding whether IDEMS is impressive. A tracker record is written
for a colleague who already works here and is trying to find a thing.

> ✅ Collaboration with CASAS Global on physiologically-based demographic
> modelling (PBDM).

Eleven words, every one load-bearing. The median initiative description in
Collaboratorium is **10 words**. Seventy of the 127 that have one are ten words
or fewer. Two are longer than 60. If you are writing 60, you are writing the
wrong thing.

The judgements — satisfying, impactful, challenging, rewarding, seminal — are
not facts about the work and have no home here. Drop them. If a thing mattered,
the activities under it will show that.

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
a third. Check `snapshot.yaml` before you name anything.

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

**One sentence saying what the thing is.** Not what was achieved, not why it
matters, not who funded it.

> ✅ `r-instat` — A free menu driven statistics software powered by R. It is
> designed to exploit the power of the R statistical system while simultaneously
> being as easy to use as other traditional point and click statistics software.
>
> ✅ `Certificator` — Web-based API for creating course completion certificates
> for ParentText.
>
> ✅ `Tricots` — Developed tools, workflows and training materials to import,
> clean, analyse and interpret Tricot data in R-Instat.

**Aim for ten words.** Not a range — a target. The measured median is 10, and
55% of the ones that exist are ten words or fewer; twenty-five is already an
unusually long one. An earlier version of this page said "ten to twenty-five
words", and the first producer to read it wrote a median of 19.5 with not one
description at ten words or under, because a range reads as permission to use
all of it.

Present tense for a thing that exists, past tense for work that was done. A
noun phrase is a complete and good description — it does not need a verb.

Leave it empty rather than padding it. Twenty-six existing initiatives have no
description, which is honest; one of them says `No`, which is worse than empty.
If the source tells you nothing about what a thing *is*, say nothing.

---

## Activity descriptions

Longer than an initiative's, because an activity is a specific thing that
happened and the detail is the point. **Aim for twenty words** — again a
target, not a range. The measured median is 21.5.

Same warning as above, and it is not hypothetical: this page first said "the
useful range is roughly 10 to 40", and the first producer to work from it
returned a median of 32 with two thirds of its descriptions between 26 and 38.
Every one was inside the stated range and the set as a whole was half as long
again as the records it was meant to match. State the target.

**Cite the artefact. Eighteen of the 30 activity descriptions that exist contain
a URL** — the release, the PR, the paper, the recording. This is the strongest
convention in the data and the easiest for a producer to honour, since a scanner
reading GitHub or Drive already has the link in hand.

> ✅ Release notes:
> https://github.com/IDEMSInternational/open-app-builder/releases/tag/v0.23.1
>
> ✅ Michele and Santiago visited Edinburgh to meet with Chris Sangwin and
> discuss the STACK Assistant project. Chris expressed interest but is currently
> more focused on other STACK-related priorities, such as GitSync.
>
> ✅ Application was submitted to the IFS system. Feedback expected by May 2026.

Those read like a colleague telling you what happened. Specific nouns, named
people, a date, a link, and an outcome where there is one. No adjectives of
quality.

What to include when you have it: who was involved, what was produced, where it
landed, and what happened next. What to leave out: significance, difficulty,
enjoyment, and anything you are inferring about how it was received.

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
      Websites making health and safety information freely available on low-end
      devices in over eighty countries. Delivered for UNICEF.
    status: active

activities:
  - name: IoGT v2 development
    description: >-
      Built version 2 of the Internet of Good Things for UNICEF — the team's
      main focus through 2021.
    initiatives: [iogt]
    people: [Gabe Bolton]
    start_date: 2021-01-01
    end_date: 2021-12-31
    status: active
    inferred:
      start_date: source says "this year"; no month given
      end_date: source says "this year"; no month given
```

Note what went: the adjectives, the enumerated list of health topics, `tags`,
and the gerund name. Note what arrived: a parent initiative, a person, and a
declared inference on both dates.
