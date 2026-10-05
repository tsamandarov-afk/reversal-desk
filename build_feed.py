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
               for c, v in d["coins"].items() if c != "ZEC"},
        bets=[{k: b.get(k) for k in ("coin", "t", "side", "ask", "status", "pnl", "rsi", "pb")} for b in d["bets"][:40]],
        bt=dict(wr=bt.get("wr"), trades=bt.get("trades"), breakeven=bt.get("breakeven"), max_dd=bt.get("max_dd")),
    )


DESK_START, DESK_PCT = 10000.0, 0.02
CAPS = dict(BTC=1000, ETH=300, SOL=150, XRP=100, DOGE=90, BNB=25, ZEC=25)  # потолок ставки по глубине стакана
POLY = Path.home() / "wave-paper/polymarket"


def desk():
    """Виртуальный счёт $10 000: ставки обоих потоков (5м и 15м, базовый пресет) по реальным ценам входа из журналов
    наблюдателя, ставка = 2% капитала (с потолком по монете). Счёт считается по событиям: деньги заморожены до расчёта."""
    bets = []
    for name, per in (("5m", 300), ("15m", 900)):
        j = json.loads((POLY / ("journal_5m.json" if name == "5m" else "journal.json")).read_text())
        for b in j["bets"]:
            if (b["status"] in ("won", "lost", "open") and b.get("v", {}).get("base", True) and b.get("ask")
                    and b["coin"] != "ZEC" and b["ask"] <= 0.55):   # 05.10.2026: only "no ZEC, entry <= 55¢"
                bets.append(dict(b, tf=name, per=per, ret=(b.get("pnl") or 0) / 10.0))  # доходность на $1 ставки (в журнале $10)
    bets.sort(key=lambda b: b["t"])
    t0 = bets[0]["t"]
    cash, locked, pend, curve, done, wins, per_coin, per_tf, log = DESK_START, 0.0, [], [[t0, DESK_START]], 0, 0, {}, {}, []

    def settle(upto):
        nonlocal cash, locked, done, wins
        pend.sort(key=lambda p: p[0])
        while pend and pend[0][0] <= upto:
            st, stake, b = pend.pop(0)
            if b["status"] == "open":
                pend.append((st + 10**9, stake, b))  # ещё не рассчитана
                pend.sort(key=lambda p: p[0])
                if pend[0][0] > upto:
                    break
                continue
            locked -= stake
            pnl = stake * b["ret"]
            cash += stake + pnl
            done += 1; wins += b["status"] == "won"
            pc = per_coin.setdefault(b["coin"], dict(n=0, w=0, pnl=0.0)); pc["n"] += 1; pc["w"] += b["status"] == "won"; pc["pnl"] += pnl
            pt = per_tf.setdefault(b["tf"], dict(n=0, w=0, pnl=0.0)); pt["n"] += 1; pt["w"] += b["status"] == "won"; pt["pnl"] += pnl
            curve.append([st, round(cash + locked, 2)])
            log.append(dict(coin=b["coin"], t=b["t"], tf=b["tf"], side=b["side"], ask=b["ask"], stake=round(stake, 2),
                            status=b["status"], pnl=round(pnl, 2)))
    for b in bets:
        settle(b["t"])
        stake = min(DESK_PCT * (cash + locked), CAPS.get(b["coin"], 25), cash)
        if stake < 1:
            continue
        cash -= stake; locked += stake
        pend.append((b["t"] + b["per"], stake, b))
    settle(10**10)
    n_open = sum(1 for p in pend if p[2]["status"] == "open")
    for p in per_coin.values():
        p["pnl"] = round(p["pnl"], 2)
    for p in per_tf.values():
        p["pnl"] = round(p["pnl"], 2)
    eq = cash + locked
    return dict(start=DESK_START, pct=DESK_PCT, started=t0, balance=round(eq, 2), closed=done, wins=wins, open=n_open,
                coins=per_coin, tf=per_tf, curve=curve[-600:], bets=log[-40:][::-1], caps=CAPS)


def main():
    f = dict(generated=datetime.now(timezone.utc).isoformat(),
             m15=slim(json.loads((SRC / "data.json").read_text()), "15m"),
             m5=slim(json.loads((SRC / "data_5m.json").read_text()), "5m"))
    # в 5м-выгрузке нет разбивки по монетам — считаем из журнала наблюдателя (базовый пресет)
    jr = json.loads((Path.home() / "wave-paper/polymarket/journal_5m.json").read_text())
    for c, v in f["m5"]["coins"].items():
        d = [b for b in jr["bets"] if b["coin"] == c and b["status"] in ("won", "lost") and b.get("v", {}).get("base", True)]
        v.update(n=len(d), w=sum(b["status"] == "won" for b in d), pnl=round(sum(b.get("pnl") or 0 for b in d), 2))
    f["desk"] = desk()
    (HERE / "feed.json").write_text(json.dumps(f, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if "--push" in sys.argv:
        g = lambda *a: subprocess.run(["git", "-C", str(HERE), *a], capture_output=True, text=True)
        g("add", "feed.json")
        if "nothing to commit" not in g("commit", "-m", f"feed {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC").stdout:
            g("push", "-q", "origin", "HEAD")


main()
