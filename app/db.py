"""SQLite 数据访问与投档运行编排。"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from .engine import (
    AdmissionEngine,
    AdmissionRecord,
    Candidate,
    Dataset,
    HighSchool,
    MiddleSchool,
    Params,
    Plan,
    PlanState,
    Qualification,
    Volunteer,
    verify_run,
)
from .snapshots import compute_input_hash, write_dataset_snapshot
from .validation import DatasetValidationError, ValidationIssue, validate_dataset

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "admission.db"
SCHEMA_PATH = BASE_DIR / "data" / "schema.sql"
SNAPSHOT_DIR = BASE_DIR / "data" / "snapshots"

RUN_STATUS_NAMES = {
    "created": "已创建",
    "batch1_done": "第一批完成",
    "batch2_done": "第二批完成",
    "batch3_done": "第三批完成",
    "completed": "已完成",
    "failed": "失败",
}


class AppError(Exception):
    """业务异常基类。"""


class NotFoundError(AppError):
    pass


class DatasetLockedError(AppError):
    pass


class RunStateError(AppError):
    pass


class DataConflictError(AppError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_run_code() -> str:
    return "R" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2).upper()


def connect(db_path: str | os.PathLike[str] = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = str(db_path)
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(conn: sqlite3.Connection, schema_path: str | os.PathLike[str] = SCHEMA_PATH) -> None:
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    # 兼容旧版本数据库：补充默认规则参数列
    columns = {row[1] for row in conn.execute("PRAGMA table_info(dataset_meta)")}
    for name, ddl in (
        ("default_g1", "INTEGER NOT NULL DEFAULT 712"),
        ("default_delta", "INTEGER NOT NULL DEFAULT 40"),
        ("default_city_line", "INTEGER NOT NULL DEFAULT 492"),
    ):
        if name not in columns:
            conn.execute(f"ALTER TABLE dataset_meta ADD COLUMN {name} {ddl}")
    conn.execute(
        """
        INSERT INTO dataset_meta (id, year, version, updated_at, locked, locked_by_run_id, input_hash, generator_seed, note)
        VALUES (1, 2026, 1, ?, 0, NULL, NULL, NULL, '')
        ON CONFLICT(id) DO NOTHING
        """,
        (now_iso(),),
    )
    conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> Optional[dict[str, Any]]:
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# 数据版本
# ---------------------------------------------------------------------------


def get_meta(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM dataset_meta WHERE id = 1").fetchone()
    if row is None:
        init_db(conn)
        row = conn.execute("SELECT * FROM dataset_meta WHERE id = 1").fetchone()
    return dict(row)


def require_unlocked(conn: sqlite3.Connection) -> dict[str, Any]:
    meta = get_meta(conn)
    if meta["locked"]:
        raise DatasetLockedError(
            f"当前数据版本已被运行 #{meta['locked_by_run_id']} 锁定，"
            "请先“创建新数据版本”后再修改输入数据"
        )
    return meta


def touch_dataset(conn: sqlite3.Connection, note: str = "") -> None:
    """输入数据变更：版本号 +1，清除旧哈希。调用方需先 require_unlocked。"""
    conn.execute(
        """
        UPDATE dataset_meta
        SET version = version + 1,
            updated_at = ?,
            input_hash = NULL,
            note = CASE WHEN ? = '' THEN note ELSE ? END
        WHERE id = 1
        """,
        (now_iso(), note, note),
    )


def unlock_dataset(conn: sqlite3.Connection) -> dict[str, Any]:
    """创建新的数据版本并解锁，历史运行保留。"""
    meta = get_meta(conn)
    with conn:
        conn.execute(
            """
            UPDATE dataset_meta
            SET version = version + 1,
                updated_at = ?,
                locked = 0,
                locked_by_run_id = NULL,
                input_hash = NULL
            WHERE id = 1
            """,
            (now_iso(),),
        )
    return get_meta(conn)


# ---------------------------------------------------------------------------
# 数据集读写
# ---------------------------------------------------------------------------


def dataset_counts(conn: sqlite3.Connection, year: Optional[int] = None) -> dict[str, int]:
    year = year or get_meta(conn)["year"]
    counts = {}
    for table in ("high_schools", "middle_schools", "candidates"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    for table in ("admission_plans", "autonomous_qualifications", "volunteers"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE year = ?", (year,)).fetchone()[0]
    return counts


def load_dataset(conn: sqlite3.Connection, year: Optional[int] = None) -> Dataset:
    meta = get_meta(conn)
    year = int(year or meta["year"])
    ds = Dataset(
        params=Params(
            year=year,
            g1=int(meta.get("default_g1", 712)),
            delta=int(meta.get("default_delta", 40)),
            city_line=int(meta.get("default_city_line", 492)),
        )
    )

    for r in conn.execute("SELECT * FROM high_schools ORDER BY id"):
        ds.high_schools[r["id"]] = HighSchool(
            id=r["id"], code=r["code"], name=r["name"], category=r["category"],
            intake_batch=r["intake_batch"], has_autonomous=bool(r["has_autonomous"]),
            total_plan=r["total_plan"], campus=r["campus"] or "",
        )
    for r in conn.execute("SELECT * FROM middle_schools ORDER BY id"):
        ds.middle_schools[r["id"]] = MiddleSchool(
            id=r["id"], code=r["code"], name=r["name"], district=r["district"] or ""
        )
    for r in conn.execute("SELECT * FROM candidates ORDER BY id"):
        ds.candidates[r["id"]] = Candidate(
            id=r["id"], candidate_no=r["candidate_no"], name=r["name"],
            middle_school_id=r["middle_school_id"], score=r["score"], tie_seq=r["tie_seq"],
        )
    for r in conn.execute("SELECT * FROM admission_plans WHERE year = ? ORDER BY id", (year,)):
        ds.plans[r["id"]] = Plan(
            id=r["id"], high_school_id=r["high_school_id"], batch=r["batch"],
            category=r["category"], initial_quota=r["initial_quota"],
            control_line=r["control_line"], middle_school_id=r["middle_school_id"],
            note=r["note"] or "",
        )
    for r in conn.execute("SELECT * FROM autonomous_qualifications WHERE year = ? ORDER BY id", (year,)):
        ds.qualifications.append(
            Qualification(
                candidate_id=r["candidate_id"], high_school_id=r["high_school_id"],
                status=r["status"], rank=r["rank"],
            )
        )
    for r in conn.execute("SELECT * FROM volunteers WHERE year = ? ORDER BY candidate_id, batch, seq", (year,)):
        ds.volunteers.append(
            Volunteer(
                candidate_id=r["candidate_id"], batch=r["batch"], seq=r["seq"],
                high_school_id=r["high_school_id"],
            )
        )
    return ds.build_indexes()


def _chunked(rows: list[tuple], size: int = 50000) -> Iterable[list[tuple]]:
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def replace_dataset(
    conn: sqlite3.Connection,
    ds: Dataset,
    seed: Optional[int] = None,
    delete_runs: bool = True,
    note: str = "",
) -> dict[str, Any]:
    """用新的数据集替换当前输入数据。

    这是破坏性操作：默认同时删除历史运行与快照，避免外键悬空。
    调用前应确认数据未锁定；界面会二次确认。
    """
    require_unlocked(conn)
    snapshot_paths: list[str] = []
    if delete_runs:
        snapshot_paths = [
            r["snapshot_path"] for r in conn.execute("SELECT snapshot_path FROM sim_runs WHERE snapshot_path IS NOT NULL")
        ]
    with conn:
        if delete_runs:
            conn.execute("DELETE FROM sim_runs")
        conn.execute("DELETE FROM volunteers")
        conn.execute("DELETE FROM autonomous_qualifications")
        conn.execute("DELETE FROM admission_plans")
        conn.execute("DELETE FROM candidates")
        conn.execute("DELETE FROM high_schools")
        conn.execute("DELETE FROM middle_schools")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN "
            "('high_schools','middle_schools','candidates','admission_plans',"
            "'autonomous_qualifications','volunteers','sim_runs','run_admissions',"
            "'run_transfers','run_events')"
        )

        hs_rows = [
            (h.id, h.code, h.name, h.category, h.intake_batch, int(h.has_autonomous), h.total_plan, h.campus)
            for h in sorted(ds.high_schools.values(), key=lambda x: x.id)
        ]
        ms_rows = [
            (m.id, m.code, m.name, m.district)
            for m in sorted(ds.middle_schools.values(), key=lambda x: x.id)
        ]
        cand_rows = [
            (c.id, c.candidate_no, c.name, c.middle_school_id, c.score, c.tie_seq)
            for c in sorted(ds.candidates.values(), key=lambda x: x.id)
        ]
        plan_rows = [
            (p.id, ds.params.year, p.high_school_id, p.batch, p.category,
             p.initial_quota, p.control_line, p.middle_school_id, p.note)
            for p in sorted(ds.plans.values(), key=lambda x: x.id)
        ]
        qual_rows = [
            (ds.params.year, q.candidate_id, q.high_school_id, q.status, q.rank)
            for q in ds.qualifications
        ]
        vol_rows = [
            (ds.params.year, v.candidate_id, v.batch, v.seq, v.high_school_id)
            for v in ds.volunteers
        ]

        conn.executemany(
            "INSERT INTO high_schools (id, code, name, category, intake_batch, has_autonomous, total_plan, campus) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", hs_rows,
        )
        conn.executemany(
            "INSERT INTO middle_schools (id, code, name, district) VALUES (?, ?, ?, ?)", ms_rows
        )
        conn.executemany(
            "INSERT INTO candidates (id, candidate_no, name, middle_school_id, score, tie_seq) "
            "VALUES (?, ?, ?, ?, ?, ?)", cand_rows,
        )
        conn.executemany(
            "INSERT INTO admission_plans (id, year, high_school_id, batch, category, initial_quota, "
            "control_line, middle_school_id, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", plan_rows,
        )
        for chunk in _chunked(qual_rows):
            conn.executemany(
                "INSERT INTO autonomous_qualifications (year, candidate_id, high_school_id, status, rank) "
                "VALUES (?, ?, ?, ?, ?)", chunk,
            )
        for chunk in _chunked(vol_rows, 100000):
            conn.executemany(
                "INSERT INTO volunteers (year, candidate_id, batch, seq, high_school_id) "
                "VALUES (?, ?, ?, ?, ?)", chunk,
            )

        conn.execute(
            """
            UPDATE dataset_meta
            SET year = ?, version = version + 1, updated_at = ?, locked = 0,
                locked_by_run_id = NULL, input_hash = NULL, generator_seed = ?,
                default_g1 = ?, default_delta = ?, default_city_line = ?, note = ?
            WHERE id = 1
            """,
            (
                ds.params.year, now_iso(), seed, ds.params.g1, ds.params.delta,
                ds.params.city_line, note,
            ),
        )

    for path in snapshot_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
    return dataset_counts(conn, ds.params.year)


# ---------------------------------------------------------------------------
# 运行创建与执行
# ---------------------------------------------------------------------------


def get_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM sim_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"运行 #{run_id} 不存在")
    data = dict(row)
    data["status_name"] = RUN_STATUS_NAMES.get(data["status"], data["status"])
    data["batch_name"] = f"第{data['current_batch']}批" if data["current_batch"] else "未开始"
    return data


def list_runs(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT r.*,
               (SELECT COUNT(*) FROM run_admissions a WHERE a.run_id = r.id) AS admitted_count
        FROM sim_runs r
        ORDER BY r.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["status_name"] = RUN_STATUS_NAMES.get(d["status"], d["status"])
        result.append(d)
    return result


def create_run(
    conn: sqlite3.Connection,
    params: Params,
    note: str = "",
    snapshot_dir: str | os.PathLike[str] = SNAPSHOT_DIR,
    parent_run_id: Optional[int] = None,
) -> dict[str, Any]:
    if params.trace_level not in ("full", "summary"):
        raise RunStateError("trace_level 必须为 full 或 summary")
    meta = get_meta(conn)
    ds = load_dataset(conn, params.year)
    ds.params = params
    issues = validate_dataset(ds)
    errors = [i for i in issues if i.level == "error"]
    if errors:
        raise DatasetValidationError(issues)

    run_code = new_run_code()
    path = os.path.join(str(snapshot_dir), f"{run_code}.json.gz")
    sha, size = write_dataset_snapshot(ds, path)
    input_sha = compute_input_hash(ds)

    if meta["input_hash"] and meta["input_hash"] != input_sha:
        try:
            os.remove(path)
        except OSError:
            pass
        raise DataConflictError(
            "当前数据与已锁定版本的快照不一致。请创建新的数据版本后重新运行。"
        )

    with conn:
        cur = conn.execute(
            """
            INSERT INTO sim_runs
                (run_code, year, g1, delta, city_line, trace_level, status, current_batch,
                 dataset_version, input_hash, snapshot_path, snapshot_sha256, parent_run_id, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'created', 0, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_code, params.year, params.g1, params.delta, params.city_line,
                params.trace_level, meta["version"], input_sha, path, sha, parent_run_id, note, now_iso(),
            ),
        )
        run_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT INTO run_plan_state (run_id, plan_id, initial_quota, transferred_in, transferred_out, admitted_count) "
            "VALUES (?, ?, ?, 0, 0, 0)",
            [(run_id, p.id, p.initial_quota) for p in ds.plans.values()],
        )
        summary_rows = [
            (run_id, c.id, 0, None, None, None, None, "NOT_STARTED", "未开始投档")
            for c in ds.candidates.values()
        ]
        for chunk in _chunked(summary_rows, 50000):
            conn.executemany(
                "INSERT INTO run_candidate_summary (run_id, candidate_id, admitted, admitted_batch, "
                "admitted_plan_id, admitted_high_school_id, admitted_volunteer_seq, "
                "final_reason_code, final_reason_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                chunk,
            )
        conn.execute(
            "INSERT INTO run_snapshots (run_id, path, sha256, size_bytes, created_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, path, sha, size, now_iso()),
        )
        conn.execute(
            """
            UPDATE dataset_meta
            SET locked = 1, locked_by_run_id = COALESCE(locked_by_run_id, ?),
                input_hash = ?, updated_at = ?
            WHERE id = 1
            """,
            (run_id, input_sha, now_iso()),
        )
    run = get_run(conn, run_id)
    run["validation"] = [i.to_dict() for i in issues]
    return run


