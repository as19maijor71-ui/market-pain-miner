from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpportunityScore:
    frequency: int
    urgency: int
    willingness_to_pay: int
    mvp_speed: int
    repeatability: int
    defensibility: int
    data_access: int

    @property
    def total(self) -> int:
        return (
            self.frequency
            + self.urgency
            + self.willingness_to_pay
            + self.mvp_speed
            + self.repeatability
            + self.defensibility
            + self.data_access
        )

    @property
    def verdict(self) -> str:
        if self.total >= 28:
            return "strong"
        if self.total >= 21:
            return "promising"
        if self.total >= 14:
            return "watch"
        return "weak"

