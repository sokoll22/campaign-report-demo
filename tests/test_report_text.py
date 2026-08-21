"""
generate_report(): офлайн-шаблоны и парсинг JSON-ответа Claude в онлайн-режиме.

Найдено 21.08.2026 при добавлении demo-токена (см. test_security_gate.py):
онлайн-ветка возвращала headline/insights/recommendations как None (модель
писала свободным текстом в raw_text, который никто дальше не разбирал) —
шаблон index.html делает `{% for line in result.report.insights %}` и упал бы
на первом же реальном прогоне. Переписано на структурированный JSON-ответ
с честным откатом на офлайн-текст, если модель всё-таки не вернула валидный
JSON — вместо падения страницы или тихой выдачи пустого отчёта.
"""
import sys
import types

import pytest

from report_text import generate_report

SUMMARY = {"total_spend": 100.0, "total_revenue": 300.0, "incomplete_dates": []}
CHANNELS = [{"channel": "Google", "spend": 100.0, "revenue": 300.0, "roi": 2.0, "ctr": 0.05}]


def _fake_anthropic(monkeypatch, response_text):
    """Подменяет модуль anthropic на стаб, который возвращает заданный текст,
    не делая реального сетевого вызова."""

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
    assert result["insights"]  # непустой список — офлайн-шаблон сработал


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
    assert result["insights"]  # честный офлайн-контент, а не None/пусто
