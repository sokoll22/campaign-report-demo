"""
Генерация текстовой части отчёта: сводка, инсайты, рекомендации.

Не покрыто TDD-циклом целиком, потому что итоговый текст — это проза,
у неё нет единственного "правильного" результата, который можно
проверить assert'ом. Но сами цифры, вокруг которых строится текст
(ROI, CTR, лучший/худший канал), уже посчитаны и протестированы в
report_engine.py — здесь только оборачиваем их в читаемый текст.

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
                f"{c['channel']}: ROI {roi_pct:+d}% — канал окупается, "
                f"потрачено ${c['spend']:.0f}, выручка ${c['revenue']:.0f}."
            )
        else:
            insights.append(
                f"{c['channel']}: ROI {roi_pct:+d}% — канал уходит в минус, "
                f"стоит пересмотреть бюджет или креативы."
            )

    if summary["incomplete_dates"]:
        dates = ", ".join(summary["incomplete_dates"])
        insights.append(
            f"Данные за {dates} неполные — эти цифры в сумме учтены частично."
        )

    return insights


def _offline_recommendations(channel_metrics):
    recs = []
    worst = min(channel_metrics, key=lambda c: c["roi"]) if channel_metrics else None
    best = max(channel_metrics, key=lambda c: c["roi"]) if channel_metrics else None

    if worst and worst["roi"] < 0:
        recs.append(f"Сократить или пересмотреть бюджет на {worst['channel']}.")
    if best and best["roi"] > 0 and best != worst:
        recs.append(f"Рассмотреть увеличение бюджета на {best['channel']} — он в плюсе.")
    if not recs:
        recs.append("Данных пока недостаточно для конкретных рекомендаций.")
    return recs


def generate_report(summary, channel_metrics):
    """Возвращает dict: headline, insights (list[str]), recommendations (list[str]), mode."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        return {
            "headline": (
                f"За период потрачено ${summary['total_spend']:.0f}, "
                f"выручка ${summary['total_revenue']:.0f}."
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
        "Ты помогаешь агентству написать короткий отчёт клиенту по рекламной "
        "кампании. Вот посчитанные цифры (используй их, не выдумывай новые):\n"
        f"Сводка: {summary}\n"
        f"По каналам: {channel_metrics}\n"
        "Напиши: 1) заголовок-сводку одной фразой, 2) 3-5 инсайтов простым "
        "языком, 3) рекомендации на следующий период. Коротко, по-деловому."
    )
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text
    return {"headline": None, "insights": None, "recommendations": None,
            "raw_text": text, "mode": "online"}
