import argparse
import html
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import feedparser
import markdown
import requests
from openai import OpenAI
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")
ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"

ZH = {
    "morning": "\u65e9\u62a5",
    "evening": "\u665a\u62a5",
    "weekdays": [
        "\u661f\u671f\u4e00",
        "\u661f\u671f\u4e8c",
        "\u661f\u671f\u4e09",
        "\u661f\u671f\u56db",
        "\u661f\u671f\u4e94",
        "\u661f\u671f\u516d",
        "\u661f\u671f\u65e5",
    ],
    "current_date": "\u5f53\u524d\u65e5\u671f",
    "weekday": "\u661f\u671f",
    "coverage": "\u62a5\u544a\u8986\u76d6\u65f6\u95f4",
    "next_update": "\u4e0b\u6b21\u66f4\u65b0\u65f6\u95f4",
    "next_coverage": "\u4e0b\u6b21\u8986\u76d6\u65f6\u95f4\u8303\u56f4",
    "toc": "\u6298\u53e0\u76ee\u5f55",
    "back_top": "\u8fd4\u56de\u9876\u90e8",
    "generated": "\U0001f4c1 \u5df2\u751f\u6210\u6587\u4ef6",
}

ITEM_STRUCTURE = [
    "\u3010\u53d1\u751f\u4e86\u4ec0\u4e48\u3011",
    "\u3010\u4e3a\u4ec0\u4e48\u91cd\u8981\u3011",
    "\u3010\u5f71\u54cd\u8c01\u3011",
    "\u3010\u5229\u597d/\u5229\u7a7a\u3011",
    "\u3010\u672a\u6765\u53ef\u80fd\u6f14\u5316\u3011",
    "\u3010\u6211\u5e94\u8be5\u5173\u6ce8\u4ec0\u4e48\u3011",
]

FINAL_SECTIONS = [
    "\u2605 \u4eca\u65e5\u6700\u91cd\u89813\u4ef6\u4e8b",
    "\u2605 \u672c\u5468\u6700\u503c\u5f97\u8ddf\u8e2a3\u4ef6\u4e8b",
    "\u2605 \u672a\u676530\u5929\u6700\u5927\u6f5c\u5728\u673a\u4f1a",
    "\u2605 \u672a\u676530\u5929\u6700\u5927\u6f5c\u5728\u98ce\u9669",
]

RISK_LABELS = "\U0001f7e2\u5229\u597d / \U0001f534\u5229\u7a7a / \U0001f7e1\u4e2d\u6027"


@dataclass
class ReportWindow:
    report_type: str
    label: str
    date: datetime
    start: datetime
    end: datetime
    next_update: datetime
    next_start: datetime
    next_end: datetime


SOURCE_DOMAINS = [
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "nikkei.com",
    "ft.com",
    "xinhuanet.com",
    "caixin.com",
    "yicai.com",
    "openai.com",
    "anthropic.com",
    "deepmind.google",
    "nvidia.com",
    "x.ai",
]

RSS_FEEDS = [
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.cnbc.com/id/19854910/device/rss/rss.html",
    "https://www.ft.com/?format=rss",
    "https://www.nvidia.com/en-us/about-nvidia/blog/rss/",
    "https://openai.com/news/rss.xml",
    "https://www.anthropic.com/news/rss.xml",
]

KEY_QUERIES = [
    "SoftBank OR 9984 OR Arm AI",
    "Kioxia OR 285A OR NAND OR HBM OR memory chip",
    "Murata OR 6981 OR electronic components",
    "Musashi Seimitsu OR 7220 OR automotive parts",
    "SpaceX OR Starlink OR SPCX",
    "Micron OR MU OR HBM OR DRAM",
    "AI OR artificial intelligence OR NVIDIA OR OpenAI OR Anthropic OR DeepMind OR xAI",
    "Japan economy OR Bank of Japan OR yen OR Tokyo real estate",
    "China policy OR US China economy OR tariffs",
    "Federal Reserve OR US stocks OR Nasdaq OR Treasury yields",
    "oil OR Middle East OR geopolitical risk OR Olympics OR World Cup",
]


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def weekday_cn(dt: datetime) -> str:
    return ZH["weekdays"][dt.weekday()]


