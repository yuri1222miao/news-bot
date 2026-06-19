import argparse
import os
from datetime import datetime
from pathlib import Path

import requests
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
LABELS = {"morning": "\u65e9\u62a5", "evening": "\u665a\u62a5"}


def report_files(report_type: str) -> tuple[Path, Path]:
    today = datetime.now(JST).strftime("%Y-%m-%d")
    label = LABELS[report_type]
    return OUTPUTS / f"{today}_{label}.md", OUTPUTS / f"{today}_{label}.html"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["morning", "evening"], required=True)
    args = parser.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required.")

    md, html = report_files(args.type)
    missing = [str(path) for path in (md, html) if not path.exists()]
    if missing:
        raise SystemExit(f"Missing report files: {missing}")

    base = f"https://api.telegram.org/bot{token}"
    text = f"\U0001f4c1 \u5df2\u751f\u6210\u6587\u4ef6\n- {md.name}\n- {html.name}"
    response = requests.post(
        f"{base}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    response.raise_for_status()

    for file_path in (md, html):
        with file_path.open("rb") as handle:
            response = requests.post(
                f"{base}/sendDocument",
                data={"chat_id": chat_id},
                files={"document": (file_path.name, handle)},
                timeout=60,
            )
        response.raise_for_status()


if __name__ == "__main__":
    main()
