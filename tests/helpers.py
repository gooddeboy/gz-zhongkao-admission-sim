from __future__ import annotations

from typing import Any

from app.engine import Dataset


def make_dataset(
    *,
    g1: int = 720,
    delta: int = 40,
    city_line: int = 600,
    middle_schools: list[dict[str, Any]] | None = None,
    high_schools: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    plans: list[dict[str, Any]] | None = None,
    qualifications: list[dict[str, Any]] | None = None,
    volunteers: list[dict[str, Any]] | None = None,
) -> Dataset:
    data = {
        "params": {"year": 2026, "g1": g1, "delta": delta, "city_line": city_line, "trace_level": "full"},
        "middle_schools": middle_schools or [{"id": 1, "code": "M01", "name": "测试初中", "district": "测试区"}],
        "high_schools": high_schools or [],
        "candidates": candidates or [],
        "plans": plans or [],
        "qualifications": qualifications or [],
        "volunteers": volunteers or [],
    }
    return Dataset.from_dict(data)


def hs(
    id: int, code: str, name: str, batch: int = 3, autonomous: int = 0, total: int = 0,
    category: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "code": code,
        "name": name,
        "category": category or ("示范性" if batch == 3 else "非示范"),
        "intake_batch": batch,
        "has_autonomous": autonomous,
        "total_plan": total,
    }


def cand(id: int, no: str, score: int, middle: int = 1, tie: int = 1, name: str | None = None) -> dict[str, Any]:
    return {
        "id": id,
        "candidate_no": no,
        "name": name or f"考生{no}",
        "middle_school_id": middle,
        "score": score,
        "tie_seq": tie,
    }


def plan(
    id: int, high: int, batch: int, quota: int, middle: int | None = None, control: int = 600,
    category: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "high_school_id": high,
        "batch": batch,
        "category": category or {1: "自主招生", 2: "名额分配", 3: "统招", 4: "统招"}[batch],
        "initial_quota": quota,
        "control_line": control,
        "middle_school_id": middle,
        "note": "",
    }


def vol(candidate: int, batch: int, seq: int, high: int) -> dict[str, Any]:
    return {"candidate_id": candidate, "batch": batch, "seq": seq, "high_school_id": high}


def qual(candidate: int, high: int, rank: int | None, status: str = "qualified") -> dict[str, Any]:
    return {"candidate_id": candidate, "high_school_id": high, "status": status, "rank": rank}


def admission_set(ds: Dataset, result) -> set[tuple[str, int, str, int]]:
    return {
        (
            ds.candidates[a.candidate_id].candidate_no,
            a.batch,
            ds.high_schools[a.high_school_id].code,
            a.volunteer_seq,
        )
        for a in result.admissions
    }


def outcomes_for(result, candidate_id: int) -> dict[int, Any]:
    return {o.batch: o for o in result.outcomes if o.candidate_id == candidate_id}
