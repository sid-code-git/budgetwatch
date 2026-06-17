---
title: "Sample Report — Placeholder"
town: "Exampleville"
state: "IL"
fiscal_year: "2023"
population: 4200
severity: "medium"
news_desert: true
lat: 40.1
lng: -89.3
source_url: ""
draft: true
---

This is a placeholder report. It will not appear on the live site. Replace this file with a real report once you have your first town's data.

To add a real report, copy this file, rename it to `yourtown-state-YYYY.md`, fill in the front matter fields, and write the report body below.

## How to write a report

Each finding should use this HTML block:

```html
<div class="finding high">
  <div class="finding-label">High · Year-over-year spike</div>
  <div class="finding-fact">The Police Department budget increased 43% from FY2022 ($1.2M) to FY2023 ($1.72M), an increase of $520,000.</div>
  <div class="finding-question">What drove the 43% increase in Police Department spending? Was this a planned expansion, a one-time equipment purchase, or a new contract?</div>
  <div class="finding-source">Source: FY2023 Annual Budget, p. 34</div>
</div>
```

Severity classes are `high`, `medium`, and `low`.
