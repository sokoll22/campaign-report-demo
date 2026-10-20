"""
Generates the text part of the report: summary, insights, recommendations.

Not fully covered by TDD, because the final text is prose with no single
"correct" result to assert on. The numbers the text is built around (ROI, CTR,
best/worst channel) are already computed and tested in report_engine.py; this
module only wraps them in readable text.

All user-facing text (offline templates and the Claude prompt in online mode)
is in English: the demo is shown to English-speaking agencies, so the UI and
output languages should match.

Two modes:
- Online: ANTHROPIC_API_KEY is set AND the caller confirmed allow_llm (secret
  demo token, see app.py) -> Claude writes the text from the numbers.
- Offline: either condition is missing -> the numbers are slotted into
  prewritten phrase templates. Lower quality, but the page works and the mode
  is shown in the report.
"""
import json
import os
import re


def _offline_insights(summary, channel_metrics):
    insights = []
    for c in sorted(channel_metrics, key=lambda c: c["roi"], reverse=True):
        roi_pct = round(c["roi"] * 100)
        if c["roi"] >= 0:
            insights.append(
                f"{c['channel']}: ROI {roi_pct:+d}% — profitable channel, "
                f"spent ${c['spend']:.0f}, revenue ${c['revenue']:.0f}."
            )
        else:
            insights.append(
                f"{c['channel']}: ROI {roi_pct:+d}% — losing money, "
                f"worth revisiting the budget or creatives."
            )

    if summary["incomplete_dates"]:
        dates = ", ".join(summary["incomplete_dates"])
        insights.append(
            f"Data for {dates} is incomplete — totals only partially reflect these dates."
        )

    return insights


def _offline_recommendations(channel_metrics):
    recs = []
    worst = min(channel_metrics, key=lambda c: c["roi"]) if channel_metrics else None
    best = max(channel_metrics, key=lambda c: c["roi"]) if channel_metrics else None

    if worst and worst["roi"] < 0:
        recs.append(f"Cut or reconsider the budget for {worst['channel']}.")
    if best and best["roi"] > 0 and best != worst:
        recs.append(f"Consider increasing the budget for {best['channel']} — it's profitable.")
    if not recs:
        recs.append("Not enough data yet for specific recommendations.")
    return recs


def _offline_report(summary, channel_metrics, mode="offline"):
    return {
        "headline": (
            f"Over this period: ${summary['total_spend']:.0f} spent, "
            f"${summary['total_revenue']:.0f} in revenue."
        ),
        "insights": _offline_insights(summary, channel_metrics),
        "recommendations": _offline_recommendations(channel_metrics),
        "mode": mode,
    }


def analyze_mismatched_document(df, allow_llm=False):
    """Short AI description of an uploaded file that was read (df exists) but
    doesn't match the campaign schema (required columns missing).

    Live mode only: without a confirmed demo token (allow_llm) or without a
    server-side key this returns None, and the caller (app.py) shows no
    analysis block, only the plain "missing columns" message. There is no
    offline approximation: the content of a file can't be understood without a
    model, and guessing from column headers alone would mean inventing facts.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not (allow_llm and api_key):
        return None

    columns = [str(c) for c in df.columns]
    sample_rows = df.head(3).to_dict(orient="records")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompt = (
        "A user uploaded a file to a campaign-report tool, but it doesn't "
        "match the expected campaign-metrics schema (date, channel, "
        "impressions, clicks, conversions, spend, revenue). Here is what "
        "the file actually contains:\n"
        f"Columns: {columns}\n"
        f"First rows: {sample_rows}\n"
        "In 1-2 short sentences, explain in plain language what kind of "
        "document this looks like and why it doesn't match the campaign-"
        "report schema. Be specific about the columns you see. Return "
        "ONLY plain text — no JSON, no markdown, no quotes."
    )
    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        return text or None
    except Exception:
        # Network error, rate limit, unexpected response shape, anything.
        # Don't crash the page: without the AI description the user still gets
        # the plain missing-columns error, as if this function didn't exist.
        return None


def generate_report(summary, channel_metrics, allow_llm=False):
    """Return a dict: headline, insights (list[str]), recommendations (list[str]), mode.

    allow_llm is enabled only after app.py has verified the secret demo token.
    A server-side ANTHROPIC_API_KEY alone is not enough: the page is public,
    and without this check any visitor could trigger paid API calls just by
    uploading a file.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not (allow_llm and api_key):
        return _offline_report(summary, channel_metrics)

    # Online mode: a real Claude call. Not tested automatically: it needs a
    # live key and a human review of the text.
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompt = (
        "You are helping an agency write a short campaign report for a client. "
        "Here are the already-computed numbers (use them, don't invent new ones):\n"
        f"Summary: {summary}\n"
        f"By channel: {channel_metrics}\n"
        "Return ONLY valid JSON with these keys: \"headline\" (one sentence, "
        "string), \"insights\" (list of 3-5 short strings in plain language), "
        "\"recommendations\" (list of short strings for the next period). "
        "Keep it short and business-like, in English."
    )
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text
    # The model sometimes wraps JSON in ```json ... ```; strip the fence.
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
        return {
            "headline": data.get("headline") or "",
            "insights": data.get("insights") or [],
            "recommendations": data.get("recommendations") or [],
            "mode": "online",
        }
    except (json.JSONDecodeError, TypeError):
        # The model didn't return valid JSON. Don't crash the page or return
        # an empty report: fall back to offline text and mark it in `mode`, so
        # it's visible the live text failed rather than silently swapping the
        # result.
        return _offline_report(
            summary, channel_metrics,
            mode="offline (model response could not be parsed)",
        )
