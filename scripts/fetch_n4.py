#!/usr/bin/env python3
"""ナンバーズ4 当せん番号を docs/data.json に同期するスクリプト (v4)。
主ソース: hazimekom/numbers4-api (GitHub Pages静的JSON・全履歴あり)
副ソース: NUMBERS4通信 (静的HTML) ※主ソース障害時のフォールバック
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "docs" / "data.json"
API_ALL = "https://hazimekom.github.io/numbers4-api/api/v1/numbers4_all_min.json"
FALLBACK_HTML = "https://numbers4.money-plan.net/"
UA = "Mozilla/5.0 (compatible; n4quant-personal-sync/4.0; 1 req/day)"

DATE_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")
NUM4_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def fetch_api() -> list[dict]:
    arr = json.loads(http_get(API_ALL))
    out = []
    for x in arr:
        digits = x.get("digits")
        if not (isinstance(digits, list) and len(digits) == 4):
            continue
        out.append({
            "round": int(x["draw_no"]),
            "date": x.get("date"),
            "number": "".join(str(int(d)) for d in digits),
        })
    return out


def fetch_fallback() -> list[dict]:
    text = re.sub(r"<[^>]+>", " ", http_get(FALLBACK_HTML))
    text = re.sub(r"\s+", " ", text)
    results, seen = [], set()
    parts = re.split(r"(第\s*(\d{3,5})\s*回)", text)
    for i in range(1, len(parts) - 2, 3):
        rnd = int(parts[i + 1])
        block = parts[i + 2][:300]
        if rnd < 1000 or rnd in seen:
            continue
        dm = DATE_RE.search(block)
        if not dm:
            continue
        date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
        cands = NUM4_RE.findall(block)
        number = next((c for c in cands if c != dm.group(1)), None)
        if number:
            seen.add(rnd)
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
    try:
        scraped = fetch_api()
        print(f"[ok] numbers4-api: {len(scraped)}件取得")
    except Exception as e:
        print(f"[warn] numbers4-api: {e} → フォールバックへ")
        try:
            scraped = fetch_fallback()
            print(f"[ok] fallback: {len(scraped)}件抽出")
        except Exception as e2:
            print(f"[warn] fallback: {e2}")

    if not scraped:
        print("[error] 全ソースで取得に失敗しました。")
        sys.exit(1)

    added = 0
    for x in scraped:
        r = int(x["round"])
        if r in by_round:
            if by_round[r].get("number") != x["number"]:
                print(f"[warn] 第{r}回: 既存と取得が不一致。既存を保持")
        else:
            by_round[r] = x
            added += 1

    merged = [by_round[k] for k in sorted(by_round)]
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] 新規 {added} 件 / 合計 {len(merged)} 件")


if __name__ == "__main__":
    main()
