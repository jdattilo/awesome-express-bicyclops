# Awesome Express — Bicyclops

AE2 (AwesomeExpress 2) test execution engine. One of two runner components in the Cattle Suite. Executes test procedures and test cases against Dell's proprietary server caching hardware and reports results back to the central Cattle management system.

**What it does:**
- Runs structured test suites against physical caching server hardware
- Manages test procedures, test cases, and suite files
- Reports pass/fail results and logs back to Cattle/Cowtracks
- Handles parallel test execution via fork-safe process management

**Stack:** Python

---

## Cattle Suite

The Cattle Suite is a custom test automation and performance tracking platform built for Dell's proprietary server caching hardware. It managed builds, test runs, log collection, and performance reporting across physical server clusters. Dell open-sourced the full codebase when they shut down the division.

Suite components: [cattle](https://github.com/jdattilo/cattle-2.0) · [cow](https://github.com/jdattilo/cow-2.0) · [cowtracks](https://github.com/jdattilo/cowtracks-1.0) · [b2eb](https://github.com/jdattilo/b2eb-1.0) · [bicyclops](https://github.com/jdattilo/awesome-express-bicyclops) · [butterjunk](https://github.com/jdattilo/awesome-express-butterjunk)
