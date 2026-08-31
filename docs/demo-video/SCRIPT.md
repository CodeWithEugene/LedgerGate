# LedgerGate demo — AI video production pack

**Live product:** https://ledgergate.vercel.app  
**Length:** 4:45–5:00  
**Aspect:** 16:9 (frames are 3200×1800, 2× 1600×900)  
**Look:** dark UI, no captions over numbers (the UI already has them)

Use the **primary timeline** in order. Extra frames at the end are B-roll.

How to feed this to a maker:

1. ElevenLabs / Play.ht / system TTS: paste `VOICEOVER.txt`.
2. CapCut, Descript, Premiere: drop frames on a 16:9 timeline using the durations below; attach that VO.
3. Runway / Kling / Luma / Veo image-to-video: one generation per scene. Use **Motion** as the image prompt. Keep motion subtle — this is a product UI, not a trailer.
4. Do not morph the table numbers. Prefer Ken Burns (slow pan/zoom) over “the UI animates itself.”

Voice: calm, slightly low, unhurried. Not a SaaS explainer. Think a senior engineer walking a reviewer through a control.

---

## Primary timeline

### Scene 01 — The morning file
- **File:** `frames/01-inbox-guarded.png`
- **Duration:** 18s
- **Motion:** Slow zoom toward the five metric cards, then drift down into the table. Hold on Posted 18 / Needs review 33 / Gate interventions 6.
- **On-screen (optional lower third):** Dana · cash application analyst
- **Voiceover:**

> This is a morning's bank file. Sixty receipts. Dana's job is to decide which supplier invoice each one settles.
>
> Most of it is boring. The problem is the tail — a receipt short by a bank fee, one wire covering four invoices, a supplier name the bank truncated so it matches two vendors.
>
> Clearing an easy receipt saves a minute. Posting a hard one against the wrong invoice means two balances are now wrong. So Dana goes slowly on everything, because the expensive mistakes look exactly like the cheap ones until after you make them.

---

### Scene 02 — The claim, on one table
- **File:** `frames/03-evaluation-curve-guarded.png`
- **Duration:** 22s
- **Motion:** Start wide. Zoom to the Wrong payments column. Pan down from `guarded` (0, green) through `baseline` (24, red) to `reckless` (45, red), then to `reckless+gate` (0, green).
- **Voiceover:**

> An agent will clear seventy percent of this file in seconds and be confidently wrong somewhere in the tail. That is why this is still done by hand — not because it is difficult, but because nobody can bound the downside.
>
> So we did not try to build an agent that is never wrong. We built a proposer that is allowed to be wrong, and a small gate that is only allowed to say no.
>
> Read the wrong-payment column. Every gated row is zero, no matter how bad the proposer is. That is the claim. The gate is a property of the system, not of the agent behind it.

---

### Scene 03 — Switch the agent
- **File:** `frames/04-policy-menu.png`
- **Duration:** 6s
- **Motion:** Hold. Slight push-in on the open menu. Do not invent extra items.
- **Voiceover:**

> Dana's header has a proposer switch. Same file. Different agent. Watch what happens to the queue.

---

### Scene 04 — Reckless, no gate
- **File:** `frames/07-inbox-reckless.png`
- **Duration:** 12s
- **Motion:** Zoom to Posted 23 and Gate interventions 0. Pan the table outcomes: “took the first row the invoice book returned.”
- **Voiceover:**

> Reckless. It posts against the first invoice it finds. Twenty-three posted. Zero gate interventions. Coverage looks great because it never stops. This is an agent you would never put in production — and the output looks just as confident as a correct posting.

---

### Scene 05 — Same terrible proposer, gate on
- **File:** `frames/07b-inbox-reckless-gate.png`
- **Duration:** 14s
- **Motion:** Zoom to Needs review 45 and Gate interventions 45. Pan the amber banner: “withheld 45 proposed postings.”
- **Voiceover:**

> Same terrible proposer. Gate on. Posted collapses to ten. The queue fills — forty-five interventions. Vendor mismatch, already settled, over-application. The gate did not make the agent smarter. It made a bad agent safe to sit next to.

---

### Scene 06 — Back to Guarded
- **File:** `frames/08-inbox-guarded-return.png`
- **Duration:** 8s
- **Motion:** Hold on the five cards. Posted 18, awaiting 9, needs review 33, six gate interventions.
- **Voiceover:**

> Guarded is the one we would actually deploy. Procedure first, gate behind it. Eighteen posted on their own. Nine are right but over the limit. Six the agent wanted to post, and the gate refused.

---

### Scene 07 — The escalation queue
- **File:** `frames/09-needs-review.png`
- **Duration:** 16s
- **Motion:** Slow pan down the withheld cards. Pause on Everline Textiles, currency mismatch, AP-07.9(i).
- **Voiceover:**

> An escalation you still have to investigate from scratch has saved nobody anything. So this queue leads with the reason and the clause, not a receipt number.
>
> The agent proposed a posting for each of these. The gate refused. The gate can only refuse — it never invents a match — so this is a payment that would otherwise have gone out.

---

