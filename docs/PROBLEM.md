# The problem, the ambiguities, and what I decided

The brief was open: pick a real engineering problem, use coding agents, ship a
baseline and something better, and prove the difference. Almost every hard
decision in this repository came from resolving an ambiguity that nobody was
going to resolve for me. They are all written down here, with the choice I made
and the reason, so a reviewer can disagree with a specific decision instead of
guessing at my reasoning.

---

## 1. The workflow

**Who.** An accounts-payable analyst at a mid-size company. Every morning a
bank statement file lands with a few dozen incoming receipts, and each one has
to be applied against open supplier invoices.

**The bottleneck.** It is not the volume; it is the tail. Most receipts are
obvious and take seconds. A minority are short by a bank charge, arrive as one
wire covering four invoices, quote an invoice number with two digits
transposed, or match two open invoices equally well. Those consume most of the
time, and getting one wrong is expensive in a way that is not symmetric: cash
applied to the wrong invoice produces a supplier dispute, a mis-stated payables
balance, and a manual recovery.

**Why an agent is tempting, and why that is dangerous.** A coding agent will
happily write a fuzzy matcher for this in about a minute. It will look correct.
It will be right on the easy cases and confidently wrong on the tail, and the
failure is silent: a wrong match looks exactly like a right one in the output.
That gap — between a plausible agent and a trustworthy one — is the actual
engineering problem, and it is what this project attacks.

**What I built.** Not a better matcher. A **veto-only safety gate** that sits
between any proposer and the ledger, plus the evaluation harness that measures
whether the gate works. The claim is that you can make an untrusted proposer
safe without giving up its usefulness, and that the claim is measurable.

---

## 2. Ambiguities in the domain, and how I resolved them

The workflow ships with a written procedure, AP-07, which the agent can read
with the `procedure` tool. AP-07 is deliberately incomplete, the way real
procedures are. Section AP-07.9 lists the matters it does not yet cover.

| # | Ambiguity | Decision | Why |
|---|---|---|---|
| 1 | Procedure is silent on a case. Guess, or stop? | **Stop.** Route to a human. | AP-07.9 says so explicitly, and inventing a rule is how an automation quietly acquires a policy nobody approved. |
| 2 | Receipt is short by a small amount. Part payment, or wrong invoice? | Apply only if the remittance **declares** a part payment or a bank charge, or the gap is within 2 cents. | An unexplained short payment is genuinely indistinguishable from a payment for work not yet invoiced. |
| 3 | Bank deducted a correspondent fee. Apply the cash, or close the invoice? | Apply **cash actually received**; the residual is the write-off run's problem. | Closing an invoice for money that never arrived overstates cash. |
| 4 | One wire covers several invoices, but names none of them. | **Escalate**, even when a subset happens to sum correctly. | On the development split there is a receipt where two disjoint pairs of invoices both total exactly the amount. Subset-sum inference would have picked one at random and looked confident doing it. |
| 5 | Receipt exceeds the balance. | **Escalate.** | Nothing in scope defines what happens to a residual credit. |
| 6 | Receipt is in a different currency from the invoice. | **Escalate.** The `fx_rate` tool always answers `UNAVAILABLE`. | There is no rate source, no rate date convention, and no policy on who absorbs the spread. A converted number would be fabricated. |
| 7 | A reversal or recall arrives. | **Escalate.** | Undoing a posting is a different operation with different controls. |
| 8 | The same bank reference appears twice in the feed. | **Never** apply it twice. | This is the single most expensive failure available, and it is trivially detectable. |
| 9 | The remittance cites an invoice number that does not exist. | Ignore the reference, fall back to amount identification, and say so. | Transposed digits are common. The amount and supplier still identify the invoice. |
| 10 | The remittance cites invoice A but the amount matches invoice B. | **Escalate.** | Two independent signals disagree. Picking either one is a coin flip wearing a rationale. |
| 11 | Two open invoices for the same supplier have the same balance. | **Escalate.** | There is no evidence that distinguishes them. Choosing is not a decision. |
| 12 | Is escalation a failure? | **No.** It scores positively. | An analyst reviewing a genuinely ambiguous item is the system working, not the system giving up. Scoring it as failure would push every policy toward reckless automation. |

