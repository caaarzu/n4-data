#!/usr/bin/env python3
"""ナンバーズ4 当せん番号を取得して docs/data.json を差分更新するスクリプト。

- 複数ソースを順に試行(1つ成功すれば終了)
- HTML構造の変化に強いよう、タグ除去後のテキストに対する正規表現で抽出
- 既存データと回号でマージ(既存優先・不一致は警告のみ)
- 出力形式: [{"round": 6800, "date": "2026-07-10", "number": "1234"}, ...]
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "docs" / "data.json"

SOURCES = [
    # みずほ銀行 ナンバーズ4 当せん番号案内
    "https://www.mizuhobank.co.jp/takarakuji/check/numbers/numbers4/index.html",
    # 宝くじ公式サイト(フォールバック)
    "https://www.takarakuji-official.jp/ec/numbers4/",
]

UA = "n4quant-personal-sync/1.0 (individual hobby use; max 1 request/day)"

DATE_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")
NUM4_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def extract(html: str) -> list[dict]:
    """タグを除去したテキストから「第○回」ブロック単位で日付と4桁番号を抽出する。"""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    results = []
    parts = re.split(r"(第\s*\d{3,5}\s*回)", text)
    for i in range(1, len(parts) - 1, 2):
        m = re.search(r"(\d{3,5})", parts[i])
        if not m:
            continue
        rnd = int(m.group(1))
        block = parts[i + 1][:400]  # 次の回の情報が混ざらないよう近傍のみ

        date = None
        year = None
        dm = DATE_RE.search(block)
        if dm:
            year = dm.group(1)
            date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

        # 4桁候補のうち、日付の西暦と同一のものは誤検出として後回しにする
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
            scraped = extract(http_get(url))
            if scraped:
                print(f"[ok] {url}: {len(scraped)}件抽出")
                break
            print(f"[warn] {url}: 抽出0件(構造変化の可能性)")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {url}: {e}")
        time.sleep(2)

    if not scraped:
        print("[error] 全ソースで抽出に失敗しました。HTML構造の変化を確認してください。")
        sys.exit(1)

    added = 0
    for x in scraped:
        r = int(x["round"])
        if r in by_round:
            # 既存データを正として保持。番号不一致は警告のみ(誤抽出による汚染防止)
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
