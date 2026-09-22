"""Stage 11 - Fusion strategies: pure functions over model contributions.

Each function returns a 4-tuple: (decision, confidence, conflict, quorum_met).
LONG/SHORT are normalized to BUY/SELL. NO_TRADE / HOLD are treated as neutral.
"""
from __future__ import annotations

from .types import ModelContribution


def _norm(decision: str) -> str:
    d = (decision or "").upper()
    if d == "LONG":
        return "BUY"
    if d == "SHORT":
        return "SELL"
    return d


def _is_active(decision: str) -> bool:
    return _norm(decision) in ("BUY", "SELL")


def weighted_majority(contrs, weights=None, quorum: int = 2):
    weights = weights or {}
    scores: dict[str, float] = {"BUY": 0.0, "SELL": 0.0}
    for c in contrs:
        nd = _norm(c.decision)
        if nd not in scores:
            continue
        w = float(weights.get(c.model_name, 1.0))
        scores[nd] += w * max(0.0, c.confidence)
    buyers, sellers = scores["BUY"], scores["SELL"]
    conflict = buyers > 0 and sellers > 0
    active = sum(1 for c in contrs if _is_active(c.decision))
    quorum_met = active >= quorum
    if active < quorum:
        return "NO_TRADE", 0.0, conflict, False
    if buyers > sellers and buyers > 0:
        decision = "BUY"
    elif sellers > buyers:
        decision = "SELL"
    else:
        decision = "NO_TRADE"
    total = buyers + sellers
    conf = (max(buyers, sellers) / total) if total > 0 else 0.0
    return decision, conf, conflict, quorum_met


def simple_majority(contrs, quorum: int = 2):
    counts: dict[str, int] = {}
    for c in contrs:
        nd = _norm(c.decision)
        if nd in ("BUY", "SELL"):
            counts[nd] = counts.get(nd, 0) + 1
    buy, sell = counts.get("BUY", 0), counts.get("SELL", 0)
    conflict = buy > 0 and sell > 0
    active = buy + sell
    quorum_met = active >= quorum
    if active < quorum:
        return "NO_TRADE", 0.0, conflict, False
    if buy > sell and buy >= 1:
        decision = "BUY"
    elif sell > buy:
        decision = "SELL"
    else:
        decision = "NO_TRADE"
    total = len(contrs) or 1
    conf = max(buy, sell) / total
    return decision, conf, conflict, quorum_met


def unanimous(contrs, quorum: int = 2):
    acts = [_norm(c.decision) for c in contrs if _is_active(c.decision)]
    conflict = len(set(acts)) > 1
    if not acts:
        return "NO_TRADE", 0.0, False, False
    if len(acts) < quorum:
        return "NO_TRADE", 0.0, conflict, False
    if len(set(acts)) == 1:
        agreed = acts[0]
        chosen = [c for c in contrs if _norm(c.decision) == agreed]
        conf = sum(c.confidence for c in chosen) / len(chosen) if chosen else 0.0
        return agreed, conf, False, True
    return "NO_TRADE", 0.0, True, False


def consensus_quorum(contrs, quorum: int = 2):
    counts: dict[str, int] = {}
    for c in contrs:
        nd = _norm(c.decision)
        if nd in ("BUY", "SELL"):
            counts[nd] = counts.get(nd, 0) + 1
    buy, sell = counts.get("BUY", 0), counts.get("SELL", 0)
    conflict = buy > 0 and sell > 0
    if buy >= quorum and buy >= sell:
        return "BUY", buy / (len(contrs) or 1), conflict, True
    if sell >= quorum and sell > buy:
        return "SELL", sell / (len(contrs) or 1), conflict, True
    return "NO_TRADE", 0.0, conflict, False
