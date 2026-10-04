from collections import Counter, defaultdict
from dataclasses import dataclass


@dataclass
class Group:
    members: list
    origin: str
    reason: str = ""


def check_partition(entries, groups, residual):
    ids = [e["id"] for e in entries]
    out = [e["id"] for g in groups for e in g.members] + [e["id"] for e in residual]
    assert len(set(ids)) == len(ids), "input ids are not unique"
    assert Counter(out) == Counter(ids), "an entry was lost, duplicated or invented"
    assert all(g.members for g in groups), "a group is empty"


def unclaimed(entries, groups):
    claimed = {e["id"] for g in groups for e in g.members}
    return [e for e in entries if e["id"] not in claimed]


def pairs(name, amount):
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
    def run(entries):
        groups = [Group(list(entries), name)] if entries else []
        return groups, unclaimed(entries, groups)
    return run


def seq(*steps):
    def run(entries):
        groups, rest = [], entries
        for step in steps:
            found, rest = step(rest)
            groups += found
        return groups, rest
    return run


def when(pred, inner):
    def run(entries):
        groups, _ = inner([e for e in entries if pred(e)])
        return groups, unclaimed(entries, groups)
    return run


def partition_by(key, inner):
    def run(entries):
        shards = defaultdict(list)
        for e in entries:
            if key(e) is not None:
                shards[key(e)].append(e)
        groups = [g for shard in shards.values() for g in inner(shard)[0]]
        return groups, unclaimed(entries, groups)
    return run


def accept_if(pred, inner):
    def run(entries):
        groups = [g for g in inner(entries)[0] if pred(g.members)]
        return groups, unclaimed(entries, groups)
    return run


def fixed_point(inner):
    def run(entries):
        groups, rest = [], entries
        while True:
            found, left = inner(rest)
            if len(left) == len(rest):
                return groups, rest
            groups, rest = groups + found, left
    return run


def check_overrides(overrides, entries):
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
    def run(entries):
        by_id = {e["id"]: e for e in entries}
        groups = [Group([by_id[i] for i in o["ids"]], "override", o["reason"])
                  for o in overrides if o["kind"] == "group"]
        return groups, unclaimed(entries, groups)
    return run


def with_overrides(overrides, strategy):
    def run(entries):
        problems = check_overrides(overrides, entries)
        if problems:
            raise ValueError("invalid overrides:\n  " + "\n  ".join(problems))
        held = {i for o in overrides if o["kind"] == "hold" for i in o["ids"]}
        return seq(authored(overrides), when(lambda e: e["id"] not in held, strategy))(entries)
    return run
