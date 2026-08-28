# Prompts for the Claude Code window

Paste one at a time. Wait for the commit, check GitHub, then move on.

---

## Setup prompt 0 — before any stage

> Read CLAUDE.md. Then create `docs/data-model.md` documenting all
> four CSV ledgers: for each file, list every column, its data type,
> its unit (paise vs rupees), whether it can be null, and which
> columns form the join keys between ledgers. Where you don't know a
> column, list it as UNKNOWN and ask me. Also document the expected
> settlement formula and the tolerance rule. Commit as
> `docs: add data model spec`.

*Answer its questions from your actual CSV files. This one file
prevents most of the errors you'd otherwise hit later.*

---

## Stage 1 — scaffold

> Build stage 1 only: project scaffold. Create the folder structure
> described in README.md, a `requirements.txt` with pandas and
> pytest, a `config.py` holding the tolerance constant and the
> timezone, and empty `__init__.py` files. No logic yet. Show me the
> diff before committing.

---

## Stage 2 — loaders

> Build stage 2 only: one loader per ledger in `src/loaders/`. Each
> loader reads its CSV with `dtype=str` for all ID columns, parses
> dates explicitly in IST, converts every amount to integer paise,
> and returns a normalised DataFrame with a documented schema.
> Loaders must raise a clear error if an expected column from
> `docs/data-model.md` is missing — never silently fill or rename.
> Write a fixture CSV and a test for each loader. Show me the diff
> before committing.

---

## Stage 3 — matching engine

> Build stage 3 only: the matching engine in `src/matching/`. Join
> orders → payments → fees → settlements using the ID chain from
> `docs/data-model.md`, never by date proximity. Output a single
> reconciled DataFrame plus a separate `unreconciled` DataFrame
> where every row carries a reason for why it could not be matched.
> Nothing may be silently dropped — assert that input row count
> equals matched plus unreconciled. Add tests covering: clean match,
> missing payment, duplicate payment, and orphan settlement. Show me
> the diff before committing.

---

## Stage 4 — refunds and chargebacks

> Build stage 4 only: refund and chargeback detectors in
> `src/detectors/`. Each is a separate function returning order ID,
> anomaly type, expected amount, actual amount, delta, confidence,
> and reason. Write the positive and negative fixtures first, then
> the detectors. Use the tolerance constant from config.py — never
> compare amounts with `==`. Show me the diff before committing.

---

## Stage 5 — shortfalls and missing payments

> Build stage 5 only: settlement shortfall and missing payment
> detectors, same interface as stage 4. Shortfall uses the expected
> settlement formula from `docs/data-model.md`. Fixtures first.
> Then run the existing tests to confirm stages 2–4 still pass, and
> show me the output. Show me the diff before committing.

---

## Stage 6 — agent layer

> Build stage 6 only: the agent layer in `src/agent/`. It takes the
> structured output of the detectors and uses the Claude API to (a)
> classify ambiguous cases the rules marked low-confidence, and (b)
> write a one-sentence plain-English explanation for each flag. The
> agent must never modify or recompute any amount — assert this in a
> test. Read the API key from `.env`, and confirm `.env` is
> gitignored before you write any code. Show me the diff before
> committing.

---

## Stage 7 — eval harness

> Build stage 7 only: `evals/run_eval.py`. Create a labelled fixture
> set of 200 synthetic orders in `tests/fixtures/` containing
> exactly 15 refunds, 5 chargebacks, 8 shortfalls, and 3 missing
> payments, with a ground-truth labels file. The harness runs the
> full pipeline against it and prints precision, recall, and F1 per
> anomaly type plus overall match rate. Run it and paste the real
> output. Then fill the v0.1 row in the README accuracy table with
> those actual numbers. Show me the diff before committing.

---

## Stage 8 — reporting

> Build stage 8 only: report output. Generate a reconciliation
> report grouping flags by anomaly type, sorted by rupee impact
> descending, with a summary header showing total exposure. Output
> both CSV and a readable console summary. Run it on the fixtures
> and paste the output. Show me the diff before committing.

---

## Tagging a version

> Run the eval, append the results row to the README accuracy table
> as v0.2, commit, then tag v0.2 and push tags.

---

## Useful mid-flight prompts

**When something breaks:**
> The last commit broke things. Show me what changed, write a
> failing test that reproduces the bug, then fix it.

**When you don't trust a number:**
> Run the eval and paste the raw output. Don't summarise it.

**When it drifts out of scope:**
> Stop. You've changed files outside stage N. Revert anything not
> in scope and show me only the stage N changes.

**Before a demo:**
> Run the full pipeline end to end on the fixtures from a clean
> state and paste every command and its output, so I can confirm it
> works on a fresh machine.
