import pytest

from app.engine import Dataset, Plan, Qualification, Volunteer
from app.generator import load_fixture
from app.validation import DatasetValidationError, validate_dataset


@pytest.fixture()
def ds():
    return Dataset.from_dict(load_fixture("small_main").to_dict())


def codes(issues):
    return {i.code for i in issues}


def test_small_dataset_is_valid(ds):
    issues = validate_dataset(ds)
    assert not [i for i in issues if i.level == "error"]


def test_duplicate_candidate_number(ds):
    ds.candidates[2].candidate_no = ds.candidates[1].candidate_no
    assert "CAND_NO_DUP" in codes(validate_dataset(ds))


def test_invalid_score(ds):
    ds.candidates[1].score = 800
    assert "CAND_SCORE" in codes(validate_dataset(ds))


def test_duplicate_score_and_tie(ds):
    ds.candidates[2].score = ds.candidates[1].score
    ds.candidates[2].tie_seq = ds.candidates[1].tie_seq
    assert "CAND_TIE_DUP" in codes(validate_dataset(ds))


def test_duplicate_volunteer_sequence(ds):
    ds.volunteers.append(Volunteer(candidate_id=1, batch=1, seq=1, high_school_id=1))
    assert "VOL_SEQ_DUP" in codes(validate_dataset(ds))


def test_duplicate_high_school_in_same_batch(ds):
    ds.volunteers.append(Volunteer(candidate_id=4, batch=2, seq=3, high_school_id=1))
    assert "VOL_HS_DUP" in codes(validate_dataset(ds))


def test_invalid_plan_batch_for_school(ds):
    ds.plans[99] = Plan(
        id=99, high_school_id=4, batch=3, category="统招",
        initial_quota=1, control_line=600, middle_school_id=None,
    )
    assert "PLAN_INTAKE" in codes(validate_dataset(ds))


def test_duplicate_qualification_rank(ds):
    ds.qualifications.append(
        Qualification(candidate_id=2, high_school_id=1, status="qualified", rank=1)
    )
    assert "QUAL_RANK_DUP" in codes(validate_dataset(ds))


def test_plan_control_line_below_city_line(ds):
    ds.plans[1].control_line = 599
    assert "PLAN_CONTROL" in codes(validate_dataset(ds))


def test_batch2_plan_requires_middle_school(ds):
    ds.plans[2].middle_school_id = None
    assert "PLAN_MS" in codes(validate_dataset(ds))


def test_below_city_line_is_warning_not_error(ds):
    issues = validate_dataset(ds)
    below = [i for i in issues if i.code == "CAND_BELOW_CITY"]
    assert below and below[0].level == "warning"


def test_raise_on_error(ds):
    ds.candidates[1].score = 999
    with pytest.raises(DatasetValidationError):
        validate_dataset(ds, raise_on_error=True)
