"""stage_upgrade.py — paper→live promotion gating.

Per memory rule (project_stage_upgrade_checklist):
  Paper→Live 各阶段升级时必改清单；风险参数随阶段+真实 PF 用 1/4 凯利公式校准

Stages:
  S0 paper-only (no real money)
  S1 micro-live ($200-500): test fills, psychology, API reliability
  S2 small-live ($2k-5k): scale once S1 passes 30 days
  S3 medium-live ($10k+): scale once S2 passes 90 days with PF > 1.2
  S4 full-live: only after consistent multi-regime track record
"""
from __future__ import annotations

from dataclasses import dataclass

from . import position_sizing


@dataclass
class StageGate:
    stage: str
    name: str
    capital_min: float
    capital_max: float
    risk_pct_per_trade: float       # max risk per trade
    min_trades_to_advance: int
    min_pf_to_advance: float
    min_days_to_advance: int
    max_drawdown_block: float       # if exceeded, do not advance
    description: str


GATES: dict[str, StageGate] = {
    "S0": StageGate(
        stage="S0", name="paper-only",
        capital_min=0, capital_max=0,
        risk_pct_per_trade=1.0,
        min_trades_to_advance=200,  # need 200 paper trades before any real money
        min_pf_to_advance=1.20,
        min_days_to_advance=60,
        max_drawdown_block=25.0,
        description="无真金，验证信号质量、代码 bug、参数稳定性",
    ),
    "S1": StageGate(
        stage="S1", name="micro-live",
        capital_min=200, capital_max=500,
        risk_pct_per_trade=0.5,     # half the paper risk
        min_trades_to_advance=100,
        min_pf_to_advance=1.10,     # lower bar — slippage/psych eats edge
        min_days_to_advance=30,
        max_drawdown_block=15.0,
        description="测试真实滑点、API 稳定性、自己看亏损时的行为",
    ),
    "S2": StageGate(
        stage="S2", name="small-live",
        capital_min=2000, capital_max=5000,
        risk_pct_per_trade=0.75,
        min_trades_to_advance=200,
        min_pf_to_advance=1.15,
        min_days_to_advance=90,
        max_drawdown_block=18.0,
        description="确认 edge 在真钱下幸存；大幅提高决策样本",
    ),
    "S3": StageGate(
        stage="S3", name="medium-live",
        capital_min=10_000, capital_max=50_000,
        risk_pct_per_trade=1.0,
        min_trades_to_advance=300,
        min_pf_to_advance=1.20,
        min_days_to_advance=180,
        max_drawdown_block=20.0,
        description="跨 regime 验证（≥1 次 BULL/BEAR 切换），用 1/4 Kelly 校准仓位",
    ),
    "S4": StageGate(
        stage="S4", name="full-live",
        capital_min=50_000, capital_max=float("inf"),
        risk_pct_per_trade=1.0,     # but Kelly-adjusted
        min_trades_to_advance=0,    # terminal stage
        min_pf_to_advance=0.0,
        min_days_to_advance=0,
        max_drawdown_block=25.0,
        description="多 regime 长期 track record；Kelly 仓位",
    ),
}


def evaluate_promotion(current_stage: str,
                       trades_count: int,
                       observed_pf: float,
                       days_running: int,
                       max_drawdown_pct: float) -> dict:
    """Decide whether bot can be promoted to next stage.

    Returns:
      {"can_promote": bool, "next_stage": str|None, "blockers": [str]}
    """
    gate = GATES.get(current_stage)
    if not gate:
        return {"can_promote": False, "next_stage": None,
                "blockers": [f"unknown stage {current_stage}"]}

    blockers = []
    if trades_count < gate.min_trades_to_advance:
        blockers.append(
            f"trades {trades_count} < {gate.min_trades_to_advance}")
    if observed_pf < gate.min_pf_to_advance:
        blockers.append(f"PF {observed_pf:.2f} < {gate.min_pf_to_advance}")
    if days_running < gate.min_days_to_advance:
        blockers.append(f"days {days_running} < {gate.min_days_to_advance}")
    if max_drawdown_pct > gate.max_drawdown_block:
        blockers.append(
            f"maxDD {max_drawdown_pct:.1f}% > {gate.max_drawdown_block}%")

    next_stage = {
        "S0": "S1", "S1": "S2", "S2": "S3", "S3": "S4", "S4": None,
    }[current_stage]

    return {
        "can_promote": not blockers and next_stage is not None,
        "next_stage": next_stage,
        "blockers": blockers,
    }


def kelly_position_size(account: float, entry: float, stop: float,
                        win_rate: float, avg_win: float, avg_loss: float,
                        kelly_multiplier: float = 0.25,
                        cap_risk_pct: float = 1.0,
                        min_unit: float = 1.0) -> dict:
    """Stage-aware sizing using 1/4 Kelly, capped by stage's risk_pct.

    Use this once you have ≥100 real trades to estimate (win_rate, avg_win, avg_loss).
    """
    kelly_frac = position_sizing.kelly_fraction(
        win_rate, avg_win, avg_loss, kelly_multiplier)
    risk_pct = min(kelly_frac * 100, cap_risk_pct)
    if risk_pct <= 0:
        return {"error": "kelly fraction <= 0; do not trade"}
    return position_sizing.calculate(
        account, entry, stop, risk_pct=risk_pct, min_unit=min_unit)
