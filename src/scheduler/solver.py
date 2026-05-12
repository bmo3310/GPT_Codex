"""Backtracking solver for the duty roster scheduling problem."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Sequence

from .config import AttendingConfig, ResidentConfig, ScheduleConfig


@dataclass(slots=True)
class DayAssignment:
    """Concrete assignment for a single day."""

    date: date
    attending: str
    resident: Optional[str]

    @property
    def day(self) -> int:
        return self.date.day

    @property
    def is_weekend(self) -> bool:
        return self.date.weekday() >= 5


@dataclass(slots=True)
class _Day:
    day: int
    is_weekend: bool
    attending_must: Optional[str]
    resident_must: Optional[str]


@dataclass(slots=True)
class _PersonState:
    weekday_remaining: int
    weekend_remaining: int
    weekday_with_resident_remaining: int = 0
    weekend_with_resident_remaining: int = 0
    last_worked_day: Optional[int] = None

    def remaining_for_day(self, is_weekend: bool) -> int:
        return self.weekend_remaining if is_weekend else self.weekday_remaining

    def decrement(self, is_weekend: bool) -> None:
        if is_weekend:
            self.weekend_remaining -= 1
        else:
            self.weekday_remaining -= 1

    def increment(self, is_weekend: bool) -> None:
        if is_weekend:
            self.weekend_remaining += 1
        else:
            self.weekday_remaining += 1

    def decrement_with_resident(self, is_weekend: bool) -> None:
        if is_weekend:
            self.weekend_with_resident_remaining -= 1
        else:
            self.weekday_with_resident_remaining -= 1

    def increment_with_resident(self, is_weekend: bool) -> None:
        if is_weekend:
            self.weekend_with_resident_remaining += 1
        else:
            self.weekday_with_resident_remaining += 1


class ScheduleSolver:
    """Search-based solver for the scheduling problem."""

    def __init__(self, config: ScheduleConfig):
        self.config = config
        self.config.normalize()
        self.config.validate()

        self._attending_states: Dict[str, _PersonState] = {
            a.code: _PersonState(
                weekday_remaining=a.weekday_shifts,
                weekend_remaining=a.weekend_shifts,
                weekday_with_resident_remaining=a.weekday_with_resident,
                weekend_with_resident_remaining=a.weekend_with_resident,
            )
            for a in self.config.attendings
        }
        self._resident_states: Dict[str, _PersonState] = {
            r.code: _PersonState(
                weekday_remaining=r.weekday_shifts,
                weekend_remaining=r.weekend_shifts,
            )
            for r in self.config.residents
        }

        self._days: List[_Day] = self._build_days()
        self._resident_map = {r.code: r for r in self.config.residents}

    def solve(self) -> List[DayAssignment]:
        assignments: List[DayAssignment] = []
        success = self._search(0, assignments)
        if not success:
            raise ValueError("Unable to construct a valid schedule with the provided constraints")
        return sorted(assignments, key=lambda assignment: assignment.date)

    def _build_days(self) -> List[_Day]:
        from calendar import monthrange

        total_days = monthrange(self.config.year, self.config.month)[1]
        days: List[_Day] = []
        for day in range(1, total_days + 1):
            weekday = date(self.config.year, self.config.month, day).weekday()
            is_weekend = weekday >= 5
            attending_must = self._find_must(self.config.attendings, day)
            resident_must = self._find_must(self.config.residents, day)
            days.append(
                _Day(
                    day=day,
                    is_weekend=is_weekend,
                    attending_must=attending_must,
                    resident_must=resident_must,
                )
            )
        return days

    @staticmethod
    def _find_must(people: Sequence[AttendingConfig | ResidentConfig], day: int) -> Optional[str]:
        for person in people:
            if day in person.must_work:
                return person.code
        return None

    def _search(self, index: int, assignments: List[DayAssignment]) -> bool:
        if index == len(self._days):
            return self._all_requirements_met()

        day = self._days[index]
        attending_options = self._attending_candidates(day)
        for attending_code in attending_options:
            attending_state = self._attending_states[attending_code]
            attending_state.decrement(day.is_weekend)
            previous_day = attending_state.last_worked_day
            attending_state.last_worked_day = day.day

            resident_options = self._resident_candidates(day, attending_code)
            for resident_code in resident_options:
                resident_state = self._resident_states.get(resident_code)
                if resident_state:
                    resident_state.decrement(day.is_weekend)
                    resident_prev_day = resident_state.last_worked_day
                    resident_state.last_worked_day = day.day

                with_resident = resident_code is not None
                if with_resident:
                    attending_state.decrement_with_resident(day.is_weekend)

                assignments.append(
                    DayAssignment(
                        date=date(self.config.year, self.config.month, day.day),
                        attending=attending_code,
                        resident=resident_code,
                    )
                )

                if self._is_partial_solution_feasible(index + 1):
                    if self._search(index + 1, assignments):
                        return True

                assignments.pop()

                if with_resident:
                    attending_state.increment_with_resident(day.is_weekend)

                if resident_state:
                    resident_state.increment(day.is_weekend)
                    resident_state.last_worked_day = resident_prev_day

            attending_state.increment(day.is_weekend)
            attending_state.last_worked_day = previous_day

        return False

    def _attending_candidates(self, day: _Day) -> List[str]:
        candidates = []
        for attending in self.config.attendings:
            if day.day in attending.unavailable:
                continue
            if day.attending_must and attending.code != day.attending_must:
                continue
            state = self._attending_states[attending.code]
            if state.remaining_for_day(day.is_weekend) <= 0:
                continue
            if state.last_worked_day and state.last_worked_day == day.day - 1:
                continue
            if not self._can_still_meet_resident_requirement(attending, state, day.is_weekend):
                continue
            candidates.append(attending.code)
        return candidates

    def _resident_candidates(self, day: _Day, attending_code: str) -> List[Optional[str]]:
        if day.resident_must:
            resident = self._resident_map[day.resident_must]
            state = self._resident_states[resident.code]
            if state.remaining_for_day(day.is_weekend) <= 0:
                return []
            if state.last_worked_day and state.last_worked_day == day.day - 1:
                return []
            if day.day in resident.unavailable:
                return []
            return [resident.code]

        state = self._attending_states[attending_code]

        options: List[Optional[str]] = [None]
        if day.is_weekend:
            if state.weekend_with_resident_remaining <= 0:
                return options
        else:
            if state.weekday_with_resident_remaining <= 0:
                return options

        for resident in self.config.residents:
            if day.day in resident.unavailable:
                continue
            resident_state = self._resident_states[resident.code]
            if resident_state.remaining_for_day(day.is_weekend) <= 0:
                continue
            if resident_state.last_worked_day and resident_state.last_worked_day == day.day - 1:
                continue
            options.append(resident.code)
        return options

    def _can_still_meet_resident_requirement(
        self, attending: AttendingConfig, state: _PersonState, is_weekend: bool
    ) -> bool:
        remaining_shifts = state.weekend_remaining if is_weekend else state.weekday_remaining
        remaining_with_resident = (
            state.weekend_with_resident_remaining
            if is_weekend
            else state.weekday_with_resident_remaining
        )
        return remaining_shifts > 0 and remaining_with_resident <= remaining_shifts

    def _is_partial_solution_feasible(self, next_index: int) -> bool:
        # Quick pruning: ensure no remaining counts are negative and must-work days can still be honoured.
        for state in self._attending_states.values():
            if state.weekday_remaining < 0 or state.weekend_remaining < 0:
                return False
            if state.weekday_with_resident_remaining < 0 or state.weekend_with_resident_remaining < 0:
                return False
            if state.weekday_with_resident_remaining > state.weekday_remaining:
                return False
            if state.weekend_with_resident_remaining > state.weekend_remaining:
                return False

        for state in self._resident_states.values():
            if state.weekday_remaining < 0 or state.weekend_remaining < 0:
                return False

        return self._must_work_days_still_possible(next_index)

    def _must_work_days_still_possible(self, next_index: int) -> bool:
        processed_days = {info.day for info in self._days[:next_index]}
        for attending in self.config.attendings:
            state = self._attending_states[attending.code]
            remaining_must = [day for day in attending.must_work if day not in processed_days]
            if not self._can_fill_required_days(remaining_must, attending, state):
                return False
        for resident in self.config.residents:
            state = self._resident_states[resident.code]
            remaining_must = [day for day in resident.must_work if day not in processed_days]
            if not self._can_fill_required_days(remaining_must, resident, state):
                return False
        return True

    def _can_fill_required_days(
        self,
        required_days: Sequence[int],
        person: AttendingConfig | ResidentConfig,
        state: _PersonState,
    ) -> bool:
        for day in required_days:
            info = next((d for d in self._days if d.day == day), None)
            if info is None:
                continue
            if info.is_weekend:
                if state.weekend_remaining <= 0:
                    return False
                if day in person.unavailable:
                    return False
            else:
                if state.weekday_remaining <= 0:
                    return False
                if day in person.unavailable:
                    return False
            if state.last_worked_day and state.last_worked_day == day - 1:
                return False
        return True

    def _all_requirements_met(self) -> bool:
        for state in self._attending_states.values():
            if any(
                value != 0
                for value in (
                    state.weekday_remaining,
                    state.weekend_remaining,
                    state.weekday_with_resident_remaining,
                    state.weekend_with_resident_remaining,
                )
            ):
                return False
        for state in self._resident_states.values():
            if state.weekday_remaining != 0 or state.weekend_remaining != 0:
                return False
        return True
