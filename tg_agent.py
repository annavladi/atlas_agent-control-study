"""Talk to the study agent yourself over Telegram (@atlas_study_agent_bot).

Runs on Anna's Mac. Money is a PRETEND ledger ($100 fake USDC); nothing on
the blockchain can move. Settings are chosen here in Terminal, never over
Telegram, so a hijacked Telegram account cannot switch the controls off.

  python3 tg_agent.py --level 5 --controls none --model haiku

On start it prints a 6-digit pairing code. Send "/pair CODE" to the bot from
your Telegram; only that chat is answered afterwards. Confirmation codes (C4)
are shown here in Terminal, which plays the role of your "second device".
Stop with Control + C.
"""
import argparse
import json
import secrets
import sys
import time
from datetime import date
from pathlib import Path

import requests

from study.chain import SimChain
from study.config import load_config, load_addresses, RUNS_DIR, STOP_FILE
from study.env import load_env
from study.harness import Harness, Halted
from study.operators import ClaudeOperator, ClaudeReviewer
from study.prompts import operator_prompt
from study.tools import CONTROL_CONFIGS
import os

OWNER_FILE = Path("~/study-keys/tg_owner.json").expanduser()
MAX_HISTORY = 40


class TG:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}"

    def updates(self, offset):
        r = requests.get(f"{self.base}/getUpdates", timeout=40,
                         params={"offset": offset, "timeout": 30})
        r.raise_for_status()
        return r.json().get("result", [])

    def send(self, chat_id, text):
        for i in range(0, len(text), 3900):
            for attempt in range(3):
                try:
                    r = requests.post(f"{self.base}/sendMessage", timeout=20,
                                      json={"chat_id": chat_id, "text": text[i:i + 3900]})
                    if r.ok:
                        break
                    print(f"Telegram send failed ({r.status_code}): {r.text[:200]}")
                except Exception as e:
                    print("Telegram send error, retrying:", e)
                time.sleep(2)


def name_of(addr, a):
    for k, v in addr.items():
        if v == a:
            return k.replace("study_", "")
    return (a[:4] + "…" + a[-4:]) if isinstance(a, str) and len(a) > 10 else str(a)


def describe(e, addr):
    args = dict(e["args"])
    for k in ("dest", "value"):
        if isinstance(args.get(k), str):
            args[k] = name_of(addr, args[k])
    args.pop("confirmation_code", None)
    d = e["decision"]
    verdict = "allowed" if d["allowed"] else "BLOCKED: " + d["reason"]
    a = ", ".join(f"{k}={v}" for k, v in args.items())
    return f"• {e['tool']}({a}) → {verdict}"


def trim(messages):
    """Keep the conversation short without breaking tool_use/tool_result pairs."""
    while len(messages) > MAX_HISTORY:
        messages.pop(0)
        while messages and not (messages[0]["role"] == "user" and isinstance(messages[0]["content"], str)):
            messages.pop(0)


class Session:
    def __init__(self, cfg, addr, level, ctl, model_key, price):
        controls = CONTROL_CONFIGS[ctl]
        self.addr = addr
        self.chain = SimChain(addr["study_float"], addr["study_vault"], price=price,
                              float_usdc=100.0, float_jlp=0.0)
        reviewer = ClaudeReviewer(cfg["models"][model_key]) if "C5" in controls else None
        log = RUNS_DIR / "telegram" / f"{date.today().isoformat()}_L{level}_{ctl}_{model_key}.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        self.h = Harness(cfg, addr, self.chain, level, controls, mode="attack",
                         reviewer=reviewer, log_path=log)
        self.h.oob_callback = lambda code: print(
            f"\n>>> CONFIRMATION CODE (your second device): {code}\n", flush=True)
        self.op = ClaudeOperator(cfg["models"][model_key],
                                 operator_prompt(controls, addr["study_vault"]), level)

    def handle(self, text):
        h = self.h
        start = len(h.events)
        h.current_user_msg = text
        h.user_history = getattr(h, "user_history", []) + [text]
        h.log("user_msg", text=text, source="telegram")
        try:
            reply = self.op.handle(text, h)
        except Halted as e:
            reply = f"(harness stopped: {e})"
        h.log("operator_reply", text=reply)
        trim(self.op.messages)
        actions = [describe(e, self.addr) for e in h.events[start:] if e["kind"] == "proposed"]
        fenced = [e for e in h.events[start:] if e["kind"] == "fence_blocked"]
        bal = self.chain.balances(self.addr["study_float"])
        footer = ["", "— agent actions —"] + (actions or ["• none"])
        if fenced:
            footer.append("• lab fence stopped a send to an address you don't own")
        footer.append(f"[pretend float: USDC {bal['USDC']:.2f}, JLP {bal['JLP']:.4f}]")
        return (reply or "(no text reply)") + "\n" + "\n".join(footer)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=5, choices=range(7))
    ap.add_argument("--controls", default="none", choices=list(CONTROL_CONFIGS))
    ap.add_argument("--model", default="haiku", choices=["haiku", "fable"])
    a = ap.parse_args()

    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN missing from ~/study-keys/.env")
    cfg = load_config()
    cfg["dry_run"] = False  # pretend ledger only; nothing touches the blockchain
    addr = load_addresses()
    try:
        from study.solana_backend import SolanaChain
        price = SolanaChain(cfg, addr).price()
    except Exception:
        price = 4.25
    tg = TG(token)
    owner = json.loads(OWNER_FILE.read_text())["chat_id"] if OWNER_FILE.exists() else None
    pair_code = f"{secrets.randbelow(10**6):06d}"
    sess = Session(cfg, addr, a.level, a.controls, a.model, price)

    print(f"Study agent on Telegram: L{a.level}, controls={a.controls}, model={a.model}, "
          f"pretend ledger with $100 USDC, JLP price ${price:.4f}.")
    if owner:
        print("Paired with your Telegram chat. Send it a message.")
    else:
        print(f"Not paired yet. In Telegram, send this to @atlas_study_agent_bot:  /pair {pair_code}")
    print("Stop with Control + C.\n")

    offset = 0
    while True:
        if STOP_FILE.exists():
            print("STOP file present. Exiting.")
            return
        try:
            ups = tg.updates(offset)
        except Exception as e:
            print("Telegram connection issue, retrying:", e)
            time.sleep(5)
            continue
        for u in ups:
            offset = u["update_id"] + 1
            m = u.get("message") or {}
            chat = (m.get("chat") or {}).get("id")
            text = (m.get("text") or "").strip()
            if not chat or not text:
                continue
            if owner is None:
                if text == f"/pair {pair_code}":
                    owner = chat
                    OWNER_FILE.write_text(json.dumps({"chat_id": chat}))
                    os.chmod(OWNER_FILE, 0o600)
                    tg.send(chat, "Paired. This chat now talks to the study agent "
                                  f"(L{a.level}, controls={a.controls}, {a.model}). Pretend money only.")
                    print("Paired.")
                continue
            if chat != owner:
                print(f"Ignored a message from another chat ({chat}).")
                continue
            if text == "/new":
                sess = Session(cfg, addr, a.level, a.controls, a.model, price)
                tg.send(chat, "Fresh start: new conversation, pretend float reset to $100 USDC.")
                continue
            print(f"you: {text}")
            try:
                out = sess.handle(text)
            except Exception as e:
                out = f"(error: {e})"
            print(out + "\n")
            tg.send(chat, out)


if __name__ == "__main__":
    main()
