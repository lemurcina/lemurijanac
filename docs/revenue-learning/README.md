# Revenue Learning Log — NextLevel Media LA / Local-Service Vertical

## Purpose

Daily evidence-backed learning briefs that improve how the current LA local-service acquisition system operates.  
Scope is strictly the **active vertical**: local contractors (electricians, handyman, EV-installers, similar) in Los Angeles.

This is **not** a place to propose new verticals.  See `PORTFOLIO_CONTRACT.md` for expansion rules.

## File structure

```
docs/revenue-learning/
  README.md          — this file
  PLAYBOOK.md        — lessons that have survived validation or repeated evidence
  YYYY-MM-DD.md      — one brief per calendar day (UTC)
```

## Daily brief contract

Each dated file must contain:

- **≤ 5 new lessons**, each with:
  - Source URL / title / date (if available)
  - What changed or was learned
  - Confidence level (`HIGH` / `MEDIUM` / `LOW`)
  - Direct relevance to current workflow
  - One concrete improvement proposal
  - A falsification / stop condition
- **≤ 3 proposed changes**, prioritised by expected value, reversibility, and zero/low capital risk
- Every claim labelled `FACT`, `INFERENCE`, or `EXPERIMENT`
- No fabricated metrics, no fake customer evidence, no unverifiable benchmarks

## Source hierarchy

1. First-party platform/documentation sources (Google Business Profile/Search Central, web.dev/Chrome, MDN/W3C, Vercel/GitHub docs).
2. Reputable industry research / case studies with transparent methodology.
3. Experienced practitioner sources only when clearly marked as opinion and cross-checked.

Avoid: SEO-content farms, unverifiable guru claims, fake benchmarks, scraped/private data, paywall evasion.

## Promotion to PLAYBOOK.md

A lesson graduates to `PLAYBOOK.md` when:
- It is supported by ≥ 2 independent credible sources, **or**
- It has been tested in a controlled experiment with a clear positive outcome, **and**
- Its falsification condition has not been triggered.

## Safety boundaries

- No new vertical proposals unless the active vertical is proven structurally invalid under `PORTFOLIO_CONTRACT.md`.
- No fabricated evidence, no deceptive copy, no regulated-activity overreach.
- When a proposed improvement touches code, copy, tests, or UX, open a narrowly scoped follow-up issue/PR rather than silently changing production behaviour.
