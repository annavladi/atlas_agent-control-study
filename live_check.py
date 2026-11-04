"""Step 1 live check (run on Anna's Mac). Sends NOTHING.

Reads price and balances from mainnet and builds (but does not send) a $1
buy and a $1 transfer to the study vault, proving the real code paths work.
    python3 live_check.py
"""
from study.config import load_config, load_addresses
from study.solana_backend import SolanaChain

cfg = load_config(require_file=False)
addr = load_addresses()
c = SolanaChain(cfg, addr)
f, v = addr["study_float"], addr["study_vault"]
print(f"JLP price: ${c.price():.4f}")
for name, a in (("float", f), ("vault", v)):
    b = c.balances(a)
    print(f"{name:6} {a}: USDC {b['USDC']:.2f}  JLP {b['JLP']:.4f}  SOL {c.sol_balance(a):.4f}")
fb = c.balances(f)
if fb["USDC"] < 1 or c.sol_balance(f) < 0.005:
    print("\nFloat not funded yet (needs USDC + ~0.1 SOL). Skipping the build checks.")
else:
    s = c.swap(f, "USDC", 1.0, dry_run=True)
    print(f"Built (not sent) $1 buy: ~{s['out_amount']:.4f} JLP")
    t = c.transfer(f, "USDC", 1.0, v, dry_run=True)
    print("Built (not sent) $1 USDC transfer to study vault: OK")
print("\nNothing was sent.")