def load_run_state(
    conn: sqlite3.Connection, run_id: int
) -> tuple[dict[int, PlanState], dict[int, AdmissionRecord], dict[int, int]]:
    states: dict[int, PlanState] = {}
    for r in conn.execute("SELECT * FROM run_plan_state WHERE run_id = ?", (run_id,)):
        states[r["plan_id"]] = PlanState(
            plan_id=r["plan_id"], initial_quota=r["initial_quota"],
            transferred_in=r["transferred_in"], transferred_out=r["transferred_out"],
            admitted_count=r["admitted_count"],
        )
    admitted: dict[int, AdmissionRecord] = {}
    plan_orders: dict[int, int] = {}
    for r in conn.execute("SELECT * FROM run_admissions WHERE run_id = ?", (run_id,)):
        rec = AdmissionRecord(
            candidate_id=r["candidate_id"], plan_id=r["plan_id"],
            high_school_id=r["high_school_id"], middle_school_id=r["middle_school_id"],
            batch=r["batch"], volunteer_seq=r["volunteer_seq"], score=r["score"],
            tie_seq=r["tie_seq"], band=r["band"], admission_order=r["admission_order"],
        )
        admitted[rec.candidate_id] = rec
        plan_orders[rec.plan_id] = max(plan_orders.get(rec.plan_id, 0), rec.admission_order)
    return states, admitted, plan_orders


