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
- Онлайн: есть ANTHROPIC_API_KEY И вызывающий код подтвердил allow_llm
  (секретный demo-токен, см. app.py, добавлено 21.08.2026) -> Claude пишет
  живой текст по цифрам.
- Офлайн: любое из двух не выполнено -> подставляем цифры в заготовленные
  шаблоны фраз. Качество ниже, но страница работает и это честно видно
  в отчёте.
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
    """Короткий AI-разбор загруженного файла, когда он прочитан (df есть),
    но не подходит под схему кампании (нет нужных колонок). Добавлено
    25.08.2026 по просьбе Макса.

    Live-режим only, по решению Макса от 25.08.2026: без подтверждённого
    demo-токена (allow_llm) или без ключа на сервере просто возвращаем
    None — вызывающий код (app.py) в этом случае не покажет блок анализа,
    останется только честная фраза "не хватает колонок". Никакого офлайн-
    приближения не делаем: нельзя понять содержимое файла без модели, а
    придумывать вывод по одним заголовкам колонок значило бы выдумывать
    факты.
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
        # Сеть, лимит, неожиданный формат ответа — что угодно. Не роняем
        # страницу: без AI-разбора остаётся обычная честная ошибка о
        # нехватке колонок, ровно как было бы без этой функции.
        return None


def generate_report(summary, channel_metrics, allow_llm=False):
    """Возвращает dict: headline, insights (list[str]), recommendations (list[str]), mode.

    allow_llm включается только когда app.py проверил секретный demo-токен —
    наличия ANTHROPIC_API_KEY на сервере одного недостаточно (страница
    публичная, без этой проверки любой посетитель мог бы вызывать платный
    API просто загрузив файл — исправлено 21.08.2026).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not (allow_llm and api_key):
        return _offline_report(summary, channel_metrics)

    # Онлайн-режим: реальный вызов Claude. Не тестируем автоматически —
    # тут нужен живой ключ и ручная проверка текста человеком.
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
    # Модель иногда оборачивает JSON в ```json ... ``` — снимаем обёртку.
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
        # Модель не вернула валидный JSON — не роняем страницу и не выдаём
        # пустой отчёт, откатываемся на офлайн-текст и честно помечаем это
        # в mode, чтобы было видно, что живой текст не получился, а не
        # тихо подменяем результат.
        return _offline_report(
            summary, channel_metrics,
            mode="offline (model response could not be parsed)",
        )
