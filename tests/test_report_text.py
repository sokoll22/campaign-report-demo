"""
generate_report(): offline templates and parsing of Claude's JSON response in
online mode.

Regression found while adding the demo token (see test_security_gate.py): the
online branch returned headline/insights/recommendations as None (the model
wrote free text into raw_text, which nothing parsed), and index.html's
`{% for line in result.report.insights %}` would have crashed on the first
real run. Rewritten to a structured JSON response, with a fallback to offline
text if the model still returns invalid JSON, instead of crashing the page or
silently returning an empty report.
"""
import sys
import types

import pytest

from report_text import generate_report

SUMMARY = {"total_spend": 100.0, "total_revenue": 300.0, "incomplete_dates": []}
CHANNELS = [{"channel": "Google", "spend": 100.0, "revenue": 300.0, "roi": 2.0, "ctr": 0.05}]


def _fake_anthropic(monkeypatch, response_text):
    """Replace the anthropic module with a stub that returns the given text,
    without making a real network call."""

    class FakeContent:
        def __init__(self, text):
            self.text = text

    class FakeMessage:
        def __init__(self, text):
            self.content = [FakeContent(text)]

    class FakeMessages:
        def create(self, **kwargs):
            return FakeMessage(response_text)

    class FakeClient:
        def __init__(self, api_key=None):
            self.messages = FakeMessages()

    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)


def test_allow_llm_false_returns_offline_without_network(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    result = generate_report(SUMMARY, CHANNELS, allow_llm=False)
    assert result["mode"] == "offline"
    assert result["insights"]  # non-empty list: the offline template worked


def test_no_api_key_returns_offline_even_if_allow_llm_true(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = generate_report(SUMMARY, CHANNELS, allow_llm=True)
    assert result["mode"] == "offline"


def test_allow_llm_true_parses_valid_json_response(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    _fake_anthropic(
        monkeypatch,
        '{"headline": "h", "insights": ["i1", "i2"], "recommendations": ["r1"]}',
    )
    result = generate_report(SUMMARY, CHANNELS, allow_llm=True)
    assert result["mode"] == "online"
    assert result["headline"] == "h"
    assert result["insights"] == ["i1", "i2"]
    assert result["recommendations"] == ["r1"]


def test_allow_llm_true_strips_markdown_json_fence(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    _fake_anthropic(
        monkeypatch,
        '```json\n{"headline": "h2", "insights": ["x"], "recommendations": ["y"]}\n```',
    )
    result = generate_report(SUMMARY, CHANNELS, allow_llm=True)
    assert result["mode"] == "online"
    assert result["headline"] == "h2"


def test_invalid_json_response_falls_back_to_offline_without_crashing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    _fake_anthropic(monkeypatch, "not json at all")
    result = generate_report(SUMMARY, CHANNELS, allow_llm=True)
    assert result["mode"].startswith("offline")
    assert result["insights"]  # real offline content, not None/empty