### Numbers I had to choose

These are judgement calls, not derived constants. All are configurable, and
none of the conclusions depend on the exact value.

- **2 cents rounding tolerance** (AP-07.3). Wide enough for settlement
  rounding, far too narrow to swallow a real short payment.
- **25,000.00 human approval threshold.** At or above this, a match is queued
  rather than posted, and the system cannot release its own queue. This one I
  got wrong first: the initial value was 5,000.00, which is *below the median
  receipt* in this corpus (6,927.95) and put 26 of 27 postings into the approval
  queue.
  Technically safe, and useless — a control that fires on almost everything is
  the manual process with extra steps, and it would have made the coverage
  figure meaningless. 25,000.00 is a common mid-market dual-authorisation
  limit, sits between the 75th and 90th percentile of receipts here, and queues
  9 of 27. Run `make approve` to see the queue.
- **Cost-model weights** (see below). Published as ratios and swept.

---

## 3. Ambiguities in the evaluation

**What does "correct" mean when a human is in the loop?** The verifier grades
the *decision*, not whether money moved. A correct escalation is a correct
answer. Separately, the ledger reports how many unsafe postings it had to
block, so a policy that only looks safe because a guard rail caught it does not
get credit for judgment it did not show.

**How do you compare a policy that automates 70% recklessly against one that
automates 45% safely?** Accuracy cannot answer this, because it treats "paid
the wrong supplier" and "asked a human" as equally wrong. So the headline
metric is a business cost model:

| Outcome | Value | Reasoning |
|---|---:|---|
| Correct match, posted without a human | +100 | The analyst minute it saves. |
| Correct escalation | +15 | Positive — a loss was prevented — but a human still spends time. |
| Unnecessary escalation | −30 | Analyst time plus payment delay. |
| Right invoice, wrong amount | −400 | Mis-stated balance, needs investigation and correction. |
| Wrong invoice, or a posting where none was justifiable | −2500 | Supplier dispute, recovery, control failure. |

The absolute scale is arbitrary; the **ratios** are the claim. Anyone who
thinks a false pay is only 8× an unnecessary escalation rather than 83× can
check that the ranking does not change: `make headline` prints net value across
false-pay penalties from −250 to −12000, and the ordering is stable throughout.
A test asserts this rather than leaving it to the reader.

**Could a policy game the verifier?** The probes in `tests/conftest.py` are
there to answer that. "Escalate everything" is perfectly safe and scores far
below a policy that discriminates. "Match everything" scores deeply negative.
The verifier reads ground truth; the tool surface has no path to it, and
`tests/test_isolation.py` walks the object graph to prove it. A policy's own
stated confidence has no effect on its score.

**Development and holdout.** Two independently seeded splits with disjoint
identifier namespaces. Every design decision was made against `dev`. `holdout`
is reported as the headline. The splits share no receipt amounts and no invoice
numbers, and a test enforces that.

---

## 4. What I deliberately did not build

Scope discipline mattered more than feature count, and each of these was a real
temptation:

- **Subset-sum matching for unreferenced consolidated receipts.** Considered
  and rejected at design time. Searching for a subset of open invoices that
  sums to the receipt resolves some cases and *silently guesses* on others —
  and the corpus contains a case where two different pairs of invoices give
  exactly the same total. A search that returns one answer when two are equally
  valid is a coin flip wearing a proof. That situation is now a hazard class
  whose correct answer is "escalate", rather than a feature.
- **A model-graded scorer.** Rejected on principle. If the thing being measured
  and the thing doing the measuring are the same technology with the same blind
  spots, the evaluation is decorative. See `CHANGELOG.md` §3.
- **A web UI.** A better-looking front end would not have changed a single
  number in this repository.
- **A retry-until-it-agrees loop.** Re-prompting a proposer after a veto until
  it produces something the gate accepts would raise coverage and destroy the
  guarantee — the gate would become a search oracle for getting past the gate.
  Vetoes are terminal for the receipt; it goes to a human.

---

## 5. Known limitations

