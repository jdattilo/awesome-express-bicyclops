# Awesome Express — Bicyclops

*One of two runners that do the actual work — executing test procedures against the software under test. The name's an inside joke; the fork-safe parallel execution is dead serious.*

<div align="center">

![Cattle Suite](https://img.shields.io/badge/Cattle_Suite-test_runner-5cefff?style=for-the-badge&labelColor=06060e)
![License](https://img.shields.io/badge/license-GPL--3.0-ff4dd8?style=for-the-badge&labelColor=06060e)
[![Author: Joseph Dattilo](https://img.shields.io/badge/author-Joseph_Dattilo-4dff9e?style=for-the-badge&labelColor=06060e)](https://datepalm.media)

</div>

AE2 (AwesomeExpress 2) test execution engine — one of two runner components in the Cattle Suite. Executes test procedures and test cases against the software under test on each node and reports results back to the central Cattle management system.

**What it does:**
- Runs structured test suites against the software under test
- Manages test procedures, test cases, and suite files
- Reports pass/fail results and logs back to Cattle/Cowtracks
- Handles parallel test execution via fork-safe process management

**Stack:** Python

---

## The Cattle Suite

The Cattle Suite is a **general-purpose, distributed testing harness** I built at Dell. It deploys lightweight micro-servers across an entire datacenter, runs tests against the software under test on every node, and streams **testing progress and result monitoring datacenter-wide** in real time — so you can watch a whole datacenter's worth of tests march along from a single dashboard. (Yes, it's all named after cattle. Once you're herding a datacenter of machines, the metaphor writes itself.)

Its first job was exercising **Dell's custom server caching software** at scale, but the harness itself is product-agnostic: deploy the agents, point them at whatever you need to test, and Cattle handles execution, log collection, and datacenter-wide monitoring.

I was the **primary developer of the entire suite** — architecture through implementation — during my time at Dell. When the division was wound down in a merger, I asked Dell to release the code as open source rather than let it vanish into a defunct internal repo. They agreed, and it's here under GPL-3.0: real infrastructure that ran across real datacenters, not a demo.

**Components:** [cattle](https://github.com/jdattilo/cattle-2.0) (central dashboard) · [cow](https://github.com/jdattilo/cow-2.0) (live monitoring) · [cowtracks](https://github.com/jdattilo/cowtracks-1.0) (log collection) · [b2eb](https://github.com/jdattilo/b2eb-1.0) (hardware inventory) · [bicyclops](https://github.com/jdattilo/awesome-express-bicyclops) + [butterjunk](https://github.com/jdattilo/awesome-express-butterjunk) (test runners)

## Author

**Joseph Dattilo** — primary developer of the Cattle Suite, authored during my time at Dell and open-sourced by Dell at my request when the division closed. I now run [**Date Palm Media**](https://datepalm.media), building business automation and AI-native software.

[datepalm.media](https://datepalm.media) · [github.com/jdattilo](https://github.com/jdattilo) · [LinkedIn](https://www.linkedin.com/in/joedattilo/)
