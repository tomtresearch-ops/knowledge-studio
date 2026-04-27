# Agent Context Structure

This folder structure lives alongside your projects and teaches your agents how to operate.

```
/agent-context/
│
├── CLAUDE.md                 # High-level personality and heuristics
│
├── preferences/
│   ├── content-criteria.md   # What makes content worth capturing
│   ├── trusted-sources.md    # People/channels whose content always matters
│   ├── rejected-patterns.md  # Types of content to auto-filter
│   └── style-notes.md        # How you like outputs formatted
│
├── examples/
│   ├── liked/                # Links or summaries of content you kept
│   ├── rejected/             # Content you passed on (with brief reason)
│   └── edge-cases/           # Maybes — helps calibrate the boundary
│
├── feedback/
│   └── decisions.jsonl       # Running log: {item, decision, timestamp, reason?}
│
└── domain-specific/
    ├── robotics.md           # Specific interests, key questions, people to track
    ├── ai-futures.md         # Timelines, predictions you care about
    └── [topic].md            # Add as needed
```

---

## File Contents — Starting Templates

### CLAUDE.md
```markdown
# Agent Personality

You are helping Tom curate, synthesize, and publish content about AI and robotics futures.

## Core heuristics
- Signal density matters. Skip fluff.
- Practitioners > commentators
- Contrarian views welcome IF backed by evidence
- Primary sources > summaries > commentary
- Specific predictions with timeframes > vague speculation

## Workflow
- Surface candidates, don't overwhelm
- When uncertain, include with a flag rather than filtering out
- Tom's judgment is fast — optimize for putting the right things in front of him
```

### preferences/content-criteria.md
```markdown
# Content Criteria

## Always surface
- Novel predictions with reasoning
- Technical depth from practitioners
- Contrarian takes with evidence
- Primary research or data
- People Tom has flagged as trusted

## Usually skip
- Hype without substance
- Regurgitated news
- Listicles and roundups
- Content older than 2 years (unless foundational)
- Anything paywalled without summary

## Edge cases — surface with flag
- Famous person saying something new (might be signal, might be noise)
- Dense technical content outside Tom's core domains
- Controversial takes (flag for manual review)
```

### preferences/trusted-sources.md
```markdown
# Trusted Sources

These people's content gets surfaced automatically.

## Robotics / Embodied AI
- [Add names as you identify them]

## AI Futures / AGI Timelines
- [Add names]

## Economics / Labor Impact
- [Add names]

## Wildcards (cross-domain thinkers)
- [Add names]
```

### preferences/rejected-patterns.md
```markdown
# Rejected Patterns

Auto-filter these unless explicitly searching for them.

- "Top 10..." style content
- Reaction videos without original analysis
- Press release rewrites
- Content that's >80% clips from other sources
- AI-generated summary channels
- Paywalled without transcript/summary available
```

### domain-specific/ai-futures.md
```markdown
# AI Futures — Domain Context

## Key questions I'm tracking
- AGI timelines (when, what capabilities)
- Robotics integration into daily life
- Labor market disruption pace
- Regulatory responses by region

## Active predictions to monitor
- [Add specific predictions with sources and dates]

## People with track records
- [Who has been right? Wrong? Why?]
```

---

## Usage

Claude loads relevant files before acting:
- General tasks → CLAUDE.md + preferences/
- Content discovery → above + domain-specific/[topic].md + examples/
- Evaluation assist → above + feedback/decisions.jsonl

As you accept/reject, the feedback log grows. Periodically review: "Analyze my last 50 decisions. Any patterns worth adding to preferences?"

Agents get smarter by accumulating your judgments, not by magic.
