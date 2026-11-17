from app.cases import case_list, run_case


def test_case_list():
    cases = case_list()
    assert {c["key"] for c in cases} == {"batch_slip", "all_batches_slip"}


def test_batch_slip_case_baseline_and_adjusted():
    result = run_case("batch_slip")[0]
    base_focus = result["baseline"]["focus"]["candidate"]
    adj_focus = result["adjusted"]["focus"]["candidate"]
    assert base_focus["admitted"] is True
    assert base_focus["admitted_batch"] == 4
    assert base_focus["admitted_high_school_name"] == "海珠非示范高中"
    assert adj_focus["admitted"] is True
    assert adj_focus["admitted_batch"] == 3
    assert adj_focus["admitted_high_school_name"] == "广雅示范高中"

    base_batch3 = next(b for b in base_focus["batch_results"] if b["batch"] == 3)
    assert base_batch3["status"] == "NOT_ADMITTED"
    assert base_batch3["reason_code"] == "PLAN_FULL"

    changes = {c["candidate_no"]: c for c in result["comparison"]["changes"]}
    assert changes["C1"]["baseline"]["batch"] == 4
    assert changes["C1"]["adjusted"]["batch"] == 3
    assert changes["C2"]["baseline"]["admitted"] is True
    assert changes["C2"]["adjusted"]["admitted"] is False
    assert changes["C5"]["baseline"]["admitted"] is False
    assert changes["C5"]["adjusted"]["admitted"] is True


def test_all_batches_slip_case_baseline_and_adjusted():
    result = run_case("all_batches_slip")[0]
    base_focus = result["baseline"]["focus"]["candidate"]
    adj_focus = result["adjusted"]["focus"]["candidate"]
    assert base_focus["admitted"] is False
    assert adj_focus["admitted"] is True
    assert adj_focus["admitted_batch"] == 4
    assert adj_focus["admitted_high_school_name"] == "海珠非示范高中"

    changes = {c["candidate_no"]: c for c in result["comparison"]["changes"]}
    assert changes["C1"]["baseline"]["admitted"] is False
    assert changes["C1"]["adjusted"]["admitted"] is True
    assert changes["C4"]["baseline"]["admitted"] is True
    assert changes["C4"]["adjusted"]["admitted"] is False


def test_case_volunteers_only_focus_changes():
    result = run_case("batch_slip")[0]
    base_vols = result["baseline"]["focus"]["volunteers"]
    adj_vols = result["adjusted"]["focus"]["volunteers"]
    assert base_vols != adj_vols
    # 其他考生的数据与志愿在案例文件中保持一致，由 comparison 的挤出效应验证
    assert result["comparison"]["changes"]
