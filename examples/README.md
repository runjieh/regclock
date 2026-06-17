# examples

Runnable demos against public regulatory deadlines.

| File | Demonstrates |
|---|---|
| `sec_10k_apple.py` | Apple Inc. SEC Form 10-K. Fiscal year ends on the last Saturday of September; large accelerated filers must file within 60 calendar days. Uses real EDGAR filing dates for FY2023-FY2025. |
| `gdpr_breach_notification.py` | GDPR Art. 33 breach notification: 72-hour rule. Shows the state machine across upcoming / satisfied / overdue. |
| `data/sec_obligations.yaml` | YAML obligation file for the CLI: Apple 10-K (60 days) and 10-Q (40 days). |
| `data/sec_events.jsonl` | Event log paired with the YAML: triggers and EDGAR-acceptance evidence. |

## Run

```bash
python examples/sec_10k_apple.py
python examples/gdpr_breach_notification.py

regclock status \
  examples/data/sec_obligations.yaml \
  --events examples/data/sec_events.jsonl \
  --asof 2026-06-15

regclock pack \
  examples/data/sec_obligations.yaml \
  --events examples/data/sec_events.jsonl \
  --period 2025-01-01:2025-12-31
```
