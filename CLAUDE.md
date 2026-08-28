# Working rules for Claude

Read this fully before every task. Also read `docs/data-model.md`
before touching any code that reads a CSV.

---

## 1. Session start checklist

Before doing anything else in a new session, run these and report
the result in two lines:

```bash
git remote -v
git status
```

- If there is no `origin` remote, stop and tell me. Do not start
  writing code into an untracked folder.
- If there are uncommitted changes from a previous session, show me
  what they are and ask what to do before proceeding.
- If `git status` shows the branch is ahead of `origin/main`, push
  first, then continue.

## 2. GitHub connection

This project pushes to a GitHub remote called `origin` on branch
`main`. Authentication is already handled by the GitHub CLI (`gh`)
on this machine — you do not need tokens, keys, or credentials.

- If a git or `gh` command fails with an authentication error, stop
  immediately and tell me to run `gh auth login`. Never attempt to
  work around it, never create a token, never edit credential files.
- If `origin` is missing entirely, tell me, and offer to run:
  `gh repo create finance-controller --private --source=. --remote=origin --push`
- Verify with `gh auth status` if anything looks wrong. Report the
  output rather than interpreting it for me.

## 3. Commits and pushes

- **Never commit without asking me first.**
- Before every commit show me: files changed, a one-line summary of
  each, and the exact commit message you plan to use. Then wait for
  my yes.
- **Every approved commit is immediately followed by
  `git push origin main`.** A commit that exists only locally is not
  done.
- If the push fails, stop and tell me immediately. Do not start the
  next task with an unpushed commit sitting locally.
- One commit per logical change. Never bundle unrelated work into a
  single commit. If a task produced two unrelated changes, make two
  commits.
- After every successful push, report exactly:

      Committed: <message>
      Files: <count>
      Pushed to: origin/main
      Commit: <short hash>
      Eval: <recall/F1 summary, or "not run — no logic change">

## 4. What makes a commit message meaningful

Format: `<type>: <what changed, imperative, under 60 chars>`

Types: `feat:` `fix:` `chore:` `docs:` `refactor:` `test:`

Rules:

- Describe **what changed and why it matters**, not which files you
  touched. Git already knows the files.
- Imperative mood: "add settlement shortfall detector", not "added"
  or "adding".
- Be specific enough that I could find this commit six months later
  from the message alone.
- If the change is not self-explanatory, add a body after a blank
  line explaining the reasoning or the tradeoff.
- Never use vague messages: "update", "fix bug", "changes", "wip",
  "misc". If you cannot describe it specifically, the commit is
  probably bundling unrelated work — split it.

Good:

    feat: add settlement shortfall detector with tolerance config
    fix: prevent pandas coercing payment IDs to float on CSV read
    refactor: move expected-settlement formula into single function

Bad:

    update detectors
    fix stuff
    stage 4 done

## 5. Scope discipline

- Build only the stage I ask for. Do not scaffold ahead.
- Do not refactor, rename, or "clean up" code I did not mention.
- If a stage seems to need something from a later stage, stop and
  ask me instead of building it.
- If my instruction is ambiguous, ask one clarifying question before
  writing code. Do not guess and proceed.

## 6. Never invent data

- Never invent CSV column names. Read the actual header row first,
  or read `docs/data-model.md`. If a column I described does not
  exist in the file, stop and tell me.
- Never fabricate sample data that hides a bug. Test fixtures must be
  explicitly labelled as fixtures and live in `tests/fixtures/`.
- Never hardcode a value to make a test pass.
- If a calculation depends on a business rule not written down in
  `docs/data-model.md`, ask me for the rule and then add it to that
  file in the same change.

## 7. The determinism boundary

This is the core architectural rule of the project.

- **Matching and arithmetic are deterministic Python.** Joining
  orders to payments to fees to settlements, and computing expected
  vs actual amounts, is pandas. Never an LLM call.
- **The LLM classifies and explains.** Why a gap exists, how to
  handle messy or partial records, and the human-readable reason
  attached to each flag.
- Never move a numeric decision into an LLM call. If you think a
  calculation is too messy for code, tell me why instead.

## 8. Money handling

- Represent all amounts as integer paise. Never float rupees.
- Never compare amounts with `==`. Use an explicit tolerance constant
  defined in one place (`config.py`), default 100 paise.
- Every amount column must have its currency and unit confirmed
  against `docs/data-model.md` before use.
- Round only at display time, never mid-calculation.
- GST on fees is a separate line from the fee itself. Do not merge
  them.

## 9. Dates and IDs

- Parse dates explicitly with a stated format. Never rely on pandas
  inferring.
- State and enforce one timezone project-wide (IST). Convert on read,
  not scattered through the code.
- Settlement lags payment by days. Never match on date proximity
  alone; always match on the ID chain first.
- Treat all IDs as strings. Never let pandas coerce them to int or
  float (use `dtype=str` on read).

## 10. Detection rules

Every anomaly detector must:

- Be a separate, individually testable function.
- Return a structured result: order ID, anomaly type, expected
  amount, actual amount, delta, confidence, and a reason string.
- Have at least one positive fixture and one negative fixture in
  `tests/fixtures/` written *before* the detector.
- Never silently drop rows. Unmatched or unparseable rows go to an
  explicit `unreconciled` bucket with a reason.

## 11. Accuracy and evals

- `evals/run_eval.py` is the source of truth for accuracy. Report
  precision, recall, and F1 per anomaly type, plus overall match rate.
- Never state an accuracy number you did not just measure. If I ask
  how accurate something is and you have not run the eval, run it.
- Recall is the priority metric. A missed discrepancy is real money
  lost; a false positive is a human glance.
- **Regression gate:** before any commit that touches detection
  logic, run the eval. If recall on any existing anomaly type drops,
  do not commit. Show me the before/after numbers and stop.
- Before tagging a version, run the eval, append a row to the
  accuracy table in README.md, and put the version in the commit
  message. Tags are pushed with `git push --tags`.

## 12. Verification before claiming done

- Never say something works until you have run it.
- Run the relevant tests and paste the actual output.
- If you could not run something, say so explicitly. Do not describe
  intended behaviour as if it were observed behaviour.
- When you fix a bug, first write the failing test, then fix.

## 13. Never commit

- `.env`, API keys, tokens
- CSVs containing real merchant or transaction data
- `__pycache__`, `.venv`, `*.pyc`
- Anything in `data/` except `data/README.md`

If you are about to stage a file matching any of these, stop and
tell me instead.

## 14. Docs

- When a stage completes, update README.md (status checkboxes, the
  "Running it" section, and the accuracy table) before committing.
- When you learn or confirm a business rule, add it to
  `docs/data-model.md` in the same change.

## 15. Definition of done for a stage

A stage is not done until all of these are true:

1. The code runs end to end on the fixtures.
2. Tests exist and pass.
3. `evals/run_eval.py` has been run and did not regress.
4. README.md is updated.
5. You have shown me the diff and I have said yes.
6. The commit is **pushed** and you have reported the hash.
