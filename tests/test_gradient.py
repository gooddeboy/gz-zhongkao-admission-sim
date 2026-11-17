from app.engine import AdmissionEngine, gradient_band, max_gradient_band

from .helpers import admission_set, cand, hs, make_dataset, plan, vol


def test_gradient_band_boundaries():
    assert gradient_band(720, 720, 40, 600) == 1
    assert gradient_band(719, 720, 40, 600) == 2
    assert gradient_band(680, 720, 40, 600) == 2
    assert gradient_band(679, 720, 40, 600) == 3
    assert gradient_band(640, 720, 40, 600) == 3
    assert gradient_band(639, 720, 40, 600) == 4
    assert gradient_band(600, 720, 40, 600) == 4
    assert gradient_band(599, 720, 40, 600) is None
    assert max_gradient_band(720, 40, 600) == 4
    assert max_gradient_band(712, 40, 492) == 7


def test_gradient_priority_high_band_later_volunteer_beats_low_band_first():
    ds = make_dataset(
        high_schools=[hs(1, "A", "A高中"), hs(2, "B", "B高中")],
        candidates=[cand(1, "高", 730), cand(2, "低", 700), cand(3, "填", 740)],
        plans=[plan(1, 1, 3, 1), plan(2, 2, 3, 1)],
        volunteers=[
            vol(1, 3, 1, 2), vol(1, 3, 2, 1),
            vol(2, 3, 1, 1),
            vol(3, 3, 1, 2),
        ],
    )
    result = AdmissionEngine(ds).run_all()
    assert admission_set(ds, result) == {("填", 3, "B", 1), ("高", 3, "A", 2)}
    assert result.plan_states[1].admitted_count == 1
    assert result.plan_states[2].admitted_count == 1


def test_same_gradient_volunteer_priority_and_last_admitted():
    """任务书最低测试示例：甲690第一志愿先于乙710第二志愿录取。"""
    ds = make_dataset(
        high_schools=[hs(1, "A", "A高中"), hs(2, "B", "B高中")],
        candidates=[
            cand(1, "甲", 690), cand(2, "乙", 710),
            cand(3, "丙", 700), cand(4, "丁", 720),
        ],
        plans=[plan(1, 1, 3, 2), plan(2, 2, 3, 1)],
        volunteers=[
            vol(1, 3, 1, 1),
            vol(2, 3, 1, 2), vol(2, 3, 2, 1),
            vol(3, 3, 1, 2),
            vol(4, 3, 1, 2),
        ],
    )
    result = AdmissionEngine(ds).run_all()
    assert admission_set(ds, result) == {
        ("丁", 3, "B", 1), ("甲", 3, "A", 1), ("乙", 3, "A", 2),
    }
    a_admissions = sorted(
        [a for a in result.admissions if a.plan_id == 1], key=lambda a: a.admission_order
    )
    assert [a.score for a in a_admissions] == [690, 710]
    assert min(a.score for a in a_admissions) == 690
    last = a_admissions[-1]
    assert last.score == 710 and last.volunteer_seq == 2
    assert result.plan_states[1].admitted_count == 2


def test_same_score_uses_tie_sequence():
    ds = make_dataset(
        high_schools=[hs(1, "A", "A高中")],
        candidates=[
            cand(1, "甲", 720, tie=1), cand(2, "乙", 720, tie=2),
            cand(3, "丙", 719, tie=1),
        ],
        plans=[plan(1, 1, 3, 2)],
        volunteers=[vol(1, 3, 1, 1), vol(2, 3, 1, 1), vol(3, 3, 1, 1)],
    )
    result = AdmissionEngine(ds).run_all()
    assert admission_set(ds, result) == {("甲", 3, "A", 1), ("乙", 3, "A", 1)}
    plan_admissions = sorted(result.admissions, key=lambda a: a.admission_order)
    assert [a.tie_seq for a in plan_admissions] == [1, 2]


def test_boundary_scores_enter_expected_bands():
    ds = make_dataset(
        high_schools=[hs(1, "A", "A高中")],
        candidates=[
            cand(1, "S720a", 720, tie=1), cand(2, "S720b", 720, tie=2),
            cand(3, "S719", 719), cand(4, "S680", 680),
            cand(5, "S640", 640), cand(6, "S600", 600),
            cand(7, "S599", 599),
        ],
        plans=[plan(1, 1, 3, 6)],
        volunteers=[vol(i, 3, 1, 1) for i in range(1, 8)],
    )
    result = AdmissionEngine(ds).run_all()
    admitted = {ds.candidates[a.candidate_id].candidate_no for a in result.admissions}
    assert admitted == {"S720a", "S720b", "S719", "S680", "S640", "S600"}
    assert "S599" not in admitted
    assert result.plan_states[1].admitted_count == 6
