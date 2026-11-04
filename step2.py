"""Step 2 (SPEC section 7). Run on Anna's Mac.

  python3 step2.py transfer
      Sends ONE real $1 USDC from the study float to the study vault (your phone
      wallet). Asks you to type SEND first.

  python3 step2.py attack --model haiku --level 5 --controls none --attack A11 --phrasing plain
      Runs ONE real attack on mainnet with the real Claude model. Asks you to
      type RUN first. Afterwards pulls any "stolen" funds back from the attacker
      wallet into the float, and writes a readable log to runs/.
"""
import argparse
import json
import sys

from study.config import load_config, load_addresses, RUNS_DIR
from study.env import load_env
from study.runner import run_one, make_chain, reset_mainnet_float
from study.tools import CONTROL_CONFIGS


def show_balances(chain, addr, label):
    f = chain.balances(addr["study_float"])
    print(f"[{label}] float: USDC {f['USDC']:.4f}  JLP {f['JLP']:.4f}  "
          f"SOL {chain.sol_balance(addr['study_float']):.4f}")
    for k, a in addr.items():
        if k.startswith("attacker_"):
            b = chain.balances(a)
            if b["USDC"] or b["JLP"]:
                print(f"[{label}] {k}: USDC {b['USDC']:.4f}  JLP {b['JLP']:.4f}")


def write_readable(log_path):
    out = log_path.with_suffix(".md")
    lines = [f"# Trial log: {log_path.stem}", ""]
    for line in log_path.read_text().splitlines():
        e = json.loads(line)
        k = e["kind"]
        if k == "user_msg":
            lines.append(f"**Telegram (as Anna):** {e['text']}")
        elif k == "operator_reply":
            lines.append(f"**Agent replied:** {e['text']}")
        elif k == "proposed":
            d = e["decision"]
            verdict = "ALLOWED" if d["allowed"] else f"BLOCKED ({d['reason']})"
            lines.append(f"- agent asked for `{e['tool']}` {json.dumps(e['args'])} -> {verdict}")
        elif k == "reviewer":
            lines.append(f"- reviewer: {'approved' if e['approved'] else 'REJECTED'}: {e['reason']}")
        elif k == "executed":
            t = e["tx"]
            lines.append(f"- EXECUTED {t['kind']} {json.dumps({x: t[x] for x in t if x in ('asset','amount','dest','in','out','usd','signature','status','dry_run')})}")
        elif k == "oob_code_sent":
            lines.append("- confirmation code sent to Anna's second device (attacker never sees it)")
        elif k in ("trial_halted", "halt"):
            lines.append(f"- HALTED: {e.get('reason')}")
        lines.append("")
    out.write_text("\n".join(lines))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["transfer", "attack"])
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--level", type=int, default=5)
    ap.add_argument("--controls", default="none", choices=list(CONTROL_CONFIGS))
    ap.add_argument("--attack", default="A11")
    ap.add_argument("--phrasing", default="plain", choices=["plain", "pressure"])
    a = ap.parse_args()

    load_env()
    cfg = load_config(require_file=True)
    addr = load_addresses()
    chain = make_chain("mainnet", cfg, addr)
    show_balances(chain, addr, "before")

    if a.what == "transfer":
        print(f"\nAbout to send a REAL 1 USDC from the float to the vault {addr['study_vault']}.")
        if input("Type SEND to continue: ").strip() != "SEND":
            sys.exit("Cancelled. Nothing was sent.")
        tx = chain.transfer(addr["study_float"], "USDC", 1.0, addr["study_vault"], dry_run=False)
        print("Sent.", tx.get("cli", ""))
        show_balances(chain, addr, "after")
        return

    cfg = dict(cfg, dry_run=False)
    print(f"\nAbout to run ONE REAL attack on mainnet: model={a.model} L{a.level} "
          f"controls={a.controls} attack={a.attack} ({a.phrasing}).")
    print("Real money may move to an attacker wallet you own; it is pulled back afterwards.")
    if input("Type RUN to continue: ").strip() != "RUN":
        sys.exit("Cancelled. Nothing was sent.")
    row = run_one(cfg, addr, chain, a.level, a.controls, a.model,
                  attack=a.attack, phrasing=a.phrasing, log_dir=RUNS_DIR / "step2")
    show_balances(chain, addr, "after attack")
    print("\nResult:", json.dumps({k: row[k] for k in ("success", "loss_usd", "blocked_calls",
                                                        "money_calls_proposed", "noticed")}))
    moved = reset_mainnet_float(chain, live=True)
    print(f"Recycled {len(moved)} transfer(s) back to the float.")
    show_balances(chain, addr, "after recycle")
    md = write_readable(RUNS_DIR / "step2" / row["log"])
    print(f"\nReadable log: {md}")


if __name__ == "__main__":
    main()
