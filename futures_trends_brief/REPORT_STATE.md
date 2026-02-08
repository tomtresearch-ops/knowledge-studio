# 2026 Futures Report — State Snapshot
*Last updated: 2026-02-07*
*Purpose: Pick this up cold in a fresh session. Everything needed is here.*

---

## What This Is

A forward-looking futures report — "The What and The When" — covering 8 domains with predictions, timelines, and cross-domain synthesis. NOT a retrospective. Published as if it were January/February 2026.

Three-layer differentiation:
1. **Aggregation** — institutional + voice data nobody has time to compile themselves
2. **Tom's Synthesis Per Domain** — opinionated prediction layer (appears as "Tom's Take" at end of each section)
3. **Cross-Domain Synthesis** — the centerpiece. Where domains collide. Comes at the end after all domains.

Full plan: `ANNUAL_REPORT_PLAN.md`
Full roster: `ROSTER_AND_SPEC.md`

---

## Completion Status

### Domains

| # | Domain | Research | Draft | Tom Review | Status |
|---|--------|----------|-------|------------|--------|
| 1 | AI & Machine Intelligence | DONE | FIRST DRAFT | IN PROGRESS | Tom reviewing, has feedback |
| 2 | Robotics & Physical AI | Not started | — | — | — |
| 3 | Longevity & Future of Medicine | Not started | — | — | — |
| 4 | Energy & Climate | Not started | — | — | — |
| 5 | Geopolitics & Demographics | Not started | — | — | — |
| 6 | Economics & Work | Not started | — | — | — |
| 7 | Space & Frontier Tech | Not started | — | — | — |
| 8 | Culture, Identity & Society | Not started | — | — | — |
| — | Cross-Domain Synthesis | Not started | — | — | Comes last, after all domains |

### Per-Domain Section Structure
Each domain follows this pattern (decided):
1. **State of Play** — brief context, orient the reader
2. **What's Coming** — aggregated predictions from institutions and voices
3. **The Timeline** — tables: near-term (2026-27), mid-term (2028-30), horizon (2030+)
4. **Key Voices** — where experts agree/disagree, the tension points
5. **Wild Cards** — what could accelerate or derail
6. **Tom's Take** — the opinionated synthesis, where the report's voice lives

---

## AI Domain — Current Feedback & Open Issues

