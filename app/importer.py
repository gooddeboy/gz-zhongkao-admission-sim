"""CSV 批量导入。

导入采用“全有或全无”策略：任一行校验失败则整体回滚，并返回行号与原因。
"""

from __future__ import annotations

import csv
import io
import sqlite3
from typing import Any, Optional

from .db import AppError, get_meta, require_unlocked, touch_dataset
from .engine import VOLUNTEER_LIMITS


class CsvImportError(AppError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors[:10]))


def _reader(text: str) -> csv.DictReader:
    text = text.lstrip("\ufeff")
    return csv.DictReader(io.StringIO(text))


def _norm(fieldnames: Optional[list[str]]) -> dict[str, str]:
    return {h.strip().lower(): h for h in (fieldnames or [])}


def _val(row: dict[str, Any], mapping: dict[str, str], key: str) -> str:
    col = mapping.get(key)
    return (row.get(col) or "").strip() if col else ""


def _require_headers(mapping: dict[str, str], required: list[str]) -> None:
    missing = [h for h in required if h not in mapping]
    if missing:
        raise CsvImportError([f"缺少表头：{', '.join(missing)}"])


def _int(value: str, label: str, line: int, errors: list[str]) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"第 {line} 行：{label} 必须为整数（当前值：{value!r}）")
        return None


def import_high_schools(conn: sqlite3.Connection, text: str) -> dict[str, Any]:
    require_unlocked(conn)
    reader = _reader(text)
    mapping = _norm(reader.fieldnames)
    _require_headers(mapping, ["code", "name", "category", "intake_batch"])
    errors: list[str] = []
    rows = []
    seen = set()
    for line, row in enumerate(reader, start=2):
        code = _val(row, mapping, "code")
        name = _val(row, mapping, "name")
        category = _val(row, mapping, "category")
        intake = _int(_val(row, mapping, "intake_batch"), "统招批次", line, errors)
        has_auto = _int(_val(row, mapping, "has_autonomous") or "0", "自主招生标志", line, errors)
        total = _int(_val(row, mapping, "total_plan") or "0", "总计划", line, errors)
        if not code or not name:
            errors.append(f"第 {line} 行：编号和名称不能为空")
            continue
        if code in seen:
            errors.append(f"第 {line} 行：CSV 内高中编号重复 {code}")
            continue
        seen.add(code)
        if category not in ("示范性", "非示范"):
            errors.append(f"第 {line} 行：类型必须为示范性或非示范")
        if intake not in (3, 4):
            errors.append(f"第 {line} 行：统招批次必须为 3 或 4")
        if intake == 4 and has_auto:
            errors.append(f"第 {line} 行：第四批高中不能自主招生")
        rows.append((code, name, category, intake or 3, int(bool(has_auto)), total or 0, _val(row, mapping, "campus")))
    if not errors:
        existing = {r[0] for r in conn.execute("SELECT code FROM high_schools")}
        for i, r in enumerate(rows):
            if r[0] in existing:
                errors.append(f"高中编号已存在：{r[0]}")
    if errors:
        raise CsvImportError(errors)
    with conn:
        conn.executemany(
            "INSERT INTO high_schools (code, name, category, intake_batch, has_autonomous, total_plan, campus) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", rows,
        )
        touch_dataset(conn)
    return {"imported": len(rows)}


def import_middle_schools(conn: sqlite3.Connection, text: str) -> dict[str, Any]:
    require_unlocked(conn)
    reader = _reader(text)
    mapping = _norm(reader.fieldnames)
    _require_headers(mapping, ["code", "name"])
    errors, rows, seen = [], [], set()
    for line, row in enumerate(reader, start=2):
        code, name = _val(row, mapping, "code"), _val(row, mapping, "name")
        if not code or not name:
            errors.append(f"第 {line} 行：编号和名称不能为空")
            continue
        if code in seen:
            errors.append(f"第 {line} 行：CSV 内初中编号重复 {code}")
            continue
        seen.add(code)
        rows.append((code, name, _val(row, mapping, "district")))
    existing = {r[0] for r in conn.execute("SELECT code FROM middle_schools")}
    for r in rows:
        if r[0] in existing:
            errors.append(f"初中编号已存在：{r[0]}")
    if errors:
        raise CsvImportError(errors)
    with conn:
        conn.executemany("INSERT INTO middle_schools (code, name, district) VALUES (?, ?, ?)", rows)
        touch_dataset(conn)
    return {"imported": len(rows)}


