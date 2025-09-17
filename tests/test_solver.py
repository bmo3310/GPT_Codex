from __future__ import annotations

from collections import Counter

from scheduler.config import AttendingConfig, ResidentConfig, ScheduleConfig
from scheduler.solver import ScheduleSolver


def build_sample_config() -> ScheduleConfig:
    return ScheduleConfig(
        year=2024,
        month=4,
        attendings=[
            AttendingConfig(
                code="A",
                unavailable={1, 15},
                must_work={6},
                weekday_shifts=5,
                weekend_shifts=2,
                weekday_with_resident=2,
                weekend_with_resident=1,
            ),
            AttendingConfig(
                code="B",
                unavailable={7},
                must_work={3},
                weekday_shifts=5,
                weekend_shifts=2,
                weekday_with_resident=2,
                weekend_with_resident=1,
            ),
            AttendingConfig(
                code="C",
                unavailable={13},
                must_work={10},
                weekday_shifts=4,
                weekend_shifts=1,
                weekday_with_resident=1,
                weekend_with_resident=0,
            ),
            AttendingConfig(
                code="D",
                unavailable={2},
                must_work={21},
                weekday_shifts=4,
                weekend_shifts=2,
                weekday_with_resident=1,
                weekend_with_resident=1,
            ),
            AttendingConfig(
                code="E",
                unavailable={5},
                must_work={27},
                weekday_shifts=4,
                weekend_shifts=1,
                weekday_with_resident=1,
                weekend_with_resident=1,
            ),
        ],
        residents=[
            ResidentConfig(
                code="a",
                unavailable={1, 14},
                must_work={6},
                weekday_shifts=4,
                weekend_shifts=2,
            ),
            ResidentConfig(
                code="b",
                unavailable={2},
                must_work={13},
                weekday_shifts=3,
                weekend_shifts=2,
            ),
        ],
    )


def test_solver_produces_feasible_schedule():
    config = build_sample_config()
    solver = ScheduleSolver(config)
    assignments = solver.solve()

    assert len(assignments) == 30
    assert [assignment.date.day for assignment in assignments] == list(range(1, 31))

    attending_weekday = Counter()
    attending_weekend = Counter()
    attending_with_resident_weekday = Counter()
    attending_with_resident_weekend = Counter()
    resident_weekday = Counter()
    resident_weekend = Counter()

    last_day_attending = {}
    last_day_resident = {}

    for assignment in assignments:
        current_day = assignment.date.day
        is_weekend = assignment.is_weekend
        attending_code = assignment.attending

        if attending_code in last_day_attending:
            assert current_day - last_day_attending[attending_code] > 1
        last_day_attending[attending_code] = current_day

        if is_weekend:
            attending_weekend[attending_code] += 1
        else:
            attending_weekday[attending_code] += 1

        if assignment.resident is not None:
            resident_code = assignment.resident
            if resident_code in last_day_resident:
                assert current_day - last_day_resident[resident_code] > 1
            last_day_resident[resident_code] = current_day

            if is_weekend:
                attending_with_resident_weekend[attending_code] += 1
                resident_weekend[resident_code] += 1
            else:
                attending_with_resident_weekday[attending_code] += 1
                resident_weekday[resident_code] += 1

    for attending in config.attendings:
        assigned_days = {
            assignment.date.day
            for assignment in assignments
            if assignment.attending == attending.code
        }
        assert assigned_days & attending.unavailable == set()
        assert attending.must_work <= assigned_days
        assert attending_weekday[attending.code] == attending.weekday_shifts
        assert attending_weekend[attending.code] == attending.weekend_shifts
        assert (
            attending_with_resident_weekday[attending.code]
            == attending.weekday_with_resident
        )
        assert (
            attending_with_resident_weekend[attending.code]
            == attending.weekend_with_resident
        )

    for resident in config.residents:
        worked_days = {
            assignment.date.day
            for assignment in assignments
            if assignment.resident == resident.code
        }
        assert worked_days & resident.unavailable == set()
        assert resident.must_work <= worked_days
        assert resident_weekday[resident.code] == resident.weekday_shifts
        assert resident_weekend[resident.code] == resident.weekend_shifts

    # Ensure every day has exactly one attending and at most one resident.
    by_day = {}
    for assignment in assignments:
        assert assignment.date.day not in by_day
        by_day[assignment.date.day] = assignment
        assert assignment.attending is not None

    assert set(by_day.keys()) == set(range(1, 31))
