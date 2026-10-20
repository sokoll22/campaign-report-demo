"""
Test 1 from the brief (campaign-report-demo_BRIEF.md, "Definition of done"):
a valid CSV -> a report is built with the correct summary figures.

Also covers Excel (.xlsx/.xls) support and broader file-error handling, not
just for CSV.
"""
import io
import pandas as pd
import pytest
from report_engine import parse_campaign_file, compute_summary, compute_channel_metrics

VALID_CSV = """date,channel,impressions,clicks,conversions,spend,revenue
2026-08-01,Google Ads,1000,50,5,200,800
2026-08-08,Google Ads,1200,60,6,220,900
2026-08-01,Facebook Ads,800,30,2,150,300
"""


def test_compute_summary_totals():
    df = parse_campaign_file(io.StringIO(VALID_CSV), "campaign.csv")
    summary = compute_summary(df)

    assert summary["total_impressions"] == 3000
    assert summary["total_clicks"] == 140
    assert summary["total_conversions"] == 13
    assert summary["total_spend"] == 570
    assert summary["total_revenue"] == 2000


MISSING_COLUMN_CSV = """date,channel,impressions,clicks,conversions,revenue
2026-08-01,Google Ads,1000,50,5,800
"""


def test_missing_column_raises_clear_error():
    df = parse_campaign_file(io.StringIO(MISSING_COLUMN_CSV), "campaign.csv")
    with pytest.raises(ValueError) as exc_info:
        compute_summary(df)

    assert "spend" in str(exc_info.value)


INCOMPLETE_CSV = """date,channel,impressions,clicks,conversions,spend,revenue
2026-08-01,Google Ads,1000,50,5,200,800
2026-08-08,Google Ads,1200,60,6,,900
"""


def test_incomplete_row_does_not_crash_and_is_flagged():
    df = parse_campaign_file(io.StringIO(INCOMPLETE_CSV), "campaign.csv")
    summary = compute_summary(df)

    # Don't crash; compute from what is there
    assert summary["total_spend"] == 200
    # And say honestly which dates have incomplete data
    assert "2026-08-08" in summary["incomplete_dates"]
    assert "2026-08-01" not in summary["incomplete_dates"]


def test_empty_file_raises_clear_error():
    with pytest.raises(ValueError) as exc_info:
        parse_campaign_file(io.StringIO(""), "campaign.csv")

    assert "empty" in str(exc_info.value).lower()


SINGLE_DATE_CSV = """date,channel,impressions,clicks,conversions,spend,revenue
2026-08-01,Google Ads,1000,50,5,200,800
"""


def test_single_date_data_has_no_trends():
    df = parse_campaign_file(io.StringIO(SINGLE_DATE_CSV), "campaign.csv")
    summary = compute_summary(df)

    assert summary["has_trend_data"] is False


def test_multi_date_data_has_trends():
    df = parse_campaign_file(io.StringIO(VALID_CSV), "campaign.csv")
    summary = compute_summary(df)

    assert summary["has_trend_data"] is True


CHANNEL_CSV = """date,channel,impressions,clicks,conversions,spend,revenue
2026-08-01,Google Ads,1000,50,5,200,800
2026-08-08,Google Ads,1200,60,6,220,900
2026-08-01,Facebook Ads,800,30,2,150,90
2026-08-08,Facebook Ads,900,25,1,160,80
"""


def test_channel_metrics_ranks_best_and_worst_roi():
    df = parse_campaign_file(io.StringIO(CHANNEL_CSV), "campaign.csv")
    channels = compute_channel_metrics(df)

    by_name = {c["channel"]: c for c in channels}
    # Google Ads: spend 420, revenue 1700 -> large positive ROI
    # Facebook Ads: spend 310, revenue 170 -> negative ROI
    assert by_name["Google Ads"]["roi"] > by_name["Facebook Ads"]["roi"]
    assert by_name["Facebook Ads"]["roi"] < 0


# --- Excel (.xlsx/.xls) ---

def _valid_dataframe():
    return pd.DataFrame([
        {"date": "2026-08-01", "channel": "Google Ads", "impressions": 1000,
         "clicks": 50, "conversions": 5, "spend": 200, "revenue": 800},
        {"date": "2026-08-08", "channel": "Google Ads", "impressions": 1200,
         "clicks": 60, "conversions": 6, "spend": 220, "revenue": 900},
    ])


def test_xlsx_file_parses_same_as_csv():
    buf = io.BytesIO()
    _valid_dataframe().to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)

    df = parse_campaign_file(buf, "campaign.xlsx")
    summary = compute_summary(df)

    assert summary["total_impressions"] == 2200
    assert summary["total_spend"] == 420
    assert summary["total_revenue"] == 1700