### Scene 08 — One receipt, start to finish
- **File:** `frames/10-receipt-everline-gate.png`
- **Duration:** 22s
- **Motion:** Start on the title “€8,843.10 from EVERLINE TEXTILES.” Push in on CURRENCY_MISMATCH. Then pan the “What the agent did” log: procedure, vendor, invoice, FX, withheld.
- **Voiceover:**

> Everline Textiles. Every signal agrees — vendor at 1.0, invoice number, same amount. The procedure says pay.
>
> Then the gate checks something the proposer never looked at. The receipt is in euros. The invoice is in dollars. There is no rate source, so any converted number would be invented.
>
> Verdict: withheld. Currency mismatch, clause AP-07.9. Nothing posted. Analyst queue. The procedure said pay. The written rule says this is a case the procedure does not cover. The gate is what knows the difference.

---

### Scene 09 — The clause is a link
- **File:** `frames/12-procedure-clause.png`
- **Duration:** 10s
- **Motion:** Push in on the highlighted card “Where the procedure stops,” AP-07.9. Glance the tool list on the right: `fx_rate`, `compute`.
- **Voiceover:**

> The citation is a link, not a code. Dana reads the rule the business wrote, in the words they wrote it. Arithmetic and FX are tools, not things the agent does in its head.

---

### Scene 10 — Dual authorisation
- **File:** `frames/13-approvals.png`
- **Duration:** 8s
- **Motion:** Hold on the first card, $29,376.73, then the Approve button.
- **Voiceover:**

> These matches are right. They are just at or above twenty-five thousand, so a person signs before the money moves. The threshold is a policy dial. The gate is what makes the decision safe. This is what makes the large ones accountable to a name.

---

### Scene 11 — The ledger will not release itself
- **File:** `frames/14-approve-dialog.png`
- **Duration:** 12s
- **Motion:** Slow zoom to “Your name” and the note that the ledger rejects any approval that does not name a person.
- **Voiceover:**

> The interface has no privileged path. Approve goes through the same ledger call as the command line. If you do not declare a human, it raises. That is not a convention in a document. It is a type error. The system cannot release its own queue.

---

### Scene 12 — Reviewer's scorecard
- **File:** `frames/16-evaluation-scorecard.png`
- **Duration:** 14s
- **Motion:** Hold the ground-truth banner, then zoom Net value +3,195 and Wrong payments 0. Pan the hazard table: zeros in every penalty column.
- **Voiceover:**

> Everything Dana just used is only what a real deployment would know. There is no answer key on those screens. This page is the reviewer's view — it grades against labels that exist so we can measure the gate, not so Dana can peek.
>
> Guarded: plus three thousand one hundred ninety-five. Zero wrong payments. One hundred percent exact. Forty-five percent decided, the rest abstained rather than guessed.

---

### Scene 13 — Close
- **File:** `frames/18-inbox-close.png`
- **Duration:** 10s
- **Motion:** Slow pull-out to the full inbox. End still.
- **Voiceover:**

> We did not build an agent that never gets cash application wrong. We built one that is allowed to be wrong, and a gate that can only say no — then we measured what that safety is worth in money.

---

## B-roll (cutaways, 2–4s each)

Use if a scene needs a second angle. Do not add new VO.

| File | Use |
| --- | --- |
| `frames/02-inbox-needs-review-tab.png` | Cut to the Needs review tab on Inbox |
| `frames/05-evaluation-curve-reckless.png` | Header set to Reckless on the same comparison table |
| `frames/06-evaluation-curve-reckless-gate.png` | Header set to Reckless + gate |
| `frames/09b-needs-review-full.png` | Full withheld list |
| `frames/11-receipt-everline-investigation.png` | Scrolled investigation log |
| `frames/12b-procedure-full.png` | Full AP-07 page |
| `frames/15-invoice-register.png` | What the agent searches |
| `frames/17-evaluation-audit.png` | Gate audit tab |
| `frames/17b-evaluation-audit-full.png` | Full audit |

---

## Edit notes

- **Music:** none, or a very low drone under −20 dB. Let the UI and voice carry it.
- **Cursor:** do not fake a cursor unless you composite one. The stills already imply the click.
- **Do not show:** Evaluation numbers on operator screens as if Dana can see them. Scene 12 is the only place ground truth is allowed, and the VO says so.
- **Do not claim:** Resolve posts an allocation. Approvals post. Resolve only records a disposition.
- **Numbers to keep on screen (holdout, guarded):** 60 receipts · posted 18 · awaiting 9 · needs review 33 · gate 6. Reckless: posted 23, gate 0. Reckless+gate: posted 10, gate 45. Scorecard: +3,195 · 0 wrong · 100% exact · 45% decided.
- **Hard cut** between 04→05 and 05→06. Those are before/after. Do not dissolve — the whole point is the counts jumping.

## Duration check

01 18 + 02 22 + 03 6 + 04 12 + 05 14 + 06 8 + 07 16 + 08 22 + 09 10 + 10 8 + 11 12 + 12 14 + 13 10 = **172s** of picture against ~650 spoken words. If the VO runs long, extend 02, 05, 07, and 08 rather than speeding up the reader.
