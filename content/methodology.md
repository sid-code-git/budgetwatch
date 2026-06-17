---
title: "Methodology"
---

Every flag in a Budget Watch report is produced by one of five checks. The thresholds below are editorial judgment calls — they're documented here so you can evaluate them, challenge them, or improve on them.

The full source code for all checks lives in `analyzer.py` in our public repository.

---

## Check 1 · Year-over-year spike

**What it measures:** A budget category grew by more than 20% in a single fiscal year, adjusted for population change.

**Why 20%?** Most municipal departments have relatively stable year-to-year spending. A 20% jump is large enough that it almost certainly reflects a deliberate decision — a new program, a contract renegotiation, an unusual purchase — that deserves explanation. Below 20% we'd be flagging normal inflation and staffing adjustments.

**What it doesn't catch:** Multi-year gradual increases. A department that grows 18% per year for five years won't trip this check. That's a known limitation.

**Severity:** High if over 40%, medium if 20–40%.

---

## Check 2 · Peer-spending outlier

**What it measures:** A category's per-capita spending is more than 50% above the median for peer towns of similar size, type, and region.

**The peer problem:** This check is only as good as the peer towns we choose. Bad comparisons produce meaningless flags. We choose peers manually based on population (within 30%), municipality type (city vs. township vs. county), region (same state where possible), and economic profile. When we're uncertain about a peer choice, we don't guess — we leave the field blank and note the gap in the report.

**Severity:** High if over 100% above median, medium if 50–100%.

---

## Check 3 · Fund balance erosion

**What it measures:** The town's general fund reserve has declined in both of the two most recent fiscal years on record.

**Why it matters:** Fund balance is a town's financial cushion. Governments without adequate reserves are vulnerable to service disruptions, borrowing at bad rates, or deferring maintenance in ways that cost more later. A two-year decline doesn't necessarily indicate a problem — capital projects or economic downturns have legitimate explanations — but it's worth asking about.

**Severity:** Medium (single flag regardless of magnitude, because trajectory matters more than a single data point).

---

## Check 4 · Reserves vs. service cuts

**What it measures:** The town is holding fund balance above 15% of general fund expenditures *while simultaneously reducing spending* in categories we classify as public services (parks, libraries, public safety, roads, human services).

**The logic:** Reserves exist to provide stability. A town that accumulates large reserves while visibly cutting services that residents depend on faces a legitimate public question about priorities. This check doesn't say the answer is wrong — it says the question should be asked.

**Service categories** used in this check are listed in the `service_categories` field of the town's data file.

**Severity:** Medium.

---

## Check 5 · Unexplained inter-fund transfers

**What it measures:** A transfer between funds exceeds $50,000 (or $20 per capita, whichever is larger) and is not accompanied by a documented explanation in the budget narrative.

**What counts as documented:** A line item label like "Transfer to Capital Projects Fund — Road Resurfacing Program" is sufficient. A generic "interfund transfer" with no further description is not.

**Why this matters:** Inter-fund transfers are a common mechanism for moving money in ways that don't appear in the headline general fund figures. Most are routine and well-documented. When they're not documented, the question is simply: what is this for?

**Severity:** High if above $100 per capita, medium otherwise.

---

## What we don't check (and why)

- **Personnel decisions** — We don't flag individual salaries or staffing levels. Personnel is the largest single budget driver for most towns, and comparisons without detailed job-classification data produce more noise than signal.
- **Debt service** — Debt schedules are structurally complex and depend heavily on capital project history. We flag fund balance erosion as a proxy for fiscal stress but don't attempt to analyze debt structure directly.
- **Revenue sources** — We focus on spending. Revenue analysis (tax rates, state aid dependency, fee structures) is important but requires different data than most published budgets contain.

---

## Corrections

If you believe a flag in one of our reports is based on a misread figure, a bad peer comparison, or a documented explanation we missed, please contact us. We will review, correct the record publicly if warranted, and note the correction in the report.
