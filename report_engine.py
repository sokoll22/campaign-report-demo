"""Разбор CSV с метриками кампании и расчёт сводных показателей."""
import pandas as pd

REQUIRED_COLUMNS = [
    "date", "channel", "impressions", "clicks",
    "conversions", "spend", "revenue",
]


def parse_campaign_csv(file_or_buffer):
    try:
        return pd.read_csv(file_or_buffer)
    except pd.errors.EmptyDataError:
        raise ValueError("Файл пустой или не содержит данных.")
    except pd.errors.ParserError:
        raise ValueError("Не получилось прочитать файл — проверь, что это CSV.")


def compute_summary(df):
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"В файле не хватает колонок: {', '.join(missing)}. "
            f"Нужны: {', '.join(REQUIRED_COLUMNS)}."
        )
    numeric_cols = ["impressions", "clicks", "conversions", "spend", "revenue"]
    incomplete_mask = df[numeric_cols].isna().any(axis=1)
    incomplete_dates = sorted(df.loc[incomplete_mask, "date"].astype(str).unique())

    return {
        "total_impressions": int(df["impressions"].sum()),
        "total_clicks": int(df["clicks"].sum()),
        "total_conversions": int(df["conversions"].sum()),
        "total_spend": float(df["spend"].sum()),
        "total_revenue": float(df["revenue"].sum()),
        "incomplete_dates": incomplete_dates,
        "has_trend_data": df["date"].nunique() >= 2,
    }


def compute_channel_metrics(df):
    grouped = df.groupby("channel", dropna=True).sum(numeric_only=True)
    result = []
    for channel, row in grouped.iterrows():
        spend = float(row["spend"])
        revenue = float(row["revenue"])
        result.append({
            "channel": channel,
            "spend": spend,
            "revenue": revenue,
            "roi": (revenue - spend) / spend if spend else 0.0,
            "ctr": row["clicks"] / row["impressions"] if row["impressions"] else 0.0,
        })
    return result
