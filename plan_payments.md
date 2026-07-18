# CUB-Adjusted Property Payments

## Goal

Add a dedicated **Vivienda** workspace for configuring a property purchase,
calculating upcoming BRL obligations adjusted by CUB-SC, recording partial or
final payments, and measuring contractual progress. Existing FX purchases stay
separate; the latest USD-BRL rate is used only for an informative USD estimate.

## Domain and calculation

- Store purchase plans, recurring monthly and annual payment series, a keys
  payment, generated obligations, append-only payment transactions, and an
  auditable monthly CUB series.
- Use Decimal values and calculate `base amount x applicable CUB / base CUB`,
  rounded to BRL cents. Use the CUB value designated for the due month.
- Show future obligations as provisional when their exact CUB is unavailable,
  using the latest verified value without locking it into the contract record.
- Allow CUB adjustment to be enabled independently for installments,
  entry terms, reinforcements, and keys. Allow multiple partial payments, voided corrections,
  an explicit final contractual override, and protected history once paid.
- Measure both settled obligations and money: actual paid, nominal total,
  adjusted/provisional remaining amount, and variance.

## Interface

- Add a **Vivienda** navigation tab and a setup wizard that previews and then
  generates entry terms, monthly installments, yearly reinforcements, and the keys payment.
- Lead the workspace with the next due date, its CUB calculation, BRL amount,
  and current USD estimate. Follow with progress, a contract timeline, a chart
  comparing nominal and CUB-adjusted installments, the obligation table,
  payment history, and CUB management.
- Support verified manual CUB entry and an assisted preview from the official
  Sinduscon BC page. The preview never saves automatically and failures never
  modify stored values.
- Keep the established dark UI, using amber for reinforcements, emerald for
  settled obligations, and red for overdue obligations.

## Verification

- Cover schedule generation, month-end dates, CUB rounding and fallback,
  partial/full/overpayments, voids, settlement overrides, plan isolation,
  parser failures, forms, routes, navigation, and dashboard totals.
- Run Django checks, migration drift checks, Ruff, focused payment tests, and
  the full pytest suite. Stabilize pre-existing weekend-sensitive OER tests and
  migration-seeded pair assumptions separately from feature behavior.

## Assumptions

- The contract uses non-desonerado CUB/2006 residential-medium values for Santa
  Catarina and BRL amounts.
- Assisted imports require confirmation; there is no automatic scheduled save.
- FX execution, accounting integration, bank fees, and payment alerts are out of
  scope for this version.
