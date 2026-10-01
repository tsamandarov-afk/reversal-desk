#!/usr/bin/env python3
"""Собирает feed.json из данных демо-наблюдателя (бумажная торговля, реальных денег нет) и пушит в репозиторий."""
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

SRC = Path.home() / "polymarket-agent-site"
HERE = Path(__file__).parent


def slim(d, tf):
    bt = d.get("bt") or {}
    return dict(
        tf=tf, started=d["started"], start=d["start"], stake=d["stake"], balance=d["balance"],
        closed=d["closed"], wins=d["wins"], open=d["open"], avg_ask=d.get("avg_ask"),
        avg_fill100=d.get("avg_fill100"),
        curve=(d.get("curve") or d["live_variants"][0]["curve"])[-400:],
        coins={c: dict(n=v.get("n", 0), w=v.get("w", 0), pnl=v.get("pnl", 0), radar=v.get("radar"))
               for c, v in d["coins"].items()},
        bets=[{k: b.get(k) for k in ("coin", "t", "side", "ask", "status", "pnl", "rsi", "pb")} for b in d["bets"][:40]],
        bt=dict(wr=bt.get("wr"), trades=bt.get("trades"), breakeven=bt.get("breakeven"), max_dd=bt.get("max_dd")),
    )


def main():
    f = dict(generated=datetime.now(timezone.utc).isoformat(),
             m15=slim(json.loads((SRC / "data.json").read_text()), "15m"),
             m5=slim(json.loads((SRC / "data_5m.json").read_text()), "5m"))
    # в 5м-выгрузке нет разбивки по монетам — считаем из журнала наблюдателя (базовый пресет)
    jr = json.loads((Path.home() / "wave-paper/polymarket/journal_5m.json").read_text())
    for c, v in f["m5"]["coins"].items():
        d = [b for b in jr["bets"] if b["coin"] == c and b["status"] in ("won", "lost") and b.get("v", {}).get("base", True)]
        v.update(n=len(d), w=sum(b["status"] == "won" for b in d), pnl=round(sum(b.get("pnl") or 0 for b in d), 2))
    (HERE / "feed.json").write_text(json.dumps(f, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if "--push" in sys.argv:
        g = lambda *a: subprocess.run(["git", "-C", str(HERE), *a], capture_output=True, text=True)
        g("add", "feed.json")
        if "nothing to commit" not in g("commit", "-m", f"feed {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC").stdout:
            g("push", "-q", "origin", "HEAD")


main()
