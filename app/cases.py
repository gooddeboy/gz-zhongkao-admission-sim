"""高分滑档案例：基线 vs 仅调整高分考生志愿后的对照运行。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .engine import AdmissionEngine, BATCH_NAMES, Dataset
from .validation import validate_dataset

BASE_DIR = Path(__file__).resolve().parent.parent
CASE_PATH = BASE_DIR / "data" / "cases" / "slip_cases.json"


def load_cases(path: str | Path = CASE_PATH) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    cases = []
    for item in raw["cases"]:
        baseline = Dataset.from_dict(item["baseline"])
        adjusted = Dataset.from_dict(item["adjusted"])
        for label, ds in (("baseline", baseline), ("adjusted", adjusted)):
            issues = validate_dataset(ds)
            errors = [i for i in issues if i.level == "error"]
            if errors:
                raise ValueError(f"案例 {item['key']} {label} 数据不合法：" + "；".join(i.message for i in errors))
        cases.append({**item, "baseline_ds": baseline, "adjusted_ds": adjusted})
    return cases


def case_list() -> list[dict[str, Any]]:
    return [
        {
            "key": c["key"],
            "title": c["title"],
            "description": c["description"],
            "focus_candidate_no": c["focus_candidate_no"],
        }
        for c in load_cases()
    ]


def _candidate_map(ds: Dataset) -> dict[int, dict[str, Any]]:
    return {
        c.id: {
            "id": c.id,
            "candidate_no": c.candidate_no,
            "name": c.name,
            "score": c.score,
            "tie_seq": c.tie_seq,
            "middle_school_name": ds.middle_schools[c.middle_school_id].name,
        }
        for c in ds.candidates.values()
    }


def _scenario_summary(ds: Dataset, result) -> dict[str, Any]:
    cands = _candidate_map(ds)
    admissions = []
    for a in sorted(result.admissions, key=lambda x: (x.batch, x.plan_id, x.admission_order)):
        admissions.append(
            {
                **a.to_dict(),
                "candidate_no": cands[a.candidate_id]["candidate_no"],
                "candidate_name": cands[a.candidate_id]["name"],
                "high_school_name": ds.high_schools[a.high_school_id].name,
                "high_school_code": ds.high_schools[a.high_school_id].code,
                "middle_school_name": ds.middle_schools[a.middle_school_id].name,
                "batch_name": BATCH_NAMES[a.batch],
            }
        )

    plan_states = []
    for pid, s in sorted(result.plan_states.items()):
        p = ds.plans[pid]
        plan_states.append(
            {
                "plan_id": pid,
                "batch": p.batch,
                "batch_name": BATCH_NAMES[p.batch],
                "high_school_name": ds.high_schools[p.high_school_id].name,
                "high_school_code": ds.high_schools[p.high_school_id].code,
                "middle_school_name": (
                    ds.middle_schools[p.middle_school_id].name if p.middle_school_id else ""
                ),
                "initial_quota": s.initial_quota,
                "transferred_in": s.transferred_in,
                "transferred_out": s.transferred_out,
                "effective_quota": s.effective_quota,
                "admitted_count": s.admitted_count,
                "remaining": s.remaining,
            }
        )

    outcomes_by_candidate: dict[int, list[dict[str, Any]]] = {}
    for o in result.outcomes:
        outcomes_by_candidate.setdefault(o.candidate_id, []).append(o.to_dict())

    summaries = {}
    for cid, c in cands.items():
        rec = next((a for a in result.admissions if a.candidate_id == cid), None)
        summaries[cid] = {
            **c,
            "admitted": rec is not None,
            "admitted_batch": rec.batch if rec else None,
            "admitted_high_school_name": ds.high_schools[rec.high_school_id].name if rec else None,
            "admitted_volunteer_seq": rec.volunteer_seq if rec else None,
            "batch_results": sorted(outcomes_by_candidate.get(cid, []), key=lambda x: x["batch"]),
        }

    batch_summary = []
    for batch in (1, 2, 3, 4):
        batch_summary.append(
            {
                "batch": batch,
                "batch_name": BATCH_NAMES[batch],
                "admitted": sum(1 for a in result.admissions if a.batch == batch),
            }
        )

    return {
        "admissions": admissions,
        "plan_states": plan_states,
        "transfers": [t.to_dict() for t in result.transfers],
        "batch_summary": batch_summary,
        "candidate_summaries": summaries,
    }


def _focus_detail(ds: Dataset, summary: dict[str, Any], focus_no: str) -> dict[str, Any]:
    focus = next(c for c in summary["candidate_summaries"].values() if c["candidate_no"] == focus_no)
    volunteers = []
    for v in sorted(ds.volunteers, key=lambda x: (x.batch, x.seq)):
        if v.candidate_id != focus["id"]:
            continue
        volunteers.append(
            {
                "batch": v.batch,
                "batch_name": BATCH_NAMES[v.batch],
                "seq": v.seq,
                "high_school_id": v.high_school_id,
                "high_school_name": ds.high_schools[v.high_school_id].name,
            }
        )
    return {"candidate": focus, "volunteers": volunteers}


def _comparison(ds_base: Dataset, ds_adj: Dataset, base: dict, adj: dict) -> dict[str, Any]:
    changes = []
    for cid, b in base["candidate_summaries"].items():
        a = adj["candidate_summaries"].get(cid)
        if a is None:
            continue
        if (b["admitted"], b["admitted_batch"], b["admitted_high_school_name"]) != (
            a["admitted"], a["admitted_batch"], a["admitted_high_school_name"]
        ):
            changes.append(
                {
                    "candidate_no": b["candidate_no"],
                    "name": b["name"],
                    "score": b["score"],
                    "baseline": {
                        "admitted": b["admitted"],
                        "batch": b["admitted_batch"],
                        "high_school": b["admitted_high_school_name"],
                        "volunteer_seq": b["admitted_volunteer_seq"],
                    },
                    "adjusted": {
                        "admitted": a["admitted"],
                        "batch": a["admitted_batch"],
                        "high_school": a["admitted_high_school_name"],
                        "volunteer_seq": a["admitted_volunteer_seq"],
                    },
                }
            )
    return {"changes": changes}


def run_case(key: Optional[str] = None) -> list[dict[str, Any]]:
    results = []
    for case in load_cases():
        if key and case["key"] != key:
            continue
        base_result = AdmissionEngine(case["baseline_ds"]).run_all()
        adj_result = AdmissionEngine(case["adjusted_ds"]).run_all()
        base_summary = _scenario_summary(case["baseline_ds"], base_result)
        adj_summary = _scenario_summary(case["adjusted_ds"], adj_result)
        focus_no = case["focus_candidate_no"]
        results.append(
            {
                "key": case["key"],
                "title": case["title"],
                "description": case["description"],
                "focus_candidate_no": focus_no,
                "baseline": {
                    **base_summary,
                    "focus": _focus_detail(case["baseline_ds"], base_summary, focus_no),
                },
                "adjusted": {
                    **adj_summary,
                    "focus": _focus_detail(case["adjusted_ds"], adj_summary, focus_no),
                },
                "comparison": _comparison(case["baseline_ds"], case["adjusted_ds"], base_summary, adj_summary),
            }
        )
    if key and not results:
        raise ValueError(f"案例不存在：{key}")
    return results
