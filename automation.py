"""网页自动化示例（Playwright）：打开页面 → 抓取内容 → 存 CSV。

首次使用：
    pip install -r requirements.txt
    playwright install chromium

运行：
    python automation.py                 # 默认抓取 example.com
    python automation.py <url> <out.csv>
"""

import csv
import sys
from pathlib import Path


def crawl(url: str, out_csv: str, limit: int = 20) -> Path:
    from playwright.sync_api import sync_playwright

    rows: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        title = page.title()
        links = page.eval_on_selector_all(
            "a",
            "els => els.slice(0, 200).map(e => ({text: (e.innerText || '').trim(), href: e.href}))",
        )
        for item in links:
            if not item["text"]:
                continue
            rows.append({"page_title": title, "text": item["text"], "href": item["href"]})
            if len(rows) >= limit:
                break
        browser.close()

    path = Path(out_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fp:  # utf-8-sig 让 Excel 不乱码
        writer = csv.DictWriter(fp, fieldnames=["page_title", "text", "href"])
        writer.writeheader()
        writer.writerows(rows)
    return path


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    out = sys.argv[2] if len(sys.argv) > 2 else "data/links.csv"
    result = crawl(url, out)
    print(f"已保存 {result}")