def import_candidates(conn: sqlite3.Connection, text: str) -> dict[str, Any]:
    require_unlocked(conn)
    reader = _reader(text)
    mapping = _norm(reader.fieldnames)
    _require_headers(mapping, ["candidate_no", "name", "middle_school_code", "score", "tie_seq"])
    middle = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM middle_schools")}
    existing_no = {r[0] for r in conn.execute("SELECT candidate_no FROM candidates")}
    existing_pair = {(r[0], r[1]) for r in conn.execute("SELECT score, tie_seq FROM candidates")}
    errors, rows, seen_no, seen_pair = [], [], set(), set()
    for line, row in enumerate(reader, start=2):
        no = _val(row, mapping, "candidate_no")
        name = _val(row, mapping, "name")
        mcode = _val(row, mapping, "middle_school_code")
        score = _int(_val(row, mapping, "score"), "总分", line, errors)
        tie = _int(_val(row, mapping, "tie_seq"), "同分序号", line, errors)
        if not no or not name:
            errors.append(f"第 {line} 行：考生编号和姓名不能为空")
            continue
        if no in seen_no:
            errors.append(f"第 {line} 行：CSV 内考生编号重复 {no}")
            continue
        seen_no.add(no)
        if no in existing_no:
            errors.append(f"第 {line} 行：考生编号已存在 {no}")
        if mcode not in middle:
            errors.append(f"第 {line} 行：初中编号不存在 {mcode}")
            continue
        if score is None or tie is None:
            continue
        if not (0 <= score <= 750):
            errors.append(f"第 {line} 行：总分必须在 0-750 之间")
        if tie <= 0:
            errors.append(f"第 {line} 行：同分序号必须为正整数")
        pair = (score, tie)
        if pair in seen_pair or pair in existing_pair:
            errors.append(f"第 {line} 行：同分同序号冲突 {score}/{tie}")
        seen_pair.add(pair)
        rows.append((no, name, middle[mcode], score, tie))
    if errors:
        raise CsvImportError(errors)
    with conn:
        conn.executemany(
            "INSERT INTO candidates (candidate_no, name, middle_school_id, score, tie_seq) "
            "VALUES (?, ?, ?, ?, ?)", rows,
        )
        touch_dataset(conn)
    return {"imported": len(rows)}


