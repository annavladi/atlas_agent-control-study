"""Chain backends.

SimChain: in-memory ledger for offline tests and the always-comply checks.
Values are USD: USDC at $1, JLP at the sim price. Real mainnet backend lives
in solana_backend.py and has the same interface.
"""


class ChainError(Exception):
    pass


class SimChain:
    def __init__(self, float_addr, vault_addr, price=4.25,
                 float_usdc=100.0, float_jlp=0.0, vault_usdc=200.0):
        self.float_addr = float_addr
        self.vault_addr = vault_addr
        self._price = price
        self.bal = {float_addr: {"USDC": float_usdc, "JLP": float_jlp},
                    vault_addr: {"USDC": vault_usdc, "JLP": 0.0}}
        self.sent = []  # every executed transaction
        self.price_feed_note = ""  # A8 injects text here

    # --- reads -----------------------------------------------------------
    def price(self):
        return self._price

    def balances(self, addr):
        b = self.bal.get(addr, {"USDC": 0.0, "JLP": 0.0})
        return {"USDC": round(b["USDC"], 6), "JLP": round(b["JLP"], 6)}

    def usd_value(self, asset, amount):
        return amount if asset == "USDC" else amount * self._price

    # --- writes ----------------------------------------------------------
    def _acct(self, addr):
        return self.bal.setdefault(addr, {"USDC": 0.0, "JLP": 0.0})

    def swap(self, owner, in_asset, amount, dry_run=False):
        out_asset = "JLP" if in_asset == "USDC" else "USDC"
        a = self._acct(owner)
        if amount <= 0 or a[in_asset] + 1e-9 < amount:
            raise ChainError(f"insufficient {in_asset}")
        out = amount / self._price if in_asset == "USDC" else amount * self._price
        tx = {"kind": "swap", "owner": owner, "in": in_asset, "amount": amount,
              "out": out_asset, "out_amount": out, "dry_run": dry_run}
        if not dry_run:
            a[in_asset] -= amount
            a[out_asset] += out
        self.sent.append(tx)
        return tx

    def transfer(self, owner, asset, amount, dest, dry_run=False):
        a = self._acct(owner)
        if amount <= 0 or a[asset] + 1e-9 < amount:
            raise ChainError(f"insufficient {asset}")
        if not isinstance(dest, str) or not dest:
            raise ChainError("bad destination")
        tx = {"kind": "transfer", "owner": owner, "asset": asset,
              "amount": amount, "dest": dest, "dry_run": dry_run}
        if not dry_run:
            a[asset] -= amount
            self._acct(dest)[asset] += amount
        self.sent.append(tx)
        return tx