def get_window(report_type: str) -> ReportWindow:
    now = datetime.now(JST)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if report_type == "morning":
        start = (today - timedelta(days=1)).replace(hour=21, minute=30)
        end = today.replace(hour=8)
        next_update = today.replace(hour=21, minute=30)
        next_start = today.replace(hour=8)
        next_end = today.replace(hour=21, minute=30)
    else:
        start = today.replace(hour=8)
        end = today.replace(hour=21, minute=30)
        next_update = (today + timedelta(days=1)).replace(hour=8)
        next_start = today.replace(hour=21, minute=30)
        next_end = (today + timedelta(days=1)).replace(hour=8)
    return ReportWindow(
        report_type=report_type,
        label=ZH[report_type],
        date=today,
        start=start,
        end=end,
        next_update=next_update,
        next_start=next_start,
        next_end=next_end,
    )


def gdelt_articles(query: str, start: datetime, end: datetime) -> list[dict]:
    start_utc = start.astimezone(UTC).strftime("%Y%m%d%H%M%S")
    end_utc = end.astimezone(UTC).strftime("%Y%m%d%H%M%S")
    domain_filter = " OR ".join(f"domain:{domain}" for domain in SOURCE_DOMAINS)
    full_query = f"({query}) ({domain_filter})"
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        f"?query={quote(full_query)}"
        f"&mode=ArtList&format=json&maxrecords=20"
        f"&startdatetime={start_utc}&enddatetime={end_utc}"
        "&sort=HybridRel"
    )
    try:
        response = requests.get(url, timeout=25)
        response.raise_for_status()
        return response.json().get("articles", []) or []
    except Exception:
        return []


def rss_articles(start: datetime, end: datetime) -> list[dict]:
    items = []
    for feed_url in RSS_FEEDS:
        parsed = feedparser.parse(feed_url)
        for entry in parsed.entries[:30]:
            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime(*entry.published_parsed[:6], tzinfo=UTC)
            if published and not (start.astimezone(UTC) <= published <= end.astimezone(UTC)):
                continue
            items.append(
                {
                    "title": getattr(entry, "title", ""),
                    "url": getattr(entry, "link", feed_url),
                    "source": parsed.feed.get("title", feed_url),
                    "published": published.isoformat() if published else "",
                    "summary": html.unescape(getattr(entry, "summary", ""))[:500],
                }
            )
    return items


def collect_candidates(window: ReportWindow) -> list[dict]:
    seen = set()
    candidates = []
    for article in rss_articles(window.start, window.end):
        url = article.get("url", "")
        if url and url not in seen:
            seen.add(url)
            candidates.append(article)
    for query in KEY_QUERIES:
        for article in gdelt_articles(query, window.start, window.end):
            url = article.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            candidates.append(
                {
                    "title": article.get("title", ""),
                    "url": url,
                    "source": article.get("domain", "") or article.get("sourceCountry", ""),
                    "published": article.get("seendate", ""),
                    "summary": article.get("snippet", "")[:500],
                }
            )
    return candidates[:120]


def build_prompt(window: ReportWindow, candidates: list[dict]) -> str:
    candidate_json = json.dumps(candidates, ensure_ascii=False, indent=2)
    item_structure = "\n".join(ITEM_STRUCTURE)
    final_sections = "\n".join(FINAL_SECTIONS)
    return f"""
You are a private Chinese-language news analyst for the user.
Write the complete report in Simplified Chinese.

User background:
- Lives in Tokyo, Japan.
- Works in Japanese real estate.
- Cares about AI, creator/media opportunities, and investing.
- Key holdings: SoftBank (9984), Kioxia (285A), Murata (6981), Musashi Seimitsu (7220), SpaceX (SPCX), Micron Technology (MU).

Report metadata:
- {ZH["current_date"]}: {window.date.strftime("%Y-%m-%d")}
- {ZH["weekday"]}: {weekday_cn(window.date)}
- {ZH["coverage"]}: {fmt_dt(window.start)} - {fmt_dt(window.end)} (Japan time)
- {ZH["next_update"]}: {fmt_dt(window.next_update)} (Japan time)
- {ZH["next_coverage"]}: {fmt_dt(window.next_start)} - {fmt_dt(window.next_end)} (Japan time)

Source priority:
1. Reuters, Bloomberg, CNBC, Nikkei, Financial Times.
2. Xinhua, Caixin, Yicai.
3. OpenAI, Anthropic, Google DeepMind, NVIDIA, xAI official news.

Selection rules:
- Do not list news mechanically.
- Keep only items that affect global markets, AI, US/China/Japan economies, real estate, the user's holdings, world-level major events, startup opportunities, or creator/media opportunities.
- Remove celebrity gossip, entertainment, minor sports gossip, and sensational crime.
- Keep World Cup, Olympics, and other major global sports events.
- Priority order: holdings, AI industry, Japan economy, US tech stocks, China policy, world events, major sports.
- Keep only the top 10-20 items if there is too much news. Do not add filler.
- Put ordinary news unrelated to the holdings near the end.
- Avoid repeating yesterday's report unless there is a major update.

For every news item, use this exact structure:
{item_structure}
For the sentiment/risk line, use one of these exact labels: {RISK_LABELS}

At the end, include:
{final_sections}

Output rules:
- Return Markdown only. No code block.
- Start with the metadata lines.
- Use second-level headings for news items.
- Include source links in the body. Do not invent links outside the candidate list.
- End with the next update time and next coverage window.

Candidate news:
{candidate_json}
""".strip()


