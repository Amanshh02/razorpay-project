# Understanding this project

A plain-language explanation, written for someone with no programming
background. No prior knowledge is assumed. Every technical word is
explained the first time it appears, and every calculation is worked
through with real numbers taken from the project's own test data.

If you want the engineering version, that is
[`PROJECT_REPORT.md`](PROJECT_REPORT.md). This document covers the same
ground in ordinary English.

---

## 1. The problem, in one picture

Imagine you run a small online shop. A customer buys something for
₹41,310.64. You'd expect that money — minus a fee — to turn up in your
bank account a few days later.

Between the customer's card and your bank account, **four different
organisations each write down what they think happened**:

1. **You** write down the sale. "Customer paid ₹41,310.64."
2. **The payment gateway** (Razorpay) writes down what it actually
   collected from the card.
3. **The payment gateway** separately writes down its fee — its cut for
   processing the payment, plus tax on that fee.
4. **Your bank** writes down what it actually deposited into your
   account.

A **ledger** is just a formal word for a list of financial records — a
notebook of transactions. So there are four ledgers, kept by different
parties, describing the same money.

They should all agree. **Often they don't.**

> **The analogy.** Four people watch the same car accident and each
> writes a statement. Individually, each statement looks fine. It's only
> when you lay them side by side that you notice one person says the car
> was blue and another says green. Reconciliation is laying the
> statements side by side.

**Reconciliation** is the accounting term for that comparison: checking
records from different sources against each other to find where they
disagree. Today, most small merchants do this by hand in a spreadsheet,
once a month, and often badly. It is boring, repetitive, and the errors
are invisible — money that quietly never arrived doesn't announce
itself.

**This project automates that comparison.** It reads all four ledgers,
lines them up order by order, works out what *should* have been paid,
compares it to what *was* paid, and produces a list of every
disagreement with an explanation.

On the sample data used throughout this project — 130 orders — it finds
**₹481,919.30 of money that doesn't add up**, across 31 of those 130
orders. Nearly one order in four.

---

## 2. The four ledgers, in detail

The data arrives as four **CSV files**. CSV stands for "comma-separated
values" — a plain text file where each line is a record and commas
separate the fields. If you've ever saved a spreadsheet as `.csv`, it's
that. You can open one in Notepad and read it.

Here are the four, with what each contains:

### `orders.csv` — what the merchant believes

One line per order. Contains the order's ID, the date, which customer,
and three amounts: the price before tax, the tax charged to the
customer, and the total. It also names the payment it expects to be
linked to.

### `payments.csv` — what the gateway collected

One line per payment. The payment's ID, which order it belongs to, when
it was captured, how much, and by what method (card, UPI, wallet, net
banking).

### `fees.csv` — what the gateway charged

One line per payment. The gateway's fee, the tax on that fee, and the
two added together.

> **Two different taxes, and this matters.** There is tax the *customer*
> pays on the *purchase*, and tax the *merchant* pays on the gateway's
> *fee*. They're different amounts on different things. The project
> keeps them strictly separate — merging them would be a silent, serious
> error.

### `settlements.csv` — what the bank actually paid

One line per payout. Which payment it settles, when, how much, and the
bank's reference number.

### How they link together

Each ledger carries an ID that points at the next. The project follows
that chain — and **only** that chain:

```
an order  ──names──>  a payment  ──has──>  a fee
                            └───has───>  a settlement
```

> **Why not match by date?** Because the delay between a payment being
> taken and the money arriving isn't fixed. In this data it ranges from
> **1.59 to 4.06 days**, varying order by order. If you tried to pair
> things up by "these happened around the same time", you would pair the
> wrong ones. The ID chain is exact; dates are not.

One more trap: the bank's reference number (called a **UTR**) looks like
a unique identifier but isn't. In this data, **four reference numbers
each appear on two different payouts**, because the bank sometimes
bundles payouts into a single transfer. Using it to match would silently
merge unrelated records.

---

## 3. The arithmetic

