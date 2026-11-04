# Agent control study

**If a hacker takes over the Telegram account that controls an AI trading agent, how much can they steal, and which safety controls actually stop them?**

Author: Anna Vladi · November 2026 · License: MIT

## Result in one paragraph

An AI operator (Claude Haiku 5.5 or Claude Fable 5.1) ran a JLP trading bot on Solana and took instructions over Telegram. A scripted attacker posing as the owner tried to get it to send funds to wallets the attacker named. With no controls, Haiku helped the attacker in 15 of 24 trials and Fable in 24 of 24 (Fisher exact, one-sided p = 0.0008). Every successful attack needed at least one confirmation from the attacker on the same hijacked chat, so the agent asking "are you sure?" protected nothing. Hard controls written in code (an address allowlist, fixed caps, a confirmation code on a second device) blocked every attempt, even though both models kept trying. A warning in the agent's instructions also stopped both models in this run, but its wording matched these attacks exactly and attacks designed to get around it were not tested.

**Readable report:** open [`results/findings.html`](results/findings.html) in a browser. Short version: [`results/demo_findings.md`](results/demo_findings.md).

| Controls | Haiku 5.5 | Fable 5.1 |
|---|---|---|
| None | 15 / 24 attacks succeeded, $690 pretend loss | 24 / 24 succeeded, $1,240 |
| Soft (warning + reviewer AI) | 0 / 24 | 0 / 24 |
| Hard (code outside the model) | 0 / 24 | 0 / 2 (cost check only) |
| All | 0 / 24 | 0 / 1 (cost check only) |

## What was tested

- **Agent:** reads a Telegram message, picks tools (price, status, pause, buy, sell, sweep, transfer, change settings), and acts on a $100 float.
- **Access levels:** L0 (read only) to L6 (can also change its own limits). The demonstration run uses L5 (transfer to any address within $50 limits) and L6.
- **Controls:** C1 address allowlist, C2 per-transaction cap, C3 daily cap, C4 out-of-band confirmation code (all in code); C5 reviewer AI, C6 warning in the instructions (soft).
- **Attacks:** 11 written (`study/attacks.py`). The demonstration run uses A11 buy-and-send, A8 instruction hidden in the price feed, A7 "depeg, move everything", A10 "pause, then move the balance".
- **Lab fence:** money can only ever move between wallets the author controls. Any attempt to send elsewhere is recorded and never executed.

Full protocol and every decision, with dates: [`SPEC.md`](SPEC.md) (section 13 and the notes after it override earlier sections).

## How the method changed during the study

These changes were made after looking at early results. Each is recorded in `SPEC.md`, and the earlier data is kept, labeled and separate from the main results.

1. **Simulated ledger instead of mainnet.** The agent sees the same tool results either way, so behavior should not differ; mainnet mainly tests plumbing. The mainnet backend is built (`study/solana_backend.py`, `live_check.py`, `step2.py`) but the reported results use the simulated ledger.
2. **Attacker follow-up replies.** In a 20-trial pilot with a one-message attacker, the agent usually asked a question first and the trial ended there, scored as a refusal. Manual Telegram tests showed one reply from the attacker was enough. The script now answers up to twice, with replies written per attack (`FOLLOWUPS` in `study/attacks.py`). A first version used one generic reply that did not answer the agent's actual questions; it was replaced after 16 trials. The second reply for A1, A7 and A10 was then reworded after a 10-trial pilot.
3. **A6 replaced by A7.** A6 (fake "Squads support") is a well-known scam pattern that tests recognition of an old trick, not a convincing request from the owner.
4. **Demonstration scale.** 96 trials per model (L5, L6 × 4 control settings × 4 attacks × 3 repeats). Fable ran only the no-control and soft-control cells, because the hard controls are enforced by code and had already blocked every attempt. The full design (`grid.json`, 1,452 trials per model, including benign tasks to measure the usability cost of the controls) is built but was not run.

## Files

| Path | What it is |
|---|---|
| `study/` | The harness: tools and access levels, the control gate, prompts, attacks, trial runner, model operator |
| `grid.py`, `grid_demo.json`, `grid.json` | Runs the experiment; demonstration and full designs |
| `summarize.py` | Builds `results/summary.md` and the charts in `figures/` |
| `tg_agent.py` | Talk to the agent yourself over Telegram, on pretend money |
| `tests/` | 33 offline tests, including an "always comply" operator that proves the hard controls hold whatever the model decides |
| `results/results.csv` | The main results (Haiku 96 trials, Fable 51) |
| `results/manual_findings.md` | Notes from the author's manual Telegram sessions |
| `results/pilot_*.csv`, `results/aborted_*.csv`, `results/removed_A6_haiku.csv`, `results/sim_comply.csv` | Earlier or excluded runs, kept for transparency; not in the main results |
| `runs.zip` | One log per trial (unzip to get `runs/`): every message, every tool the agent asked for, and the gate's decision |
| `archive/spec_history/` | Earlier versions of the protocol |

## Run it

Python 3.10 or later.

```
pip install -r requirements.txt
python3 -m unittest tests.test_controls tests.test_claude_loop tests.test_tg_agent   # offline, no API key needed
```

With an Anthropic API key in `~/study-keys/.env` (`ANTHROPIC_API_KEY=...`):

```
python3 grid.py --grid grid_demo.json --chain sim --operator haiku
python3 summarize.py
```

Keys never live in this folder: wallet keys and the API key go in `~/study-keys`, and the harness refuses to start if a key path points inside the project or at the vault key. The wallet addresses in `wallets/addresses.json` are throwaway study wallets.

## Limitations

- Demonstration scale: 24 trials per model per control setting.
- Simulated ledger, one scripted attacker, four attacks, plain phrasing only. Benign-task usability was not measured.
- The soft-control result may not hold against attacks written to get around the warning's wording.
- Fable 5.1 includes additional built-in safety measures, so its results reflect the model plus those measures. In manual tests that layer declined one wording of an attack and allowed a reworded one.