def import_plans(conn: sqlite3.Connection, text: str) -> dict[str, Any]:
    require_unlocked(conn)
    reader = _reader(text)
    mapping = _norm(reader.fieldnames)
    _require_headers(mapping, ["high_school_code", "batch", "initial_quota", "control_line"])
    year = get_meta(conn)["year"]
    highs = {r["code"]: r for r in conn.execute("SELECT id, code, intake_batch, has_autonomous FROM high_schools")}
    middles = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM middle_schools")}
    errors, rows, seen = [], [], set()
    for line, row in enumerate(reader, start=2):
        hcode = _val(row, mapping, "high_school_code")
        batch = _int(_val(row, mapping, "batch"), "批次", line, errors)
        quota = _int(_val(row, mapping, "initial_quota"), "初始名额", line, errors)
        control = _int(_val(row, mapping, "control_line"), "控制线", line, errors)
        mcode = _val(row, mapping, "middle_school_code")
        h = highs.get(hcode)
        if h is None:
            errors.append(f"第 {line} 行：高中编号不存在 {hcode}")
            continue
        if batch not in (1, 2, 3, 4):
            errors.append(f"第 {line} 行：批次必须为 1-4")
            continue
        if batch == 1 and not h["has_autonomous"]:
            errors.append(f"第 {line} 行：该高中未获批自主招生")
        if batch in (2, 3) and h["intake_batch"] != 3:
            errors.append(f"第 {line} 行：该高中不在第三批招生")
        if batch == 4 and h["intake_batch"] != 4:
            errors.append(f"第 {line} 行：该高中不在第四批招生")
        mid = None
        if batch == 2:
            if not mcode:
                errors.append(f"第 {line} 行：名额分配计划必须填写初中编号")
            elif mcode not in middles:
                errors.append(f"第 {line} 行：初中编号不存在 {mcode}")
            else:
                mid = middles[mcode]
        elif mcode:
            errors.append(f"第 {line} 行：非名额分配计划不能填写初中编号")
        if quota is None or control is None:
            continue
        if quota < 0 or control < 0:
            errors.append(f"第 {line} 行：名额和控制线不能为负数")
        key = (h["id"], batch, mid)
        if key in seen:
            errors.append(f"第 {line} 行：计划重复（高中 {hcode} 批次 {batch} 初中 {mcode or '-'}）")
        seen.add(key)
        category = _val(row, mapping, "category") or {1: "自主招生", 2: "名额分配", 3: "统招", 4: "统招"}[batch]
        rows.append((year, h["id"], batch, category, quota, control, mid, _val(row, mapping, "note")))
    if errors:
        raise CsvImportError(errors)
    with conn:
        conn.executemany(
            "INSERT INTO admission_plans (year, high_school_id, batch, category, initial_quota, "
            "control_line, middle_school_id, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows,
        )
        touch_dataset(conn)
    return {"imported": len(rows)}


def import_qualifications(conn: sqlite3.Connection, text: str) -> dict[str, Any]:
    require_unlocked(conn)
    reader = _reader(text)
    mapping = _norm(reader.fieldnames)
    _require_headers(mapping, ["candidate_no", "high_school_code", "status"])
    year = get_meta(conn)["year"]
    cands = {r["candidate_no"]: r["id"] for r in conn.execute("SELECT id, candidate_no FROM candidates")}
    highs = {r["code"]: r for r in conn.execute("SELECT id, code, has_autonomous FROM high_schools")}
    existing = {(r[0], r[1]) for r in conn.execute(
        "SELECT candidate_id, high_school_id FROM autonomous_qualifications WHERE year = ?", (year,)
    )}
    existing_ranks = {(r[0], r[1]) for r in conn.execute(
        "SELECT high_school_id, rank FROM autonomous_qualifications WHERE year = ? AND rank IS NOT NULL", (year,)
    )}
    errors, rows, seen, seen_ranks = [], [], set(), set()
    for line, row in enumerate(reader, start=2):
        cno = _val(row, mapping, "candidate_no")
        hcode = _val(row, mapping, "high_school_code")
        status = _val(row, mapping, "status")
        rank_s = _val(row, mapping, "rank")
        cid, h = cands.get(cno), highs.get(hcode)
        if cid is None:
            errors.append(f"第 {line} 行：考生编号不存在 {cno}")
            continue
        if h is None:
            errors.append(f"第 {line} 行：高中编号不存在 {hcode}")
            continue
        if not h["has_autonomous"]:
            errors.append(f"第 {line} 行：该高中未获批自主招生")
        if status not in ("qualified", "disqualified"):
            errors.append(f"第 {line} 行：状态必须为 qualified 或 disqualified")
            continue
        rank = None
        if status == "qualified":
            rank = _int(rank_s, "考核排名", line, errors)
            if rank is not None and rank <= 0:
                errors.append(f"第 {line} 行：考核排名必须为正整数")
            if rank is not None:
                if (h["id"], rank) in existing_ranks or (h["id"], rank) in seen_ranks:
                    errors.append(f"第 {line} 行：高中 {hcode} 考核排名 {rank} 重复")
                seen_ranks.add((h["id"], rank))
        if (cid, h["id"]) in existing or (cid, h["id"]) in seen:
            errors.append(f"第 {line} 行：考生 {cno} 在该高中的资格记录重复")
        seen.add((cid, h["id"]))
        rows.append((year, cid, h["id"], status, rank))
    if errors:
        raise CsvImportError(errors)
    with conn:
        conn.executemany(
            "INSERT INTO autonomous_qualifications (year, candidate_id, high_school_id, status, rank) "
            "VALUES (?, ?, ?, ?, ?)", rows,
        )
        touch_dataset(conn)
    return {"imported": len(rows)}