The first draft is at `report/01_ai_machine_intelligence.md` and is also in the Briefing Room (brief #5).

### Tom's Feedback So Far

1. **$58B productivity software shakeup needs more coverage.** Currently only a line in the timeline table. Should be expanded in "What's Coming" as a subsection — it's already happening, not a prediction. Dynamics to cover: incumbents absorbing (Microsoft/Google), AI-native challengers, the middle getting crushed, workflow inversion.

2. **GDP growth mechanism needs real analysis.** The report has big GDP numbers (Goldman $7T, McKinsey $13T, ARK high single-digit growth) but doesn't trace HOW the growth materializes. The $58B example surfaces the core economic question: when companies save money, does it get redeployed into new activity (GDP grows) or just become margin (GDP shrinks in the disrupted sectors)? Tom: "I think we have some economic things to figure out here."

3. **ATM-teller analogy is instructive but insufficient.** The historical pattern (automation → cheaper operations → more activity → net growth) depends on elastic demand. Open question: is there elastic demand for knowledge work output? If companies save 40% on legal research, do they do 3x more legal research or pocket it?

4. **This economic mechanism question is cross-domain.** It applies to every domain, not just AI. Could become a through-line for the entire report or a major thread in the cross-domain synthesis. Needs real economics research — Bessen, Acemoglu, Autor are the key voices on automation and GDP.

### What's NOT Decided Yet

- Whether the economic mechanism analysis goes into the AI section, the Economics & Work section, or both
- Whether it becomes a cross-domain through-line woven into every section
- The exact narrative structure Tom wants — he said "I don't know if I'm gonna like it" and hasn't given final verdict on the structure
- Level of visualization / charting in the final report

### What IS Decided

- Domain list and order (8 domains as listed above)
- Per-domain section structure (6 parts as listed above)
- Cross-domain synthesis comes LAST, after all individual domains
- AI domain goes first
- Three-layer value model (aggregation → Tom's synthesis → cross-domain)
- Tom's AGI thesis for the AI section: frontier models are already superhuman by the "access-adjusted measure" (breadth × depth × access). The real gates are deployment, energy, governance, organizational — not capability.

---

## Research Files

All in `futures_trends_brief/research/`:

| File | Contents | Lines |
|------|----------|-------|
| `ai_institutional.md` | ARK, McKinsey, Gartner, a16z, WEF, Goldman, PwC/Deloitte/BCG predictions | ~450 |
| `ai_voices.md` | 10 AI voices: Altman, Amodei, Hinton, Hassabis, Huang, Nadella, Andreessen, Suleyman, Kurzweil, LeCun | ~400 |
| `ai_state_of_play.md` | Capabilities, agents, adoption, governance, scaling, limitations, 50+ references | ~374 |

No research files exist yet for domains 2-8.

---

## Pipeline Status (Twice-Weekly Brief)

The Futures & Trends brief pipeline is **working** — separate from the annual report.

| Component | File | Status |
|-----------|------|--------|
| Collectors | `collectors.py` | DONE — 6 collectors: InternalBriefs, RSS, arXiv, Reddit, YouTube, KnowledgeStudio. HN dropped (weak signal). Reddit bumped to 100 limit. 5 institutional YouTube queries added. |
| Synthesizer | `synthesizer.py` | DONE — Claude Haiku, cross-domain synthesis prompt, 3000 max_tokens |
| Flask route | `app.py` line ~8141 | DONE — `futures_trends` vertical, 96h window |
| Briefing Room UI | `briefing.html` line ~523 | DONE — dropdown option added, VERTICAL_META key added |
| First test run | `output/2026-02-07_futures_trends_brief.md` | DONE — 282 signals, 8504 char brief |
| Database | brief #5 in `daily_briefs` table | DONE — also loaded the annual report AI section as brief #5 |
| Git tag | — | NOT DONE — needs `futures-v1-golden` tag |

### Known Issues
- Brookings RSS feed still flaky (changed URL from `/feeds/rss/research/` to `/feed/`, may still have XML parsing issues)
- a16z RSS removed entirely (404s) — collecting via YouTube queries instead
- HN collector class still in code but not called in `collect_all()` — could be cleaned up

---

## Roster Status

Full roster in `ROSTER_AND_SPEC.md` (312 lines). Locked by Tom. Includes:
- Tier 0: Tom's original spec (8 voices)
- Tier 1: Tom explicitly added (9 voices)
- Tier 2: Claude suggested, Tom approved (22 voices)
- Tier 3: YouTube pipeline voices (4)
- Tier 4: Workflowy cross-reference adds (25+)
- Plus ~50 lower-priority names from Workflowy for future consideration
- Health-redirect list (9 names → Health & Longevity brief)
- Deceased/inactive list (6 names)

### Roster Gaps Identified
- No dedicated climate/energy foresight voice
- No dedicated demographics/population futurist beyond Zeihan
- No China/East Asia specialist beyond Kai-Fu Lee

---

## Other Pending Items (Not Report-Specific)

- Elevate Nate B Jones in AI & Tech brief YouTube queries
- Schedule daily briefs (~9-10 PM)
- Monthly/quarterly report templates — derive from annual report work
- Commit and tag futures pipeline as `futures-v1-golden`

---

## How to Resume

1. Read this file first
2. Read `ANNUAL_REPORT_PLAN.md` for the full vision
3. Read `ROSTER_AND_SPEC.md` for the source roster
4. Read `report/01_ai_machine_intelligence.md` for the current AI draft
5. The open questions are in "Tom's Feedback So Far" above — that's where the conversation paused
6. Next step after resolving AI section feedback: research + draft Domain 2 (Robotics & Physical AI) or Domain 6 (Economics & Work) given the economic mechanism questions raised
