"""Deterministic long-equity planning from user-supplied account and stop inputs."""

from dataclasses import dataclass
from decimal import Decimal

from tori_taurus.market_data.models import price, symbol


@dataclass(frozen=True)
class RiskInputs:
    symbol: str
    equity: Decimal
    buying_power: Decimal
    entry: Decimal
    requested_shares: int
    stop: Decimal | None = None
    existing_shares: int = 0
    existing_average: Decimal = Decimal(0)
    risk_budget_percent: Decimal = Decimal(1)
    max_concentration_percent: Decimal = Decimal(20)
    stop_reported_active: bool | None = None

    def __post_init__(self):
        object.__setattr__(self, "symbol", symbol(self.symbol))
        for key in (
            "equity",
            "buying_power",
            "entry",
            "existing_average",
            "risk_budget_percent",
            "max_concentration_percent",
        ):
            object.__setattr__(self, key, price(getattr(self, key)))
        if self.equity <= 0 or self.entry <= 0:
            raise ValueError("Equity and entry must be positive")
        for key in ("requested_shares", "existing_shares"):
            value = getattr(self, key)
            if type(value) is not int or value < 0:
                raise ValueError("Shares must be nonnegative integers")
        if self.existing_shares and self.existing_average <= 0:
            raise ValueError("Existing positions require positive average cost")
        for key in ("risk_budget_percent", "max_concentration_percent"):
            if not 0 < getattr(self, key) <= 100:
                raise ValueError("Budget percentages must be in (0,100]")
        if self.stop is not None:
            object.__setattr__(self, "stop", price(self.stop))
            if self.stop >= self.entry:
                raise ValueError("Long stop must be below proposed entry")
        if self.stop_reported_active is not None and type(self.stop_reported_active) is not bool:
            raise ValueError("Stop status must be bool or unknown")
        if self.stop is None and self.stop_reported_active:
            raise ValueError("Active stop report requires a stop price")


def evaluate_risk(plan: RiskInputs) -> dict:
    """Whole-share sizing; existing gains never offset new downside in budget checks."""
    existing_cost = plan.existing_shares * plan.existing_average
    add_cost = plan.requested_shares * plan.entry
    total_shares = plan.existing_shares + plan.requested_shares
    total_cost = existing_cost + add_cost
    average = total_cost / total_shares if total_shares else None
    budget = plan.equity * plan.risk_budget_percent / 100
    concentration = plan.entry * total_shares / plan.equity * 100
    affordable = int(plan.buying_power // plan.entry)
    concentration_capacity = max(
        Decimal(0),
        plan.equity * plan.max_concentration_percent / 100 - plan.existing_shares * plan.entry,
    )
    concentration_shares = int(concentration_capacity // plan.entry)
    existing_loss, add_loss, total_loss, conservative_loss, risk_shares = None, None, None, None, 0
    if plan.stop is not None:
        existing_loss = plan.existing_shares * max(Decimal(0), plan.existing_average - plan.stop)
        add_loss = plan.requested_shares * (plan.entry - plan.stop)
        total_loss = max(Decimal(0), total_cost - total_shares * plan.stop)
        conservative_loss = existing_loss + add_loss
        risk_shares = int(max(Decimal(0), budget - existing_loss) // (plan.entry - plan.stop))
    allowable = min(risk_shares, affordable, concentration_shares)
    blockers = []
    if plan.stop is None:
        blockers.append("no_defined_stop")
    elif conservative_loss > budget:
        blockers.append("risk_budget_exceeded")
    if add_cost > plan.buying_power:
        blockers.append("insufficient_buying_power")
    if concentration > plan.max_concentration_percent:
        blockers.append("concentration_limit_exceeded")
    status = (
        "unknown"
        if plan.stop_reported_active is None
        else "user_reported_active"
        if plan.stop_reported_active
        else "planned_only"
    )

    def number(value):
        return str(value) if value is not None else None

    return {
        "status": "blocked" if blockers else "within_supplied_limits",
        "symbol": plan.symbol,
        "blockers": blockers,
        "entry": str(plan.entry),
        "stop": number(plan.stop),
        "stop_status": status,
        "stop_verified_with_broker": False,
        "requested_add_shares": plan.requested_shares,
        "existing_shares": plan.existing_shares,
        "total_shares": total_shares,
        "combined_average": number(average),
        "existing_cost": str(existing_cost),
        "add_cost": str(add_cost),
        "total_cost": str(total_cost),
        "existing_planned_loss": number(existing_loss),
        "incremental_planned_loss": number(add_loss),
        "combined_net_planned_loss": number(total_loss),
        "conservative_budget_loss": number(conservative_loss),
        "account_risk_percent": number(
            conservative_loss / plan.equity * 100 if conservative_loss is not None else None
        ),
        "capital_at_risk_without_stop": str(total_cost),
        "risk_budget_dollars": str(budget),
        "risk_budget_percent": str(plan.risk_budget_percent),
        "concentration_percent_at_entry": str(concentration),
        "max_concentration_percent": str(plan.max_concentration_percent),
        "buying_power_before": str(plan.buying_power),
        "buying_power_after_add": str(plan.buying_power - add_cost),
        "allowable_add_shares": allowable,
        "share_limits": {
            "risk": risk_shares,
            "buying_power": affordable,
            "concentration": concentration_shares,
        },
        "input_basis": "user_supplied_unverified_account_and_plan",
        "note": "Long shares only; planned stop loss excludes gaps, slippage, fees and fill failure. No order or stop is placed.",
    }
