# Clean-room verification image.
#
#   docker build -t ledgergate:verify .
#   docker run --rm ledgergate:verify
#
# The default command runs the whole offline gate: corpus hash audit, the test
# suite, the baseline and advanced evaluations, the comparison table, and the
# gate audit. It needs no network access at run time and no API key -- every
# policy it exercises is deterministic.
#
#   docker run --rm --network none ledgergate:verify
#
# The image must contain everything the repository does that a test reads, or
# the container quietly runs a weaker suite than the author does. That already
# happened once: `traces/` was not copied, so the test asserting every declared
# tool is actually exercised skipped here and passed locally. A skip is not a
# pass, and the container is the environment a reviewer trusts.

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PYTHONPATH=/app/src \
    TZ=UTC

WORKDIR /app

# The only third-party package in the image is the test runner. Pinning it
# here keeps the layer cached and keeps the runtime dependency count at zero.
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir --upgrade pip==26.2 \
 && pip install --no-cache-dir -r requirements-dev.txt

COPY pyproject.toml Makefile Dockerfile ./
COPY README.md CONTRIBUTING.md SECURITY.md LICENSE ./
COPY src/ ./src/
COPY tests/ ./tests/
COPY data/ ./data/
COPY docs/ ./docs/
COPY cassettes/ ./cassettes/
COPY results/ ./results/
COPY traces/ ./traces/
COPY scripts/ ./scripts/

# Run as an unprivileged user: nothing in the verification path needs root.
RUN useradd --create-home --uid 10001 verifier \
 && mkdir -p results traces \
 && chmod +x scripts/*.sh \
 && chown -R verifier:verifier /app
USER verifier

# The same script `make verify` runs, so the container cannot drift from the
# local gate.
CMD ["sh", "scripts/verify.sh"]
