"""Stage 3.3 — Paper Risk Gate: validates orders before they reach the executor."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from crypto_quant_ai.backend.paper.account import PaperAccount

if TYPE_CHECKING:
    from crypto_quant_ai.backend.core.models import FinalDecision

# ---------------------------------------------------------------------------
# Guard at import time
# ---------------------------------------------------------------------------

LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() in ("true", "1")
if LIVE_TRADING:
    raise RuntimeError(
        "Paper trading requires LIVE_TRADING to be disabled."
        " Disable it to continue."
    )

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class RiskGateResult:
    """
    Outcome of a single risk-gate evaluation.

    Attributes
    ----------
    allowed : bool
        True when the order passed all risk checks and may proceed to execution.
    rejected : bool
        True when the order failed at least one risk check.
    reasons : list[str]
        Human-readable list of all checks run and their outcomes.
        Every rule is recorded here regardless of pass/fail.
    account_snapshot : PaperAccount | None
        Frozen snapshot of the account at evaluation time.
        Always present even when rejected.
    """

    allowed: bool
    rejected: bool
    reasons: list[str] = field(default_factory=list)
    account_snapshot: PaperAccount | None = None


@dataclass
class RiskGateAudit:
    """
    Immutable audit log of all risk-gate evaluations.

    Every call to ``check()`` — accepted or rejected — is recorded here.
    """

    evaluations: list[RiskGateResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.evaluations)

    @property
    def accepted(self) -> int:
        return sum(1 for r in self.evaluations if r.allowed)

    @property
    def rejected_count(self) -> int:
        return sum(1 for r in self.evaluations if r.rejected)


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------

DEFAULT_MIN_CONFIDENCE = 0.50
DEFAULT_MAX_POSITION_FRACTION = 1.0      # up to 100 % of cash in one order
DEFAULT_MIN_RISK_REWARD = 1.5
DEFAULT_MIN_STOP_LOSS_PCT = 0.005        # SL must be at least 0.5 % below entry
DEFAULT_MAX_SLIPPAGE_PCT = 0.05          # entry must be within 5 % of current price


# ---------------------------------------------------------------------------
# PaperRiskGate
# ---------------------------------------------------------------------------

class PaperRiskGate:
    """
    Standalone risk gate + optional executor wrapper.

    The gate evaluates every ``FinalDecision`` against configurable thresholds
    and returns a ``RiskGateResult`` without touching the account.

    When used as a wrapper (default), it sits in front of a ``PaperExecutor``
    and only forwards decisions that pass all checks.

    Safety guarantees
    ----------------
    - No real exchange connections.
    - Account state (cash / positions) is never modified by the gate itself.
    - Rejected orders never reach the executor, so cash and positions are
      guaranteed untouched on rejection.
    - ``LIVE_TRADING=true`` raises ``RuntimeError`` at import time.
    """

    def __init__(
        self,
        account: PaperAccount,
        executor: "PaperExecutor | None" = None,
        *,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        max_position_fraction: float = DEFAULT_MAX_POSITION_FRACTION,
        min_risk_reward: float = DEFAULT_MIN_RISK_REWARD,
        min_stop_loss_pct: float = DEFAULT_MIN_STOP_LOSS_PCT,
    ) -> None:
        if not (0 <= min_confidence <= 1):
            raise ValueError("min_confidence must be in [0, 1]")
        if not (0 < max_position_fraction <= 1):
            raise ValueError("max_position_fraction must be in (0, 1]")
        if min_risk_reward < 0:
            raise ValueError("min_risk_reward must be >= 0")
        if not (0 <= min_stop_loss_pct <= 1):
            raise ValueError("min_stop_loss_pct must be in [0, 1]")

        self.account = account
        self.executor = executor
        self.min_confidence = min_confidence
        self.max_position_fraction = max_position_fraction
        self.min_risk_reward = min_risk_reward
        self.min_stop_loss_pct = min_stop_loss_pct
        self._audit: RiskGateAudit = RiskGateAudit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, decision: "FinalDecision") -> RiskGateResult:
        """
        Evaluate a single decision against all risk rules.

        Returns ``RiskGateResult`` with ``allowed=True`` only when every
        rule passes. The account snapshot is always included.

        This method never modifies ``self.account``.
        """
        snapshot = PaperAccount.model_validate(self.account.model_dump())
        reasons: list[str] = []
        allowed = True

        # ── Rule 1: confidence ───────────────────────────────────────
        conf_ok = decision.confidence >= self.min_confidence
        reasons.append(
            f"[CONF] confidence={decision.confidence:.2f} "
            f"{'>=' if conf_ok else '<'} {self.min_confidence:.2f} → "
            f"{'PASS' if conf_ok else 'FAIL'}"
        )
        if not conf_ok:
            allowed = False

        # ── Rule 2: position size ──────────────────────────────────────
        max_notional = self.account.cash * self.max_position_fraction
        if decision.position_size > 0:
            size_ok = decision.position_size <= max_notional
        else:
            size_ok = True   # no size specified → skip check
        reasons.append(
            f"[SIZE] position_size={decision.position_size} "
            f"{'<=' if size_ok else '>'} max_notional={max_notional:.2f} → "
            f"{'PASS' if size_ok else 'FAIL'}"
        )
        if not size_ok:
            allowed = False

        # ── Rule 3: stop-loss for BUY / LONG ──────────────────────────
        if decision.decision in ("BUY", "LONG"):
            if decision.entry is None or decision.entry <= 0:
                sl_ok = False
            elif decision.stop_loss is None or decision.stop_loss <= 0:
                sl_ok = False
            else:
                sl_pct = (decision.entry - decision.stop_loss) / decision.entry
                sl_ok = sl_pct >= self.min_stop_loss_pct
            sl_pct_val = (
                (decision.entry - decision.stop_loss) / decision.entry
                if decision.stop_loss is not None and decision.entry > 0
                else None
            )
            sl_pct_str = f"{sl_pct_val:.2%}" if sl_pct_val is not None else "N/A"
            reasons.append(
                f"[SL]   entry={decision.entry} stop_loss={decision.stop_loss} "
                f"sl_pct={sl_pct_str} "
                f"{'>=' if sl_ok else '<'} {self.min_stop_loss_pct:.2%} → "
                f"{'PASS' if sl_ok else 'FAIL'}"
            )
            if not sl_ok:
                allowed = False

            # ── Rule 4: risk-reward for BUY / LONG ─────────────────────
            rr_ok = True
            if (
                decision.stop_loss is not None
                and decision.stop_loss > 0
                and decision.take_profit is not None
                and decision.take_profit > decision.entry
            ):
                rr = (decision.take_profit - decision.entry) / (
                    decision.entry - decision.stop_loss
                )
                rr_ok = rr >= self.min_risk_reward
                reasons.append(
                    f"[RR]   risk_reward={rr:.2f} "
                    f"{'>=' if rr_ok else '<'} {self.min_risk_reward:.2f} → "
                    f"{'PASS' if rr_ok else 'FAIL'}"
                )
                if not rr_ok:
                    allowed = False
            else:
                reasons.append(
                    f"[RR]   skip (stop_loss={decision.stop_loss}, "
                    f"take_profit={decision.take_profit})"
                )

        else:
            reasons.append(f"[SL/RR] skip (decision={decision.decision})")

        result = RiskGateResult(
            allowed=allowed,
            rejected=not allowed,
            reasons=reasons,
            account_snapshot=snapshot,
        )
        self._audit.evaluations.append(result)
        return result

    def execute(self, report: "OrchestratorReport") -> "ExecutionResult":
        """
        Gate-then-execute: check the signal first; only forward if allowed.

        Parameters
        ----------
        report : OrchestratorReport
            The multi-brain report wrapping a ``FinalDecision``.

        Returns
        -------
        ExecutionResult
            When the gate rejects the decision the returned result has
            ``executed=False`` and ``reason`` describing the failure.
            When allowed the result is whatever ``self.executor.execute``
            returns.

        Raises
        ------
        RuntimeError
            If ``self.executor`` is None (wrapper mode not set up).
        """
        if self.executor is None:
            raise RuntimeError(
                "PaperRiskGate.execute requires an executor to be set at init."
            )
        decision = report.final_decision
        gate_result = self.check(decision)
        if gate_result.rejected:
            from crypto_quant_ai.backend.paper.executor import ExecutionResult
            return ExecutionResult(
                executed=False,
                reason="Risk gate rejected: " + "; ".join(
                    r for r in gate_result.reasons if "FAIL" in r
                ),
                account_snapshot=gate_result.account_snapshot,
            )
        return self.executor.execute(report)

    @property
    def audit(self) -> RiskGateAudit:
        """Return a reference to the gate's audit log."""
        return self._audit
