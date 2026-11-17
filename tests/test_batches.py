from app.engine import AdmissionEngine, verify_run

from .helpers import admission_set, cand, hs, make_dataset, outcomes_for, plan, qual, vol


def test_autonomous_qualification_rank_and_control_line():
    ds = make_dataset(
        high_schools=[hs(1, "A", "A高中", autonomous=1, total=4)],
        candidates=[
            cand(1, "C1", 700), cand(2, "C2", 660), cand(3, "C3", 640),
            cand(4, "C4", 720), cand(5, "C5", 680), cand(6, "C6", 710),
        ],
        plans=[plan(1, 1, 1, 2, control=650), plan(2, 1, 3, 2)],
        qualifications=[
            qual(1, 1, 1), qual(2, 1, 2), qual(3, 1, 3),
            qual(5, 1, None, "disqualified"), qual(6, 1, 4),
        ],
        volunteers=[vol(i, 1, 1, 1) for i in range(1, 7)],
    )
    result = AdmissionEngine(ds).run_all()
    assert admission_set(ds, result) == {("C1", 1, "A", 1), ("C2", 1, "A", 1)}
    assert result.plan_states[1].admitted_count == 2
    reasons = {ds.candidates[cid].candidate_no: outcomes_for(result, cid)[1].reason_code for cid in range(1, 7)}
    assert reasons["C3"] == "BELOW_PLAN_CONTROL_LINE"
    assert reasons["C4"] == "NO_QUALIFICATION"
    assert reasons["C5"] == "DISQUALIFIED"
    assert reasons["C6"] == "PLAN_FULL"


def test_cross_batch_exclusion():
    ds = make_dataset(
        high_schools=[hs(1, "A", "A高中", autonomous=1, total=2)],
        candidates=[cand(1, "C1", 700), cand(2, "C2", 690)],
        plans=[plan(1, 1, 1, 1), plan(2, 1, 3, 1)],
        qualifications=[qual(1, 1, 1)],
        volunteers=[vol(1, 1, 1, 1), vol(1, 3, 1, 1), vol(2, 3, 1, 1)],
    )
    result = AdmissionEngine(ds).run_all()
    assert admission_set(ds, result) == {("C1", 1, "A", 1), ("C2", 3, "A", 1)}
    assert result.plan_states[2].admitted_count == 1
    assert outcomes_for(result, 1)[3].status == "SKIPPED"
    assert outcomes_for(result, 1)[3].reason_code == "ALREADY_ADMITTED"


def test_quota_allocation_isolation():
    ds = make_dataset(
        middle_schools=[
            {"id": 1, "code": "M1", "name": "初中一", "district": ""},
            {"id": 2, "code": "M2", "name": "初中二", "district": ""},
        ],
        high_schools=[hs(1, "A", "A高中", total=4)],
        candidates=[
            cand(1, "C1", 700, middle=1), cand(2, "C2", 690, middle=1),
            cand(3, "C3", 710, middle=2), cand(4, "C4", 600, middle=2),
            cand(5, "C5", 650, middle=1),
        ],
        plans=[
            plan(1, 1, 2, 1, middle=1), plan(2, 1, 2, 1, middle=2), plan(3, 1, 3, 2),
        ],
        volunteers=[
            vol(1, 2, 1, 1), vol(2, 2, 1, 1),
            vol(3, 2, 1, 1), vol(4, 2, 1, 1),
            vol(2, 3, 1, 1), vol(4, 3, 1, 1), vol(5, 3, 1, 1),
        ],
    )
    result = AdmissionEngine(ds).run_all()
    assert admission_set(ds, result) == {
        ("C1", 2, "A", 1), ("C3", 2, "A", 1),
        ("C2", 3, "A", 1), ("C5", 3, "A", 1),
    }
    # C2 690 分不能占用 M2 的剩余名额；M2 名额由 C3 使用
    assert result.plan_states[1].admitted_count == 1
    assert result.plan_states[2].admitted_count == 1
    assert result.plan_states[3].admitted_count == 2


def test_quota_transfer_happens_once():
    ds = make_dataset(
        high_schools=[hs(1, "A", "A高中", autonomous=1, total=5)],
        candidates=[
            cand(1, "C1", 700), cand(2, "C2", 690),
            cand(3, "C3", 680), cand(4, "C4", 670), cand(5, "C5", 660),
        ],
        plans=[plan(1, 1, 1, 2), plan(2, 1, 2, 2, middle=1), plan(3, 1, 3, 1)],
        qualifications=[qual(1, 1, 1)],
        volunteers=[
            vol(1, 1, 1, 1), vol(2, 2, 1, 1),
            vol(3, 3, 1, 1), vol(4, 3, 1, 1), vol(5, 3, 1, 1),
        ],
    )
    first = AdmissionEngine(ds).run_all()
    second = AdmissionEngine(ds).run_all()
    assert admission_set(ds, first) == {
        ("C1", 1, "A", 1), ("C2", 2, "A", 1),
        ("C3", 3, "A", 1), ("C4", 3, "A", 1), ("C5", 3, "A", 1),
    }
    assert first.plan_states[3].initial_quota == 1
    assert first.plan_states[3].transferred_in == 2
    assert first.plan_states[3].admitted_count == 3
    assert first.plan_states[3].remaining == 0
    assert sorted(t.amount for t in first.transfers) == [1, 1]
    assert sorted(t.amount for t in second.transfers) == [1, 1]
    assert first.plan_states[3].transferred_in == second.plan_states[3].transferred_in == 2
    assert verify_run(ds, first.plan_states, first.admissions) == []


def test_underfill_and_empty_plan():
    ds = make_dataset(
        high_schools=[hs(1, "A", "A高中"), hs(2, "B", "B高中")],
        candidates=[cand(1, "C1", 650)],
        plans=[plan(1, 1, 3, 2), plan(2, 2, 3, 2)],
        volunteers=[vol(1, 3, 1, 1)],
    )
    result = AdmissionEngine(ds).run_all()
    assert admission_set(ds, result) == {("C1", 3, "A", 1)}
    assert result.plan_states[1].admitted_count == 1
    assert result.plan_states[1].remaining == 1
    assert result.plan_states[2].admitted_count == 0
    assert result.plan_states[2].remaining == 2


def test_system_constraints_on_small_dataset(small_dataset):
    result = AdmissionEngine(small_dataset).run_all()
    assert verify_run(small_dataset, result.plan_states, result.admissions) == []
    assert len(result.admissions) == len({a.candidate_id for a in result.admissions})
    for pid, state in result.plan_states.items():
        assert state.admitted_count <= state.effective_quota - state.transferred_out
        assert state.initial_quota + state.transferred_in - state.transferred_out == (
            state.admitted_count + state.remaining
        )


def test_batch3_remaining_is_not_transferred_to_batch4():
    ds = make_dataset(
        high_schools=[hs(1, "A", "A高中"), hs(2, "B", "B高中", batch=4)],
        candidates=[cand(1, "C1", 650)],
        plans=[plan(1, 1, 3, 2), plan(2, 2, 4, 2)],
        volunteers=[vol(1, 3, 1, 1)],
    )
    result = AdmissionEngine(ds).run_all()
    assert result.plan_states[1].admitted_count == 1
    assert result.plan_states[1].remaining == 1
    assert result.plan_states[2].initial_quota == 2
    assert result.plan_states[2].transferred_in == 0
    assert result.plan_states[2].remaining == 2
    assert result.transfers == []

