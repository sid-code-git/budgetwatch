---
title: "{{ replace .File.ContentBaseName "-" " " | title }}"
town: ""
state: ""
fiscal_year: "{{ now.Format "2006" }}"
population: 0
severity: "medium"
news_desert: false
lat: 0.0
lng: 0.0
source_url: ""
draft: true
---

<!--
  HOW TO USE THIS TEMPLATE
  ========================
  1. Fill in the front matter above (town, state, population, lat/lng, source_url).
  2. Set severity to "high", "medium", or "low" based on your most serious flag.
  3. Set news_desert: true if this town has no local newspaper.
  4. Set draft: false when you're ready to publish.
  5. Replace this comment with your report body.

  FINDING BLOCK SYNTAX
  Use one block per flag. severity class = high / medium / low.

  <div class="finding high">
    <div class="finding-label">High · Check name</div>
    <div class="finding-fact">The fact, with figures cited.</div>
    <div class="finding-question">The neutral question the public should ask.</div>
    <div class="finding-source">Source: Budget document title, p. XX</div>
  </div>
-->

## Summary

One or two sentences describing what this report covers and why this town was selected.

## Findings

<!-- Paste your finding blocks here -->

## Background

Optional: brief context on the town, its budget size, and what fiscal years are covered.
