import os

from flask import Flask, request, render_template

from report_engine import parse_campaign_file, compute_summary, compute_channel_metrics
from report_text import generate_report

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", error=None, result=None)


@app.route("/analyze", methods=["POST"])
def analyze():
    file = request.files.get("csv_file")
    if not file or file.filename == "":
        return render_template(
            "index.html",
            error="Please upload a CSV or Excel file (.csv, .xlsx, .xls).",
            result=None,
        )

    try:
        df = parse_campaign_file(file.stream, file.filename)
        summary = compute_summary(df)
        channel_metrics = compute_channel_metrics(df)
        report = generate_report(summary, channel_metrics)
    except ValueError as e:
        return render_template("index.html", error=str(e), result=None)
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
        )

    return render_template(
        "index.html",
        error=None,
        result={"summary": summary, "channels": channel_metrics, "report": report},
    )


if __name__ == "__main__":
    # debug=True даёт удалённое выполнение кода через встроенный дебаггер —
    # опасно, если страница когда-нибудь окажется доступна не только с
    # localhost. По умолчанию выключено, включается явно через переменную
    # окружения только для локальной разработки.
    debug_mode = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=5002, debug=debug_mode)
