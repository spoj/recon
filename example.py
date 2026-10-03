"""The worked example from README.md: one month of a bank account against the
cash book. Run the rules, read the residual, apply overrides.json, run again.

    python3 example.py
"""

import json
from pathlib import Path

from recon import accept_if, check_partition, fixed_point, one_group, pairs, partition_by, seq, with_overrides

FIELDS = ("id", "side", "date", "amount", "ref", "party", "memo")
BAG = [dict(zip(FIELDS, row)) for row in [
    ("b1", "bank", "2025-03-04", 1200, "INV-101", "Larch", "LARCH LTD INV-101"),
    ("b2", "bank", "2025-03-09", 1500, "DEP-31", None, "DEPOSIT 31"),
    ("b3", "bank", "2025-03-20", 2340, "INV-130", "Sorrel", "SORREL INC INV-130"),
    ("b4", "bank", "2025-03-26", 500, None, "Alder", "ALDER INV120 PMT"),
    ("b5", "bank", "2025-03-28", 75, None, None, "TRANSFER 88412"),
    ("b6", "bank", "2025-03-31", -15, None, None, "ACCOUNT FEE MAR"),
    ("b7", "bank", "2025-03-31", 250, None, "Rowan", "ROWAN INV127 PMT"),
    ("k1", "book", "2025-03-02", 1200, "INV-101", "Larch", "Receipt Larch INV-101"),
    ("k2", "book", "2025-03-08", 1000, "DEP-31", "Larch", "Receipt Larch INV-104, deposit 31"),
    ("k3", "book", "2025-03-08", 500, "DEP-31", "Sorrel", "Receipt Sorrel INV-125, deposit 31"),
    ("k4", "book", "2025-03-03", 500, "INV-118", "Alder", "Receipt Alder INV-118"),
    ("k5", "book", "2025-03-24", 500, "INV-120", "Alder", "Receipt Alder INV-120"),
    ("k6", "book", "2025-03-19", 2430, "INV-130", "Sorrel", "Receipt Sorrel INV-130"),
    ("k7", "book", "2025-03-30", -1200, "CHQ-1047", "Hawthorn", "Cheque 1047 to Hawthorn Haulage"),
    ("k8", "book", "2025-03-10", 250, "DEP-31", "Rowan", "Receipt Rowan INV-127, deposit 31"),
]]


def signed(e):
    """Both sides record money in as positive; negate the cash book so a settled group sums to zero."""
    return e["amount"] if e["side"] == "bank" else -e["amount"]


def nets_to_zero(members):
    return sum(map(signed, members)) == 0


def ref(e):
    return e["ref"]


def party(e):
    return e["party"]


one_pass = seq(
    partition_by(ref, pairs("same ref", signed)),
    partition_by(ref, accept_if(nets_to_zero, one_group("same ref, nets to zero"))),
    partition_by(party, pairs("same party and amount", signed)),
)
rules = fixed_point(one_pass)


def show(title, groups, residual, overrides=()):
    held = {i: o["reason"] for o in overrides if o["kind"] == "hold" for i in o["ids"]}
    print(title)
    for g in groups:
        ids = " ".join(e["id"] for e in g.members)
        print(f"  {ids:<9} {g.origin:<23} net {sum(map(signed, g.members)):>5}  {g.reason}".rstrip())
    print("  residual, as the LLM reads it:")
    for e in residual:
        print("   ", json.dumps({**e, "held": held[e["id"]]} if e["id"] in held else e))
    print()


assert {"b2", "k2", "k3"} <= {e["id"] for e in one_pass(BAG)[1]}, "one pass should leave deposit 31 open"

groups, residual = rules(BAG)
check_partition(BAG, groups, residual)
show("Run 1: rules only", groups, residual)
assert [e["id"] for e in residual] == ["b3", "b5", "b6", "k5", "k6", "k7"]

overrides = json.loads((Path(__file__).parent / "overrides.json").read_text())
groups, residual = with_overrides(overrides, rules)(BAG)
check_partition(BAG, groups, residual)
show("Run 2: with overrides.json", groups, residual, overrides)
assert [e["id"] for e in residual] == ["b5", "k4"]

in_groups, left = sum(signed(e) for g in groups for e in g.members), sum(map(signed, residual))
assert in_groups + left == sum(map(signed, BAG))
print(f"Bank less book: {in_groups + left} = {in_groups} in groups {left:+} in the residual\n")

bad = [{"kind": "group", "ids": ["b5", "k9"], "reason": ""}, {"kind": "hold", "ids": ["b5"], "reason": "?"}]
try:
    with_overrides(bad, rules)(BAG)
except ValueError as err:
    print(err)
else:
    raise AssertionError("invalid overrides ran")
