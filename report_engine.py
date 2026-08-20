"""Разбор CSV/Excel с метриками кампании и расчёт сводных показателей."""
import re

import pandas as pd

REQUIRED_COLUMNS = [
    "date", "channel", "impressions", "clicks",
    "conversions", "spend", "revenue",
]
NUMERIC_COLUMNS = ["impressions", "clicks", "conversions", "spend", "revenue"]
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# Типовые альтернативные названия тех же колонок в экспортах Google/Meta/
# LinkedIn Ads — сверены по памяти (без реального файла клиента на
# 20.08.2026), совпадение только точное (по всей нормализованной строке,
# не по подстроке), чтобы не сцепить два разных поля по случайному
# совпадению куска названия. Данные не выдумываются: если совпадения нет,
# колонка остаётся как есть, и дальше сработает обычная честная ошибка
# «не хватает колонки».
CANONICAL_ALIASES = {
    "date": ["day", "reporting date", "reporting starts", "date range"],
    "channel": ["platform", "network", "source", "ad platform", "traffic source"],
    "impressions": ["impr.", "impr", "views"],
    "clicks": ["link clicks", "clicks (all)", "total clicks"],
    "conversions": ["conv.", "conv", "results", "purchases", "leads"],
    "spend": ["cost", "amount spent", "amount spent (usd)", "total spend", "media cost"],
    "revenue": [
        "conv. value", "conversion value", "total conv. value", "purchase value",
        "purchases conversion value", "sales", "revenue generated",
    ],
}


def _extension(filename):
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def _normalize(name):
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def detect_and_rename_columns(df):
    """Переименовывает колонки с типичными альтернативными названиями
    (Google/Meta/LinkedIn Ads-экспорты) в канонические имена нашей схемы.

    Не трогает колонку, если канонический вариант уже есть в файле. Если
    совпадения по алиасам нет — колонка остаётся как есть, ничего не
    подставляется: дальше по-прежнему сработает честная ошибка о нехватке
    колонки (в `compute_summary`), а не молчаливо неверный отчёт.

    Возвращает df с переименованными (где сматчилось) колонками; какие
    именно переименования применены — кладёт в `df.attrs["column_mapping"]`
    ({canonical: original_name}), чтобы показать пользователю, что к чему
    привязано, а не прятать это.
    """
    normalized_to_original = {_normalize(col): col for col in df.columns}
    canonical_present = {c for c in REQUIRED_COLUMNS if c in df.columns}

    rename_map = {}
    mapping_report = {}
    for canonical, aliases in CANONICAL_ALIASES.items():
        if canonical in canonical_present:
            continue  # своё правильное имя уже есть — не трогаем
        for alias in aliases:
            original = normalized_to_original.get(_normalize(alias))
            if original is not None:
                rename_map[original] = canonical
                mapping_report[canonical] = original
                break

    if rename_map:
        df = df.rename(columns=rename_map)
    df.attrs["column_mapping"] = mapping_report
    return df


def parse_campaign_file(file_or_buffer, filename):
    """Разбирает загруженный файл (CSV или Excel) в DataFrame.

    Формат определяется по расширению `filename`, а не по содержимому —
    это даёт понятную ошибку сразу, до попытки чтения файла.
    """
    ext = _extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        shown = ext if ext else "no extension"
        raise ValueError(
            f"Unsupported file type ({shown}). Please upload a CSV or Excel "
            "file (.csv, .xlsx, .xls)."
        )

    try:
        if ext == ".csv":
            df = pd.read_csv(file_or_buffer)
        elif ext == ".xlsx":
            df = pd.read_excel(file_or_buffer, engine="openpyxl")
        else:  # .xls
            df = pd.read_excel(file_or_buffer, engine="xlrd")
    except pd.errors.EmptyDataError:
        raise ValueError("The file is empty or contains no data.")
    except pd.errors.ParserError:
        raise ValueError("Couldn't read the file — make sure it's a valid CSV.")
    except Exception:
        # Ловим всё остальное, что могут поднять openpyxl/xlrd на битом,
        # не своём или защищённом паролем файле — пользователь должен
        # увидеть понятную фразу на странице, а не техническую ошибку
        # библиотеки или голый 500.
        raise ValueError(
            f"Couldn't read the file — make sure it's a valid {ext} file, "
            "not corrupted or password-protected."
        )

    if df.empty:
        raise ValueError("The file is empty or contains no data.")

    df = detect_and_rename_columns(df)

    # Приводим числовые колонки к числам сразу после чтения (один раз,
    # до того как их увидят compute_summary/compute_channel_metrics).
    # Мусор в числовой колонке (текст вместо числа) превращается в NaN,
    # а не роняет расчёт — дальше он обрабатывается так же, как обычные
    # пропуски (incomplete_dates), честно, без падения.
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def compute_summary(df):
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"The file is missing columns: {', '.join(missing)}. "
            f"Required: {', '.join(REQUIRED_COLUMNS)}."
        )
    incomplete_mask = df[NUMERIC_COLUMNS].isna().any(axis=1)
    incomplete_dates = sorted(df.loc[incomplete_mask, "date"].astype(str).unique())

    return {
        "total_impressions": int(df["impressions"].sum()),
        "total_clicks": int(df["clicks"].sum()),
        "total_conversions": int(df["conversions"].sum()),
        "total_spend": float(df["spend"].sum()),
        "total_revenue": float(df["revenue"].sum()),
        "incomplete_dates": incomplete_dates,
        "has_trend_data": df["date"].nunique() >= 2,
        "column_mapping": df.attrs.get("column_mapping", {}),
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
