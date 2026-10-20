"""
The demo is public (no login), and with ANTHROPIC_API_KEY on the server every
call costs real money. Previously the mere presence of the key on the server
let ANY visitor who uploaded a file switch on paid mode.

These tests pin the contract: live mode (allow_llm=True in generate_report)
is enabled ONLY when the form carries the correct DEMO_ACCESS_TOKEN in the
hidden demo_key field; the server-side ANTHROPIC_API_KEY alone is not
enough.
"""
import io

import pytest


CSV = (
    "date,channel,impressions,clicks,conversions,spend,revenue\n"
    "2026-08-01,Google,1000,50,5,100,300\n"
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "s3cr3t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

    import importlib
    import app as appmod
    importlib.reload(appmod)  # pick up environment variables from monkeypatch

    calls = []

    def fake_generate_report(summary, channel_metrics, allow_llm=False):
        calls.append(allow_llm)
        return {
            "headline": f"allow_llm={allow_llm}",
            "insights": [],
            "recommendations": [],
            "mode": "online" if allow_llm else "offline",
        }

    monkeypatch.setattr(appmod, "generate_report", fake_generate_report)
    return appmod.app.test_client(), calls


def _upload(client, demo_key=None):
    data = {"csv_file": (io.BytesIO(CSV.encode()), "test.csv")}
    if demo_key is not None:
        data["demo_key"] = demo_key
    return client.post("/analyze", data=data, content_type="multipart/form-data")


def test_index_without_key_has_empty_hidden_field(client):
    web, _ = client
    body = web.get("/").get_data(as_text=True)
    assert 'name="demo_key" value=""' in body


def test_index_with_correct_key_fills_hidden_field(client):
    web, _ = client
    body = web.get("/?key=s3cr3t").get_data(as_text=True)
    assert 'name="demo_key" value="s3cr3t"' in body


def test_analyze_without_demo_key_disallows_llm(client):
    web, calls = client
    _upload(web, demo_key="")
    assert calls == [False]


def test_analyze_with_wrong_demo_key_disallows_llm(client):
    web, calls = client
    _upload(web, demo_key="wrong")
    assert calls == [False]


def test_analyze_with_correct_demo_key_allows_llm(client):
    web, calls = client
    _upload(web, demo_key="s3cr3t")
    assert calls == [True]


def test_oversized_upload_is_rejected_before_touching_memory(client):
    """MAX_CONTENT_LENGTH: uploads used to have no size limit at all, so any
    visitor could exhaust the memory of the free Render instance with a big
    file. A body over 5 MB must be rejected with a clear error instead of
    reaching the parser."""
    web, calls = client
    big_csv = CSV + ("2026-08-02,Google,1,1,1,1,1\n" * 400_000)  # well over 5 MB
    assert len(big_csv) > 5 * 1024 * 1024

    r = web.post(
        "/analyze",
        data={"csv_file": (io.BytesIO(big_csv.encode()), "big.csv"), "demo_key": "s3cr3t"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 413
    assert "too large" in r.get_data(as_text=True)
    assert calls == []  # generate_report was never reached
