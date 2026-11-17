"""输入数据的查询与维护（CRUD）。

所有写操作都要求数据集未锁定；每次修改都会使数据版本号 +1，
从而使“当前数据”与历史运行的不可变快照区分开。
"""

from __future__ import annotations

import math
import sqlite3
from typing import Any, Optional

from .db import (
    AppError,
    NotFoundError,
    get_meta,
    now_iso,
    require_unlocked,
    touch_dataset,
)
from .engine import VOLUNTEER_LIMITS
from .validation import validate_dataset


def _page(page: int, size: int) -> tuple[int, int, int]:
    page = max(1, int(page or 1))
    size = min(200, max(1, int(size or 20)))
    return page, size, (page - 1) * size


def _result(items: list[dict], total: int, page: int, size: int) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)) if total else 1,
    }


def _exists(conn: sqlite3.Connection, table: str, row_id: int) -> bool:
    return conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)).fetchone() is not None


# ---------------------------------------------------------------------------
# 高中
# ---------------------------------------------------------------------------


def list_high_schools(
    conn: sqlite3.Connection, page: int = 1, size: int = 20, q: str = "",
    intake_batch: Optional[int] = None, category: str = "",
) -> dict[str, Any]:
    page, size, offset = _page(page, size)
    where, params = ["1=1"], []
    if q:
        where.append("(code LIKE ? OR name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if intake_batch:
        where.append("intake_batch = ?")
        params.append(intake_batch)
    if category:
        where.append("category = ?")
        params.append(category)
    clause = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM high_schools WHERE {clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM high_schools WHERE {clause} ORDER BY id LIMIT ? OFFSET ?",
        params + [size, offset],
    ).fetchall()
    return _result([dict(r) for r in rows], total, page, size)


def get_high_school(conn: sqlite3.Connection, high_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM high_schools WHERE id = ?", (high_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"高中 #{high_id} 不存在")
    return dict(row)


def _validate_high_school(data: dict[str, Any], high_id: Optional[int] = None) -> None:
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    if not code:
        raise AppError("高中编号不能为空")
    if not name:
        raise AppError("高中名称不能为空")
    if data.get("category") not in ("示范性", "非示范"):
        raise AppError("高中类型必须为“示范性”或“非示范”")
    intake_batch = int(data.get("intake_batch") or 0)
    if intake_batch not in (3, 4):
        raise AppError("统招接收批次必须为 3 或 4")
    has_autonomous = bool(data.get("has_autonomous"))
    if intake_batch == 4 and has_autonomous:
        raise AppError("第四批高中不能设置自主招生")
    if int(data.get("total_plan") or 0) < 0:
        raise AppError("总计划不能为负数")


def create_high_school(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    _validate_high_school(data)
    with conn:
        try:
            cur = conn.execute(
                "INSERT INTO high_schools (code, name, category, intake_batch, has_autonomous, total_plan, campus) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    data["code"].strip(), data["name"].strip(), data["category"],
                    int(data["intake_batch"]), int(bool(data.get("has_autonomous"))),
                    int(data.get("total_plan") or 0), (data.get("campus") or "").strip(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError(f"高中编号重复或数据不合法：{exc}") from exc
        touch_dataset(conn)
        new_id = int(cur.lastrowid)
    return get_high_school(conn, new_id)


def update_high_school(conn: sqlite3.Connection, high_id: int, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    get_high_school(conn, high_id)
    _validate_high_school(data, high_id)
    with conn:
        try:
            conn.execute(
                "UPDATE high_schools SET code = ?, name = ?, category = ?, intake_batch = ?, "
                "has_autonomous = ?, total_plan = ?, campus = ? WHERE id = ?",
                (
                    data["code"].strip(), data["name"].strip(), data["category"],
                    int(data["intake_batch"]), int(bool(data.get("has_autonomous"))),
                    int(data.get("total_plan") or 0), (data.get("campus") or "").strip(), high_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError(f"高中编号重复或数据不合法：{exc}") from exc
        touch_dataset(conn)
    return get_high_school(conn, high_id)


def delete_high_school(conn: sqlite3.Connection, high_id: int) -> None:
    require_unlocked(conn)
    get_high_school(conn, high_id)
    with conn:
        try:
            conn.execute("DELETE FROM high_schools WHERE id = ?", (high_id,))
        except sqlite3.IntegrityError as exc:
            raise AppError("该高中仍有关联的招生计划、志愿或历史运行结果，不能删除") from exc
        touch_dataset(conn)


# ---------------------------------------------------------------------------
# 初中
# ---------------------------------------------------------------------------


def list_middle_schools(
    conn: sqlite3.Connection, page: int = 1, size: int = 20, q: str = "",
    district: str = "",
) -> dict[str, Any]:
    page, size, offset = _page(page, size)
    where, params = ["1=1"], []
    if q:
        where.append("(code LIKE ? OR name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if district:
        where.append("district = ?")
        params.append(district)
    clause = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM middle_schools WHERE {clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM middle_schools WHERE {clause} ORDER BY id LIMIT ? OFFSET ?",
        params + [size, offset],
    ).fetchall()
    return _result([dict(r) for r in rows], total, page, size)


def get_middle_school(conn: sqlite3.Connection, middle_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM middle_schools WHERE id = ?", (middle_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"初中 #{middle_id} 不存在")
    return dict(row)


def create_middle_school(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    if not code or not name:
        raise AppError("初中编号和名称不能为空")
    with conn:
        try:
            cur = conn.execute(
                "INSERT INTO middle_schools (code, name, district) VALUES (?, ?, ?)",
                (code, name, (data.get("district") or "").strip()),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError(f"初中编号重复：{exc}") from exc
        touch_dataset(conn)
        new_id = int(cur.lastrowid)
    return get_middle_school(conn, new_id)


def update_middle_school(conn: sqlite3.Connection, middle_id: int, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    get_middle_school(conn, middle_id)
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    if not code or not name:
        raise AppError("初中编号和名称不能为空")
    with conn:
        try:
            conn.execute(
                "UPDATE middle_schools SET code = ?, name = ?, district = ? WHERE id = ?",
                (code, name, (data.get("district") or "").strip(), middle_id),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError(f"初中编号重复：{exc}") from exc
        touch_dataset(conn)
    return get_middle_school(conn, middle_id)


def delete_middle_school(conn: sqlite3.Connection, middle_id: int) -> None:
    require_unlocked(conn)
    get_middle_school(conn, middle_id)
    with conn:
        try:
            conn.execute("DELETE FROM middle_schools WHERE id = ?", (middle_id,))
        except sqlite3.IntegrityError as exc:
            raise AppError("该初中仍有关联的考生、名额分配计划或历史运行结果，不能删除") from exc
        touch_dataset(conn)


# ---------------------------------------------------------------------------
# 考生
# ---------------------------------------------------------------------------


def list_candidates(
    conn: sqlite3.Connection, page: int = 1, size: int = 20, q: str = "",
    middle_school_id: Optional[int] = None, min_score: Optional[int] = None,
    max_score: Optional[int] = None, sort: str = "id",
) -> dict[str, Any]:
    page, size, offset = _page(page, size)
    where, params = ["1=1"], []
    if q:
        where.append("(c.candidate_no LIKE ? OR c.name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if middle_school_id:
        where.append("c.middle_school_id = ?")
        params.append(middle_school_id)
    if min_score is not None:
        where.append("c.score >= ?")
        params.append(int(min_score))
    if max_score is not None:
        where.append("c.score <= ?")
        params.append(int(max_score))
    clause = " AND ".join(where)
    order = "c.id"
    if sort == "score_desc":
        order = "c.score DESC, c.tie_seq ASC"
    elif sort == "score_asc":
        order = "c.score ASC, c.tie_seq ASC"
    total = conn.execute(f"SELECT COUNT(*) FROM candidates c WHERE {clause}", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT c.*, m.code AS middle_school_code, m.name AS middle_school_name
        FROM candidates c JOIN middle_schools m ON m.id = c.middle_school_id
        WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?
        """,
        params + [size, offset],
    ).fetchall()
    return _result([dict(r) for r in rows], total, page, size)


def get_candidate(conn: sqlite3.Connection, candidate_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT c.*, m.code AS middle_school_code, m.name AS middle_school_name
        FROM candidates c JOIN middle_schools m ON m.id = c.middle_school_id
        WHERE c.id = ?
        """,
        (candidate_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"考生 #{candidate_id} 不存在")
    return dict(row)


def _validate_candidate(conn: sqlite3.Connection, data: dict[str, Any], candidate_id: Optional[int] = None) -> None:
    no = (data.get("candidate_no") or "").strip()
    name = (data.get("name") or "").strip()
    if not no or not name:
        raise AppError("考生编号和姓名不能为空")
    if not _exists(conn, "middle_schools", int(data.get("middle_school_id") or 0)):
        raise AppError("所属初中不存在")
    try:
        score = int(data["score"])
        tie_seq = int(data["tie_seq"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("总分和同分序号必须为整数") from exc
    if not (0 <= score <= 750):
        raise AppError("总分必须在 0-750 之间")
    if tie_seq <= 0:
        raise AppError("同分序号必须为正整数")
    dup = conn.execute(
        "SELECT id FROM candidates WHERE candidate_no = ? AND id <> ?",
        (no, candidate_id or -1),
    ).fetchone()
    if dup:
        raise AppError(f"考生编号 {no} 已存在")
    dup2 = conn.execute(
        "SELECT candidate_no FROM candidates WHERE score = ? AND tie_seq = ? AND id <> ?",
        (score, tie_seq, candidate_id or -1),
    ).fetchone()
    if dup2:
        raise AppError(f"同分同序号冲突：考生 {dup2['candidate_no']} 已使用 {score}/{tie_seq}")


def create_candidate(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    _validate_candidate(conn, data)
    with conn:
        cur = conn.execute(
            "INSERT INTO candidates (candidate_no, name, middle_school_id, score, tie_seq) VALUES (?, ?, ?, ?, ?)",
            (
                data["candidate_no"].strip(), data["name"].strip(),
                int(data["middle_school_id"]), int(data["score"]), int(data["tie_seq"]),
            ),
        )
        touch_dataset(conn)
        new_id = int(cur.lastrowid)
    return get_candidate(conn, new_id)


def update_candidate(conn: sqlite3.Connection, candidate_id: int, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    get_candidate(conn, candidate_id)
    _validate_candidate(conn, data, candidate_id)
    with conn:
        conn.execute(
            "UPDATE candidates SET candidate_no = ?, name = ?, middle_school_id = ?, score = ?, tie_seq = ? "
            "WHERE id = ?",
            (
                data["candidate_no"].strip(), data["name"].strip(),
                int(data["middle_school_id"]), int(data["score"]), int(data["tie_seq"]),
                candidate_id,
            ),
        )
        touch_dataset(conn)
    return get_candidate(conn, candidate_id)


def delete_candidate(conn: sqlite3.Connection, candidate_id: int) -> None:
    require_unlocked(conn)
    get_candidate(conn, candidate_id)
    with conn:
        try:
            conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
        except sqlite3.IntegrityError as exc:
            raise AppError("该考生已有历史运行结果，不能删除；请创建新的数据版本并清理历史运行") from exc
        touch_dataset(conn)


# ---------------------------------------------------------------------------
# 招生计划
# ---------------------------------------------------------------------------


def list_plans(
    conn: sqlite3.Connection, page: int = 1, size: int = 50, batch: Optional[int] = None,
    high_school_id: Optional[int] = None, middle_school_id: Optional[int] = None,
    q: str = "",
) -> dict[str, Any]:
    page, size, offset = _page(page, size)
    where, params = ["1=1"], []
    if batch:
        where.append("p.batch = ?")
        params.append(int(batch))
    if high_school_id:
        where.append("p.high_school_id = ?")
        params.append(int(high_school_id))
    if middle_school_id:
        where.append("p.middle_school_id = ?")
        params.append(int(middle_school_id))
    if q:
        where.append("(h.code LIKE ? OR h.name LIKE ? OR m.name LIKE ?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    clause = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM admission_plans p "
        f"JOIN high_schools h ON h.id = p.high_school_id "
        f"LEFT JOIN middle_schools m ON m.id = p.middle_school_id WHERE {clause}",
        params,
    ).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT p.*, h.code AS high_school_code, h.name AS high_school_name,
               h.intake_batch, h.has_autonomous,
               m.code AS middle_school_code, m.name AS middle_school_name
        FROM admission_plans p
        JOIN high_schools h ON h.id = p.high_school_id
        LEFT JOIN middle_schools m ON m.id = p.middle_school_id
        WHERE {clause}
        ORDER BY p.batch, p.high_school_id, p.middle_school_id, p.id
        LIMIT ? OFFSET ?
        """,
        params + [size, offset],
    ).fetchall()
    return _result([dict(r) for r in rows], total, page, size)


def get_plan(conn: sqlite3.Connection, plan_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT p.*, h.code AS high_school_code, h.name AS high_school_name,
               h.intake_batch, h.has_autonomous,
               m.code AS middle_school_code, m.name AS middle_school_name
        FROM admission_plans p
        JOIN high_schools h ON h.id = p.high_school_id
        LEFT JOIN middle_schools m ON m.id = p.middle_school_id
        WHERE p.id = ?
        """,
        (plan_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"招生计划 #{plan_id} 不存在")
    return dict(row)


def _validate_plan(conn: sqlite3.Connection, data: dict[str, Any], plan_id: Optional[int] = None) -> None:
    high_id = int(data.get("high_school_id") or 0)
    h = conn.execute("SELECT * FROM high_schools WHERE id = ?", (high_id,)).fetchone()
    if h is None:
        raise AppError("高中不存在")
    batch = int(data.get("batch") or 0)
    if batch not in (1, 2, 3, 4):
        raise AppError("批次必须为 1-4")
    if batch == 1 and not h["has_autonomous"]:
        raise AppError("该高中未获批自主招生，不能设置第一批计划")
    if batch in (2, 3) and h["intake_batch"] != 3:
        raise AppError("该高中不在第三批招生，不能设置第二批或第三批计划")
    if batch == 4 and h["intake_batch"] != 4:
        raise AppError("该高中不在第四批招生，不能设置第四批计划")
    try:
        quota = int(data.get("initial_quota"))
        control = int(data.get("control_line"))
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("初始名额和控制线必须为整数") from exc
    if quota < 0:
        raise AppError("初始名额不能为负数")
    if control < 0:
        raise AppError("控制线不能为负数")
    middle_id = data.get("middle_school_id")
    if batch == 2:
        if not middle_id:
            raise AppError("名额分配计划必须指定初中")
        if not _exists(conn, "middle_schools", int(middle_id)):
            raise AppError("名额分配计划指定的初中不存在")
        middle_id = int(middle_id)
    else:
        middle_id = None
    year = get_meta(conn)["year"]
    dup = conn.execute(
        "SELECT id FROM admission_plans WHERE year = ? AND high_school_id = ? AND batch = ? "
        "AND COALESCE(middle_school_id, -1) = ? AND id <> ?",
        (year, high_id, batch, middle_id if middle_id is not None else -1, plan_id or -1),
    ).fetchone()
    if dup:
        raise AppError("同一高中、批次、初中的计划已存在")


def create_plan(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    _validate_plan(conn, data)
    year = get_meta(conn)["year"]
    with conn:
        cur = conn.execute(
            "INSERT INTO admission_plans (year, high_school_id, batch, category, initial_quota, "
            "control_line, middle_school_id, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                year, int(data["high_school_id"]), int(data["batch"]),
                data.get("category") or {1: "自主招生", 2: "名额分配", 3: "统招", 4: "统招"}[int(data["batch"])],
                int(data["initial_quota"]), int(data["control_line"]),
                int(data["middle_school_id"]) if data.get("middle_school_id") else None,
                (data.get("note") or "").strip(),
            ),
        )
        touch_dataset(conn)
        new_id = int(cur.lastrowid)
    return get_plan(conn, new_id)


def update_plan(conn: sqlite3.Connection, plan_id: int, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    get_plan(conn, plan_id)
    _validate_plan(conn, data, plan_id)
    with conn:
        conn.execute(
            "UPDATE admission_plans SET high_school_id = ?, batch = ?, category = ?, initial_quota = ?, "
            "control_line = ?, middle_school_id = ?, note = ? WHERE id = ?",
            (
                int(data["high_school_id"]), int(data["batch"]),
                data.get("category") or {1: "自主招生", 2: "名额分配", 3: "统招", 4: "统招"}[int(data["batch"])],
                int(data["initial_quota"]), int(data["control_line"]),
                int(data["middle_school_id"]) if data.get("middle_school_id") else None,
                (data.get("note") or "").strip(), plan_id,
            ),
        )
        touch_dataset(conn)
    return get_plan(conn, plan_id)


def delete_plan(conn: sqlite3.Connection, plan_id: int) -> None:
    require_unlocked(conn)
    get_plan(conn, plan_id)
    with conn:
        try:
            conn.execute("DELETE FROM admission_plans WHERE id = ?", (plan_id,))
        except sqlite3.IntegrityError as exc:
            raise AppError("该计划已有历史运行结果，不能删除；请创建新的数据版本并清理历史运行") from exc
        touch_dataset(conn)


# ---------------------------------------------------------------------------
# 自主招生资格
# ---------------------------------------------------------------------------


def list_qualifications(
    conn: sqlite3.Connection, page: int = 1, size: int = 50, high_school_id: Optional[int] = None,
    status: str = "", q: str = "",
) -> dict[str, Any]:
    page, size, offset = _page(page, size)
    where, params = ["1=1"], []
    if high_school_id:
        where.append("q.high_school_id = ?")
        params.append(int(high_school_id))
    if status:
        where.append("q.status = ?")
        params.append(status)
    if q:
        where.append("(c.candidate_no LIKE ? OR c.name LIKE ? OR h.name LIKE ?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    clause = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM autonomous_qualifications q "
        f"JOIN candidates c ON c.id = q.candidate_id "
        f"JOIN high_schools h ON h.id = q.high_school_id WHERE {clause}",
        params,
    ).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT q.*, c.candidate_no, c.name AS candidate_name, c.score,
               h.code AS high_school_code, h.name AS high_school_name
        FROM autonomous_qualifications q
        JOIN candidates c ON c.id = q.candidate_id
        JOIN high_schools h ON h.id = q.high_school_id
        WHERE {clause}
        ORDER BY q.high_school_id, q.rank, q.id
        LIMIT ? OFFSET ?
        """,
        params + [size, offset],
    ).fetchall()
    return _result([dict(r) for r in rows], total, page, size)


def get_qualification(conn: sqlite3.Connection, qual_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT q.*, c.candidate_no, c.name AS candidate_name, c.score,
               h.code AS high_school_code, h.name AS high_school_name
        FROM autonomous_qualifications q
        JOIN candidates c ON c.id = q.candidate_id
        JOIN high_schools h ON h.id = q.high_school_id
        WHERE q.id = ?
        """,
        (qual_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"资格记录 #{qual_id} 不存在")
    return dict(row)


def _validate_qualification(conn: sqlite3.Connection, data: dict[str, Any], qual_id: Optional[int] = None) -> None:
    cid = int(data.get("candidate_id") or 0)
    hid = int(data.get("high_school_id") or 0)
    if not _exists(conn, "candidates", cid):
        raise AppError("考生不存在")
    h = conn.execute("SELECT * FROM high_schools WHERE id = ?", (hid,)).fetchone()
    if h is None:
        raise AppError("高中不存在")
    if not h["has_autonomous"]:
        raise AppError("该高中未获批自主招生，不能设置资格名单")
    status = data.get("status")
    if status not in ("qualified", "disqualified"):
        raise AppError("资格状态必须为 qualified 或 disqualified")
    rank = data.get("rank")
    if status == "qualified":
        try:
            rank = int(rank)
        except (TypeError, ValueError) as exc:
            raise AppError("已获资格考生必须填写考核排名") from exc
        if rank <= 0:
            raise AppError("考核排名必须为正整数")
    else:
        rank = None
    year = get_meta(conn)["year"]
    dup = conn.execute(
        "SELECT id FROM autonomous_qualifications WHERE year = ? AND candidate_id = ? AND high_school_id = ? AND id <> ?",
        (year, cid, hid, qual_id or -1),
    ).fetchone()
    if dup:
        raise AppError("该考生在该高中的资格记录已存在")
    if rank is not None:
        dup_rank = conn.execute(
            "SELECT c.candidate_no FROM autonomous_qualifications q JOIN candidates c ON c.id = q.candidate_id "
            "WHERE q.year = ? AND q.high_school_id = ? AND q.rank = ? AND q.id <> ?",
            (year, hid, rank, qual_id or -1),
        ).fetchone()
        if dup_rank:
            raise AppError(f"考核排名 {rank} 已被考生 {dup_rank['candidate_no']} 使用")


def create_qualification(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    _validate_qualification(conn, data)
    year = get_meta(conn)["year"]
    with conn:
        cur = conn.execute(
            "INSERT INTO autonomous_qualifications (year, candidate_id, high_school_id, status, rank) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                year, int(data["candidate_id"]), int(data["high_school_id"]),
                data["status"], int(data["rank"]) if data.get("status") == "qualified" else None,
            ),
        )
        touch_dataset(conn)
        new_id = int(cur.lastrowid)
    return get_qualification(conn, new_id)


def update_qualification(conn: sqlite3.Connection, qual_id: int, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    get_qualification(conn, qual_id)
    _validate_qualification(conn, data, qual_id)
    with conn:
        conn.execute(
            "UPDATE autonomous_qualifications SET candidate_id = ?, high_school_id = ?, status = ?, rank = ? WHERE id = ?",
            (
                int(data["candidate_id"]), int(data["high_school_id"]), data["status"],
                int(data["rank"]) if data.get("status") == "qualified" else None, qual_id,
            ),
        )
        touch_dataset(conn)
    return get_qualification(conn, qual_id)


def delete_qualification(conn: sqlite3.Connection, qual_id: int) -> None:
    require_unlocked(conn)
    get_qualification(conn, qual_id)
    with conn:
        conn.execute("DELETE FROM autonomous_qualifications WHERE id = ?", (qual_id,))
        touch_dataset(conn)


# ---------------------------------------------------------------------------
# 志愿
# ---------------------------------------------------------------------------


def list_volunteers(
    conn: sqlite3.Connection, page: int = 1, size: int = 50, candidate_id: Optional[int] = None,
    batch: Optional[int] = None, high_school_id: Optional[int] = None, q: str = "",
) -> dict[str, Any]:
    page, size, offset = _page(page, size)
    where, params = ["1=1"], []
    if candidate_id:
        where.append("v.candidate_id = ?")
        params.append(int(candidate_id))
    if batch:
        where.append("v.batch = ?")
        params.append(int(batch))
    if high_school_id:
        where.append("v.high_school_id = ?")
        params.append(int(high_school_id))
    if q:
        where.append("(c.candidate_no LIKE ? OR c.name LIKE ? OR h.name LIKE ?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    clause = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM volunteers v "
        f"JOIN candidates c ON c.id = v.candidate_id "
        f"JOIN high_schools h ON h.id = v.high_school_id WHERE {clause}",
        params,
    ).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT v.*, c.candidate_no, c.name AS candidate_name, c.score,
               h.code AS high_school_code, h.name AS high_school_name
        FROM volunteers v
        JOIN candidates c ON c.id = v.candidate_id
        JOIN high_schools h ON h.id = v.high_school_id
        WHERE {clause}
        ORDER BY v.candidate_id, v.batch, v.seq
        LIMIT ? OFFSET ?
        """,
        params + [size, offset],
    ).fetchall()
    return _result([dict(r) for r in rows], total, page, size)


def get_volunteer(conn: sqlite3.Connection, vol_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT v.*, c.candidate_no, c.name AS candidate_name, c.score,
               h.code AS high_school_code, h.name AS high_school_name
        FROM volunteers v
        JOIN candidates c ON c.id = v.candidate_id
        JOIN high_schools h ON h.id = v.high_school_id
        WHERE v.id = ?
        """,
        (vol_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"志愿 #{vol_id} 不存在")
    return dict(row)


def _validate_volunteer(conn: sqlite3.Connection, data: dict[str, Any], vol_id: Optional[int] = None) -> None:
    cid = int(data.get("candidate_id") or 0)
    hid = int(data.get("high_school_id") or 0)
    c = conn.execute("SELECT * FROM candidates WHERE id = ?", (cid,)).fetchone()
    if c is None:
        raise AppError("考生不存在")
    h = conn.execute("SELECT * FROM high_schools WHERE id = ?", (hid,)).fetchone()
    if h is None:
        raise AppError("高中不存在")
    try:
        batch = int(data.get("batch"))
        seq = int(data.get("seq"))
    except (TypeError, ValueError) as exc:
        raise AppError("批次和志愿序号必须为整数") from exc
    if batch not in VOLUNTEER_LIMITS:
        raise AppError("批次必须为 1-4")
    if not (1 <= seq <= VOLUNTEER_LIMITS[batch]):
        raise AppError(f"第 {batch} 批志愿序号必须在 1-{VOLUNTEER_LIMITS[batch]} 之间")
    if batch == 1 and not h["has_autonomous"]:
        raise AppError("该高中不参加第一批自主招生")
    if batch in (2, 3) and h["intake_batch"] != 3:
        raise AppError("该高中不参加第三批招生")
    if batch == 4 and h["intake_batch"] != 4:
        raise AppError("该高中不参加第四批招生")
    year = get_meta(conn)["year"]
    dup_seq = conn.execute(
        "SELECT id FROM volunteers WHERE year = ? AND candidate_id = ? AND batch = ? AND seq = ? AND id <> ?",
        (year, cid, batch, seq, vol_id or -1),
    ).fetchone()
    if dup_seq:
        raise AppError(f"该考生第 {batch} 批第 {seq} 志愿已存在")
    dup_high = conn.execute(
        "SELECT id FROM volunteers WHERE year = ? AND candidate_id = ? AND batch = ? AND high_school_id = ? AND id <> ?",
        (year, cid, batch, hid, vol_id or -1),
    ).fetchone()
    if dup_high:
        raise AppError(f"该考生第 {batch} 批已填报过该高中")


def create_volunteer(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    _validate_volunteer(conn, data)
    year = get_meta(conn)["year"]
    with conn:
        cur = conn.execute(
            "INSERT INTO volunteers (year, candidate_id, batch, seq, high_school_id) VALUES (?, ?, ?, ?, ?)",
            (year, int(data["candidate_id"]), int(data["batch"]), int(data["seq"]), int(data["high_school_id"])),
        )
        touch_dataset(conn)
        new_id = int(cur.lastrowid)
    return get_volunteer(conn, new_id)


def update_volunteer(conn: sqlite3.Connection, vol_id: int, data: dict[str, Any]) -> dict[str, Any]:
    require_unlocked(conn)
    get_volunteer(conn, vol_id)
    _validate_volunteer(conn, data, vol_id)
    with conn:
        conn.execute(
            "UPDATE volunteers SET candidate_id = ?, batch = ?, seq = ?, high_school_id = ? WHERE id = ?",
            (
                int(data["candidate_id"]), int(data["batch"]), int(data["seq"]),
                int(data["high_school_id"]), vol_id,
            ),
        )
        touch_dataset(conn)
    return get_volunteer(conn, vol_id)


def delete_volunteer(conn: sqlite3.Connection, vol_id: int) -> None:
    require_unlocked(conn)
    get_volunteer(conn, vol_id)
    with conn:
        conn.execute("DELETE FROM volunteers WHERE id = ?", (vol_id,))
        touch_dataset(conn)


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def validate_current(conn: sqlite3.Connection) -> dict[str, Any]:
    from .db import load_dataset

    ds = load_dataset(conn)
    issues = validate_dataset(ds)
    return {
        "ok": not any(i.level == "error" for i in issues),
        "errors": [i.to_dict() for i in issues if i.level == "error"],
        "warnings": [i.to_dict() for i in issues if i.level == "warning"],
    }