Here is the whole calculation, in one line:

> **What you should be paid = what was collected − the gateway's fee −
> the tax on that fee.**

That's it. Everything else in this project is applying that sentence
carefully and investigating what happens when it doesn't hold.

### Worked through, with a real order

This is `ord_00003`, taken directly from the project's test data.
Nothing here is invented:

```
  Customer was billed             ₹41,310.64
  Gateway collected               ₹41,310.64     ← same, as it should be
  Gateway's fee                      ₹826.21
  Tax on that fee                    ₹148.72
                                  ───────────
  Total deducted                     ₹974.93

  So you SHOULD receive           ₹40,335.71     (41,310.64 − 974.93)
  Bank ACTUALLY paid              ₹40,335.71
                                  ───────────
  Difference                           ₹0.00     ✓ clean
```

The difference is exactly zero. That order is fine, and the project
leaves it alone.

**99 of the 130 orders look exactly like this** — perfect agreement, to
the last paisa. The interesting work is the other 31.

### The word for the difference

Throughout the project, that final difference is called the **delta** —
a standard term for "the gap between expected and actual". A negative
delta means you were paid *less* than you should have been.

### A small tolerance

Amounts are never compared for *exact* equality. The project treats
anything within **₹1** as agreement. This is standard practice: when
different computer systems round amounts slightly differently, a
one-rupee gap is noise, not fraud.

On this particular data the tolerance isn't doing any work — the 99
clean orders are exact to **0 paise**, not merely close. It exists for
real-world data, where small rounding differences genuinely occur.

---

## 4. The four things that go wrong

Every problem this project finds is a negative delta — you got less than
you should have. What differs is *why*. Here is each one, with a real
example.

### 4.1 A settlement shortfall

The bank simply paid less than the arithmetic says, and nothing explains
it.

Real example, `ord_00001`:

```
  You should have received        ₹22,568.47
  Bank actually paid              ₹21,863.89
                                  ───────────
  Short by                           ₹704.58     (3.05% of the sale)
```

₹704.58 is missing and no ledger says why. Not a refund, not a
reversal — just less money than expected.

### 4.2 A refund that nobody recorded

A customer got their money back. The gateway took that refund out of
your payout. **But no ledger you hold records the refund**, so from your
side the money just vanished.

Real example, `ord_00002`:

```
  You should have received        ₹52,235.48
  Bank actually paid              ₹36,186.07
                                  ───────────
  Short by                        ₹16,049.41     (30% of the sale)
```

Exactly 30% of the sale went back to the customer. Your books don't show
it. Your bank balance does.

### 4.3 A chargeback

A **chargeback** is when a customer disputes a payment with their card
provider and the money is forcibly reversed. The gateway takes back the
whole sale **and** charges a penalty on top for the trouble.

Real example, `ord_00024`:

```
  You should have received         ₹5,040.35
  Bank actually paid                 −₹621.82    ← NEGATIVE
                                  ───────────
  Short by                         ₹5,662.17     (109.7% of the sale)
```

Look at that middle line. The bank didn't pay you less — **it took money
out**. You lost the entire sale plus ₹500 in penalty, so the payout is
negative.

This is why the software has to handle negative amounts properly.
**12 of the 127 payouts in this data are negative.** A program that
assumed money only flows one direction would either crash or silently
produce nonsense.

> **The tell-tale sign.** A chargeback is the only case where you lose
> *more than the sale was worth*. Above, the shortfall is 109.7% of the
> sale. That "more than 100%" signature is what lets the software
> recognise a chargeback with certainty.

### 4.4 A payment that never arrived

You recorded a sale. The gateway has no record of it at all.

Real example, `ord_00006`:

```
  You recorded a sale of          ₹14,757.93
  Gateway's record                 (none)
  Bank paid                            ₹0.00
                                  ───────────
  At risk                         ₹14,757.93     — the entire sale
```