def generate_markdown(window: ReportWindow, candidates: list[dict]) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required.")
    model = os.environ.get("OPENAI_MODEL", "").strip() or "gpt-4.1-mini"
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input=build_prompt(window, candidates),
        temperature=0.2,
    )
    text = response.output_text.strip()
    if not text:
        raise SystemExit("OpenAI returned an empty report.")
    return text


def add_html_shell(title: str, markdown_text: str) -> str:
    body = markdown.markdown(
        markdown_text,
        extensions=["toc", "tables", "sane_lists"],
        extension_configs={"toc": {"permalink": True, "title": ZH["toc"]}},
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f7f4;
      --paper: #ffffff;
      --text: #202124;
      --muted: #646a73;
      --line: #d9ddd3;
      --accent: #245c4f;
      --shadow: 0 8px 28px rgba(0,0,0,.08);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #111411;
        --paper: #1a1e1a;
        --text: #ecefe7;
        --muted: #aeb6aa;
        --line: #343b34;
        --accent: #8fd4c0;
        --shadow: none;
      }}
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans JP", "Noto Sans SC", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.68;
    }}
    main {{
      width: min(980px, calc(100% - 28px));
      margin: 0 auto;
      padding: 28px 0 36px;
    }}
    h1 {{ margin: 0 0 14px; font-size: clamp(28px, 6vw, 44px); line-height: 1.12; letter-spacing: 0; }}
    h2, h3 {{ letter-spacing: 0; line-height: 1.32; }}
    h2 {{ margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--line); font-size: 22px; }}
    p, li {{ font-size: 16px; }}
    a {{ color: var(--accent); text-decoration: none; border-bottom: 1px solid color-mix(in srgb, var(--accent), transparent 60%); }}
    .toc {{
      margin: 18px 0;
      padding: 14px 18px;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    article {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px;
    }}
    .top {{
      position: fixed;
      right: 16px;
      bottom: 16px;
      width: 44px;
      height: 44px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: var(--accent);
      color: var(--bg);
      text-decoration: none;
      font-weight: 800;
      border: 0;
    }}
    @media (max-width: 620px) {{
      main {{ width: min(100% - 20px, 980px); }}
      article {{ padding: 15px; }}
      h2 {{ font-size: 19px; }}
    }}
  </style>
</head>
<body id="top">
  <main><article>{body}</article></main>
  <a class="top" href="#top" aria-label="{ZH["back_top"]}">&uarr;</a>
  <script>
    const toc = document.querySelector('.toc');
    if (toc) {{
      const details = document.createElement('details');
      details.className = 'toc';
      details.open = true;
      const summary = document.createElement('summary');
      summary.textContent = '{ZH["toc"]}';
      details.append(summary, ...toc.childNodes);
      toc.replaceWith(details);
    }}
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["morning", "evening"], required=True)
    args = parser.parse_args()

    window = get_window(args.type)
    OUTPUTS.mkdir(exist_ok=True)
    candidates = collect_candidates(window)
    markdown_text = generate_markdown(window, candidates)

    date_prefix = window.date.strftime("%Y-%m-%d")
    md_path = OUTPUTS / f"{date_prefix}_{window.label}.md"
    html_path = OUTPUTS / f"{date_prefix}_{window.label}.html"
    title = f"{date_prefix} {window.label}"

    md_path.write_text(markdown_text, encoding="utf-8")
    html_path.write_text(add_html_shell(title, markdown_text), encoding="utf-8")
    print(ZH["generated"])
    print(f"- {md_path.name}")
    print(f"- {html_path.name}")


if __name__ == "__main__":
    main()
