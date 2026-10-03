"""Reconciliation as composable partitioning, with authored overrides.

Reference implementation of README.md: standard library only, read top to bottom.

    entry     a dict with a unique, stable "id"; every other field is yours
    group     members (entries), origin (the rule or decision that made it), reason
    strategy  a function: entries -> (groups, residual)

Invariant: every input entry lands in exactly one group or in the residual.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass


@dataclass
class Group:
    members: list
    origin: str
    reason: str = ""


def check_partition(entries, groups, residual):
    """Fail unless every input entry is in exactly one group or in the residual."""
    ids = [e["id"] for e in entries]
    out = [e["id"] for g in groups for e in g.members] + [e["id"] for e in residual]
    assert len(set(ids)) == len(ids), "input ids are not unique"
    assert Counter(out) == Counter(ids), "an entry was lost, duplicated or invented"
    assert all(g.members for g in groups), "a group is empty"


def unclaimed(entries, groups):
    """The entries that no group claims, in input order."""
    claimed = {e["id"] for g in groups for e in g.members}
    return [e for e in entries if e["id"] not in claimed]


# Leaves find groups among the entries they are given. The name is the origin.


def pairs(name, amount):
    """Pair each entry with the earliest unpaired entry of equal and opposite amount."""
    def run(entries):
        waiting, groups = defaultdict(list), []
        for e in entries:
            a = amount(e)
            if a and waiting[-a]:
                groups.append(Group([waiting[-a].pop(0), e], name))
            else:
                waiting[a].append(e)
        return groups, unclaimed(entries, groups)
    return run


def one_group(name):
    """Put everything it is given into one group."""
    def run(entries):
        groups = [Group(list(entries), name)] if entries else []
        return groups, unclaimed(entries, groups)
    return run


# Combinators build strategies from strategies.


def seq(*steps):
    """Run each step on what the earlier steps left."""
    def run(entries):
        groups, rest = [], entries
        for step in steps:
            found, rest = step(rest)
            groups += found
        return groups, rest
    return run


def when(pred, inner):
    """Run inner on the entries that satisfy pred; the others pass through."""
    def run(entries):
        groups, _ = inner([e for e in entries if pred(e)])
        return groups, unclaimed(entries, groups)
    return run


def partition_by(key, inner):
    """Run inner separately on each set of entries sharing a key; key None passes through."""
    def run(entries):
        shards = defaultdict(list)
        for e in entries:
            if key(e) is not None:
                shards[key(e)].append(e)
        groups = [g for shard in shards.values() for g in inner(shard)[0]]
        return groups, unclaimed(entries, groups)
    return run


def accept_if(pred, inner):
    """Keep inner's groups whose members satisfy pred; the others dissolve whole."""
    def run(entries):
        groups = [g for g in inner(entries)[0] if pred(g.members)]
        return groups, unclaimed(entries, groups)
    return run


# Overrides are decisions, written as plain data after reading the residual:
#   {"kind": "group", "ids": [...], "reason": "..."}  these entries form one group
#   {"kind": "hold",  "ids": [...], "reason": "..."}  no rule may use these entries


def check_overrides(overrides, entries):
    """Every problem with these overrides for these entries; empty means valid."""
    known, used, problems = {e["id"] for e in entries}, {}, []
    for n, o in enumerate(overrides):
        if o.get("kind") not in ("group", "hold"):
            problems.append(f"override {n}: kind must be 'group' or 'hold'")
        if not (isinstance(o.get("reason"), str) and o["reason"].strip()):
            problems.append(f"override {n}: reason is required")
        ids = o.get("ids")
        if not (isinstance(ids, list) and ids):
            problems.append(f"override {n}: ids must be a non-empty list")
            continue
        for i in ids:
            if i not in known:
                problems.append(f"override {n}: unknown id {i!r}")
            elif i in used:
                problems.append(f"override {n}: id {i!r} is already in override {used[i]}")
            else:
                used[i] = n
    return problems


def authored(overrides):
    """Leaf: one group per "group" override, with origin "override" and its reason."""
    def run(entries):
        by_id = {e["id"]: e for e in entries}
        groups = [Group([by_id[i] for i in o["ids"]], "override", o["reason"])
                  for o in overrides if o["kind"] == "group"]
        return groups, unclaimed(entries, groups)
    return run


def with_overrides(overrides, strategy):
    """Validate, then run seq(authored(overrides), when(not held, strategy))."""
    def run(entries):
        problems = check_overrides(overrides, entries)
        if problems:
            raise ValueError("invalid overrides:\n  " + "\n  ".join(problems))
        held = {i for o in overrides if o["kind"] == "hold" for i in o["ids"]}
        return seq(authored(overrides), when(lambda e: e["id"] not in held, strategy))(entries)
    return run
