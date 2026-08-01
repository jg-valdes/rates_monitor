# Product Roadmap

## Product vision

Start with a dependable personal control system for one apartment investment in
Brazil. Preserve the calculation and audit model so it can later support buyers,
builders, property managers, or real-estate organizations without prematurely
adding SaaS complexity.

## Phase 1 — Solid personal product (current)

The current release is single-owner, passcode-protected, and SQLite-backed.
Its product contract is:

- exchange-rate monitoring and conversion history;
- CUB-SC-adjusted property obligations and projections;
- explicit confirmation before imported CUB values are saved;
- source provenance visible in the UI;
- append-oriented payment corrections and protected historical calculations;
- automated tests, migration checks, linting, and container validation in CI;
- a guarded scheduler that starts only in the single production web worker;
- documented backup and restore procedures.

Near-term hardening targets:

- periodically perform and record a restore drill from the SQLite backup;
- add structured error monitoring before depending on the app operationally;
- add an explicit application health endpoint if external monitoring is adopted;
- keep calculation regression fixtures based on real contract examples;
- review dependency and Django security updates on a regular cadence.

## Phase 2 — Product-ready pilot

Promote this phase only when more than one real user or property needs access.

- Replace the shared passcode with normal user authentication.
- Add ownership boundaries to every plan, CUB record, purchase, and alert.
- Add role-ready audit events for material contract changes.
- Support exports for obligations, payments, CUB history, and calculation detail.
- Add onboarding, recovery, privacy, retention, and support workflows.
- Add staging, production monitoring, automated backups, and release versioning.
- Validate CUB source licensing, attribution, and extraction reliability.

SQLite can still support a small controlled pilot if writes remain low and the
deployment stays on one host.

## Phase 3 — SaaS foundation

Move to PostgreSQL when any of these triggers becomes real:

- multiple application instances or hosts need concurrent database access;
- organization users frequently write payments or plans at the same time;
- tenant isolation, row-level policies, or operational reporting becomes necessary;
- backup recovery objectives exceed what file-level SQLite backups can provide;
- background work expands beyond the current single in-process scheduler.

The SaaS foundation should then add:

- tenant-aware models and authorization enforced at every query boundary;
- organizations, memberships, roles, invitations, and property portfolios;
- PostgreSQL migrations tested against production-sized copies;
- a durable task queue for imports, reports, reminders, and notifications;
- object storage for contracts and supporting documents;
- observability, rate limiting, secrets management, and incident procedures;
- subscription, entitlement, and usage boundaries only after pricing validation.

## Phase 4 — Builder and real-estate organization product

Potential organization capabilities, subject to customer discovery:

- builder-managed developments, units, buyers, and contract templates;
- bulk generation of payment schedules and CUB adjustments;
- approval workflows for imported indices and contractual overrides;
- buyer portals with statements, reminders, and document delivery;
- portfolio cash-flow forecasting and delinquency reporting;
- accounting and bank reconciliation integrations;
- jurisdiction-specific index providers and contract rules beyond CUB-SC;
- organization-level audit exports and compliance controls.

## Explicitly deferred

The following are not accidental gaps in the personal release:

- automated money movement or FX execution;
- accounting or bank integrations;
- bank-fee calculation;
- payment reminders and collection workflows;
- multi-tenant billing;
- PostgreSQL solely for perceived maturity.

Each should enter the roadmap only with a real user, operational, or regulatory
requirement and its corresponding tests and audit rules.
