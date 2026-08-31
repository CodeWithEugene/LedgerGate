# Solution video script (target 4:45, hard limit 5:00)

Follows the required beats in order: **problem → simple baseline → one full
execution → final comparison → the changelog → the change that contributed most
→ one experiment removed.**

Screen recording plus voice. Terminal at a large font; one editor window.
Every command below is real, runs offline, and finishes in seconds.

**Before recording:** run `make setup` once so nothing waits on installation.
Check no terminal tab, editor tab, shell prompt, or `env` output shows a
credential. Recommend recording in a fresh shell.

---

## 0:00–0:45 — The problem

**On screen:** `data/holdout/payments.json`, scrolling slowly.

> "This is a morning's bank file for an accounts payable team. Dana's job is to
> decide which supplier invoice each receipt settles.
>
> Most of it is boring. The problem is the tail — a receipt short by fourteen
> euros because a correspondent bank took a fee, one wire covering four
> invoices where the reference only names the first, a supplier name the bank
> truncated so it fuzzy-matches two different vendors, two open invoices for
> the same amount.
>
> And the cost is asymmetric. Clearing an easy receipt saves a minute. Posting
> a hard one against the wrong invoice means two supplier balances are now
> wrong, and unwinding it is a manual journal, a phone call, and possibly a
> control finding. So Dana goes slowly on everything, because the expensive
> mistakes look exactly like the cheap ones until after you make them.
>
> An agent will clear seventy percent of this file in seconds and be
> confidently wrong somewhere in the tail. That's why this is still done by
> hand. Not because it's difficult — because nobody can bound the downside."

---

## 0:45–1:25 — The simple baseline

```bash
make eval-baseline
```

> "So here's the baseline. Resolve the supplier by name similarity, find an
> invoice with the same amount, widen the tolerance, take the first candidate.
> This is a fair baseline, not a strawman — nothing in it is sabotaged and it
> gets every clean receipt right."

Point at, in order: **net value −57985**, **false pays: 24**, and the
`postings the sandbox ledger refused` block.

> "Twenty-four false pays out of sixty. And these refusals are the *ledger*
> catching things the policy was fully prepared to do — pay an already-settled
> invoice, apply a euro receipt to a dollar invoice, process the same bank
> reference twice. The ledger saved it. The judgment was still wrong, and I
> score those separately, because a system that only works because the database
> said no is not a system that works."

---

## 1:25–2:40 — One realistic execution, start to finish

```bash
make trace-sample
```

Scroll through **one complete episode** without cutting away. Call out in order:

1. **The agent instructions** in the header — exactly what it was told.
2. **`procedure("identification")`** — the written SOP it works to.
3. **`resolve_vendor`** → two candidates, similarity scores close together.
4. **`find_invoice_by_number`** → the reference resolves.
5. **`compute`** — *"arithmetic is a tool call. It never does money maths in
   its head, so every calculation is in the record where you can check it."*
6. **`procedure("gaps")`** — AP-07.9. *"The procedure admits what it doesn't
   cover — cross-currency, overpayments, reversals, predated receipts — and it
   ends with 'do not infer a rule.' That's the interesting part. Real
   procedures have holes."*
7. **The gate verdict** — the veto, its reason code, and the clause it cites.
8. **The decision** — and either the posting or the analyst queue.

Then the human checkpoint:

```bash
make approve
```

> "High-value matches don't post. They queue. And the system cannot release its
> own queue — `approve` raises unless the caller declares a human. That's not a
> convention in a doc, it's a type error."

---

## 2:40–3:45 — The final comparison, and exactly what the gate caught

```bash
make headline
```

> "Same corpus, same frozen verifier — its SHA-256 is printed on every
> scorecard, so you can see the scoring rules didn't change between runs.
>
> The rows are in pairs: each proposer, then the same proposer behind the gate.
> Top pair is a deliberately reckless proposer that posts against the first row
> it sees. Then the baseline. Then a faithful implementation of the procedure.
>
> Look down the false-pay column. Forty-five, then zero. Twenty-four, then
> zero. Six, then zero. **The safety guarantee doesn't depend on how good the
> proposer is.**
>
> Now look at over-escalation — that's the cost, correct postings the gate
> withheld unnecessarily. Twelve, seven, zero. **The guarantee is flat. The
> price falls as the proposer improves.** So containment isn't a crutch you
> remove when the model gets good enough."

Point at the **sensitivity sweep**.