Here the exposure is the **full amount**, with no fee deducted. The
reasoning is simple: if the gateway never received the payment, it never
charged a fee for processing it. Deducting a fee that was never charged
would understate what you actually lost.

*(This turned out to be a genuine error in the project's own test data,
caught and corrected. See §8.2.)*

### 4.5 And one in the other direction

The bank paid **more** than expected. This isn't good news — it usually
means a duplicate payout or a correction that will be clawed back later.

The project reports overpayments **completely separately** from money
owed, and never subtracts one from the other. If you had ₹200,000
missing and ₹200,000 overpaid and you netted them off, you'd report zero
problems while having two serious ones.

---

## 5. Why money is counted in whole paise

This is a small detail with large consequences, and it's worth
understanding because it's a classic and expensive mistake.

**The project never stores an amount as a decimal number of rupees.**
Every amount is stored as a whole number of paise. ₹41,310.64 is stored
as `4131064`.

### Why? Because computers can't store some decimals exactly

Computers work in binary — powers of two. Just as you cannot write
one-third exactly in decimal (0.3333... forever), a computer cannot
store many ordinary decimal fractions exactly. It stores the closest
value it can and the tiny error hides.

The most famous demonstration:

```
  0.1 + 0.2  should be  0.3
  a computer gets       0.30000000000000004
```

Individually harmless. Across thousands of transactions, the errors
accumulate and your books stop balancing.

### A real example from this project's data

Order `ord_00046` has a pre-tax amount of ₹27,588.75. The tax is 18%.

Doing it in **whole paise**, as the project does:

```
  2758875 × 0.18 = 496597.5  →  rounds to  496598 paise  =  ₹4,965.98
```

Doing it in **decimal rupees**, the naive way:

```
  27588.75 × 0.18  the computer calculates  4965.974999999999
                   rounded to 2 decimals =  4965.97
                                         =  496597 paise
```

**One paisa different.** The true answer ends in exactly `.975`, which
should round up — but the computer's stored value is a hair *below*
that, so it rounds down instead.

It gets worse. Converting an amount to rupees and back again doesn't
even return the original number. Three real examples from this data:

```
  1911685 paise  →  ₹19,116.85  →  back to  1911684.9999999998
  3915609 paise  →  ₹39,156.09  →  back to  3915608.9999999995
  4087730 paise  →  ₹40,877.30  →  back to  4087730.0000000005
```

Two of those three lose a paisa if the computer simply chops off the
decimal part. **18 of the 127 payment amounts in this data fail to
survive that round trip.**

Using whole numbers makes the entire category of error impossible.
`10 + 20 = 30` is always exactly true. There is no rounding, because
there is nothing to round.

---

## 6. Is this artificial intelligence?

Partly, and it's worth being exact, because "AI" is used loosely.

### Nothing was trained. No machine learning happened here.

**Machine learning** means showing a computer many examples and letting
it adjust itself until it gets good at a task — the way you might learn
to recognise a friend's handwriting from seeing lots of it. The result
is a **model**: a large set of numbers, learned from data, that the
computer consults to make predictions.

**None of that happened in this project.** There is no training step, no
learned numbers, no fitting, nothing that improves by looking at
examples. Searching the entire codebase for any training operation
returns nothing.

The rules the project uses are ordinary arithmetic that a person wrote
down. Three of them contain a number chosen by a human judgement call
rather than derived from anything — and the code says so in a comment,
describing them as *"heuristics tuned on synthetic fixtures, not
contractual values"*. **A person choosing a number is not machine
learning.** Calling it that would be false.

### What *is* used

A **large language model** — the technology behind ChatGPT and Claude.
Specifically Claude Sonnet 4.6, used exactly as it comes. Not trained,
not adjusted, not fine-tuned for this project in any way.

> **The analogy.** Think of it as phoning a knowledgeable colleague. You
> describe one specific case, they give you an opinion, you hang up. You
> don't teach them anything, they don't remember the call, and you
> certainly don't let them do your arithmetic.

### What the language model does

