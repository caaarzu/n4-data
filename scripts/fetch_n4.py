#!/usr/bin/env python3
"""ナンバーズ4 当せん番号+実配当を docs/data.json に同期するスクリプト (v5)。
主ソース: hazimekom/numbers4-api の numbers4_all_full.json (全履歴+実配当)
副ソース: NUMBERS4通信 (静的HTML・配当なし) ※主ソース障害時のフォールバック
data.json 形式: [{"round":7024,"date":"2026-07-10","number":"0430","ps":654400,"pb":54500}]
  ps=ストレート実配当, pb=ボックス実配当 (取得できた回のみ)
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "docs" / "data.json"
API_FULL = "https://hazimekom.github.io/numbers4-api/api/v1/numbers4_all_full.json"
API_MIN = "https://hazimekom.github.io/numbers4-api/api/v1/numbers4_all_min.json"
FALLBACK_HTML = "https://numbers4.money-plan.net/"
UA = "Mozilla/5.0 (compatible; n4quant-personal-sync/5.0; 1 req/day)"

DATE_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")
NUM4_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="ignore")


def to_rec(x: dict) -> dict | None:
    digits = x.get("digits")
    if not (isinstance(digits, list) and len(digits) == 4):
        return None
    rec = {
        "round": int(x["draw_no"]),
        "date": x.get("date"),
        "number": "".join(str(int(d)) for d in digits),
    }
    prize = x.get("prize") or {}
    ps = prize.get("straight")
    pb = prize.get("box")
    if isinstance(ps, (int, float)) and ps > 0:
        rec["ps"] = int(ps)
    if isinstance(pb, (int, float)) and pb > 0:
        rec["pb"] = int(pb)
    return rec


def fetch_api() -> list[dict]:
    try:
        arr = json.loads(http_get(API_FULL))
        src = "full(配当あり)"
    except Exception as e:
        print(f"[warn] all_full 取得失敗: {e} → all_min にフォールバック")
        arr = json.loads(http_get(API_MIN))
        src = "min(配当なし)"
    out = [r for r in (to_rec(x) for x in arr) if r]
    print(f"[ok] numbers4-api {src}: {len(out)}件")
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
    except Exception as e:
        print(f"[warn] numbers4-api: {e} → HTMLフォールバックへ")
        try:
            scraped = fetch_fallback()
            print(f"[ok] fallback: {len(scraped)}件抽出")
        except Exception as e2:
            print(f"[warn] fallback: {e2}")

    if not scraped:
        print("[error] 全ソースで取得に失敗しました。")
        sys.exit(1)

    added = enriched = 0
    for x in scraped:
        r = int(x["round"])
        cur = by_round.get(r)
        if cur is None:
            by_round[r] = x
            added += 1
            continue
        # 番号の不一致は警告のみ(既存優先)。欠損フィールドは補完。
        if cur.get("number") != x["number"]:
            print(f"[warn] 第{r}回: 既存と取得が不一致。既存を保持")
            continue
        changed = False
        for k in ("date", "ps", "pb"):
            if x.get(k) and not cur.get(k):
                cur[k] = x[k]
                changed = True
        if changed:
            by_round[r] = cur
            enriched += 1

    merged = [by_round[k] for k in sorted(by_round)]
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    ps_count = sum(1 for x in merged if x.get("ps"))
    print(f"[done] 新規 {added} / 配当補完 {enriched} / 合計 {len(merged)}件 (実配当 {ps_count}件)")


if __name__ == "__main__":
    main()
