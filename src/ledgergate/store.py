"""Persist and reload a corpus, with content hashes.

The corpus is committed to the repository rather than generated at evaluation
time. Both paths are supported and both must agree: ``make corpus`` regenerates
from the seed and ``make verify-corpus`` re-derives the hashes and compares
them to the committed manifest. If a change to the generator silently altered
the benchmark, the manifest check fails and every published number is
invalidated on the spot.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .corpus import Corpus
from .types import (
    allocations_from_list,
    invoice_from_dict,
    payment_from_dict,
    to_json,
    truth_from_dict,
)

FILES = ("invoices.json", "payments.json", "opening_ledger.json", "truth.json")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_corpus(corpus: Corpus, root: Path) -> dict[str, str]:
    """Write the corpus to ``root`` and return the file hash manifest."""
    directory = root / corpus.name
    directory.mkdir(parents=True, exist_ok=True)

    (directory / "invoices.json").write_text(to_json(list(corpus.invoices)), encoding="utf-8")
    (directory / "payments.json").write_text(to_json(list(corpus.payments)), encoding="utf-8")
    (directory / "opening_ledger.json").write_text(
        to_json(list(corpus.opening_allocations)), encoding="utf-8"
    )
    (directory / "truth.json").write_text(to_json(list(corpus.truths)), encoding="utf-8")

    hashes = {name: sha256_file(directory / name) for name in FILES}
    manifest = {
        "name": corpus.name,
        "seed": corpus.seed,
        "invoices": len(corpus.invoices),
        "payments": len(corpus.payments),
        "sha256": hashes,
    }
    (directory / "manifest.json").write_text(to_json(manifest), encoding="utf-8")
    return hashes


def load_corpus(root: Path, name: str) -> Corpus:
    directory = root / name
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))

    def read(filename: str) -> list:
        return json.loads((directory / filename).read_text(encoding="utf-8"))

    return Corpus(
        name=manifest["name"],
        seed=int(manifest["seed"]),
        invoices=tuple(invoice_from_dict(d) for d in read("invoices.json")),
        payments=tuple(payment_from_dict(d) for d in read("payments.json")),
        opening_allocations=allocations_from_list(read("opening_ledger.json")),
        truths=tuple(truth_from_dict(d) for d in read("truth.json")),
    )


def verify_manifest(root: Path, name: str) -> list[str]:
    """Return a list of mismatch descriptions; empty means the corpus is intact."""
    directory = root / name
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    for filename, expected in manifest["sha256"].items():
        actual = sha256_file(directory / filename)
        if actual != expected:
            problems.append(f"{name}/{filename}: expected {expected[:16]}, found {actual[:16]}")
    return problems