When the arithmetic finds a gap, the software often can't tell *why*.
A missing ₹16,049.41 could be an unrecorded refund or an unexplained
shortfall — the four ledgers contain nothing that distinguishes them.

So for the uncertain cases only, the software describes the situation in
words and asks the model what it thinks. The model replies with three
things: a label, how confident it is, and one sentence of explanation in
plain English.

Concretely, per full run: **43 questions asked**, each one independent.

### What it is structurally prevented from doing

This is the important part. The model is not trusted with anything it
could damage:

- **It cannot change a single number.** Its reply has no field for an
  amount. The amounts are calculated before it's consulted and copied
  through untouched afterwards. An automated check verifies every amount
  is byte-for-byte identical before and after — including a deliberately
  hostile test where the model overrules *every* case.
- **It cannot decide what the program does next.** It has no ability to
  run anything. It answers one question and stops.
- **It cannot overrule a confident calculation.** Cases the arithmetic
  is certain about are never shown to it at all.
- **It cannot see the answer key.** The file containing the correct
  answers is off-limits to everything except the marking script.

> **Why so restricted?** Because a language model that can act on a
> settlement calculation is one that can corrupt it. A merchant defending
> a figure to an auditor needs that figure to be reproducible — the same
> input giving the same output, every time, for a reason you can point
> at. Arithmetic does that. Generated text does not.

### What it actually contributed

Measured honestly: on the harder of two test sets, overall accuracy went
from **0.615 to 0.731**. The entire improvement came from **one** of the
five problem types — chargebacks where the penalty wasn't the usual ₹500
— which went from 0.571 to a perfect 1.000.

On the easier test set it changed nothing at all: it reviewed 23 cases,
agreed with all 23.

So: the language model improved one category out of five, on one test
set out of two. That's a real fix to a real weakness. It is not the
model "doing the reconciliation" — the arithmetic does that.

---

## 7. How it was built

The project was built in nine numbered stages, each finished and checked
before the next began. Some vocabulary first:

- A **commit** is a saved checkpoint with a description of what changed.
  This project is built from several dozen, each one reviewed before it
  was saved.
- A **test** is a small automated check that some specific behaviour is
  correct. They run in seconds and catch mistakes immediately. This
  project has **193**.
- **Test data** (or **fixtures**) is fake but realistic data used for
  checking. Real merchant data is never used.

### The stages

**Before stage 1 — write down what the data means.** Before any code, a
specification was written describing all four files: every column, what
unit it's in, how the files link. Crucially, every claim in it was
*checked against the actual data* rather than assumed.

**Stage 1 — the skeleton.** Empty folders and two settings: the ₹1
tolerance and the timezone. Almost no code — and it still contained a
bug that would have surfaced much later (§8.1).

**Stage 2 — reading the files.** One reader per ledger. Each knows
exactly which columns it needs and **refuses to run** if one is missing,
rather than guessing or filling in blanks.

**Stage 3 — lining the ledgers up.** Following the ID chain. The
important guarantee: **nothing may be silently lost.** Every single input
row must end up either successfully matched or explicitly listed as
unmatched with a reason. The software checks this itself and refuses to
return a result if the count doesn't balance.

**Stage 4 — spotting refunds and chargebacks.** Where a real decision
had to be made, described in §9.

**Stage 5 — spotting shortfalls and missing payments.** Plus
overpayments, which until then had been slipping through unnoticed.

**Stage 7, deliberately before stage 6 — the marking script.** Built
*before* the language model layer, on purpose: you need a way to measure
before you can tell whether an addition helps. This immediately revealed
a problem (§9.3).

**Stage 6 — the language model layer.** Described in §6.

**Stage 8 — the report.** Groups problems by type, sorts by rupee
impact, leads with the total at risk.

**Stage 9 — the dashboard.** A web page showing the results. It is
deliberately **incapable** of recalculating anything — it can only
display what the report already produced. Two different numbers for the
same order, and nobody can tell which is real.

