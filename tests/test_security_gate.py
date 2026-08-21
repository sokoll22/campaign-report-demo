"""
Демка публичная (нет логина), а с ANTHROPIC_API_KEY на сервере каждый вызов —
реальные деньги. Добавлено 21.08.2026 после того, как Макс спросил, что будет,
если демку без него найдёт и начнёт крутить кто-то посторонний: раньше факта
наличия ключа на сервере хватало, чтобы ЛЮБОЙ посетитель, загрузивший файл,
включил платный режим.

Эти тесты фиксируют контракт: живой режим (allow_llm=True в generate_report)
включается ТОЛЬКО когда форма несёт верный DEMO_ACCESS_TOKEN в скрытом поле
demo_key — само наличие ANTHROPIC_API_KEY на сервере недостаточно.
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
    importlib.reload(appmod)  # подхватить переменные окружения из monkeypatch

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
    """MAX_CONTENT_LENGTH (добавлено 21.08.2026): раньше загрузка файла не
    имела предела размера вообще — любой посетитель мог занять память
    бесплатного инстанса на Render большим файлом. Тело больше 5 МБ должно
    быть отклонено с понятной ошибкой, а не дойти до парсинга."""
    web, calls = client
    big_csv = CSV + ("2026-08-02,Google,1,1,1,1,1\n" * 400_000)  # заметно больше 5 МБ
    assert len(big_csv) > 5 * 1024 * 1024

    r = web.post(
        "/analyze",
        data={"csv_file": (io.BytesIO(big_csv.encode()), "big.csv"), "demo_key": "s3cr3t"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 413
    assert "too large" in r.get_data(as_text=True)
    assert calls == []  # до generate_report даже не дошло