def _persist_batch(
    conn: sqlite3.Connection,
    run_id: int,
    dataset: Dataset,
    result,
    trace_level: str,
) -> None:
    now = now_iso()
    with conn:
        if result.admissions:
            conn.executemany(
                """
                INSERT INTO run_admissions
                    (run_id, candidate_id, plan_id, high_school_id, middle_school_id, batch,
                     volunteer_seq, score, tie_seq, band, admission_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (run_id, a.candidate_id, a.plan_id, a.high_school_id, a.middle_school_id,
                     a.batch, a.volunteer_seq, a.score, a.tie_seq, a.band, a.admission_order, now)
                    for a in result.admissions
                ],
            )
        conn.executemany(
            "UPDATE run_plan_state SET transferred_in = ?, transferred_out = ?, admitted_count = ? "
            "WHERE run_id = ? AND plan_id = ?",
            [
                (s.transferred_in, s.transferred_out, s.admitted_count, run_id, pid)
                for pid, s in result.plan_states.items()
            ],
        )
        if result.transfers:
            conn.executemany(
                "INSERT INTO run_transfers (run_id, from_batch, from_plan_id, high_school_id, "
                "middle_school_id, amount, to_plan_id, group_key, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (run_id, t.from_batch, t.from_plan_id, t.high_school_id, t.middle_school_id,
                     t.amount, t.to_plan_id, t.group_key, now)
                    for t in result.transfers
                ],
            )
        if result.events:
            conn.executemany(
                "INSERT INTO run_events (run_id, batch, event_type, candidate_id, plan_id, volunteer_seq, "
                "band, remaining_before, remaining_after, message, detail_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id, e.get("batch"), e.get("type"), e.get("candidate_id"), e.get("plan_id"),
                        e.get("volunteer_seq"), e.get("band"), e.get("remaining_before"),
                        e.get("remaining_after"), e.get("message"),
                        json.dumps(e.get("detail"), ensure_ascii=False) if e.get("detail") is not None else None,
                        now,
                    )
                    for e in result.events
                ],
            )

        detail_json = trace_level == "full"
        conn.executemany(
            "INSERT OR REPLACE INTO run_candidate_results "
            "(run_id, candidate_id, batch, status, reason_code, reason_text, admitted_plan_id, detail_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id, o.candidate_id, o.batch, o.status, o.reason_code, o.reason_text,
                    o.admitted_plan_id,
                    json.dumps(o.detail, ensure_ascii=False) if detail_json else None,
                )
                for o in result.outcomes
            ],
        )

        admitted_rows = []
        unadmitted_rows = []
        for o in result.outcomes:
            if o.status == "ADMITTED":
                admitted_rows.append(
                    (
                        o.batch, o.admitted_plan_id,
                        dataset.plans[o.admitted_plan_id].high_school_id if o.admitted_plan_id else None,
                        next((d["seq"] for d in o.detail if d.get("code") == "ADMITTED"), None),
                        o.reason_code, o.reason_text, run_id, o.candidate_id,
                    )
                )
            else:
                unadmitted_rows.append((o.reason_code, o.reason_text, run_id, o.candidate_id))
        if admitted_rows:
            conn.executemany(
                "UPDATE run_candidate_summary SET admitted = 1, admitted_batch = ?, admitted_plan_id = ?, "
                "admitted_high_school_id = ?, admitted_volunteer_seq = ?, final_reason_code = ?, "
                "final_reason_text = ? WHERE run_id = ? AND candidate_id = ?",
                admitted_rows,
            )
        if unadmitted_rows:
            conn.executemany(
                "UPDATE run_candidate_summary SET final_reason_code = ?, final_reason_text = ? "
                "WHERE run_id = ? AND candidate_id = ? AND admitted = 0",
                unadmitted_rows,
            )

        remaining_plans = sum(1 for s in result.plan_states.values() if s.remaining > 0)
        conn.execute(
            "INSERT OR REPLACE INTO run_batch_summary "
            "(run_id, batch, processed_candidates, admitted_count, transfer_out, remaining_plans, started_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, result.batch, len(result.outcomes), len(result.admissions),
                sum(t.amount for t in result.transfers), remaining_plans, now, now,
            ),
        )
        status = "completed" if result.batch == 4 else f"batch{result.batch}_done"
        conn.execute(
            "UPDATE sim_runs SET current_batch = ?, status = ?, error_message = NULL, "
            "finished_at = CASE WHEN ? = 'completed' THEN ? ELSE finished_at END WHERE id = ?",
            (result.batch, status, status, now, run_id),
        )


def execute_batch(conn: sqlite3.Connection, run_id: int, batch: Optional[int] = None) -> dict[str, Any]:
    run = get_run(conn, run_id)
    if run["status"] in ("completed", "failed"):
        raise RunStateError(f"运行 {run['run_code']} 状态为 {run['status_name']}，不能继续执行")
    expected = run["current_batch"] + 1
    if batch is None:
        batch = expected
    if batch != expected:
        raise RunStateError(f"下一批应为第 {expected} 批，不能直接执行第 {batch} 批")

    meta = get_meta(conn)
    if meta["version"] != run["dataset_version"] or (
        meta["input_hash"] and meta["input_hash"] != run["input_hash"]
    ):
        raise DataConflictError("数据版本已变化，不能继续执行该运行。请基于新版本创建新的运行。")

    ds = load_dataset(conn, run["year"])
    ds.params = Params(
        year=run["year"], g1=run["g1"], delta=run["delta"],
        city_line=run["city_line"], trace_level=run["trace_level"],
    )
    states, admitted, plan_orders = load_run_state(conn, run_id)
    engine = AdmissionEngine(ds, admitted, states, plan_orders)
    try:
        result = engine.run_batch(batch)
        errors = verify_run(ds, engine.states, engine.admitted.values())
        if errors:
            raise RunStateError("运行一致性校验失败：" + "；".join(errors[:10]))
        _persist_batch(conn, run_id, ds, result, run["trace_level"])
    except Exception as exc:
        try:
            with conn:
                conn.execute(
                    "UPDATE sim_runs SET status = 'failed', error_message = ? WHERE id = ?",
                    (str(exc), run_id),
                )
        except Exception:
            pass
        raise

    out = get_run(conn, run_id)
    out["batch_result"] = {
        "batch": result.batch,
        "admitted_count": len(result.admissions),
        "processed_candidates": len(result.outcomes),
        "transfer_out": sum(t.amount for t in result.transfers),
        "transfers": [t.to_dict() for t in result.transfers],
        "remaining_plans": sum(1 for s in result.plan_states.values() if s.remaining > 0),
    }
    return out


def execute_all(conn: sqlite3.Connection, run_id: int) -> dict[str, Any]:
    while True:
        run = get_run(conn, run_id)
        if run["current_batch"] >= 4 or run["status"] in ("completed", "failed"):
            return run
        execute_batch(conn, run_id, run["current_batch"] + 1)


def verify_run_db(conn: sqlite3.Connection, run_id: int) -> dict[str, Any]:
    run = get_run(conn, run_id)
    ds = load_dataset(conn, run["year"])
    ds.params = Params(
        year=run["year"], g1=run["g1"], delta=run["delta"],
        city_line=run["city_line"], trace_level=run["trace_level"],
    )
    states, admitted, _ = load_run_state(conn, run_id)
    errors = verify_run(ds, states, admitted.values())
    return {"ok": not errors, "errors": errors, "run_id": run_id}


def run_progress(conn: sqlite3.Connection, run_id: int) -> dict[str, Any]:
    run = get_run(conn, run_id)
    batches = [dict(r) for r in conn.execute(
        "SELECT * FROM run_batch_summary WHERE run_id = ? ORDER BY batch", (run_id,)
    )]
    plan_batches = []
    for batch in (1, 2, 3, 4):
        row = conn.execute(
            """
            SELECT COUNT(*) AS plan_count,
                   COALESCE(SUM(s.initial_quota), 0) AS initial_total,
                   COALESCE(SUM(s.transferred_in), 0) AS in_total,
                   COALESCE(SUM(s.transferred_out), 0) AS out_total,
                   COALESCE(SUM(s.admitted_count), 0) AS admitted_total,
                   COALESCE(SUM(s.initial_quota + s.transferred_in - s.transferred_out - s.admitted_count), 0) AS remaining_total,
                   SUM(CASE WHEN s.initial_quota + s.transferred_in - s.transferred_out - s.admitted_count > 0 THEN 1 ELSE 0 END) AS underfilled_plans
            FROM run_plan_state s
            JOIN admission_plans p ON p.id = s.plan_id
            WHERE s.run_id = ? AND p.batch = ?
            """,
            (run_id, batch),
        ).fetchone()
        plan_batches.append({"batch": batch, **dict(row)})

    transfers = [dict(r) for r in conn.execute(
        "SELECT t.*, h.name AS high_school_name, m.name AS middle_school_name, "
        "p.batch AS to_batch "
        "FROM run_transfers t "
        "JOIN high_schools h ON h.id = t.high_school_id "
        "LEFT JOIN middle_schools m ON m.id = t.middle_school_id "
        "JOIN admission_plans p ON p.id = t.to_plan_id "
        "WHERE t.run_id = ? ORDER BY t.id",
        (run_id,),
    )]
    return {
        "run": run,
        "batches": batches,
        "plan_batches": plan_batches,
        "transfers": transfers,
    }