---

## 8. What went wrong along the way

Every project has failures. Hiding them makes a report less trustworthy,
not more. Here is each one, explained from scratch.

### 8.1 A setting that looked right and could not be used

The project stores times in Indian Standard Time. The setting said
`"Asia/Kolkata"` — correct spelling, correct format, entirely valid.

**It didn't work.** Windows doesn't ship with the world timezone
database, and Python needs one to convert a name like "Asia/Kolkata"
into an actual time offset. The lookup found **zero timezones** — not a
missing entry, an empty reference book.

The fix was adding the timezone database as a requirement. Afterwards,
**598 timezones** were available and the conversion worked.

**The lesson:** a setting that looks correct can still be unusable. The
only way to know is to *use* it. This was found because the project's
own rules require running things rather than assuming they work — and
the temptation at that stage was strong, since it was "just" a folder
structure and two settings.

### 8.2 The answer key was wrong

To measure accuracy you need an **answer key** — a separate file listing
the correct answer for each order, so the software's output can be
marked like an exam.

While writing the missing-payment rule, the key and the rule disagreed
about three orders. The key said `ord_00006` should have been paid
₹14,409.64; the rule said the full ₹14,757.93.

The difference was ₹348.29. Working out what that number *was*:

```
  ₹14,757.93 × 2% × 1.18  =  ₹348.29
```

Exactly the gateway's fee plus tax on it. **All three orders matched
this pattern to the paisa.**

So the program that generated the test data had deducted a processing
fee from three orders **where the payment never reached the gateway** —
where no fee could possibly have been charged.

**The key was wrong, not the rule.** It was corrected.

**The lesson:** the answer key is not automatically right. When your
program and your answer key disagree, the honest question is *which one
is wrong* — and it isn't always the program. The dangerous move would
have been "fixing" the program to match, which would have made the
accuracy score meaningless while looking like an improvement.

### 8.3 A boundary placed exactly where the data sits

The software rates how confident it is. The boundary between "very
confident" and "fairly confident" was set at 25%.

One refund, `ord_00026`, was a refund of **exactly 25%** — and came out
on the *wrong side* of a 25% boundary.

Here's why. The refund was 25% of ₹52,594.13, which is ₹13,148.5325 —
and money can't have fractions of a paisa, so it was stored rounded
*down* to ₹13,148.53. Dividing back:

```
  13,148.53 ÷ 52,594.13 = 0.2499999524661782...
```

Which is *just below* 0.25. Four of the five 25% refunds happened to
round the other way; this one didn't.

**The problem wasn't the rounding — it was placing a boundary exactly
where the data clusters.** Real refunds are commonly 25%, 30%, 50% or
100%. A line drawn at 25% is decided by rounding noise rather than by
meaning.

The fix moved the boundary to 22%, where no natural refund percentage
sits. The rejected alternative was rounding the numbers before
comparing — which would have hidden this specific case while leaving the
boundary on the cluster point, so the next dataset would resurface it.

**The lesson:** never put a dividing line exactly where your data
naturally piles up.

### 8.4 A confidence score that was confident about the wrong thing

The software rates each finding's confidence, so uncertain ones can get
a second opinion. The obvious check: are the low-confidence answers
actually the wrong ones?

**They were the opposite.**

```
  marked "high confidence"    12 right,  5 wrong
  marked "medium"              2 right,  5 wrong
  marked "low confidence"      2 right,  0 wrong    ← all correct
```

Every low-confidence answer was right. **Five of the ten mistakes were
marked high confidence.**

