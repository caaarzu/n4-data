#!/usr/bin/env python3
"""ナンバーズ4 当せん番号を取得して docs/data.json を差分更新するスクリプト (v2)。

v1からの変更点:
- みずほ銀行/宝くじ公式サイトは当せん番号をJavaScriptで描画するため、
  Playwright(ヘッドレスChromium)でページを完全レンダリングしてから抽出する方式に変更。
- 誤抽出防止を強化: 「抽せん日(日付)」が同一ブロック内に存在する回のみ採用。
"""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA_PATH = Path(__file__).resolve().parent.parent / "docs" / "data.json"

SOURCES = [
    # みずほ銀行 ナンバーズ4 当せん番号案内(直近分)
    "https://www.mizuhobank.co.jp/takarakuji/check/numbers/numbers4/index.html",
    # 宝くじ公式サイト(フォールバック)
    "https://www.takarakuji-official.jp/ec/numbers4/",
]

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 n4quant-personal-sync/2.0"

DATE_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")
NUM4_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def get_rendered_text(url: str) -> str:
    """ヘッドレスChromiumでJS描画完了後のページ本文テキストを取得する。"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=UA)
        page.goto(url, wait_until="networkidle", timeout=60_000)
        # 描画完了の目印(「当せん番号」の文言)を待つ。出なくても本文取得は続行
        try:
            page.wait_for_selector("text=当せん番号", timeout=20_000)
        except Exception:
            pass
        page.wait_for_timeout(2_000)  # 遅延描画の保険
        text = page.inner_text("body")
        browser.close()
    return re.sub(r"\s+", " ", text)


def extract(text: str) -> list[dict]:
    """「第○回」ブロック単位で抽せん日と4桁番号を抽出する。

    誤抽出防止のため、ブロック内に「YYYY年M月D日」形式の日付が
    存在する回のみを有効データとして採用する(ナビゲーションリンク等の
    「第1回〜第20回」のような文字列を除外するため)。
    """
    results = []
    parts = re.split(r"(第\s*\d{3,5}\s*回)", text)
    for i in range(1, len(parts) - 1, 2):
        m = re.search(r"(\d{3,5})", parts[i])
        if not m:
            continue
        rnd = int(m.group(1))
        block = parts[i + 1][:400]

        dm = DATE_RE.search(block)
        if not dm:
            continue  # 日付なし=ナビ等の誤マッチとして棄却
        year = dm.group(1)
        date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

        cands = NUM4_RE.findall(block)
        number = next((c for c in cands if c != year), cands[0] if cands else None)
        if number:
            results.append({"round": rnd, "date": date, "number": number})
    return results


def main() -> None:
    existing = []
    if DATA_PATH.exists():
        try:
            existing = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    by_round = {int(x["round"]): dict(x) for x in existing if "round" in x}

    scraped: list[dict] = []
    for url in SOURCES:
        try:
            text = get_rendered_text(url)
            scraped = extract(text)
            if scraped:
                print(f"[ok] {url}: {len(scraped)}件抽出")
                break
            # デバッグ用に本文の先頭を出力(構造変化の調査に使う)
            print(f"[warn] {url}: 抽出0件。本文冒頭: {text[:300]}")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {url}: {e}")
        time.sleep(2)

    if not scraped:
        print("[error] 全ソースで抽出に失敗しました。上のログの本文冒頭を確認してください。")
        sys.exit(1)

    added = 0
    for x in scraped:
        r = int(x["round"])
        if r in by_round:
            if by_round[r].get("number") != x["number"]:
                print(f"[warn] 第{r}回: 既存({by_round[r].get('number')}) と 取得({x['number']}) が不一致。既存を保持")
            elif x.get("date") and not by_round[r].get("date"):
                by_round[r]["date"] = x["date"]
        else:
            by_round[r] = x
            added += 1

    merged = [by_round[k] for k in sorted(by_round)]
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"[done] 新規 {added} 件 / 合計 {len(merged)} 件 -> {DATA_PATH}")


if __name__ == "__main__":
    main()
