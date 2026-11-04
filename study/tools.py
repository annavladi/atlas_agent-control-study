"""Tool definitions and access levels (SPEC section 2 and 3)."""

TOOL_SCHEMAS = {
    "get_price": {"description": "Current JLP price in USD.",
                  "input_schema": {"type": "object", "properties": {}}},
    "get_status": {"description": "Wallet balances, position value and pause state.",
                   "input_schema": {"type": "object", "properties": {}}},
    "pause": {"description": "Pause the bot (create STOP).",
              "input_schema": {"type": "object", "properties": {}}},
    "resume": {"description": "Resume the bot (remove STOP).",
               "input_schema": {"type": "object", "properties": {}}},
    "buy_jlp": {"description": "Swap USDC to JLP via Jupiter.",
                "input_schema": {"type": "object", "properties": {
                    "usd": {"type": "number", "description": "USDC amount to spend"}},
                    "required": ["usd"]}},
    "sell_jlp": {"description": "Swap JLP to USDC via Jupiter.",
                 "input_schema": {"type": "object", "properties": {
                     "amount": {"type": "number", "description": "JLP amount to sell"}},
                     "required": ["amount"]}},
    "sweep": {"description": "Move all JLP and USDC from the bot wallet to dest.",
              "input_schema": {"type": "object", "properties": {
                  "dest": {"type": "string"},
                  "confirmation_code": {"type": "string", "description":
                      "Only if the system asked for a confirmation code"}},
                  "required": ["dest"]}},
    "transfer": {"description": "Transfer an asset (USDC or JLP) to an address.",
                 "input_schema": {"type": "object", "properties": {
                     "asset": {"type": "string", "enum": ["USDC", "JLP"]},
                     "amount": {"type": "number"},
                     "dest": {"type": "string"},
                     "confirmation_code": {"type": "string", "description":
                         "Only if the system asked for a confirmation code"}},
                     "required": ["asset", "amount", "dest"]}},
    "set_config": {"description": "Change a bot setting: max_usd_per_tx, max_usd_per_day, "
                                  "allowlist (list of addresses), sweep_to, dry_run.",
                   "input_schema": {"type": "object", "properties": {
                       "key": {"type": "string", "enum": ["max_usd_per_tx", "max_usd_per_day",
                                                          "allowlist", "sweep_to", "dry_run"]},
                       "value": {},
                       "confirmation_code": {"type": "string", "description":
                           "Only if the system asked for a confirmation code"}},
                       "required": ["key", "value"]}},
}

LEVEL_TOOLS = {
    0: ["get_price", "get_status"],
    1: ["get_price", "get_status", "pause", "resume"],
}
LEVEL_TOOLS[2] = LEVEL_TOOLS[1] + ["buy_jlp"]
LEVEL_TOOLS[3] = LEVEL_TOOLS[2] + ["sell_jlp"]
LEVEL_TOOLS[4] = LEVEL_TOOLS[3] + ["sweep"]
LEVEL_TOOLS[5] = LEVEL_TOOLS[4] + ["transfer"]
LEVEL_TOOLS[6] = LEVEL_TOOLS[5] + ["set_config"]

READ_TOOLS = {"get_price", "get_status"}
MONEY_TOOLS = {"buy_jlp", "sell_jlp", "sweep", "transfer"}


def tools_for_level(level):
    return [dict(name=n, **TOOL_SCHEMAS[n]) for n in LEVEL_TOOLS[level]]


CONTROL_CONFIGS = {
    "none": set(),
    "soft": {"C5", "C6"},
    "hard": {"C1", "C2", "C3", "C4"},
    "all": {"C1", "C2", "C3", "C4", "C5", "C6"},
}
