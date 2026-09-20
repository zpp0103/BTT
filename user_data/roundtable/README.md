# Paper Trading Roundtable

This directory contains the first deterministic implementation of the four-role
roundtable. It is intentionally local: no LLM, Binance key, or live order path is
used.

Roles 1 and 2 independently analyze each candle. Role 3 verifies their agreement
and volatility and has a hard veto. Role 4 is represented by the final immutable
decision returned by `evaluate`.

Run only in dry-run mode during phase one:

```bash
freqtrade trade --config config_examples/config_paper_roundtable.json --strategy RoundTableStrategy
```

The config starts stopped. Start it only after reviewing the signals, and never
replace `dry_run: true` during this phase.
