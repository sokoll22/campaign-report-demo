# campaign-report-demo — project brief

> Produced with the `demo-project-interview` skill (live test on a real task), 2026-08-15.
> Demo #2 from the `STRATEGY.md` backlog (milestone "Ready to sell", due 2026-08-31).

## Goal

Show agencies how the routine of assembling a client's ad campaign report goes
from manual work (~40 minutes) to an automatic process taking a few seconds.
The agency uploads a table of raw campaign metrics and gets a finished report
with conclusions and recommendations that can be forwarded to their client
almost unedited, under the agency's own brand.

## Audience

Marketing, SEO, RevOps and CRM agencies (5-30 people) that sell AI features to
clients but lack the capacity to build them (only 13% of HubSpot partners
actually earn from AI services while 92% are increasing AI budgets; the demo
targets that gap). The work is white-label: delivered in the agency's name,
not the contractor's.

## In scope

- Upload CSV/Excel with columns common to any campaign: date, channel,
  impressions, clicks, conversions, spend, revenue.
- Automatic calculation of key metrics and trends over the period.
- LLM-generated text report: a short summary for the period, 3-5 plain-language
  insights (what grew, what dropped, where spend is wasted), and
  recommendations for the next period.
- A web page with the result (Flask, modeled on lead-router-demo).
- An honest metric on the page: "~40 minutes by hand, now a few seconds".

## Out of scope

- Real connections to ad accounts (Google Ads, Meta, etc.): file upload only.
- Storing report history between visits: each time is a new file and a new
  report, nothing is persisted (as in lead-router-demo).
- Multiple clients at once: one file, one report at a time, no login or
  accounts.
- PDF export: a web page is enough.

## Edge cases

- Empty file, or not CSV/Excel: a clear error with no technical jargon.
- Required columns missing (e.g. no "spend"): say which columns are missing
  instead of silently producing a broken report.
- Rows with missing or zero values: do not break the calculation, and say
  honestly in the report that "data is incomplete for such-and-such period"
  (in the spirit of the quoted/inferred markers from lead-router-demo).
- Very little data (1-2 rows): the report is still built, but without
  "trends", since there is nothing to compare against.

## Definition of done

- Upload a test CSV and the report is built and shown on the web page.
- The report contains all parts: summary, 3-5 insights, recommendations, as
  meaningful text rather than boilerplate.
- An honest before/after comparison metric is shown.
- Verified on 2-3 test files, including one "imperfect" file (with gaps) to
  exercise the edge cases.
- Publishing to a public URL is a separate, deferred task and is not part of
  this demo's definition of done.

## Technical constraints

- Python + Flask (the lead-router-demo stack; no new tooling).
- pandas (or the csv module) for parsing.
- Anthropic API for generating the report text, with an offline mode when no
  key is set (lower quality, but the page works).
- The deadline is deliberately not fixed in the brief: the decision was to do
  it now (2026-08-15) rather than postpone to Monday (see the project log).
