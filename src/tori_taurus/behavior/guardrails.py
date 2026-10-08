"""Explicit user-supplied loss, exit, and thesis context; no inferred trade history."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from tori_taurus.market_data.models import price, utc
from tori_taurus.risk import RiskInputs, evaluate_risk


@dataclass(frozen=True)
class GuardrailInputs:
    losses_today: Decimal = Decimal(0)
    daily_loss_limit_percent: Decimal = Decimal(3)
    last_exit_at: datetime | None = None
    cooldown_minutes: int = 15
    reference_price: Decimal | None = None
    max_chase_percent: Decimal = Decimal(3)
    thesis_reconfirmed: bool = False

    def __post_init__(self):
        for key in ("losses_today", "daily_loss_limit_percent", "max_chase_percent"):
            object.__setattr__(self, key, price(getattr(self, key)))
        if not 0 < self.daily_loss_limit_percent <= 100:
            raise ValueError("Daily loss limit must be in (0,100]")
        if type(self.cooldown_minutes) is not int or self.cooldown_minutes < 0:
            raise ValueError("Cooldown must be nonnegative whole minutes")
        if self.last_exit_at is not None:
            object.__setattr__(self, "last_exit_at", utc(self.last_exit_at))
        if self.reference_price is not None:
            object.__setattr__(self, "reference_price", price(self.reference_price))
            if self.reference_price <= 0:
                raise ValueError("Reference price must be positive")
        if type(self.thesis_reconfirmed) is not bool:
            raise ValueError("Thesis reconfirmation must be boolean")


def evaluate_guardrails(plan: RiskInputs, context: GuardrailInputs, *, as_of: datetime) -> dict:
    as_of = utc(as_of)
    if context.last_exit_at is not None and context.last_exit_at > as_of:
        raise ValueError("Last exit must not be in the future")
    risk = evaluate_risk(plan)
    planned = risk["conservative_budget_loss"]
    planned_loss = Decimal(planned) if planned is not None else None
    limit = plan.equity * context.daily_loss_limit_percent / 100
    blockers, unevaluated = [], []
    if context.losses_today >= limit:
        blockers.append("daily_loss_limit_reached")
    elif planned_loss is not None and context.losses_today + planned_loss > limit:
        blockers.append("planned_loss_exceeds_daily_headroom")
    if planned_loss is None:
        unevaluated.append("daily_planned_loss_without_stop")
    cooldown_remaining = 0
    if context.last_exit_at is not None:
        remaining = (
            context.last_exit_at + timedelta(minutes=context.cooldown_minutes) - as_of
        ).total_seconds()
        cooldown_remaining = max(0, int(remaining + 0.999999))
        if cooldown_remaining > 0:
            blockers.append("exit_cooldown_active")
    extension = None
    if context.reference_price is None:
        unevaluated.append("chase_reference_not_supplied")
    else:
        extension = (plan.entry / context.reference_price - 1) * 100
        if extension > context.max_chase_percent:
            blockers.append("entry_chasing_reference")
    averaging_down = (
        plan.requested_shares > 0
        and plan.existing_shares > 0
        and plan.entry < plan.existing_average
    )
    if averaging_down and not context.thesis_reconfirmed:
        blockers.append("unsupported_averaging_down")
    daily_shares = 0
    if plan.stop is not None:
        existing_loss = Decimal(risk["existing_planned_loss"])
        remaining_budget = max(Decimal(0), limit - context.losses_today - existing_loss)
        daily_shares = int(remaining_budget // (plan.entry - plan.stop))
    guarded_shares = (
        0 if blockers or unevaluated else min(risk["allowable_add_shares"], daily_shares)
    )
    return {
        "allowable_add_shares_after_guardrails": guarded_shares,
        "daily_loss_share_ceiling": daily_shares,
        "status": "blocked"
        if blockers
        else "incomplete"
        if unevaluated
        else "within_supplied_limits",
        "blockers": blockers,
        "unevaluated": unevaluated,
        "as_of": as_of.isoformat(),
        "losses_today": str(context.losses_today),
        "daily_loss_limit_dollars": str(limit),
        "daily_headroom_before_plan": str(max(Decimal(0), limit - context.losses_today)),
        "daily_headroom_after_plan": str(limit - context.losses_today - planned_loss)
        if planned_loss is not None
        else None,
        "cooldown_remaining_seconds": cooldown_remaining,
        "entry_extension_percent": str(extension) if extension is not None else None,
        "averaging_down": averaging_down,
        "thesis_reconfirmed_by_user": context.thesis_reconfirmed,
        "input_basis": "user_supplied_unverified_context",
        "note": "Losses are gross realized losses today; wins do not reset the loss budget. User thesis confirmation does not prove an add is justified.",
    }
