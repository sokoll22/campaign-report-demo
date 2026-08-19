"""
Генерация текстовой части отчёта: сводка, инсайты, рекомендации.

Не покрыто TDD-циклом целиком, потому что итоговый текст — это проза,
у неё нет единственного "правильного" результата, который можно
проверить assert'ом. Но сами цифры, вокруг которых строится текст
(ROI, CTR, лучший/худший канал), уже посчитаны и протестированы в
report_engine.py — здесь только оборачиваем их в читаемый текст.

Весь текст, который видит пользователь (офлайн-шаблоны и промпт для
Claude в онлайн-режиме), — на английском: демо показывается
англоязычным агентствам, язык интерфейса и вывода должен совпадать.

Два режима:
- Онлайн: есть ANTHROPIC_API_KEY -> Claude пишет живой текст по цифрам.
- Офлайн: ключа нет -> подставляем цифры в заготовленные шаблоны фраз.
  Качество ниже, но страница работает и это честно видно в отчёте.
"""
import os


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


def generate_report(summary, channel_metrics):
    """Возвращает dict: headline, insights (list[str]), recommendations (list[str]), mode."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        return {
            "headline": (
                f"Over this period: ${summary['total_spend']:.0f} spent, "
                f"${summary['total_revenue']:.0f} in revenue."
            ),
            "insights": _offline_insights(summary, channel_metrics),
            "recommendations": _offline_recommendations(channel_metrics),
            "mode": "offline",
        }

    # Онлайн-режим: реальный вызов Claude. Не тестируем автоматически —
    # тут нужен живой ключ и ручная проверка текста человеком.
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompt = (
        "You are helping an agency write a short campaign report for a client. "
        "Here are the already-computed numbers (use them, don't invent new ones):\n"
        f"Summary: {summary}\n"
        f"By channel: {channel_metrics}\n"
        "Write, in English: 1) a one-sentence headline summary, 2) 3-5 insights "
        "in plain language, 3) recommendations for the next period. "
        "Keep it short and business-like."
    )
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text
    return {"headline": None, "insights": None, "recommendations": None,
            "raw_text": text, "mode": "online"}
