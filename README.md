# Campaign Report Demo

Upload a CSV or Excel export from Google, Meta or LinkedIn Ads and get a
client-ready campaign report in seconds: a spend/revenue summary, ROI and CTR
per channel, plain-language insights and recommendations. It replaces roughly
40 minutes of manual spreadsheet work per report.

**Live demo:** <https://campaign-report-demo.onrender.com>

## Quick start

```bash
pip install -r requirements.txt
python3 app.py
```

Then open <http://127.0.0.1:5002>.

## Online and offline modes

- **Offline (default):** no API key needed. The summary, insights and
  recommendations are built from prewritten templates around the computed
  numbers.
- **Online:** set `ANTHROPIC_API_KEY` and the report text is written by a
  Claude model instead.

```bash
ANTHROPIC_API_KEY=sk-... python3 app.py
```

In both modes the numbers are computed from the uploaded file, never by the
model. Only the prose around them differs. The report shows which mode
produced it.

Because the page is public-facing, a server-side key alone does not enable
online mode. The request must also carry the secret `DEMO_ACCESS_TOKEN` (open
the page with `?key=<token>`), so random visitors cannot trigger paid API
calls. If the model returns something unparseable, the report falls back to
offline text and says so.

## Input format

Expected columns: `date, channel, impressions, clicks, conversions, spend, revenue`.

Accepted formats are `.csv`, `.xlsx` and `.xls` (detected by file extension).
A sample file is defined in `tests/test_report_engine.py` (`VALID_CSV`).

Common alternative column names from ad-platform exports (for example `Day`,
`Cost`, `Impr.`, `Conv. value`) are recognized automatically and mapped to the
schema above. The page shows exactly which column was mapped to which field.
Matching is exact on the normalized header, and nothing is invented: if a
field is not found under its own name or a known alias, you get the usual
"missing column" error.

## What the page does

- Upload a file and get a summary (spend and revenue), per-channel insights
  (ROI, whether the channel pays off), recommendations, and a per-channel table
  (spend, revenue, ROI, CTR).
- Nothing is stored. The report is rebuilt from the uploaded file every time.
- Bad input produces a clear message, not a crash: wrong extension, empty
  file, missing columns, corrupted Excel file, files over 5 MB, and any
  unexpected error (a catch-all in `app.py` so users never see a bare 500).
  Non-numeric junk in a numeric column is treated as a missing value and
  reported as incomplete data.

## Architecture

```
CSV / Excel file
   │
   ▼
report_engine.py   parsing + calculation: campaign summary, per-channel
   │               metrics (ROI, CTR), incomplete rows handled without crashing
   ▼
report_text.py     text layer: headline, insights, recommendations.
   │               online (Anthropic API writes the text from the numbers) or
   │               offline (templates around the same numbers)
   ▼
app.py             Flask wrapper: file upload, engine call, template rendering
```

## Tests

The suite has 28 tests, 17 of them for `report_engine.py`, which covers file
parsing and the numbers, where there is a single correct result. The prose in
`report_text.py` has no single right answer, so it is only checked for
structure and fallback behavior.

```bash
pip install pytest xlwt
python3 -m pytest tests/ -q
```

`xlwt` is only needed by the `.xls` test. The app itself reads `.xls` with
`xlrd`, which is already in `requirements.txt`.

## Roadmap

- Period-over-period comparison (growth/decline per channel).
- PDF export of the report.
- Direct import from the Google/Meta/LinkedIn Ads APIs instead of manual upload.

## License

MIT, see [LICENSE](LICENSE).
