"""Parse CSV/Excel campaign metrics and compute summary figures."""
import re

import pandas as pd

REQUIRED_COLUMNS = [
    "date", "channel", "impressions", "clicks",
    "conversions", "spend", "revenue",
]
NUMERIC_COLUMNS = ["impressions", "clicks", "conversions", "spend", "revenue"]
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# Common alternative names for the same columns in Google/Meta/LinkedIn Ads
# exports, recalled from memory (no real client file to check against).
# Matching is exact on the whole normalized string, not on substrings, so two
# different fields can't be joined by a partial name match. Nothing is
# invented: with no match the column stays as is, and the usual "missing
# column" error is raised later.
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
    """Rename columns with common alternative names (Google/Meta/LinkedIn Ads
    exports) to the canonical names of our schema.

    A column is left alone if its canonical name is already in the file. With
    no alias match the column stays as is and nothing is filled in, so the
    honest missing-column error in `compute_summary` still fires instead of a
    silently wrong report.

    Returns the df with matched columns renamed. The renames applied are
    stored in `df.attrs["column_mapping"]` ({canonical: original_name}) so the
    user can see what was mapped to what.
    """
    normalized_to_original = {_normalize(col): col for col in df.columns}
    canonical_present = {c for c in REQUIRED_COLUMNS if c in df.columns}

    rename_map = {}
    mapping_report = {}
    for canonical, aliases in CANONICAL_ALIASES.items():
        if canonical in canonical_present:
            continue  # the correct name is already present, leave it alone
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
    """Parse an uploaded file (CSV or Excel) into a DataFrame.

    The format is chosen by the extension of `filename`, not by content, so an
    unsupported type fails with a clear error before any read is attempted.
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
        # Catch everything else openpyxl/xlrd can raise on a corrupted,
        # wrong-type or password-protected file: the user should see a clear
        # message on the page, not a library error or a bare 500.
        raise ValueError(
            f"Couldn't read the file — make sure it's a valid {ext} file, "
            "not corrupted or password-protected."
        )

    if df.empty:
        raise ValueError("The file is empty or contains no data.")

    df = detect_and_rename_columns(df)

    # Coerce numeric columns right after reading (once, before
    # compute_summary/compute_channel_metrics see them). Junk in a numeric
    # column (text instead of a number) becomes NaN instead of crashing the
    # calculation, and is then handled like any other gap (incomplete_dates).
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
