"""
Тест 1 из брифа (project-name_BRIEF.md, "Критерий готовности"):
корректный CSV -> отчёт строится с правильными суммарными показателями.
"""
import io
import pytest
from report_engine import parse_campaign_csv, compute_summary, compute_channel_metrics

VALID_CSV = """date,channel,impressions,clicks,conversions,spend,revenue
2026-08-01,Google Ads,1000,50,5,200,800
2026-08-08,Google Ads,1200,60,6,220,900
2026-08-01,Facebook Ads,800,30,2,150,300
"""


def test_compute_summary_totals():
    df = parse_campaign_csv(io.StringIO(VALID_CSV))
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
    df = parse_campaign_csv(io.StringIO(MISSING_COLUMN_CSV))
    with pytest.raises(ValueError) as exc_info:
        compute_summary(df)

    assert "spend" in str(exc_info.value)


INCOMPLETE_CSV = """date,channel,impressions,clicks,conversions,spend,revenue
2026-08-01,Google Ads,1000,50,5,200,800
2026-08-08,Google Ads,1200,60,6,,900
"""


def test_incomplete_row_does_not_crash_and_is_flagged():
    df = parse_campaign_csv(io.StringIO(INCOMPLETE_CSV))
    summary = compute_summary(df)

    # Не падаем, считаем по тому, что есть
    assert summary["total_spend"] == 200
    # И честно говорим, за какие даты данные неполные
    assert "2026-08-08" in summary["incomplete_dates"]
    assert "2026-08-01" not in summary["incomplete_dates"]


def test_empty_file_raises_clear_error():
    with pytest.raises(ValueError) as exc_info:
        parse_campaign_csv(io.StringIO(""))

    assert "empty" in str(exc_info.value).lower()


SINGLE_DATE_CSV = """date,channel,impressions,clicks,conversions,spend,revenue
2026-08-01,Google Ads,1000,50,5,200,800
"""


def test_single_date_data_has_no_trends():
    df = parse_campaign_csv(io.StringIO(SINGLE_DATE_CSV))
    summary = compute_summary(df)

    assert summary["has_trend_data"] is False


def test_multi_date_data_has_trends():
    df = parse_campaign_csv(io.StringIO(VALID_CSV))
    summary = compute_summary(df)

    assert summary["has_trend_data"] is True


CHANNEL_CSV = """date,channel,impressions,clicks,conversions,spend,revenue
2026-08-01,Google Ads,1000,50,5,200,800
2026-08-08,Google Ads,1200,60,6,220,900
2026-08-01,Facebook Ads,800,30,2,150,90
2026-08-08,Facebook Ads,900,25,1,160,80
"""


def test_channel_metrics_ranks_best_and_worst_roi():
    df = parse_campaign_csv(io.StringIO(CHANNEL_CSV))
    channels = compute_channel_metrics(df)

    by_name = {c["channel"]: c for c in channels}
    # Google Ads: spend 420, revenue 1700 -> ROI положительный и большой
    # Facebook Ads: spend 310, revenue 170 -> ROI отрицательный
    assert by_name["Google Ads"]["roi"] > by_name["Facebook Ads"]["roi"]
    assert by_name["Facebook Ads"]["roi"] < 0
