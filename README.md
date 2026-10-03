# recon

Reconciliation as composable partitioning, plus overrides that an LLM can write.

This is an idea with a reference implementation, not a package. Read this file, then [`recon.py`](recon.py), one file of standard-library Python meant to be read top to bottom, and rebuild it in whatever language you are working in. `python3 example.py` runs the worked example below and checks the invariant. There is nothing to install.

## The invariant

A reconciliation takes a bag of entries (bank lines, ledger lines, invoices, payments: anything with a unique, stable id) and returns groups and a residual.

- A **group** is a set of entries settled together: matched to each other, or explained by one reason. It records its **origin**, the rule or decision that made it, and for a decision its **reason**.
- The **residual** is everything not yet settled.

**Every input entry lands in exactly one group or in the residual.** Nothing is lost, duplicated or invented. Any sum over the bag therefore splits exactly into per-group sums plus the residual's sum, so the reconciliation statement falls out of the output. Check the invariant after every run (`check_partition`); it is cheap.

## The algebra

A **strategy** is a function `bag -> (groups, residual)` that keeps the invariant. Strategies are built from two kinds of parts.

**Leaves** find groups. A leaf groups only entries it was given, uses each at most once, and returns the rest as its residual. It takes a name, which becomes the origin of its groups. Inside, a leaf can use any technique, from key lookups to min-cost flow or other combinatorial search; [florecon](https://github.com/spoj/florecon) has examples.

- `pairs(name, amount)`: pair each entry with the earliest unpaired entry of equal and opposite amount.
- `one_group(name)`: put everything it is given into one group.

**Combinators** build strategies from strategies.

- `seq(s1, s2, ...)`: each step runs on what the earlier steps left. Earlier steps claim entries first, so put specific rules first.
- `when(pred, s)`: `s` sees only the entries that satisfy `pred`; the rest pass through.
- `partition_by(key, s)`: `s` runs separately on each set of entries that share a key; entries whose key is null pass through.
- `accept_if(pred, s)`: keep the groups of `s` whose members satisfy `pred`; the others dissolve whole back into the residual.

**Acceptance** is a plain predicate over a group's members, such as "signed amounts sum to zero" or `abs(net) <= 1`. There is no tolerance type; write the inequality.

Amounts are functions passed in (`signed` in the example), not a field the library knows, so sign conventions and currencies stay with the caller.

Leaves group only what they are given, and combinators only route entries to inner strategies or hand them back, so every composition keeps the invariant. Familiar rules are compositions, not new leaves. "Lines that share a reference and net to zero" is:

```python
partition_by(ref, accept_if(nets_to_zero, one_group("same ref, nets to zero")))
```

## Overrides

After a run, an LLM (or a person) reads the residual and writes decisions as plain data: a JSON list with one object per decision.

```json
[
  {"kind": "group", "ids": ["b4", "k5"], "reason": "bank memo 'ALDER INV120 PMT' names INV-120: b4 pays k5, not k4"},
  {"kind": "hold", "ids": ["k4"], "reason": "INV-118 receipt booked 3 Mar has no bank credit this month; ask receivables whether it was paid"}
]
```

- `group`: these entries form one group, with origin `override` and this reason. One id explains a single entry, such as a fee not yet booked or a cheque not yet presented.
- `hold`: these entries skip every rule and stay in the residual, shown with the reason. Use it to keep an entry open, for example when a rule's match is wrong and the right one is unknown.
- `reason` is required. Give the evidence a reviewer needs to agree without redoing the work.

**Validation.** Before anything runs, every problem is listed, and any problem stops the run:

- `kind` is `group` or `hold`;
- `ids` is a non-empty list of ids in the bag;
- no id appears in more than one override;
- `reason` is non-empty text.

Other fields are ignored. An unknown id is an error, not a warning, so when the bag changes a stale override is removed on purpose instead of being skipped silently.

**Application.** Overrides compile into the same algebra:

```
with_overrides(overrides, s) = seq(authored(group overrides), when(id not held, s))
```

`authored` is a leaf that emits the override groups. Because it is a leaf inside `seq` and `when`, the invariant holds with nothing new to prove, and every rule runs on what the decisions left. Wrap the outermost strategy, since validation needs the whole bag. Applying overrides inside the composition, rather than patching results afterwards, means no group that a rule accepted is ever edited.

On purpose, overrides do not:

- **unmatch.** To break a wrong match, group the right entries; the wrong group can no longer form. If the right partner is unknown, hold the entry.
- **edit entries.** Fix data before matching. A wrong amount stays visible as an override group whose net is not zero.
- **go through acceptance.** Acceptance gates rules, not decisions. An override group's net is reported, not checked.

## The loop

```
overrides = []
repeat:
    groups, residual = with_overrides(overrides, rules)(bag)
    check_partition(bag, groups, residual)
    show the LLM the residual (JSON lines, hold reasons attached)
        and the groups made by the weakest rules (filter by origin)
    the LLM appends overrides; a person reviews the diff
until the residual holds only what is genuinely open
```

Rules do the mechanical bulk and overrides carry the judgment. When the same kind of override keeps coming back, make it a rule.

## Worked example

One bank account for one month, synthetic ([`example.py`](example.py)). Both sides record money in as positive.

| id | side | date | amount | ref | party | memo |
|---|---|---|--:|---|---|---|
| b1 | bank | 2025-03-04 | 1200 | INV-101 | Larch | LARCH LTD INV-101 |
| b2 | bank | 2025-03-09 | 1500 | DEP-31 | | DEPOSIT 31 |
| b3 | bank | 2025-03-20 | 2340 | INV-130 | Sorrel | SORREL INC INV-130 |
| b4 | bank | 2025-03-26 | 500 | | Alder | ALDER INV120 PMT |
| b5 | bank | 2025-03-28 | 75 | | | TRANSFER 88412 |
| b6 | bank | 2025-03-31 | -15 | | | ACCOUNT FEE MAR |
| k1 | book | 2025-03-02 | 1200 | INV-101 | Larch | Receipt Larch INV-101 |
| k2 | book | 2025-03-08 | 1000 | DEP-31 | Larch | Receipt Larch INV-104, deposit 31 |
| k3 | book | 2025-03-08 | 500 | DEP-31 | Sorrel | Receipt Sorrel INV-125, deposit 31 |
| k4 | book | 2025-03-03 | 500 | INV-118 | Alder | Receipt Alder INV-118 |
| k5 | book | 2025-03-24 | 500 | INV-120 | Alder | Receipt Alder INV-120 |
| k6 | book | 2025-03-19 | 2430 | INV-130 | Sorrel | Receipt Sorrel INV-130 |
| k7 | book | 2025-03-30 | -1200 | CHQ-1047 | Hawthorn | Cheque 1047 to Hawthorn Haulage |

```python
def signed(e):  # negate the cash book so that a settled group sums to zero
    return e["amount"] if e["side"] == "bank" else -e["amount"]

def nets_to_zero(members):
    return sum(map(signed, members)) == 0

# ref(e) and party(e) return those fields; None (b4 has no ref) leaves an entry out
rules = seq(
    partition_by(ref, pairs("same ref", signed)),
    partition_by(ref, accept_if(nets_to_zero, one_group("same ref, nets to zero"))),
    partition_by(party, pairs("same party and amount", signed)),
)
```

Run 1, rules only:

```
b1 k1     same ref                net     0
b2 k2 k3  same ref, nets to zero  net     0
b4 k4     same party and amount   net     0
residual: b3 b5 b6 k5 k6 k7
```

Reading the residual: k5, Alder's INV-120 receipt, has no bank line. The bank line that pays it is b4 (`ALDER INV120 PMT`), which the weakest rule paired with k4, Alder's other receipt of 500. b3 and k6 are the same invoice with transposed digits, b6 is a fee, k7 is a cheque not yet presented, and b5 is unknown. The LLM writes [`overrides.json`](overrides.json): the two overrides above, plus

```json
{"kind": "group", "ids": ["b3", "k6"], "reason": "both are INV-130; the cash book has 2430 where the bank received 2340 (transposed digits); correct the cash book"},
{"kind": "group", "ids": ["b6"], "reason": "March account fee, not yet in the cash book; book it"},
{"kind": "group", "ids": ["k7"], "reason": "cheque 1047 written 30 Mar, not yet presented at the bank"}
```

Run 2, `with_overrides(overrides, rules)`:

```
b4 k5     override                net     0  bank memo 'ALDER INV120 PMT' names INV-120: b4 pays k5, not k4
b3 k6     override                net   -90  both are INV-130; the cash book has 2430 where the bank ...
b6        override                net   -15  March account fee, not yet in the cash book; book it
k7        override                net  1200  cheque 1047 written 30 Mar, not yet presented at the bank
b1 k1     same ref                net     0
b2 k2 k3  same ref, nets to zero  net     0
residual: b5, k4 (held: INV-118 receipt booked 3 Mar has no bank credit this month; ...)
```

The bank is 670 above the cash book, and every unit of it now has a place: -90 keying error, -15 fee, +1200 unpresented cheque, +75 unknown credit, -500 held receipt. Without the hold, the next unexplained 500 from Alder would be paired with k4 by the weakest rule, and both would drop out of sight.

## Why rules plus authored overrides

- **The numbers underdetermine the answer.** Equal amounts recur, so several groupings often net to zero, and only one of them is what happened. b4 nets against k4 and k5 alike; only the memo says which. The deciding fact usually sits in a memo, a remittance advice or a conversation, which an LLM can read and cite.
- **Every group says why it exists.** A rule's group carries the rule, and an override carries its reason, so a reviewer can check a group without redoing the work.
- **A wrong match hides work.** The residual is the work list. Clearing two unrelated entries against each other shortens it by burying two problems. Narrow rules and `hold` keep it honest.
- **Decisions are data.** Overrides are validated, diffed and reviewed like code, and they replay on every run while new entries are matched around them.
- **The LLM reads only the long tail.** Rules settle the bulk cheaply. The LLM reads the residual and the weakest rules' groups, which is where judgment is needed.

## Rebuilding it

- Make ids unique and stable across runs: derive them from source keys such as a statement line or a document and line number, never from row position. Overrides name ids, and leaves break ties by input order, so keep the input order stable too.
- Use integer amounts in minor units, so that "nets to zero" is exact.
- A leaf must group only entries it was given, each at most once. `check_partition` catches one that doesn't.
- Report every group's origin and net. Grouped is not reconciled: a group from a loose rule is a proposal.
- Prefer absolute tolerances. A tolerance relative to the largest line grows with the group and can hide a real difference.
- Add leaves as the data needs them. florecon also had leaves for reference tokens shared in free text, running balances that clear in date order, and date windows.

## Where this comes from

Distilled from [florecon](https://github.com/spoj/florecon), which also allocates costs; allocation is out of scope here. Kept: the invariant, the strategy type, `seq`, `when`, `partition_by`, `accept_if`, and two leaves (florecon's `exact_1to1` and `soak`). Overrides are new.
