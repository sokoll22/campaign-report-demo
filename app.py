import hmac
import os

from flask import Flask, request, render_template

from report_engine import parse_campaign_file, compute_summary, compute_channel_metrics
from report_text import generate_report

app = Flask(__name__)

# Ограничение на размер загружаемого файла (добавлено 21.08.2026). Страница
# публичная и раньше не имела вообще никакого предела — кто угодно мог
# отправить огромный файл и занять память бесплатного инстанса на Render.
# Flask сам обрывает приём тела запроса, как только оно превышает этот размер
# (до того, как файл целиком попадёт в память) и возвращает 413 — обработчик
# ниже превращает это в понятную фразу на странице, а не голую ошибку.
# 5 МБ — с большим запасом на реальный CSV/Excel с кампаниями, но не позволяет
# залить что-то по-настоящему большое.
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


@app.errorhandler(413)
def _file_too_large(_error):
    # Тело запроса могло оборваться на середине, поэтому не пытаемся читать
    # request.form здесь (сам demo_key мог не долиститься) — просто честная
    # ошибка, без сохранения unlock-состояния для этого конкретного ответа.
    return render_template(
        "index.html",
        error="That file is too large — 5 MB max. Trim it or use a smaller sample.",
        result=None,
        unlocked=False,
        demo_key="",
    ), 413

# Секретный параметр демо-доступа (добавлено 21.08.2026). Страница публичная,
# и без этого одного факта наличия ANTHROPIC_API_KEY на Render хватало, чтобы
# ЛЮБОЙ загрузивший файл посетитель запускал платный вызов Claude. Теперь
# живой режим требует ещё и токен, известный только Максу — передаётся через
# ?key=... в ссылке на демку и держится в скрытом поле формы при отправке.
DEMO_ACCESS_TOKEN = os.environ.get("DEMO_ACCESS_TOKEN", "")


def _check_token(token: str) -> bool:
    """Сравнение постоянного времени. Пустой/неверный DEMO_ACCESS_TOKEN на
    сервере — живой режим выключен вообще, это безопасный вариант по
    умолчанию, если Макс забыл его задать в Render."""
    return bool(DEMO_ACCESS_TOKEN) and hmac.compare_digest(token or "", DEMO_ACCESS_TOKEN)


@app.route("/", methods=["GET"])
def index():
    unlocked = _check_token(request.args.get("key", ""))
    return render_template(
        "index.html",
        error=None,
        result=None,
        unlocked=unlocked,
        demo_key=request.args.get("key", "") if unlocked else "",
    )


@app.route("/analyze", methods=["POST"])
def analyze():
    unlocked = _check_token(request.form.get("demo_key", ""))
    demo_key = request.form.get("demo_key", "") if unlocked else ""

    file = request.files.get("csv_file")
    if not file or file.filename == "":
        return render_template(
            "index.html",
            error="Please upload a CSV or Excel file (.csv, .xlsx, .xls).",
            result=None,
            unlocked=unlocked,
            demo_key=demo_key,
        )

    try:
        df = parse_campaign_file(file.stream, file.filename)
        summary = compute_summary(df)
        channel_metrics = compute_channel_metrics(df)
        report = generate_report(summary, channel_metrics, allow_llm=unlocked)
    except ValueError as e:
        return render_template(
            "index.html", error=str(e), result=None,
            unlocked=unlocked, demo_key=demo_key,
        )
    except Exception:
        # Подстраховка: любая непредвиденная ошибка (не ValueError) не должна
        # показывать пользователю голый 500 или трейсбек — только понятную
        # фразу. Сама ошибка уходит в лог сервера для разбора.
        app.logger.exception("Unexpected error while building the report")
        return render_template(
            "index.html",
            error="Something went wrong while building the report. Please try "
            "again or use a different file.",
            result=None,
            unlocked=unlocked,
            demo_key=demo_key,
        )

    return render_template(
        "index.html",
        error=None,
        result={"summary": summary, "channels": channel_metrics, "report": report},
        unlocked=unlocked,
        demo_key=demo_key,
    )


if __name__ == "__main__":
    # debug=True даёт удалённое выполнение кода через встроенный дебаггер —
    # опасно, если страница когда-нибудь окажется доступна не только с
    # localhost. По умолчанию выключено, включается явно через переменную
    # окружения только для локальной разработки.
    debug_mode = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=5002, debug=debug_mode)
