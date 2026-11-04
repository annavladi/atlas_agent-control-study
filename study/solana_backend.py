"""Mainnet backend. Same interface as SimChain.

Swap and transfer code paths are copied from the live bot's jlp_dca.py (the
live bot is not imported or touched). dry_run=True builds the transaction but
does not send it: swaps get a real Jupiter transaction that is decoded and
signed locally; transfers run spl-token with --sign-only.
"""
import base64
import json
import subprocess
import time
from pathlib import Path

import requests

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JLP_MINT = "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4"
MINTS = {"USDC": USDC_MINT, "JLP": JLP_MINT}
DECIMALS = 6
JUP_BASE = "https://lite-api.jup.ag/swap/v1"


class ChainError(Exception):
    pass


class SolanaChain:
    def __init__(self, cfg, addresses):
        self.cfg = cfg
        self.rpc_url = cfg["rpc_url"]
        self.float_addr = addresses["study_float"]
        self.vault_addr = addresses["study_vault"]
        self.addresses = addresses
        self.keypaths = {addresses["study_float"]: cfg["float_keypair_path"]}
        kdir = Path(cfg["attacker_keypair_dir"])
        for name, a in addresses.items():
            if name.startswith("attacker_"):
                self.keypaths[a] = str(kdir / f"{name}.json")
        self.sent = []
        self._price_cache = (0, None)

    # --- RPC / Jupiter (from jlp_dca.py) -------------------------------
    def rpc(self, method, params):
        r = requests.post(self.rpc_url, json={"jsonrpc": "2.0", "id": 1,
                                              "method": method, "params": params}, timeout=30)
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise ChainError(f"RPC {method} error: {body['error']}")
        return body["result"]

    def quote(self, in_mint, out_mint, amount_raw):
        r = requests.get(f"{JUP_BASE}/quote", timeout=30, params={
            "inputMint": in_mint, "outputMint": out_mint, "amount": amount_raw,
            "slippageBps": int(self.cfg["slippage_bps"]), "swapMode": "ExactIn"})
        r.raise_for_status()
        return r.json()

    # --- reads ---------------------------------------------------------
    def price(self):
        t, p = self._price_cache
        if p is None or time.time() - t > 20:
            q = self.quote(JLP_MINT, USDC_MINT, 10 ** DECIMALS)
            p = int(q["outAmount"]) / 10 ** DECIMALS
            self._price_cache = (time.time(), p)
        return p

    def balances(self, addr):
        out = {}
        for asset, mint in MINTS.items():
            res = self.rpc("getTokenAccountsByOwner", [addr, {"mint": mint}, {"encoding": "jsonParsed"}])
            out[asset] = sum(float(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
                             for a in res["value"])
        return out

    def sol_balance(self, addr):
        return self.rpc("getBalance", [addr])["value"] / 1e9

    def usd_value(self, asset, amount):
        return amount if asset == "USDC" else amount * self.price()

    # --- writes --------------------------------------------------------
    def _keypair(self, owner):
        from solders.keypair import Keypair
        path = self.keypaths.get(owner)
        if not path:
            raise ChainError("no key for this owner (the agent never holds the vault key)")
        return Keypair.from_bytes(bytes(json.loads(Path(path).read_text())))

    def swap(self, owner, in_asset, amount, dry_run=True):
        from solders.message import to_bytes_versioned
        from solders.transaction import VersionedTransaction
        out_asset = "JLP" if in_asset == "USDC" else "USDC"
        q = self.quote(MINTS[in_asset], MINTS[out_asset], int(round(amount * 10 ** DECIMALS)))
        r = requests.post(f"{JUP_BASE}/swap", timeout=30, json={
            "quoteResponse": q, "userPublicKey": owner, "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True, "prioritizationFeeLamports": "auto"})
        r.raise_for_status()
        tx = VersionedTransaction.from_bytes(base64.b64decode(r.json()["swapTransaction"]))
        kp = self._keypair(owner)
        signed = VersionedTransaction.populate(tx.message, [kp.sign_message(to_bytes_versioned(tx.message))])
        rec = {"kind": "swap", "owner": owner, "in": in_asset, "amount": amount,
               "out": out_asset, "out_amount": int(q["outAmount"]) / 10 ** DECIMALS,
               "dry_run": dry_run, "built": True}
        if not dry_run:
            sig = self.rpc("sendTransaction", [base64.b64encode(bytes(signed)).decode(),
                                               {"encoding": "base64", "skipPreflight": False, "maxRetries": 3}])
            rec.update(signature=sig, status=self.confirm(sig))
        self.sent.append(rec)
        return rec

    def transfer(self, owner, asset, amount, dest, dry_run=True, fee_payer=None):
        kp = self.keypaths.get(owner)
        if not kp:
            raise ChainError("no key for this owner")
        payer = self.keypaths[fee_payer] if fee_payer else kp
        cmd = ["spl-token", "transfer", MINTS[asset], f"{amount:.6f}", dest,
               "--owner", kp, "--fee-payer", payer, "--fund-recipient",
               "--allow-non-system-account-recipient", "--url", self.rpc_url]
        if dry_run:
            bh = self.rpc("getLatestBlockhash", [{"commitment": "finalized"}])["value"]["blockhash"]
            cmd += ["--sign-only", "--blockhash", bh, "--mint-decimals", str(DECIMALS)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            raise ChainError((res.stderr or res.stdout).strip()[:300])
        rec = {"kind": "transfer", "owner": owner, "asset": asset, "amount": amount,
               "dest": dest, "dry_run": dry_run, "built": True, "cli": res.stdout.strip()[-200:]}
        self.sent.append(rec)
        return rec

    def confirm(self, sig, attempts=30):
        for _ in range(attempts):
            st = self.rpc("getSignatureStatuses", [[sig]])["value"][0]
            if st is not None:
                if st.get("err"):
                    return f"failed: {st['err']}"
                if st.get("confirmationStatus") in ("confirmed", "finalized"):
                    return st["confirmationStatus"]
            time.sleep(2)
        return "unconfirmed"

    # --- recycling -----------------------------------------------------
    def recycle_attackers(self, dry_run=True):
        """Sweep every attacker wallet back to the float. The float pays fees,
        so attacker wallets never need SOL."""
        moved = []
        for name, a in self.addresses.items():
            if not name.startswith("attacker_"):
                continue
            for asset, amt in self.balances(a).items():
                if amt > 0:
                    moved.append(self.transfer(a, asset, amt, self.float_addr,
                                               dry_run=dry_run, fee_payer=self.float_addr))
        return moved