> "And because I chose the cost weights, the table re-scores across a
> forty-eight-fold range of false-pay penalties. The ranking never changes. It
> isn't an artefact of my constants."

Then, without pausing:

```bash
make gate-audit
```

> "And you don't have to take the bottom row on trust. This is every decision
> the gate changed, against ground truth. Six interventions out of sixty — and
> those six are *exactly* the six the written procedure would have paid wrongly.
> Three currency mismatches, three receipts dated before the invoice existed.
> Each one cites the clause it's enforcing, so it arrives on Dana's desk
> already explained.
>
> Bottom line is the one I'd point at: **correct postings blocked, zero.** Run
> it against the reckless proposer and it's still zero. The gate has never
> withheld a posting a proposer had right — so that over-escalation column
> isn't the gate refusing good answers, it's the proposer producing bad ones.
> I had those two conflated in the first version of this audit; entry thirteen.
>
> And the last line re-checks monotonicity on the run you just watched: the
> gate withheld only. It created no match and it altered no allocation."

---

## 3:45–4:12 — The changelog, and the change that mattered most

**On screen:** `docs/CHANGELOG.md`.

> "Every entry is labelled as either a design decision or an iteration driven
> by evidence, because conflating those would be its own kind of dishonesty.
>
> **The change that contributed most is entry eight.** I originally had a single
> ablation — one proposer, gate on and off, six false pays down to zero. I
> nearly shipped that as the headline. But it answers a narrower question than
> it looks like it does. It shows the gate helping *that* proposer, and it has
> no reply at all to the obvious objection: surely a strong model doesn't need
> a babysitter.
>
> So I made the gate wrap *any* proposer and added the reckless one as a lower
> anchor. That turned a single number into a shape — and the shape is the
> actual finding. One ablation could never have shown it."

Optionally show entry 5 for ten seconds:

> "And my favourite: the gate started vetoing consolidated receipts as
> predated. The gate was right and my *benchmark* was wrong — the generator
> dated them off the wrong invoice. A safety component found a labelling bug in
> the thing grading it. A gate derived from the answer key couldn't have
> disagreed with the answer key."

---

## 4:12–4:36 — One experiment I removed

> "Entry nine. I built the whole thing around a live model arm — a tool-using
> agent with record-and-replay cassettes, so an untrusted frontier model would
> be the top of that curve. It ran. I had about two hundred and thirty recorded
> responses.
>
> Then I checked how it was authenticating. The only endpoint I had was a
> third-party gateway that rejects any client not claiming to be a first-party
> tool — so the run was setting its user agent to `claude-cli` to get in. It was
> working because it was lying about what it was.
>
> I killed the run, threw away the recordings, and deleted the user-agent
> override so the header can't be reconfigured at all. The rules require using
> every component per its service terms, and a result you got by
> misrepresenting yourself isn't evidence. It cost me the strongest row in the
> table. The code is still in the repo and tested — anyone with a legitimate
> key runs two make targets and the row comes back."

---

## 4:36–4:58 — Main failure mode, and the hot take

> "Main failure mode, stated plainly: **a gate can only veto what someone
> thought of.** The hazard taxonomy is mine. The holdout resamples the same
> generator, so it proves robustness to different values and nothing about
> robustness to a different taxonomy. A hazard I didn't imagine is missing from
> both splits and wouldn't show up as a miss in any number I've shown you.
>
> The hot take: **the interesting artifact in an agentic system isn't the
> agent, it's the thing with the authority to say no.** Everyone is racing to
> make proposers smarter. A smarter proposer still can't demonstrate it should
> be trusted with a payment — its case for itself reads the same whether it's
> right or wrong. A small, monotone, independently-verifying gate can. And its
> guarantee didn't weaken as the proposer got better. Only its price did."

---

## Checklist before uploading

- [ ] Under 5:00.
- [ ] Opens with the problem, then the simple baseline.
- [ ] One full execution shown end to end, not cut away from.
- [ ] Retries / tool feedback and the human checkpoint both visible.
- [ ] Final comparison shown on screen with real output.
- [ ] `make gate-audit` shown — the claim checked against ground truth on camera.
- [ ] Changelog shown and briefly explained.
- [ ] The change that contributed most is named explicitly (entry 8).
- [ ] One removed experiment is named explicitly (entry 9).
- [ ] Main failure mode stated out loud.
- [ ] Hot take stated out loud.
- [ ] No API key, token, `.env`, or `env` output visible in any frame.
