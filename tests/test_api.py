import json

import pytest

from app.db import RunStateError, connect, execute_batch


def _create_run(client, trace_level="full"):
    res = client.post(
        "/api/runs",
        json={"g1": 720, "delta": 40, "city_line": 600, "trace_level": trace_level, "note": "pytest"},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_generate_small_and_meta(small_client):
    meta = small_client.get("/api/meta").json()
    assert meta["counts"]["candidates"] == 17
    assert meta["counts"]["high_schools"] == 4
    assert meta["defaults"] == {"year": 2026, "g1": 720, "delta": 40, "city_line": 600}
    assert meta["bands"][0]["range"] == "总分 ≥ 720"


def test_stepwise_run_progress_verify_stats_and_exports(small_client):
    run = _create_run(small_client)
    run_id = run["id"]
    assert run["status"] == "created"
    assert run["snapshot_path"]

    statuses = []
    for _ in range(4):
        res = small_client.post(f"/api/runs/{run_id}/execute-next")
        assert res.status_code == 200, res.text
        statuses.append(res.json()["status"])
    assert statuses == ["batch1_done", "batch2_done", "batch3_done", "completed"]

    verify = small_client.get(f"/api/runs/{run_id}/verify").json()
    assert verify["ok"] is True

    progress = small_client.get(f"/api/runs/{run_id}/progress").json()
    assert progress["run"]["status"] == "completed"
    assert [b["admitted_count"] for b in progress["batches"]] == [3, 5, 6, 2]
    assert len(progress["transfers"]) == 2

    stats = small_client.get(f"/api/runs/{run_id}/stats").json()
    assert stats["summary"]["admitted_candidates"] == 16
    assert stats["summary"]["unadmitted_candidates"] == 1
    assert stats["summary"]["total_initial"] == 18
    assert stats["summary"]["total_transferred_in"] == 2
    assert stats["summary"]["total_transferred_out"] == 2
    assert stats["summary"]["total_effective"] == 18
    assert stats["summary"]["plan_completion_rate"] == pytest.approx(16 / 18, abs=1e-4)
    high = {h["high_school_code"]: h for h in stats["high_stats"]}
    assert high["G02"]["total_effective"] == 8
    assert high["G02"]["completion_rate"] == 1.0
    assert high["G04"]["completion_rate"] == 0.5
    plan = {p["plan_id"]: p for p in stats["plan_stats"]}
    assert plan[8]["min_score"] == 640
    assert plan[8]["last_admitted"]["candidate_no"] == "C12"
    assert plan[8]["last_admitted"]["score"] == 660
    assert plan[8]["last_admitted"]["volunteer_seq"] == 2

    for kind in (
        "admissions", "plans", "candidates", "high_schools",
        "middle_schools", "score_distribution", "reasons",
    ):
        res = small_client.get(f"/api/runs/{run_id}/export/{kind}")
        assert res.status_code == 200, kind
        assert res.content.startswith(b"\xef\xbb\xbf")

    snapshot = small_client.get(f"/api/runs/{run_id}/snapshot")
    assert snapshot.status_code == 200
    assert snapshot.content.startswith(b"\x1f\x8b")


def test_run_repeatable_and_independent(small_client, completed_run):
    first = small_client.get(f"/api/runs/{completed_run}/admissions?size=500").json()
    second_run = _create_run(small_client, trace_level="summary")
    assert second_run["id"] != completed_run
    res = small_client.post(f"/api/runs/{second_run['id']}/execute-all")
    assert res.status_code == 200, res.text
    second = small_client.get(f"/api/runs/{second_run['id']}/admissions?size=500").json()

    def key(items):
        return {
            (a["candidate_no"], a["batch"], a["high_school_code"], a["volunteer_seq"])
            for a in items["items"]
        }

    assert key(first) == key(second)
    assert first["total"] == second["total"] == 16
    assert small_client.get(f"/api/runs/{completed_run}/verify").json()["ok"] is True
    assert small_client.get(f"/api/runs/{second_run['id']}/verify").json()["ok"] is True


def test_locked_data_cannot_be_edited_until_new_version(small_client, completed_run):
    payload = {
        "code": "G901", "name": "测试新增高中", "category": "示范性",
        "intake_batch": 3, "has_autonomous": False, "total_plan": 0,
    }
    res = small_client.post("/api/high-schools", json=payload)
    assert res.status_code == 409
    assert res.json()["code"] == "DATASET_LOCKED"

    before = small_client.get("/api/meta").json()["meta"]["version"]
    unlock = small_client.post("/api/dataset/unlock", json={"confirm": True})
    assert unlock.status_code == 200
    after = small_client.get("/api/meta").json()["meta"]["version"]
    assert after == before + 1

    res = small_client.post("/api/high-schools", json=payload)
    assert res.status_code == 200, res.text
    assert res.json()["code"] == "G901"
    # 历史运行仍可查询，且不受新版本输入影响
    assert small_client.get(f"/api/runs/{completed_run}/stats").json()["summary"]["admitted_candidates"] == 16


def test_candidate_explanations(small_client, completed_run):
    c15 = small_client.get(f"/api/runs/{completed_run}/candidate/15").json()
    assert c15["summary"]["admitted"] == 0
    assert c15["summary"]["final_reason_code"] == "BELOW_CITY_LINE"
    assert "低于" in c15["summary"]["final_reason_text"]

    c07 = small_client.get(f"/api/runs/{completed_run}/candidate/7").json()
    batch3 = next(b for b in c07["batch_results"] if b["batch"] == 3)
    assert batch3["status"] == "ADMITTED"
    assert batch3["detail"][0]["code"] in ("OUTRANKED", "PLAN_FULL")

    c01 = small_client.get(f"/api/runs/{completed_run}/candidate/1").json()
    assert c01["summary"]["admitted"] == 1
    assert c01["summary"]["admitted_batch"] == 1
    assert c01["admission"]["high_school_code"] == "G01"
    assert c01["admission"]["volunteer_seq"] == 1


def test_invalid_import_rolls_back(small_client):
    before = small_client.get("/api/meta").json()["counts"]["candidates"]
    csv = "candidate_no,name,middle_school_code,score,tie_seq\nC01,重复考生,M01,700,9\n"
    res = small_client.post("/api/import/candidates", json={"csv": csv})
    assert res.status_code == 400
    assert res.json()["code"] == "IMPORT_ERROR"
    after = small_client.get("/api/meta").json()["counts"]["candidates"]
    assert after == before

    csv2 = "candidate_no,name,middle_school_code,score,tie_seq\nC999,非法分数,M01,999,1\n"
    res = small_client.post("/api/import/candidates", json={"csv": csv2})
    assert res.status_code == 400


def test_validation_endpoint(small_client):
    res = small_client.get("/api/validate").json()
    assert res["ok"] is True
    assert any(w["code"] == "CAND_BELOW_CITY" for w in res["warnings"])


def test_execute_after_completed_is_rejected(small_client):
    run = _create_run(small_client)
    small_client.post(f"/api/runs/{run['id']}/execute-all")
    res = small_client.post(f"/api/runs/{run['id']}/execute-next")
    assert res.status_code == 409


def test_same_batch_cannot_be_executed_twice(small_client):
    run = _create_run(small_client)
    assert small_client.post(f"/api/runs/{run['id']}/execute-next").status_code == 200
    conn = connect(small_client.app.state.db_path)
    try:
        with pytest.raises(RunStateError):
            execute_batch(conn, run["id"], 1)
    finally:
        conn.close()


def test_import_valid_high_school(client):
    csv = (
        "code,name,category,intake_batch,has_autonomous,total_plan,campus\n"
        "G901,测试示范高中,示范性,3,1,400,\n"
    )
    res = client.post("/api/import/high-schools", json={"csv": csv})
    assert res.status_code == 200, res.text
    assert res.json()["imported"] == 1
    assert client.get("/api/meta").json()["counts"]["high_schools"] == 1


def test_create_run_rejects_invalid_data(small_client):
    conn = connect(small_client.app.state.db_path)
    try:
        conn.execute("UPDATE admission_plans SET control_line = 500 WHERE id = 1")
        conn.commit()
    finally:
        conn.close()
    res = small_client.post(
        "/api/runs",
        json={"g1": 720, "delta": 40, "city_line": 600, "trace_level": "full"},
    )
    assert res.status_code == 400
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert any(i["code"] == "PLAN_CONTROL" for i in body["issues"])

