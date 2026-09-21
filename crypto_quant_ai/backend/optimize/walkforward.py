"""Stage 8 - walk-forward splitter and evaluator."""
from __future__ import annotations

from typing import Any, Sequence

from crypto_quant_ai.backend.replay.types import ReplayConfig

from .types import ParamSpace, SearchConfig, WalkForwardConfig, WindowResult
from .search import optimize, _evaluate


def _split_windows(n: int, wf: WalkForwardConfig) -> list[tuple[int, int, int, int]]:
    windows: list[tuple[int, int, int, int]] = []
    start = 0
    while True:
        train_start = start
        train_end = start + wf.train_size
        test_start = train_end
        test_end = test_start + wf.test_size
        if test_end > n:
            break
        windows.append((train_start, train_end, test_start, test_end))
        start += wf.step
    return windows


def walk_forward(space: ParamSpace, candles: Sequence[Any], search: SearchConfig,
                 wf: WalkForwardConfig, replay_config: ReplayConfig) -> list[WindowResult]:
    n = len(candles)
    windows = _split_windows(n, wf)
    results: list[WindowResult] = []
    for idx, (ts_, te, vs, ve) in enumerate(windows):
        train = list(candles[ts_:te])
        test = list(candles[vs:ve])
        _cands, best = optimize(space, train, search, replay_config)
        if best is None:
            continue
        oos = _evaluate(best.params, test, replay_config)
        results.append(WindowResult(
            index=idx,
            train_start=ts_, train_end=te, test_start=vs, test_end=ve,
            best_params=best.params,
            in_sample=best.metrics,
            out_of_sample=oos.metrics if oos.is_completed else {},
        ))
    return results