def import_volunteers(conn: sqlite3.Connection, text: str) -> dict[str, Any]:
    require_unlocked(conn)
    reader = _reader(text)
    mapping = _norm(reader.fieldnames)
    _require_headers(mapping, ["candidate_no", "batch", "seq", "high_school_code"])
    year = get_meta(conn)["year"]
    cands = {r["candidate_no"]: r["id"] for r in conn.execute("SELECT id, candidate_no FROM candidates")}
    highs = {r["code"]: r for r in conn.execute("SELECT id, code, intake_batch, has_autonomous FROM high_schools")}
    existing = {(r[0], r[1], r[2]) for r in conn.execute(
        "SELECT candidate_id, batch, seq FROM volunteers WHERE year = ?", (year,)
    )}
    existing_high = {(r[0], r[1], r[2]) for r in conn.execute(
        "SELECT candidate_id, batch, high_school_id FROM volunteers WHERE year = ?", (year,)
    )}
    errors, rows, seen, seen_high = [], [], set(), set()
    for line, row in enumerate(reader, start=2):
        cno = _val(row, mapping, "candidate_no")
        hcode = _val(row, mapping, "high_school_code")
        batch = _int(_val(row, mapping, "batch"), "批次", line, errors)
        seq = _int(_val(row, mapping, "seq"), "志愿序号", line, errors)
        cid, h = cands.get(cno), highs.get(hcode)
        if cid is None:
            errors.append(f"第 {line} 行：考生编号不存在 {cno}")
            continue
        if h is None:
            errors.append(f"第 {line} 行：高中编号不存在 {hcode}")
            continue
        if batch not in VOLUNTEER_LIMITS:
            errors.append(f"第 {line} 行：批次必须为 1-4")
            continue
        if seq is None or not (1 <= seq <= VOLUNTEER_LIMITS[batch]):
            errors.append(f"第 {line} 行：第 {batch} 批志愿序号必须在 1-{VOLUNTEER_LIMITS[batch]} 之间")
            continue
        if batch == 1 and not h["has_autonomous"]:
            errors.append(f"第 {line} 行：该高中不参加第一批自主招生")
        if batch in (2, 3) and h["intake_batch"] != 3:
            errors.append(f"第 {line} 行：该高中不参加第三批招生")
        if batch == 4 and h["intake_batch"] != 4:
            errors.append(f"第 {line} 行：该高中不参加第四批招生")
        key = (cid, batch, seq)
        hkey = (cid, batch, h["id"])
        if key in existing or key in seen:
            errors.append(f"第 {line} 行：考生 {cno} 第 {batch} 批第 {seq} 志愿重复")
        if hkey in existing_high or hkey in seen_high:
            errors.append(f"第 {line} 行：考生 {cno} 第 {batch} 批重复填报 {hcode}")
        seen.add(key)
        seen_high.add(hkey)
        rows.append((year, cid, batch, seq, h["id"]))
    if errors:
        raise CsvImportError(errors)
    with conn:
        conn.executemany(
            "INSERT INTO volunteers (year, candidate_id, batch, seq, high_school_id) VALUES (?, ?, ?, ?, ?)", rows,
        )
        touch_dataset(conn)
    return {"imported": len(rows)}