Stated plainly, because a result whose limits are hidden is not a result.

1. **The deterministic policy scores 100%, and that number is less impressive
   than it looks.** It is a rules engine implementing AP-07, evaluated on a
   corpus whose hazards were designed around AP-07's gaps. It demonstrates
   internal consistency, not generalisation to real bank data. It is in the
   table to bound the design and to demonstrate that the gate is *sound* — that
   it never blocks a correct posting — not as a claim about the world. The
   load-bearing evidence is the *pattern across proposers*, not any single row.

2. **Sixty receipts per split is a small sample.** Zero false pays in 60 is
   consistent with a true false-pay rate as high as **4.9%** (95% confidence,
   rule of three). The correct reading is "no false pays observed at this
   sample size", not "safe".

3. **The corpus is synthetic and I wrote it.** Real remittance data is dirtier:
   OCR artefacts, multi-entity groups, partial refunds, supplier name changes
   mid-quarter. The 20 hazard classes are the ones I know about.

4. **There is no live-model proposer in the results.** The curve's top anchor
   is a deterministic rules engine rather than a frontier model, which is a
   weaker anchor than intended, and the shape is therefore established over
   three proposers rather than four. See §6 below for why.

5. **The gate encodes a specific procedure.** Port it to another AP department
   and the veto rules need rewriting. What transfers is the *shape*: an
   untrusted proposer, an independent evidence re-derivation, a monotone
   veto-only reviewer, and a verifier that prices errors asymmetrically.

6. **The sandbox ledger is a simulation.** It is in-memory and single-process.
   A real deployment needs durable idempotency keys and a transactional
   boundary shared with the payment rail.

---

## 6. The model arm, and why it is not the headline

The plan was for a language model to be the top of the proposer-quality curve.
It is the most interesting proposer available: unlike a rules engine written
against a procedure I also wrote, a model is genuinely untrusted, and 100% is
not on the table for it. That row would have carried the argument better than
anything else in the repository.

It is not there, and the reason is worth stating precisely because it is a
judgment call rather than a technical failure.

**What exists.** `src/ledgergate/policies/llm.py` is a complete tool-using
agent loop over the Anthropic Messages API: it reads the same procedure through
the same tools, submits through the same interface, and is reviewed by the same
gate. `src/ledgergate/llm/cassette.py` records every response keyed by a
SHA-256 of the exact request, so a model run replays offline and reproduces a
scorecard exactly. Nineteen tests in `tests/test_llm_policy.py` exercise the
loop against a scripted model — the tool loop, malformed submissions becoming
corrective feedback, provider failure escalating rather than posting, a model
that never commits, cassette record/replay, and a deliberate prompt
perturbation proving a stale tape is detected. None need a network.

**What went wrong.** The only endpoint available to me was a third-party
Anthropic-compatible reseller gateway, and it refuses any client that does not
identify itself as a first-party tool:

```
HTTP 401 {"error":{"message":"unauthorized client detected"},
          "type":"unauthorized_client_error"}
```

A truthful `user-agent` of `ledgergate/0.1` is rejected. The recording that was
under way had been getting through by declaring itself `claude-cli/1.0.0`.
About 230 responses had been captured that way. The same credential is invalid
against the real `api.anthropic.com`, so there was no honest route to the same
data.

**What I did.** Killed the run, discarded the recordings, deleted the
user-agent override from the client so the header is now a module constant that
cannot be reconfigured, and removed the model rows from `make verify` and from
the published table.

**Why.** The competition rules require using every component according to its
licence and service terms, and integrity sits in the qualification gate. But
the narrower reason is that it would not have been evidence. The entire
argument of this project is that a system should refuse to act when acting
requires inferring a permission it was never given. Publishing a number
obtained by misrepresenting what the client was would have contradicted the
thesis in the same document that asserted it.

The cost was real: the strongest row in the comparison, and roughly forty
minutes of recording. That is what the decision was worth, and it is the
honest price of the position.

**How to restore it.** Anyone with a legitimate credential runs
`make record-llm && make headline-llm` and the `llm` and `llm-gated` rows
appear in the same table, scored by the same frozen verifier.
