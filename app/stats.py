"""结果查询、统计与导出。"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from collections import defaultdict
from typing import Any, Optional

from .db import NotFoundError, get_meta, get_run, load_dataset
from .engine import BATCH_NAMES, Params, gradient_band, max_gradient_band


def _detail(row: sqlite3.Row) -> list[dict[str, Any]]:
    if not row["detail_json"]:
        return []
    try:
        return json.loads(row["detail_json"])
    except (TypeError, ValueError):
        return []


# ---------------------------------------------------------------------------
# 考生结果
# ---------------------------------------------------------------------------


def candidate_result(conn: sqlite3.Connection, run_id: int, candidate_id: int) -> dict[str, Any]:
    run = get_run(conn, run_id)
    c = conn.execute(
        """
        SELECT c.*, m.code AS middle_school_code, m.name AS middle_school_name
        FROM candidates c JOIN middle_schools m ON m.id = c.middle_school_id
        WHERE c.id = ?
        """,
        (candidate_id,),
    ).fetchone()
    if c is None:
        raise NotFoundError(f"考生 #{candidate_id} 不存在")
    summary = conn.execute(
        "SELECT * FROM run_candidate_summary WHERE run_id = ? AND candidate_id = ?",
        (run_id, candidate_id),
    ).fetchone()
    if summary is None:
        raise NotFoundError(f"运行 #{run_id} 中没有该考生的结果")

    batch_results = []
    for row in conn.execute(
        "SELECT * FROM run_candidate_results WHERE run_id = ? AND candidate_id = ? ORDER BY batch",
        (run_id, candidate_id),
    ):
        d = dict(row)
        d["batch_name"] = BATCH_NAMES.get(d["batch"], f"第{d['batch']}批")
        d["detail"] = _detail(row)
        d["detail_available"] = bool(row["detail_json"])
        d.pop("detail_json", None)
        batch_results.append(d)

    volunteers = []
    for row in conn.execute(
        """
        SELECT v.*, h.code AS high_school_code, h.name AS high_school_name
        FROM volunteers v JOIN high_schools h ON h.id = v.high_school_id
        WHERE v.year = ? AND v.candidate_id = ?
        ORDER BY v.batch, v.seq
        """,
        (run["year"], candidate_id),
    ):
        d = dict(row)
        d["batch_name"] = BATCH_NAMES.get(d["batch"], f"第{d['batch']}批")
        volunteers.append(d)

    admission = conn.execute(
        """
        SELECT a.*, h.code AS high_school_code, h.name AS high_school_name,
               p.category, p.control_line,
               m.code AS middle_school_code, m.name AS middle_school_name
        FROM run_admissions a
        JOIN high_schools h ON h.id = a.high_school_id
        JOIN admission_plans p ON p.id = a.plan_id
        JOIN middle_schools m ON m.id = a.middle_school_id
        WHERE a.run_id = ? AND a.candidate_id = ?
        """,
        (run_id, candidate_id),
    ).fetchone()

    return {
        "run": run,
        "candidate": dict(c),
        "summary": dict(summary),
        "batch_results": batch_results,
        "volunteers": volunteers,
        "admission": dict(admission) if admission else None,
    }


def list_run_candidates(
    conn: sqlite3.Connection, run_id: int, page: int = 1, size: int = 20, q: str = "",
    status: str = "", batch: Optional[int] = None,
) -> dict[str, Any]:
    get_run(conn, run_id)
    page = max(1, int(page or 1))
    size = min(200, max(1, int(size or 20)))
    offset = (page - 1) * size
    where = ["s.run_id = ?"]
    params: list[Any] = [run_id]
    if q:
        where.append("(c.candidate_no LIKE ? OR c.name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if status == "admitted":
        where.append("s.admitted = 1")
    elif status == "unadmitted":
        where.append("s.admitted = 0")
    if batch:
        where.append("s.admitted_batch = ?")
        params.append(int(batch))
    clause = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM run_candidate_summary s JOIN candidates c ON c.id = s.candidate_id WHERE {clause}",
        params,
    ).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT c.id, c.candidate_no, c.name, c.score, c.tie_seq,
               m.code AS middle_school_code, m.name AS middle_school_name,
               s.admitted, s.admitted_batch, s.admitted_volunteer_seq,
               s.final_reason_code, s.final_reason_text,
               h.code AS high_school_code, h.name AS high_school_name
        FROM run_candidate_summary s
        JOIN candidates c ON c.id = s.candidate_id
        JOIN middle_schools m ON m.id = c.middle_school_id
        LEFT JOIN high_schools h ON h.id = s.admitted_high_school_id
        WHERE {clause}
        ORDER BY c.id
        LIMIT ? OFFSET ?
        """,
        params + [size, offset],
    ).fetchall()
    items = []
    for row in rows:
        d = dict(row)
        d["admitted_batch_name"] = BATCH_NAMES.get(d["admitted_batch"], "") if d["admitted_batch"] else ""
        items.append(d)
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, (total + size - 1) // size),
    }


