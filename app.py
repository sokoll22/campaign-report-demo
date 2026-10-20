import hmac
import os

from flask import Flask, request, render_template

from report_engine import parse_campaign_file, compute_summary, compute_channel_metrics
from report_text import generate_report, analyze_mismatched_document

app = Flask(__name__)

# Cap on upload size. The page is public, so without a limit anyone could send
# a huge file and exhaust the memory of the free Render instance. Flask aborts
# reading the request body once it exceeds this size (before the whole file is
# in memory) and returns 413; the handler below turns that into a readable
# message. 5 MB leaves plenty of room for a real campaign CSV/Excel file.
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


@app.errorhandler(413)
def _file_too_large(_error):
    # The request body may have been cut off mid-way, so don't read
    # request.form here (demo_key itself may be missing). Return a plain error
    # without carrying over the unlock state.
    return render_template(
        "index.html",
        error="That file is too large — 5 MB max. Trim it or use a smaller sample.",
        result=None,
        doc_analysis=None,
        unlocked=False,
        demo_key="",
    ), 413

# Secret demo-access token. The page is public, and a server-side
# ANTHROPIC_API_KEY alone used to let ANY visitor who uploaded a file trigger
# a paid Claude call. Live mode now also requires this token, passed as ?key=...
# in the demo link and kept in a hidden form field on submit.
DEMO_ACCESS_TOKEN = os.environ.get("DEMO_ACCESS_TOKEN", "")


def _check_token(token: str) -> bool:
    """Constant-time comparison. An empty or wrong DEMO_ACCESS_TOKEN on the
    server disables live mode entirely, which is the safe default if the
    token was never configured."""
    return bool(DEMO_ACCESS_TOKEN) and hmac.compare_digest(token or "", DEMO_ACCESS_TOKEN)


@app.route("/", methods=["GET"])
def index():
    unlocked = _check_token(request.args.get("key", ""))
    return render_template(
        "index.html",
        error=None,
        result=None,
        doc_analysis=None,
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
            doc_analysis=None,
            unlocked=unlocked,
            demo_key=demo_key,
        )

    try:
        df = parse_campaign_file(file.stream, file.filename)
    except ValueError as e:
        # The file couldn't be read at all (unsupported format, empty,
        # corrupted): there is no df to analyze, only the error message.
        return render_template(
            "index.html", error=str(e), result=None, doc_analysis=None,
            unlocked=unlocked, demo_key=demo_key,
        )
    except Exception:
        app.logger.exception("Unexpected error while reading the file")
        return render_template(
            "index.html",
            error="Something went wrong while reading the file. Please try "
            "again or use a different file.",
            result=None,
            doc_analysis=None,
            unlocked=unlocked,
            demo_key=demo_key,
        )

    try:
        summary = compute_summary(df)
        channel_metrics = compute_channel_metrics(df)
        report = generate_report(summary, channel_metrics, allow_llm=unlocked)
    except ValueError as e:
        # The file was read (df exists) but lacks the required campaign
        # columns: not a broken file, just the wrong document. In live mode
        # (valid demo token + server key) show a short AI description of what
        # the document is instead of a bare error. Live mode only: otherwise
        # just the error message, with no made-up analysis.
        doc_analysis = None
        if unlocked:
            doc_analysis = analyze_mismatched_document(df, allow_llm=unlocked)
        return render_template(
            "index.html", error=str(e), result=None, doc_analysis=doc_analysis,
            unlocked=unlocked, demo_key=demo_key,
        )
    except Exception:
        # Safety net: any unexpected (non-ValueError) error must not show the
        # user a bare 500 or traceback, only a readable message. The error
        # itself goes to the server log.
        app.logger.exception("Unexpected error while building the report")
        return render_template(
            "index.html",
            error="Something went wrong while building the report. Please try "
            "again or use a different file.",
            result=None,
            doc_analysis=None,
            unlocked=unlocked,
            demo_key=demo_key,
        )

    return render_template(
        "index.html",
        error=None,
        result={"summary": summary, "channels": channel_metrics, "report": report},
        doc_analysis=None,
        unlocked=unlocked,
        demo_key=demo_key,
    )


if __name__ == "__main__":
    # debug=True exposes remote code execution via the built-in debugger,
    # which is dangerous if the app is ever reachable beyond localhost. Off by
    # default; enabled explicitly through an environment variable for local
    # development only.
    debug_mode = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=5002, debug=debug_mode)
