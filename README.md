#  Jakarta Cafe QA — POS System Testing Portfolio

This repository documents my independent QA process — from test planning to bug reporting to automation — applied to a real Point-of-Sale (POS) system I designed, built, and tested myself.

> **Note:** This is a solo practice project. Team roles referenced in the test plan (QA Lead, Developer, Owner) are simulated to demonstrate understanding of a real-world QA workflow within a team setting.

---

##  Project Overview

**Warteg Babi POS & Order System** (a.k.a. `pos-babi`) is a Telegram Mini App (TMA) point-of-sale system built for a food stall, handling order input, payment processing, and stock/reporting management — designed to replace manual cashier workflows with a fast, accurate digital system.

### Core Features
- **Order & Menu Management** — add/edit/delete menu items, toggle stock availability
- **POS Cashier Flow** — dine-in/takeaway orders, item variations, receipt printing, price calculation
- **Payment Processing** — supports Cash and ABA QR payment methods, with a payment state machine ensuring payment status stays independent from kitchen/order status
- **Admin Console** — real-time order mirroring, transaction void/cancellation handling
- **Sales Reporting** — daily/monthly revenue recap, best-selling item tracking

---

##  Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python (aiohttp) |
| Database | SQLite |
| Bot Layer | python-telegram-bot (PTB) |
| Frontend | Vanilla JavaScript (Telegram Mini App) |
| Hosting | VPS, Nginx reverse proxy, systemd service management |

---

##  QA Process

This repo follows a structured QA workflow, applied end-to-end on the `pos-babi` system:

```
Test Plan → Traceability Matrix → Test Case Execution → Bug Reporting → Automation
```

1. **[Test Plan](./test-plans/warteg-babi-test-plan.md)**
   Defines scope, quality objectives, severity classification, suspension/resumption criteria, and exit criteria for the testing cycle.

2. **[Traceability Matrix](./test-cases/traceability-matrix.md)**
   Maps each requirement to its corresponding test case, ensuring full coverage across payment, ordering, and admin flows.

3. **[Bug Reports](./bug-reports/)**
   Individual defect reports (POSBABI-012 through POSBABI-017) written using a structured template — covering reproduction steps, severity, expected vs. actual behavior.

4. **Automation** *(in progress)*
   Playwright test scripts covering core payment and order flows — added as automation skills are developed.

---

##  Repository Structure

```
jakarta-cafe-qa/
├── README.md
├── test-plans/
│   └── warteg-babi-test-plan.md
├── bug-reports/
│   ├── POSBABI-012.md
│   ├── POSBABI-013.md
│   └── ...
├── test-cases/
│   └── traceability-matrix.md
└── automation/
    └── (Playwright scripts — coming soon)
```

---

## Why This Project

I'm transitioning from an F&B operations background into a QA/SDET role. Rather than only studying theory, I built a real system end-to-end and applied a professional QA process to it — treating it the way I would a production application, to build genuine, demonstrable testing experience.