The reason is worth following. Confidence was calculated as *"how far is
this from the dividing line?"* — far away meant confident. But recall
from §4.3 that a chargeback loses *more than the whole sale*, around
105%. The dividing line for refunds is at 20%. So a chargeback sits
enormously far past that line — and if the software failed to recognise
it as a chargeback (because the penalty wasn't the expected ₹500), it
would call it a refund **with maximum confidence**.

**Distance from a line tells you nothing about whether the line is in
the right place** — and the line was exactly what the software was
getting wrong.

The fix: confidence now reflects *what kind of test was used*. Tests that
match exact arithmetic (chargeback, missing payment, overpayment) are
high confidence, because they either match or they don't. Tests that
compare against a judgement-call threshold are **never** high confidence,
no matter how far past it the number falls.

Afterwards: high confidence became **6 right, 0 wrong**, and every
mistake sat in the lower bands where a second opinion would catch it.
**No answer changed** — only the confidence rating.

### 8.5 The language model made things worse, and was caught

When the language model layer was first switched on, the harder test set
improved — and the **easier test set got worse**, dropping from a perfect
score.

The project has a rule: if accuracy drops anywhere, don't save the work.
The rule fired. The work was stopped and investigated.

One order had changed: `ord_00026` again, the exact-25% refund from
§8.3. The model had reclassified it, explaining:

> "The shortfall is exactly 25.0% of the captured payment — a
> suspiciously clean fraction for a real customer refund, which by
> definition should be an arbitrary amount."

**The model's reasoning was sound. The instruction it was given was
wrong.** The written instructions handed to the model included the
sentence *"Real refunds are arbitrary amounts"* — true in the real
world, false in this test data, where refunds were generated as round
percentages. The model reasoned correctly from a false premise it was
given.

The fix was not to correct the sentence. It was to raise the bar: the
model may now only overrule the arithmetic when it says it is **highly**
confident. Looking at the evidence:

```
  3 overrules made with HIGH confidence   →  all 3 correct
  2 overrules made with medium confidence →  both wrong
```

Every confident overrule was right; every hesitant one was wrong.
Raising the bar kept all three fixes and eliminated both mistakes.

**The lesson:** written instructions to a language model are as much a
part of the system as the code. A false statement in them produces
confidently wrong results.

### 8.6 A guarantee that stopped being true halfway through

After the fix in §8.4, "high confidence" was trustworthy. That fact was
about to be used to decide which findings could be acted on
automatically.

Checking rather than assuming revealed a hole. The guarantee held for
confidence ratings produced by the *arithmetic* — but the language model
**writes its own confidence into the same field**. On the harder test
set, exactly one finding came out marked high confidence with the wrong
answer.

The arithmetic's guarantee was silently overwritten by a later step
using the same box for a different meaning.

Nothing was built on the flawed assumption, because it was checked
before being relied on. The recommendation was written as "act only on
these specific problem types" rather than "act on anything marked high
confidence".

**The lesson:** a guarantee established at one point can be quietly
invalidated later. Check it where you're about to rely on it, not where
it was created.

### 8.7 Checks that flagged their own documentation

Three times, an automated check for a forbidden pattern reported a
violation that didn't exist. Each time, it had found the rule *written
down in a comment* explaining that the thing was forbidden.

A file that documents "this file must never read the answer key"
contains the words "answer key". A plain text search cannot tell the
difference between doing something and describing it.

The fix was to check the code's actual structure rather than its text.
**The lesson:** the better a file documents its own rules, the more
likely a naive text search is to accuse it of breaking them.

### 8.8 Mistakes in how the work was done

Not the software's — the process's.

**The tough test set is less tough than intended.** Stage 4 explicitly
rejected a shortcut: identifying refunds by "is this an exact round
percentage?" That works on the test data only because of how the test
data was generated, and would fail immediately on real data. The
adversarial test set — built specifically to defeat such shortcuts — was
then written with **5 of its 14 refunds as exact round percentages**.
Nine of fourteen are genuinely irregular, so the set still works, and no
reported score depends on the shortcut. But it's a weaker test than it
should have been, and three of those five are among the cases the
software still gets wrong.

**A confident claim that was false.** When adding the timezone database
(§8.1), I stated that a different library bundled its own copy so it
"would probably have worked anyway". That was wrong for the version in
use. The claim was volunteered, unasked, and incorrect.

**A rule followed four times out of five.** The project's rules require
ticking off each stage in the README as it completes. Stages 1 through 5
all finished without it, and the gap was only noticed at stage 7.

---

## 9. What the accuracy numbers mean

The project reports numbers like "0.731". Here is what they are.

### The three measures

Imagine a smoke alarm.

- **Precision** — of all the times it went off, how often was there
  actually a fire? Poor precision means false alarms.
- **Recall** — of all the actual fires, how many did it catch? Poor
  recall means fires it slept through.
- **F1** — a single number combining both, which is only high when
  *both* are high. It's harsh: excellent precision with terrible recall
  still scores badly.

All three run from 0 (useless) to 1 (perfect).

### Which matters more here?

**Recall.** A missed discrepancy is money permanently lost. A false
alarm costs a human thirty seconds to dismiss. Those are not equally
bad, so the project prioritises catching everything.

### Worked through with real numbers

Take chargebacks on the harder test set, using only the arithmetic
rules. There are **5** real chargebacks. The software flagged **2**.

```
  Correctly flagged                       2
  Wrongly flagged (wasn't a chargeback)   0
  Missed                                  3

  Precision = 2 ÷ (2 + 0) = 1.000   ← never cried wolf
  Recall    = 2 ÷ (2 + 3) = 0.400   ← caught under half
  F1        = 0.571
```

Perfect precision, poor recall. Everything it flagged was genuinely a
chargeback; it just missed three of five — the ones with an unusual
penalty amount, from §8.4.

**Reporting only the precision here would be technically true and deeply
misleading.** This is exactly why both are always shown.

*(After the language model layer, this same measure goes to a perfect
1.000 — all five found, none wrongly flagged.)*

### The other number: match rate

**Match rate** is different — it measures how many orders could be
traced through all four ledgers at all. It's **0.977**: 127 of 130. The
three that don't trace are the missing payments, which by definition
have nothing to trace to. They're reported as problems, not quietly
dropped.

---

## 10. Why there are two sets of test data

This is the most important section for judging whether the results mean
anything.

### The problem with marking your own homework

The original test set has 130 orders. On it, the software scores
**perfectly — 1.000 on every category**.

That sounds excellent. **It is close to meaningless**, and the project
says so repeatedly and prominently.

The rules were written *by looking at this data*. The threshold
separating refunds from shortfalls was chosen after examining these
numbers. Scoring perfectly on the data you designed against is not
evidence — it's circular.

There's a measurable way to see this. In this data, the largest
shortfall is 18.18% of its sale and the smallest refund is 25.00%.
There's a **6.8-percentage-point gap with nothing in it**. The threshold
was placed in that gap, so it cannot possibly be wrong here. One real
merchant with a 22% refund lands in the hole.

### So a second set was built to break it

A second set of 40 orders was created **deliberately designed to defeat
the rules**: refunds below the threshold, shortfalls above it,
chargebacks with unusual penalties, two refunds on one order, a refund
and a shortfall combined.

The rules were **not adjusted** to pass it. That would move the problem
rather than fix it.

```
                        original set    adversarial set
  rules only               1.000             0.615
  with language model      1.000             0.731
```

**That drop, from 1.000 to 0.615, is the honest measure of what the
rules are worth.** The perfect score measures the test, not the
software.

### One genuinely good result

On both sets, in both modes, the software **never misses a problem and
never invents one**. Every one of the 31 and 26 real problems is
detected, and no clean order is ever wrongly flagged.

Every error is a *misclassification* — the right order flagged with the
wrong explanation. Given that a missed problem is lost money and a
mislabelled one is still surfaced for a human, that's the right way to
be wrong.

---

## 11. What it still gets wrong

**Seven orders** on the harder set end up with the wrong label. All seven
sit on the same boundary: telling a refund apart from a shortfall.

The obvious response is to move the threshold. **This was tested, and it
doesn't work.**

Listing every refund and shortfall by size, they **interleave**:

```
  12.0%  refund      14.2%  refund      15.0%  refund     17.3%  refund
  21.2%  refund      23.8%  refund      25.7%  refund     26.9%  refund
  28.0%  SHORTFALL
  30.0%  refund      31.6%  refund      33.4%  refund
  35.0%  SHORTFALL
```

There is no line you can draw through that list with refunds cleanly on
one side. **Nineteen refunds are smaller than the largest shortfall.**
Every possible threshold was tried; the best conceivable one still gets
**three wrong** — and choosing it would mean tuning the software to the
answer key, which is cheating and which the project forbids.

**This isn't a tuning problem. It's a missing-information problem.** The
four ledgers simply do not contain anything that distinguishes "the bank
underpaid you by 15%" from "a customer was refunded 15%". Both look
identical.

### What would actually fix it

**A fifth ledger listing refunds.** With one, the question stops being a
guess: a gap with a matching refund record *is* a refund; a gap without
one *is* a shortfall. The ambiguity disappears entirely, because it was
never really a software problem.

The language model, correctly, doesn't pretend otherwise. Shown one of
these cases it said a plain shortfall was *"at least equally
plausible"* — an accurate description of a case with no distinguishing
evidence.

---

## 12. Honest limitations

Collected in one place.

1. **The perfect score is a statement about the test data**, not the
   software. Stated repeatedly, because it's the number most likely to
   be skimmed and the one that means least.
2. **The adversarial test set is partly compromised** (§8.8). Five of
   its fourteen refunds carry the very pattern the set exists to defeat,
   and three of those are among the seven failures. No reported score
   depends on it, but the test is weaker than intended. It's recorded
   rather than fixed, because regenerating the data would change every
   reported number at the same time as fixing the flaw — and changing
   your data and your results in one move, before a deadline, is worse
   than documenting the flaw clearly.
3. **130 orders is not a speed test.** The software processes them in
   roughly a seventh to a fifth of a second — the exact figure varies
   with how busy the machine is — which is real, but that's a batch small
   enough to fit in memory trivially. Nothing here shows how it behaves
   with a hundred thousand orders.
4. **It identifies problems; it does not fix them.** Nothing files a
   dispute or claws money back. That's deliberate: acting wrongly on a
   misclassified case is worse than not acting. The seven it gets wrong
   are exactly why.
5. **The "agent" is a single question, not an autonomous system.** It
   answers one question at a time with no tools and no memory. That's a
   design choice, not a shortcoming — but it isn't what "AI agent"
   sometimes implies.
6. **Three things about real data remain unknown**: whether the fee rate
   is really fixed, what other statuses real files contain, and which
   fields can be blank. All three become answerable the first time real
   merchant data is used.

---

## 13. Running it yourself

From the project folder:

```bash
python -m src.main --data tests/fixtures --out reports/
```

Prints the summary and writes a spreadsheet of every problem found.

```bash
python evals/run_eval.py
```

Marks the software against the answer key and prints the accuracy
tables. **This needs no account, no key and no internet** — the
arithmetic runs entirely on your machine, so anyone can reproduce every
rules-only figure in this project.

```bash
streamlit run src/dashboard/app.py
```

Opens the results as a web page. Run the first command first, or it will
politely tell you there's nothing to show.

Adding `--agent` to either of the first two turns on the language model
layer. That one needs an account key, and it's the only part that costs
anything.

---

## In one paragraph

Four organisations keep separate records of the same money. This
software reads all four, lines them up by ID, works out what each payout
should have been, and reports every discrepancy with an explanation and
a rupee amount. The arithmetic is ordinary code — reproducible,
auditable, and never touched by AI. A language model is consulted only
on the ambiguous cases, only for a label and a sentence, and it is
structurally prevented from altering a single number. On 130 test orders
it finds ₹481,919.30 unaccounted for and misses nothing. On 40 orders
built specifically to defeat it, it gets seven labels wrong — and the
reason those seven are wrong is that the information needed to get them
right isn't in the files.
