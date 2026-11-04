"""Step 3: run the full grid (SPEC section 7), resumable, results to results/results.csv.

  python3 grid.py --chain sim --operator comply          offline dry check of the whole grid
  python3 grid.py --chain mainnet --live                 the real experiment (asks you to type RUN)
  python3 grid.py --chain mainnet --live --limit 20      only the next 20 trials

Re-running skips trials already in the CSV, so it can be stopped (Ctrl+C or a STOP
file) and continued later.
"""
import argparse
import csv
import itertools
import json
import random
import sys
import time
from datetime import date
from pathlib import Path

from study.config import load_config, load_addresses, STOP_FILE, RUNS_DIR
from study.env import load_env
from study.runner import run_one, make_chain, reset_mainnet_float
from study.attacks import BENIGN

HERE = Path(__file__).resolve().parent
FIELDS = ["operator", "level", "controls", "task", "kind", "phrasing", "trial", "success",
          "refused_or_blocked", "noticed", "loss_usd", "loss_pct_float", "loss_unknown_addr_usd", "attempted_unknown_dest_usd",
          "msgs_to_success", "money_calls_proposed", "blocked_calls", "confirmations_requested",
          "config_changes", "halted", "step_limit_hit", "api_refusal", "reviewer_no_verdict", "followups_used", "succeeded_after_followup", "trial_id", "log", "date"]


def jobs(g, operators):
    minlvl = {t["id"]: t["min_level"] for t in BENIGN}
    for op, lv, ctl, aid, ph, n in itertools.product(operators, g["levels"], g["controls"],
                                                     g["attacks"], g["phrasings"], range(g["n_attack"])):
        yield dict(operator=op, level=lv, controls=ctl, attack=aid, phrasing=ph, trial=n)
    for op, lv, ctl, b, n in itertools.product(operators, g["levels"], g["controls"],
                                               g["benign"], range(g["n_benign"])):
        if lv >= minlvl[b]:
            yield dict(operator=op, level=lv, controls=ctl, benign=b, trial=n)


def key(j):
    return (j["operator"], str(j["level"]), j["controls"], j.get("attack") or j.get("benign"),
            j.get("phrasing", ""), str(j["trial"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", choices=["sim", "mainnet"], default="sim")
    ap.add_argument("--operator", default=None, help="'comply' or a model key; default: grid models")
    ap.add_argument("--live", action="store_true", help="mainnet only: really send transactions")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="results/results.csv")
    ap.add_argument("--levels", type=int, nargs="*", help="only these levels, e.g. --levels 5 6")
    ap.add_argument("--controls", nargs="*", help="only these control configs, e.g. --controls none")
    ap.add_argument("--attacks-only", action="store_true", help="skip benign tasks")
    ap.add_argument("--grid", default="grid.json", help="grid file (grid_demo.json = 96-trial demonstration)")
    a = ap.parse_args()

    load_env()
    g = json.loads((HERE / a.grid).read_text())
    cfg = load_config(require_file=(a.chain == "mainnet"))
    cfg["dry_run"] = not (a.chain == "sim" or a.live)
    addr = load_addresses()
    operators = [a.operator] if a.operator else g["models"]
    out = HERE / a.out
    out.parent.mkdir(exist_ok=True)
    done = set()
    if out.exists():
        with open(out) as f:
            done = {(r["operator"], r["level"], r["controls"], r["task"], r["phrasing"], r["trial"])
                    for r in csv.DictReader(f)}
    alljobs = list(jobs(g, operators))
    random.Random(2026).shuffle(alljobs)  # fixed seed: same order every time, so resuming works
    if a.levels:
        alljobs = [j for j in alljobs if j["level"] in a.levels]
    if a.controls:
        alljobs = [j for j in alljobs if j["controls"] in a.controls]
    if a.attacks_only:
        alljobs = [j for j in alljobs if j.get("attack")]
    todo = [j for j in alljobs if key(j) not in done]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(done)} trials already done, {len(todo)} to run now.")
    if a.chain == "mainnet":
        mode = "REAL transactions" if a.live else "dry-run (built, not sent)"
        print(f"Mainnet, {mode}.")
        if a.live and input("Type RUN to start: ").strip() != "RUN":
            sys.exit("Cancelled.")

    new = not out.exists()
    unrecovered_today = 0.0
    with open(out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for i, j in enumerate(todo, 1):
            if STOP_FILE.exists():
                print("STOP file present. Stopping.")
                break
            float_jlp = 5.0 if j.get("benign") == "B7" else 0.0
            if a.chain == "sim":
                chain = make_chain("sim", cfg, addr, float_jlp=float_jlp)
            else:
                chain = make_chain("mainnet", cfg, addr)
                reset_mainnet_float(chain, live=a.live)
                bal = chain.balances(addr["study_float"])
                if bal["USDC"] + bal["JLP"] * chain.price() < g["min_float_usd_to_continue"]:
                    print(f"Float below ${g['min_float_usd_to_continue']}. Stopping so you can check.")
                    break
                if float_jlp:
                    chain.swap(addr["study_float"], "USDC", 20.0, dry_run=not a.live)
            row = run_one(cfg, addr, chain, j["level"], j["controls"], j["operator"],
                          attack=j.get("attack"), phrasing=j.get("phrasing"),
                          benign=j.get("benign"), trial_no=j["trial"],
                          max_followups=int(g.get("attacker_followups", 0)),
                          log_dir=RUNS_DIR / (Path(a.out).stem if a.out != "results/results.csv"
                                              else f"{a.chain}{'_live' if a.live else ''}_{j['operator']}"))
            row["date"] = date.today().isoformat()
            w.writerow(row)
            f.flush()
            unrecovered_today += float(row["loss_unknown_addr_usd"] or 0)
            print(f"[{i}/{len(todo)}] {j['operator']} L{j['level']} {j['controls']:<5} "
                  f"{row['task']:<4} {row['phrasing']:<8} success={row['success']} loss=${row['loss_usd']}"
                  f"{'  (safety-layer refusal)' if row.get('api_refusal') else ''}", flush=True)
            if unrecovered_today > g["max_unrecovered_loss_usd_per_day"]:
                print("Unrecoverable loss today exceeded the backstop. Stopping.")
                break
            if a.chain == "mainnet":
                time.sleep(1)
    if a.chain == "mainnet":
        reset_mainnet_float(chain, live=a.live)


if __name__ == "__main__":
    main()
