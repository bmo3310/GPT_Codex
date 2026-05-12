"""Configuration models for the duty roster scheduler."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Sequence, Set


@dataclass(slots=True)
class BasePersonConfig:
    """Common configuration for both attendings and residents."""

    code: str
    unavailable: Set[int] = field(default_factory=set)
    must_work: Set[int] = field(default_factory=set)
    weekday_shifts: int = 0
    weekend_shifts: int = 0

    def normalize(self) -> None:
        self.unavailable = set(self.unavailable)
        self.must_work = set(self.must_work)

    def validate(self, total_weekdays: int, total_weekends: int) -> None:
        if self.weekday_shifts < 0 or self.weekend_shifts < 0:
            raise ValueError(f"{self.code}: shift counts must be non-negative")
        if self.weekday_shifts > total_weekdays:
            raise ValueError(
                f"{self.code}: weekday shifts ({self.weekday_shifts}) exceed available weekdays ({total_weekdays})"
            )
        if self.weekend_shifts > total_weekends:
            raise ValueError(
                f"{self.code}: weekend shifts ({self.weekend_shifts}) exceed available weekends ({total_weekends})"
            )
        if self.unavailable & self.must_work:
            conflict = sorted(self.unavailable & self.must_work)
            raise ValueError(f"{self.code}: days marked unavailable and must-work overlap: {conflict}")
        if len(self.must_work) > self.weekday_shifts + self.weekend_shifts:
            raise ValueError(
                f"{self.code}: number of must-work days exceeds total scheduled shifts"
            )


@dataclass(slots=True)
class AttendingConfig(BasePersonConfig):
    """Configuration for attending physicians."""

    weekday_with_resident: int = 0
    weekend_with_resident: int = 0

    def validate(self, total_weekdays: int, total_weekends: int) -> None:  # type: ignore[override]
        BasePersonConfig.validate(self, total_weekdays, total_weekends)
        if self.weekday_with_resident < 0 or self.weekend_with_resident < 0:
            raise ValueError(f"{self.code}: resident coverage requirements must be non-negative")
        if self.weekday_with_resident > self.weekday_shifts:
            raise ValueError(
                f"{self.code}: weekday-with-resident count exceeds weekday shifts"
            )
        if self.weekend_with_resident > self.weekend_shifts:
            raise ValueError(
                f"{self.code}: weekend-with-resident count exceeds weekend shifts"
            )


@dataclass(slots=True)
class ResidentConfig(BasePersonConfig):
    """Configuration for residents."""


@dataclass(slots=True)
class ScheduleConfig:
    """Top-level configuration describing the roster to generate."""

    year: int
    month: int
    attendings: Sequence[AttendingConfig]
    residents: Sequence[ResidentConfig]

    @property
    def codes(self) -> List[str]:
        return [a.code for a in self.attendings] + [r.code for r in self.residents]

    def normalize(self) -> None:
        for person in self.attendings:
            person.normalize()
        for person in self.residents:
            person.normalize()

    def validate(self) -> None:
        from calendar import monthrange

        total_days = monthrange(self.year, self.month)[1]
        weekdays = 0
        weekends = 0
        for day in range(1, total_days + 1):
            weekday = _is_weekend(self.year, self.month, day)
            if weekday:
                weekends += 1
            else:
                weekdays += 1

        attending_weekday_total = sum(a.weekday_shifts for a in self.attendings)
        attending_weekend_total = sum(a.weekend_shifts for a in self.attendings)
        if attending_weekday_total != weekdays or attending_weekend_total != weekends:
            raise ValueError(
                "Attendings' weekday/weekend shift counts must exactly cover the month: "
                f"expected {weekdays} weekdays/{weekends} weekends but received {attending_weekday_total}/{attending_weekend_total}."
            )

        for attending in self.attendings:
            attending.validate(weekdays, weekends)

        for resident in self.residents:
            resident.validate(weekdays, weekends)

        attending_resident_weekday = sum(a.weekday_with_resident for a in self.attendings)
        attending_resident_weekend = sum(a.weekend_with_resident for a in self.attendings)
        resident_weekday_total = sum(r.weekday_shifts for r in self.residents)
        resident_weekend_total = sum(r.weekend_shifts for r in self.residents)

        if attending_resident_weekday != resident_weekday_total or attending_resident_weekend != resident_weekend_total:
            raise ValueError(
                "Resident shift totals must match the attendings' requested coverage with residents."
            )

        self._validate_day_specific_rules(total_days)

    def _validate_day_specific_rules(self, total_days: int) -> None:
        attending_by_day = {day: [] for day in range(1, total_days + 1)}
        resident_by_day = {day: [] for day in range(1, total_days + 1)}

        for attending in self.attendings:
            for day in attending.must_work:
                self._ensure_valid_day(day, total_days, attending.code)
                attending_by_day[day].append(attending.code)
            for day in attending.unavailable:
                self._ensure_valid_day(day, total_days, attending.code)

        for resident in self.residents:
            for day in resident.must_work:
                self._ensure_valid_day(day, total_days, resident.code)
                resident_by_day[day].append(resident.code)
            for day in resident.unavailable:
                self._ensure_valid_day(day, total_days, resident.code)

        for day, codes in attending_by_day.items():
            if len(codes) > 1:
                raise ValueError(
                    f"Multiple attendings marked as must-work on the same day {day}: {codes}"
                )
        for day, codes in resident_by_day.items():
            if len(codes) > 1:
                raise ValueError(
                    f"Multiple residents marked as must-work on the same day {day}: {codes}"
                )

    @staticmethod
    def _ensure_valid_day(day: int, total_days: int, code: str) -> None:
        if day < 1 or day > total_days:
            raise ValueError(f"{code}: day {day} is outside the month")


def _is_weekend(year: int, month: int, day: int) -> bool:
    from datetime import date

    return date(year, month, day).weekday() >= 5
