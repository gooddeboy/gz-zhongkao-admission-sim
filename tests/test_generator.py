import json

from app.engine import AdmissionEngine, verify_run
from app.generator import generate_dataset, generate_preset, load_fixture
from app.validation import validate_dataset


def test_generated_medium_dataset_is_valid_and_runs():
    ds = generate_dataset(
        seed=42, middle_count=10, high_count=5, candidate_count=120,
        g1=712, delta=40, city_line=492,
    )
    issues = validate_dataset(ds)
    assert not [i for i in issues if i.level == "error"]
    result = AdmissionEngine(ds).run_all()
    assert verify_run(ds, result.plan_states, result.admissions) == []
    assert len(result.admissions) == len({a.candidate_id for a in result.admissions})
    assert len(result.admissions) > 0
    assert len(ds.volunteers) > 0


def test_generator_is_deterministic():
    kwargs = dict(
        seed=2026, middle_count=12, high_count=6, candidate_count=150,
        g1=712, delta=40, city_line=492,
    )
    a = generate_dataset(**kwargs)
    b = generate_dataset(**kwargs)
    assert json.dumps(a.to_dict(), ensure_ascii=False, sort_keys=True) == json.dumps(
        b.to_dict(), ensure_ascii=False, sort_keys=True
    )


def test_small_preset_is_fixture():
    ds = generate_preset("small")
    fixture = load_fixture("small_main")
    assert set(ds.candidates) == set(fixture.candidates)
    assert len(ds.plans) == len(fixture.plans)


def test_generated_plan_accounting():
    ds = generate_dataset(
        seed=7, middle_count=20, high_count=8, candidate_count=500,
        g1=712, delta=40, city_line=492,
    )
    result = AdmissionEngine(ds).run_all()
    for pid, state in result.plan_states.items():
        assert state.initial_quota >= 0
        assert state.transferred_in >= 0
        assert state.transferred_out >= 0
        assert state.admitted_count >= 0
        assert state.remaining >= 0
        assert state.initial_quota + state.transferred_in - state.transferred_out == (
            state.admitted_count + state.remaining
        )