# ---------------------------------------------------------------------------
# 录取名单 / 计划余额 / 流水
# ---------------------------------------------------------------------------


def list_admissions(
    conn: sqlite3.Connection, run_id: int, page: int = 1, size: int = 50,
    batch: Optional[int] = None, high_school_id: Optional[int] = None,
    middle_school_id: Optional[int] = None, plan_id: Optional[int] = None, q: str = "",
) -> dict[str, Any]:
    get_run(conn, run_id)
    page = max(1, int(page or 1))
    size = min(500, max(1, int(size or 50)))
    offset = (page - 1) * size
    where, params = ["a.run_id = ?"], [run_id]
    if batch:
        where.append("a.batch = ?")
        params.append(int(batch))
    if high_school_id:
        where.append("a.high_school_id = ?")
        params.append(int(high_school_id))
    if middle_school_id:
        where.append("a.middle_school_id = ?")
        params.append(int(middle_school_id))
    if plan_id:
        where.append("a.plan_id = ?")
        params.append(int(plan_id))
    if q:
        where.append("(c.candidate_no LIKE ? OR c.name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    clause = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM run_admissions a JOIN candidates c ON c.id = a.candidate_id WHERE {clause}",
        params,
    ).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT a.*, c.candidate_no, c.name AS candidate_name,
               h.code AS high_school_code, h.name AS high_school_name,
               m.code AS middle_school_code, m.name AS middle_school_name,
               p.category, p.control_line
        FROM run_admissions a
        JOIN candidates c ON c.id = a.candidate_id
        JOIN high_schools h ON h.id = a.high_school_id
        JOIN middle_schools m ON m.id = a.middle_school_id
        JOIN admission_plans p ON p.id = a.plan_id
        WHERE {clause}
        ORDER BY a.batch, a.plan_id, a.admission_order
        LIMIT ? OFFSET ?
        """,
        params + [size, offset],
    ).fetchall()
    items = []
    for row in rows:
        d = dict(row)
        d["batch_name"] = BATCH_NAMES.get(d["batch"], "")
        items.append(d)
    return {
        "items": items, "total": total, "page": page, "size": size,
        "pages": max(1, (total + size - 1) // size),
    }


def _admissions_by_plan(conn: sqlite3.Connection, run_id: int) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute(
        """
        SELECT a.*, c.candidate_no, c.name AS candidate_name
        FROM run_admissions a JOIN candidates c ON c.id = a.candidate_id
        WHERE a.run_id = ? ORDER BY a.plan_id, a.admission_order
        """,
        (run_id,),
    ):
        result[row["plan_id"]].append(dict(row))
    return result


def _last_min(records: list[dict[str, Any]]) -> tuple[Optional[int], Optional[dict[str, Any]]]:
    if not records:
        return None, None
    min_score = min(r["score"] for r in records)
    last = max(records, key=lambda r: r["admission_order"])
    return min_score, {
        "candidate_id": last["candidate_id"],
        "candidate_no": last["candidate_no"],
        "name": last["candidate_name"],
        "score": last["score"],
        "volunteer_seq": last["volunteer_seq"],
        "tie_seq": last["tie_seq"],
        "admission_order": last["admission_order"],
    }


def plan_balances(
    conn: sqlite3.Connection, run_id: int, batch: Optional[int] = None,
    high_school_id: Optional[int] = None, middle_school_id: Optional[int] = None,
    page: int = 1, size: int = 100,
) -> dict[str, Any]:
    get_run(conn, run_id)
    page = max(1, int(page or 1))
    size = min(500, max(1, int(size or 100)))
    offset = (page - 1) * size
    where, params = ["s.run_id = ?"], [run_id]
    if batch:
        where.append("p.batch = ?")
        params.append(int(batch))
    if high_school_id:
        where.append("p.high_school_id = ?")
        params.append(int(high_school_id))
    if middle_school_id:
        where.append("p.middle_school_id = ?")
        params.append(int(middle_school_id))
    clause = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM run_plan_state s JOIN admission_plans p ON p.id = s.plan_id WHERE {clause}",
        params,
    ).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT s.*, p.batch, p.category, p.control_line,
               h.code AS high_school_code, h.name AS high_school_name,
               m.code AS middle_school_code, m.name AS middle_school_name
        FROM run_plan_state s
        JOIN admission_plans p ON p.id = s.plan_id
        JOIN high_schools h ON h.id = p.high_school_id
        LEFT JOIN middle_schools m ON m.id = p.middle_school_id
        WHERE {clause}
        ORDER BY p.batch, p.high_school_id, p.middle_school_id, p.id
        LIMIT ? OFFSET ?
        """,
        params + [size, offset],
    ).fetchall()
    by_plan = _admissions_by_plan(conn, run_id)
    items = []
    for row in rows:
        d = dict(row)
        d["effective_quota"] = d["initial_quota"] + d["transferred_in"]
        d["remaining"] = d["effective_quota"] - d["transferred_out"] - d["admitted_count"]
        d["completion_rate"] = (
            round(d["admitted_count"] / d["effective_quota"], 4) if d["effective_quota"] else None
        )
        min_score, last = _last_min(by_plan.get(d["plan_id"], []))
        d["min_score"] = min_score
        d["last_admitted"] = last
        d["batch_name"] = BATCH_NAMES.get(d["batch"], "")
        items.append(d)
    return {
        "items": items, "total": total, "page": page, "size": size,
        "pages": max(1, (total + size - 1) // size),
    }


def list_transfers(conn: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    get_run(conn, run_id)
    rows = conn.execute(
        """
        SELECT t.*, h.code AS high_school_code, h.name AS high_school_name,
               m.code AS middle_school_code, m.name AS middle_school_name,
               p.batch AS to_batch
        FROM run_transfers t
        JOIN high_schools h ON h.id = t.high_school_id
        LEFT JOIN middle_schools m ON m.id = t.middle_school_id
        JOIN admission_plans p ON p.id = t.to_plan_id
        WHERE t.run_id = ? ORDER BY t.id
        """,
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_events(
    conn: sqlite3.Connection, run_id: int, limit: int = 200, event_type: str = "",
    batch: Optional[int] = None,
) -> list[dict[str, Any]]:
    get_run(conn, run_id)
    limit = min(2000, max(1, int(limit or 200)))
    where, params = ["run_id = ?"], [run_id]
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)
    if batch:
        where.append("batch = ?")
        params.append(int(batch))
    rows = conn.execute(
        f"SELECT * FROM run_events WHERE {' AND '.join(where)} ORDER BY id LIMIT ?",
        params + [limit],
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["detail"] = json.loads(d["detail_json"]) if d["detail_json"] else None
        d.pop("detail_json", None)
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


def compute_stats(conn: sqlite3.Connection, run_id: int) -> dict[str, Any]:
    run = get_run(conn, run_id)
    meta = get_meta(conn)
    ds = load_dataset(conn, run["year"])
    ds.params = Params(
        year=run["year"], g1=run["g1"], delta=run["delta"],
        city_line=run["city_line"], trace_level=run["trace_level"],
    )
    params = run
    by_plan = _admissions_by_plan(conn, run_id)

    total_candidates = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    eligible = conn.execute(
        "SELECT COUNT(*) FROM candidates WHERE score >= ?", (run["city_line"],)
    ).fetchone()[0]
    admitted = conn.execute(
        "SELECT COUNT(*) FROM run_candidate_summary WHERE run_id = ? AND admitted = 1", (run_id,)
    ).fetchone()[0]
    unadmitted = total_candidates - admitted

    by_batch_rows = conn.execute(
        "SELECT batch, COUNT(*) AS count FROM run_admissions WHERE run_id = ? GROUP BY batch ORDER BY batch",
        (run_id,),
    ).fetchall()
    admitted_by_batch = {int(r["batch"]): r["count"] for r in by_batch_rows}

    plan_rows = conn.execute(
        """
        SELECT s.*, p.batch, p.category, p.high_school_id, p.middle_school_id,
               h.code AS high_school_code, h.name AS high_school_name,
               h.category AS high_category, h.intake_batch,
               m.code AS middle_school_code, m.name AS middle_school_name
        FROM run_plan_state s
        JOIN admission_plans p ON p.id = s.plan_id
        JOIN high_schools h ON h.id = p.high_school_id
        LEFT JOIN middle_schools m ON m.id = p.middle_school_id
        WHERE s.run_id = ?
        ORDER BY p.batch, p.high_school_id, p.middle_school_id, p.id
        """,
        (run_id,),
    ).fetchall()

    plan_stats: list[dict[str, Any]] = []
    for row in plan_rows:
        d = dict(row)
        d["effective_quota"] = d["initial_quota"] + d["transferred_in"]
        d["available_quota"] = d["effective_quota"] - d["transferred_out"]
        d["remaining"] = d["available_quota"] - d["admitted_count"]
        d["completion_rate"] = (
            round(d["admitted_count"] / d["effective_quota"], 4) if d["effective_quota"] else None
        )
        min_score, last = _last_min(by_plan.get(d["plan_id"], []))
        d["min_score"] = min_score
        d["last_admitted"] = last
        d["batch_name"] = BATCH_NAMES.get(d["batch"], "")
        plan_stats.append(d)

    # 高中汇总：整体 + 分批
    high_map: dict[int, dict[str, Any]] = {}
    for p in plan_stats:
        hid = p["high_school_id"]
        if hid not in high_map:
            high_map[hid] = {
                "high_school_id": hid,
                "high_school_code": p["high_school_code"],
                "high_school_name": p["high_school_name"],
                "category": p["high_category"],
                "intake_batch": p["intake_batch"],
                "total_initial": 0,
                "total_in": 0,
                "total_out": 0,
                "total_effective": 0,
                "total_admitted": 0,
                "total_remaining": 0,
                "by_batch": {},
                "admissions": [],
            }
        h = high_map[hid]
        h["total_initial"] += p["initial_quota"]
        h["total_in"] += p["transferred_in"]
        h["total_out"] += p["transferred_out"]
        h["total_admitted"] += p["admitted_count"]
        h["total_remaining"] += p["remaining"]
        b = h["by_batch"].setdefault(
            p["batch"],
            {
                "batch": p["batch"], "batch_name": p["batch_name"],
                "initial": 0, "in": 0, "out": 0, "effective": 0,
                "admitted": 0, "remaining": 0, "admissions": [],
            },
        )
        b["initial"] += p["initial_quota"]
        b["in"] += p["transferred_in"]
        b["out"] += p["transferred_out"]
        b["admitted"] += p["admitted_count"]
        b["remaining"] += p["remaining"]
        b["admissions"].extend(by_plan.get(p["plan_id"], []))
        h["admissions"].extend(by_plan.get(p["plan_id"], []))

    high_stats = []
    for h in high_map.values():
        recs = h.pop("admissions")
        min_score = min((r["score"] for r in recs), default=None)
        last = max(recs, key=lambda r: r["id"]) if recs else None
        h["min_score"] = min_score
        h["last_admitted"] = (
            {
                "candidate_id": last["candidate_id"], "candidate_no": last["candidate_no"],
                "name": last["candidate_name"], "score": last["score"],
                "batch": last["batch"], "volunteer_seq": last["volunteer_seq"],
                "tie_seq": last["tie_seq"],
            }
            if last else None
        )
        # 学校总体有效计划 = 初始 + 转入 - 转出，避免把校内结转重复计算
        h["total_effective"] = h["total_initial"] + h["total_in"] - h["total_out"]
        h["completion_rate"] = (
            round(h["total_admitted"] / h["total_effective"], 4) if h["total_effective"] else None
        )
        batches = []
        for b in sorted(h["by_batch"].values(), key=lambda x: x["batch"]):
            brecs = b.pop("admissions")
            b["effective"] = b["initial"] + b["in"] - b["out"]
            b["min_score"] = min((r["score"] for r in brecs), default=None)
            blast = max(brecs, key=lambda r: r["id"]) if brecs else None
            b["last_admitted"] = (
                {
                    "candidate_no": blast["candidate_no"], "name": blast["candidate_name"],
                    "score": blast["score"], "volunteer_seq": blast["volunteer_seq"],
                    "tie_seq": blast["tie_seq"],
                }
                if blast else None
            )
            b["completion_rate"] = round(b["admitted"] / b["effective"], 4) if b["effective"] else None
            batches.append(b)
        h["by_batch"] = batches
        high_stats.append(h)
    high_stats.sort(key=lambda x: x["high_school_id"])

    # 初中汇总：名额分配计划余额 + 该校全部录取人数
    middle_stats = []
    for m in ds.middle_schools.values():
        quota_plans = [p for p in plan_stats if p["batch"] == 2 and p["middle_school_id"] == m.id]
        admitted_from_middle = conn.execute(
            "SELECT COUNT(*) FROM run_admissions WHERE run_id = ? AND middle_school_id = ?",
            (run_id, m.id),
        ).fetchone()[0]
        middle_stats.append(
            {
                "middle_school_id": m.id,
                "middle_school_code": m.code,
                "middle_school_name": m.name,
                "district": m.district,
                "quota_plan_count": len(quota_plans),
                "quota_effective": sum(p["effective_quota"] for p in quota_plans),
                "quota_admitted": sum(p["admitted_count"] for p in quota_plans),
                "quota_remaining": sum(p["remaining"] for p in quota_plans),
                "admitted_total": admitted_from_middle,
            }
        )

    # 分数分布
    cand_rows = conn.execute(
        """
        SELECT c.score, s.admitted FROM candidates c
        JOIN run_candidate_summary s ON s.candidate_id = c.id AND s.run_id = ?
        """,
        (run_id,),
    ).fetchall()
    max_band = max_gradient_band(run["g1"], run["delta"], run["city_line"])
    band_counts = {
        b: {"band": b, "total": 0, "eligible": 0, "admitted": 0} for b in range(1, max_band + 1)
    }
    below = {"band": None, "total": 0, "eligible": 0, "admitted": 0}
    bins: dict[str, dict[str, Any]] = {}
    for r in cand_rows:
        score = r["score"]
        band = gradient_band(score, run["g1"], run["delta"], run["city_line"])
        if band is None:
            below["total"] += 1
            if r["admitted"]:
                below["admitted"] += 1
        else:
            band_counts[band]["total"] += 1
            band_counts[band]["eligible"] += 1
            if r["admitted"]:
                band_counts[band]["admitted"] += 1
        if score < 300:
            key = "<300"
        elif score >= 750:
            key = "750"
        else:
            low = (score // 20) * 20
            key = f"{low}-{low + 19}"
        b = bins.setdefault(key, {"range": key, "total": 0, "admitted": 0})
        b["total"] += 1
        if r["admitted"]:
            b["admitted"] += 1

    def band_range(b: int) -> str:
        if b == 1:
            return f"≥{run['g1']}"
        low = max(run["city_line"], run["g1"] - (b - 1) * run["delta"])
        high = run["g1"] - (b - 2) * run["delta"]
        return f"{low}-{high - 1}"

    bands = []
    for b in range(1, max_band + 1):
        row = band_counts[b]
        row["range"] = band_range(b)
        row["admission_rate"] = round(row["admitted"] / row["total"], 4) if row["total"] else 0
        bands.append(row)
    below["range"] = f"<{run['city_line']}"
    below["admission_rate"] = 0
    bands.append(below)

    reasons = [
        dict(r)
        for r in conn.execute(
            """
            SELECT final_reason_code AS code, final_reason_text AS text, COUNT(*) AS count
            FROM run_candidate_summary WHERE run_id = ? AND admitted = 0
            GROUP BY final_reason_code, final_reason_text ORDER BY count DESC
            """,
            (run_id,),
        )
    ]

    transfer_rows = conn.execute(
        "SELECT from_batch, COUNT(*) AS count, SUM(amount) AS amount FROM run_transfers "
        "WHERE run_id = ? GROUP BY from_batch ORDER BY from_batch",
        (run_id,),
    ).fetchall()
    transfers = [dict(r) for r in transfer_rows]

    total_initial = sum(p["initial_quota"] for p in plan_stats)
    total_in = sum(p["transferred_in"] for p in plan_stats)
    total_out = sum(p["transferred_out"] for p in plan_stats)
    # 全局有效计划按“初始 + 转入 - 转出”计算，避免校内结转被重复计入
    total_effective = total_initial + total_in - total_out
    total_plan_admitted = sum(p["admitted_count"] for p in plan_stats)
    total_remaining = sum(p["remaining"] for p in plan_stats)
    all_admission_scores = [
        a["score"] for recs in by_plan.values() for a in recs
    ]

    histogram = []
    for b in bins.values():
        b["admission_rate"] = round(b["admitted"] / b["total"], 4) if b["total"] else 0
        histogram.append(b)
    histogram.sort(key=lambda x: (
        0 if x["range"] == "<300" else 1,
        int(x["range"].split("-")[0]) if "-" in x["range"] else 999,
    ))

    return {
        "run": run,
        "params": {
            "year": run["year"], "g1": run["g1"], "delta": run["delta"],
            "city_line": run["city_line"], "max_band": max_band,
        },
        "dataset_version": meta["version"],
        "summary": {
            "total_candidates": total_candidates,
            "eligible_candidates": eligible,
            "admitted_candidates": admitted,
            "unadmitted_candidates": unadmitted,
            "candidate_admission_rate": round(admitted / total_candidates, 4) if total_candidates else 0,
            "plan_count": len(plan_stats),
            "total_initial": total_initial,
            "total_transferred_in": total_in,
            "total_transferred_out": total_out,
            "total_effective": total_effective,
            "total_plan_admitted": total_plan_admitted,
            "total_remaining": total_remaining,
            "plan_completion_rate": round(total_plan_admitted / total_effective, 4) if total_effective else 0,
            "min_admitted_score": min(all_admission_scores) if all_admission_scores else None,
            "admitted_by_batch": admitted_by_batch,
        },
        "plan_stats": plan_stats,
        "high_stats": high_stats,
        "middle_stats": middle_stats,
        "bands": bands,
        "histogram": histogram,
        "reasons": reasons,
        "transfers": transfers,
    }


# ---------------------------------------------------------------------------
# CSV 导出
# ---------------------------------------------------------------------------


def _csv_bytes(header: list[str], rows: list[list[Any]]) -> bytes:
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def export_csv(conn: sqlite3.Connection, run_id: int, kind: str) -> tuple[str, bytes]:
    run = get_run(conn, run_id)
    stats = compute_stats(conn, run_id)

    if kind == "admissions":
        rows = []
        for r in conn.execute(
            """
            SELECT a.*, c.candidate_no, c.name AS candidate_name,
                   h.code AS high_school_code, h.name AS high_school_name,
                   m.code AS middle_school_code, m.name AS middle_school_name,
                   p.category
            FROM run_admissions a
            JOIN candidates c ON c.id = a.candidate_id
            JOIN high_schools h ON h.id = a.high_school_id
            JOIN middle_schools m ON m.id = a.middle_school_id
            JOIN admission_plans p ON p.id = a.plan_id
            WHERE a.run_id = ? ORDER BY a.batch, a.plan_id, a.admission_order
            """,
            (run_id,),
        ):
            rows.append([
                r["batch"], BATCH_NAMES.get(r["batch"], ""), r["candidate_no"], r["candidate_name"],
                r["score"], r["tie_seq"], r["middle_school_code"], r["middle_school_name"],
                r["high_school_code"], r["high_school_name"], r["category"],
                r["plan_id"], r["volunteer_seq"], r["band"], r["admission_order"],
            ])
        return (
            f"{run['run_code']}_录取名单.csv",
            _csv_bytes(
                ["批次", "批次名称", "考生编号", "姓名", "总分", "同分序号", "初中编号", "初中",
                 "高中编号", "高中", "计划类别", "计划ID", "志愿序号", "梯度", "计划内录取顺序"],
                rows,
            ),
        )

    if kind == "plans":
        rows = []
        for p in stats["plan_stats"]:
            last = p["last_admitted"] or {}
            rows.append([
                p["batch"], p["batch_name"], p["high_school_code"], p["high_school_name"],
                p["middle_school_code"] or "", p["middle_school_name"] or "", p["category"],
                p["initial_quota"], p["transferred_in"], p["transferred_out"],
                p["effective_quota"], p["admitted_count"], p["remaining"],
                p["completion_rate"] if p["completion_rate"] is not None else "",
                p["min_score"] if p["min_score"] is not None else "无",
                last.get("candidate_no", "无"), last.get("name", ""),
                last.get("score", ""), last.get("volunteer_seq", ""), last.get("tie_seq", ""),
            ])
        return (
            f"{run['run_code']}_计划统计.csv",
            _csv_bytes(
                ["批次", "批次名称", "高中编号", "高中", "初中编号", "初中", "类别",
                 "初始计划", "转入", "转出", "有效计划", "已录取", "余额", "完成率",
                 "最低录取分", "末位考生编号", "末位考生", "末位分数", "末位志愿", "末位同分序号"],
                rows,
            ),
        )

    if kind == "candidates":
        rows = []
        for r in conn.execute(
            """
            SELECT c.candidate_no, c.name, c.score, c.tie_seq,
                   m.code AS middle_school_code, m.name AS middle_school_name,
                   s.admitted, s.admitted_batch, s.admitted_volunteer_seq,
                   h.code AS high_school_code, h.name AS high_school_name,
                   s.final_reason_code, s.final_reason_text
            FROM run_candidate_summary s
            JOIN candidates c ON c.id = s.candidate_id
            JOIN middle_schools m ON m.id = c.middle_school_id
            LEFT JOIN high_schools h ON h.id = s.admitted_high_school_id
            WHERE s.run_id = ? ORDER BY c.id
            """,
            (run_id,),
        ):
            rows.append([
                r["candidate_no"], r["name"], r["score"], r["tie_seq"],
                r["middle_school_code"], r["middle_school_name"],
                "是" if r["admitted"] else "否",
                r["admitted_batch"] or "", BATCH_NAMES.get(r["admitted_batch"], "") if r["admitted_batch"] else "",
                r["high_school_code"] or "", r["high_school_name"] or "",
                r["admitted_volunteer_seq"] or "",
                r["final_reason_code"], r["final_reason_text"],
            ])
        return (
            f"{run['run_code']}_考生录取结果.csv",
            _csv_bytes(
                ["考生编号", "姓名", "总分", "同分序号", "初中编号", "初中", "是否录取",
                 "录取批次", "批次名称", "录取高中编号", "录取高中", "录取志愿序号", "结果代码", "结果说明"],
                rows,
            ),
        )

    if kind == "high_schools":
        rows = []
        for h in stats["high_stats"]:
            last = h["last_admitted"] or {}
            rows.append([
                h["high_school_code"], h["high_school_name"], h["category"], h["intake_batch"],
                h["total_initial"], h["total_effective"], h["total_admitted"], h["total_remaining"],
                h["completion_rate"] if h["completion_rate"] is not None else "",
                h["min_score"] if h["min_score"] is not None else "无",
                last.get("candidate_no", "无"), last.get("score", ""), last.get("volunteer_seq", ""),
            ])
        return (
            f"{run['run_code']}_高中统计.csv",
            _csv_bytes(
                ["高中编号", "高中", "类型", "统招批次", "初始计划", "有效计划", "录取人数",
                 "余额", "完成率", "最低录取分", "末位考生编号", "末位分数", "末位志愿"],
                rows,
            ),
        )

    if kind == "middle_schools":
        rows = [
            [
                m["middle_school_code"], m["middle_school_name"], m["district"],
                m["quota_plan_count"], m["quota_effective"], m["quota_admitted"],
                m["quota_remaining"], m["admitted_total"],
            ]
            for m in stats["middle_stats"]
        ]
        return (
            f"{run['run_code']}_初中统计.csv",
            _csv_bytes(
                ["初中编号", "初中", "区", "名额分配计划数", "名额分配有效计划",
                 "名额分配录取", "名额分配余额", "该校全部录取人数"],
                rows,
            ),
        )

    if kind == "score_distribution":
        rows = [
            [b["range"], b["total"], b["admitted"], b["total"] - b["admitted"], b["admission_rate"]]
            for b in stats["histogram"]
        ]
        return (
            f"{run['run_code']}_分数分布.csv",
            _csv_bytes(["分数段", "考生数", "录取人数", "未录取人数", "录取率"], rows),
        )

    if kind == "reasons":
        rows = [[r["code"], r["text"], r["count"]] for r in stats["reasons"]]
        return (
            f"{run['run_code']}_未录取原因.csv",
            _csv_bytes(["原因代码", "原因说明", "人数"], rows),
        )

    raise NotFoundError(f"不支持的导出类型：{kind}")
