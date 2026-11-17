import json
from pathlib import Path

from app.engine import AdmissionEngine, verify_run

from .helpers import admission_set

EXPECTED = json.loads(
    (Path(__file__).resolve().parent / "expected" / "small_expected.json").read_text(encoding="utf-8")
)


def _plan_stats(ds, result, high_code: str, batch: int):
    high_id = next(h.id for h in ds.high_schools.values() if h.code == high_code)
    plan_id = next(p.id for p in ds.plans.values() if p.high_school_id == high_id and p.batch == batch)
    admissions = sorted(
        [a for a in result.admissions if a.plan_id == plan_id], key=lambda a: a.admission_order
    )
    last = admissions[-1]
    return {
        "min_score": min(a.score for a in admissions),
        "last_candidate_no": ds.candidates[last.candidate_id].candidate_no,
        "last_score": last.score,
        "last_volunteer_seq": last.volunteer_seq,
        "last_admission_order": last.admission_order,
    }


def test_small_dataset_matches_manual_expectations(small_dataset):
    result = AdmissionEngine(small_dataset).run_all()

    expected_admissions = {
        (a["candidate_no"], a["batch"], a["high_school_code"], a["volunteer_seq"])
        for a in EXPECTED["admissions"]
    }
    assert admission_set(small_dataset, result) == expected_admissions

    batch_counts = {
        str(batch): sum(1 for a in result.admissions if a.batch == batch) for batch in (1, 2, 3, 4)
    }
    assert batch_counts == EXPECTED["batch_counts"]

    for pid, expected in EXPECTED["plan_states"].items():
        state = result.plan_states[int(pid)]
        assert state.initial_quota == expected["initial"]
        assert state.transferred_in == expected["in"]
        assert state.transferred_out == expected["out"]
        assert state.admitted_count == expected["admitted"]
        assert state.remaining == expected["remaining"]

    transfers = sorted(
        [
            {
                "from_batch": t.from_batch,
                "from_plan_id": t.from_plan_id,
                "to_plan_id": t.to_plan_id,
                "amount": t.amount,
            }
            for t in result.transfers
        ],
        key=lambda t: (t["from_batch"], t["from_plan_id"]),
    )
    assert transfers == sorted(EXPECTED["transfers"], key=lambda t: (t["from_batch"], t["from_plan_id"]))

    for key, expected in EXPECTED["plan_stats"].items():
        code, batch = key.split(":")
        assert _plan_stats(small_dataset, result, code, int(batch)) == expected

    admitted_ids = {a.candidate_id for a in result.admissions}
    unadmitted = {
        c.candidate_no for c in small_dataset.candidates.values() if c.id not in admitted_ids
    }
    assert unadmitted == set(EXPECTED["unadmitted"])

    assert verify_run(small_dataset, result.plan_states, result.admissions) == []


def test_stepwise_execution_equals_full_run(small_dataset):
    full = AdmissionEngine(small_dataset).run_all()

    engine = AdmissionEngine(small_dataset)
    admitted = {}
    states = None
    all_admissions = []
    for batch in (1, 2, 3, 4):
        part = engine.run_batch(batch)
        all_admissions.extend(part.admissions)
        admitted.update(engine.admitted)
        states = engine.states
        engine = AdmissionEngine(small_dataset, admitted=dict(admitted), plan_states=dict(states))

    assert {(a.candidate_id, a.plan_id, a.volunteer_seq) for a in all_admissions} == {
        (a.candidate_id, a.plan_id, a.volunteer_seq) for a in full.admissions
    }
    assert {pid: (s.transferred_in, s.transferred_out, s.admitted_count, s.remaining) for pid, s in states.items()} == {
        pid: (s.transferred_in, s.transferred_out, s.admitted_count, s.remaining)
        for pid, s in full.plan_states.items()
    }