def test_xls_file_parses_same_as_csv():
    xlwt = pytest.importorskip("xlwt")
    # pandas 2.x no longer registers xlwt as an ExcelWriter engine, so the
    # .xls test file is built with xlwt directly, bypassing pandas.to_excel.
    # The engine for READING .xls (xlrd) is used in report_engine as usual.
    book = xlwt.Workbook()
    sheet = book.add_sheet("Sheet1")
    df = _valid_dataframe()
    for col_idx, col_name in enumerate(df.columns):
        sheet.write(0, col_idx, col_name)
    for row_idx, row in enumerate(df.itertuples(index=False), start=1):
        for col_idx, value in enumerate(row):
            sheet.write(row_idx, col_idx, value)
    buf = io.BytesIO()
    book.save(buf)
    buf.seek(0)

    parsed = parse_campaign_file(buf, "campaign.xls")
    summary = compute_summary(parsed)

    assert summary["total_impressions"] == 2200
    assert summary["total_spend"] == 420


def test_unsupported_extension_raises_clear_error():
    with pytest.raises(ValueError) as exc_info:
        parse_campaign_file(io.BytesIO(b"not a real file"), "campaign.txt")

    assert ".txt" in str(exc_info.value) or "Unsupported" in str(exc_info.value)


def test_no_extension_raises_clear_error():
    with pytest.raises(ValueError):
        parse_campaign_file(io.BytesIO(b"whatever"), "campaign")


def test_corrupted_xlsx_raises_clear_error_not_traceback():
    broken = io.BytesIO(b"this is not a real xlsx file, just plain text")

    with pytest.raises(ValueError) as exc_info:
        parse_campaign_file(broken, "campaign.xlsx")

    message = str(exc_info.value).lower()
    assert "couldn't read the file" in message


GARBAGE_VALUE_CSV = """date,channel,impressions,clicks,conversions,spend,revenue
2026-08-01,Google Ads,1000,50,5,200,800
2026-08-08,Google Ads,1200,60,6,N/A,900
"""


def test_garbage_numeric_value_does_not_crash_and_is_flagged():
    """Junk in a numeric column (text instead of a number) must not cause a
    500; it is flagged as "incomplete data", like empty values."""
    df = parse_campaign_file(io.StringIO(GARBAGE_VALUE_CSV), "campaign.csv")
    summary = compute_summary(df)
    channels = compute_channel_metrics(df)

    assert summary["total_spend"] == 200
    assert "2026-08-08" in summary["incomplete_dates"]
    # compute_channel_metrics neither crashes nor stays silent: the channel is in the result
    assert any(c["channel"] == "Google Ads" for c in channels)


# --- Alternative column name recognition ---
# (common Google/Meta/LinkedIn Ads exports name the same fields differently)

ALIAS_HEADER_CSV = """Day,Platform,Impr.,Clicks (all),Conv.,Cost,Conv. value
2026-08-01,Google Ads,1000,50,5,200,800
2026-08-08,Google Ads,1200,60,6,220,900
"""


def test_alternate_column_names_are_recognized():
    df = parse_campaign_file(io.StringIO(ALIAS_HEADER_CSV), "campaign.csv")
    summary = compute_summary(df)

    assert summary["total_impressions"] == 2200
    assert summary["total_spend"] == 420
    assert summary["total_revenue"] == 1700


def test_alternate_column_names_are_reported_in_mapping():
    df = parse_campaign_file(io.StringIO(ALIAS_HEADER_CSV), "campaign.csv")
    summary = compute_summary(df)

    mapping = summary["column_mapping"]
    assert mapping["date"] == "Day"
    assert mapping["channel"] == "Platform"
    assert mapping["spend"] == "Cost"
    assert mapping["revenue"] == "Conv. value"


def test_canonical_column_already_present_is_not_overridden():
    """If the file already has a correctly named column, an alias with the same
    meaning (should one also appear) doesn't replace it; no mapping is created
    for it, since there is nothing to rename."""
    df = parse_campaign_file(io.StringIO(VALID_CSV), "campaign.csv")
    summary = compute_summary(df)

    assert summary["column_mapping"] == {}


def test_unrecognized_columns_still_raise_honest_missing_column_error():
    """If a column name is neither canonical nor a known alias, no data is
    filled in and the honest error stays, as before."""
    unknown_header_csv = (
        "SomeDate,SomeChannel,impressions,clicks,conversions,spend,revenue\n"
        "2026-08-01,Google Ads,1000,50,5,200,800\n"
    )
    df = parse_campaign_file(io.StringIO(unknown_header_csv), "campaign.csv")
    with pytest.raises(ValueError) as exc_info:
        compute_summary(df)

    assert "date" in str(exc_info.value)
