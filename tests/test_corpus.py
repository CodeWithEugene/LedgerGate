"""The benchmark has to be trustworthy before any score computed on it means anything."""

from __future__ import annotations

import json

import pytest
from conftest import DATA_ROOT

from ledgergate.corpus import HAZARDS, CorpusAuditError, audit_corpus, build_corpus
from ledgergate.store import load_corpus, verify_manifest
from ledgergate.types import Truth, to_json


def test_generation_is_deterministic():
    a = build_corpus("dev", 20260828, instances=3)
    b = build_corpus("dev", 20260828, instances=3)
    assert to_json(list(a.invoices)) == to_json(list(b.invoices))
    assert to_json(list(a.payments)) == to_json(list(b.payments))
    assert to_json(list(a.truths)) == to_json(list(b.truths))


def test_dev_and_holdout_are_genuinely_different():
    """Tuning on dev must not be tuning on holdout."""
    dev = build_corpus("dev", 20260828, instances=3)
    holdout = build_corpus("holdout", 20260831, instances=3)

    dev_amounts = {p.amount_cents for p in dev.payments}
    holdout_amounts = {p.amount_cents for p in holdout.payments}
    overlap = dev_amounts & holdout_amounts
    assert len(overlap) / len(holdout_amounts) < 0.05, f"splits share receipts: {overlap}"

    dev_memos = {p.memo for p in dev.payments}
    holdout_memos = {p.memo for p in holdout.payments}
    assert len(dev_memos & holdout_memos) <= 6  # only generic strings like "ACH CREDIT"


@pytest.mark.parametrize("name,seed", [("dev", 20260828), ("holdout", 20260831)])
def test_ground_truth_invariants_hold(name, seed):
    corpus = build_corpus(name, seed, instances=3)
    checks = audit_corpus(corpus)
    assert len(checks) >= 9


@pytest.mark.parametrize("name", ["dev", "holdout"])
def test_committed_corpus_matches_its_manifest(name):
    """Catches an edited data file, or a generator change that was not re-committed."""
    problems = verify_manifest(DATA_ROOT, name)
    assert problems == [], problems


@pytest.mark.parametrize("name,seed", [("dev", 20260828), ("holdout", 20260831)])
def test_committed_corpus_equals_a_fresh_generation(name, seed):
    on_disk = load_corpus(DATA_ROOT, name)
    fresh = build_corpus(name, seed, instances=3)
    assert to_json(list(on_disk.payments)) == to_json(list(fresh.payments))
    assert to_json(list(on_disk.invoices)) == to_json(list(fresh.invoices))


def test_every_hazard_class_is_exercised(dev_corpus):
    present = {t.hazard for t in dev_corpus.truths}
    assert present == set(HAZARDS)


def test_audit_actually_rejects_a_broken_corpus(dev_corpus):
    """A validator that never fails is decoration, not a control."""
    from dataclasses import replace

    broken = replace(
        dev_corpus,
        truths=tuple(
            Truth(t.payment_id, t.hazard, "MATCH", (), t.note) if i == 0 else t
            for i, t in enumerate(dev_corpus.truths)
        ),
    )
    with pytest.raises(CorpusAuditError):
        audit_corpus(broken)


def test_no_real_world_identifiers_leak_into_the_corpus():
    """Everything must be synthetic. Nothing here may resemble live data."""
    corpus = build_corpus("dev", 20260828, instances=3)
    blob = (to_json(list(corpus.invoices)) + to_json(list(corpus.payments))).lower()
    for forbidden in ("@", "iban", "swift", "sort code", "routing", "ssn", "http"):
        assert forbidden not in blob, f"{forbidden!r} appears in the synthetic corpus"


def test_money_is_always_integer_cents(dev_corpus):
    for invoice in dev_corpus.invoices:
        assert isinstance(invoice.amount_cents, int)
        assert isinstance(invoice.credit_note_cents, int)
    for payment in dev_corpus.payments:
        assert isinstance(payment.amount_cents, int)
    raw = json.loads((DATA_ROOT / "dev" / "payments.json").read_text())
    assert all(isinstance(row["amount_cents"], int) for row in raw)
