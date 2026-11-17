"""数据快照与输入哈希。

每次投档运行都把输入数据写成不可变的 gzip JSON 快照，并计算：
- input_hash：只对输入数据（学校、考生、计划、资格、志愿）做规范化哈希，
  不包含 G₁/Δ/L 等运行参数，因此同一数据可以用不同规则参数重复运行；
- snapshot_sha256：快照文件本身的 SHA-256，用于校验文件完整性。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from typing import Any

from .engine import Dataset


class _HashWriter:
    def __init__(self, raw) -> None:
        self.raw = raw
        self.sha = hashlib.sha256()
        self.size = 0

    def write(self, data: bytes) -> int:
        self.sha.update(data)
        self.size += len(data)
        return self.raw.write(data)

    def flush(self) -> None:
        self.raw.flush()


def _write_sections(w, ds: Dataset) -> None:
    """写入不含 params 的数据区，字段顺序固定，保证哈希可复现。"""
    sections = [
        ("high_schools", [h.to_dict() for h in sorted(ds.high_schools.values(), key=lambda x: x.id)]),
        ("middle_schools", [m.to_dict() for m in sorted(ds.middle_schools.values(), key=lambda x: x.id)]),
        ("candidates", [c.to_dict() for c in sorted(ds.candidates.values(), key=lambda x: x.id)]),
        ("plans", [p.to_dict() for p in sorted(ds.plans.values(), key=lambda x: x.id)]),
    ]
    for idx, (name, rows) in enumerate(sections):
        if idx:
            w(",")
        w(f'"{name}":[')
        for i, row in enumerate(rows):
            if i:
                w(",")
            w(json.dumps(row, ensure_ascii=False, sort_keys=True))
        w("]")

    w(',"qualifications":[')
    quals = sorted(
        ds.qualifications,
        key=lambda q: (q.high_school_id, q.rank if q.rank is not None else 10**9, q.candidate_id),
    )
    for i, q in enumerate(quals):
        if i:
            w(",")
        w(json.dumps(q.to_dict(), ensure_ascii=False, sort_keys=True))
    w("]")

    w(',"volunteers":[')
    vols = sorted(ds.volunteers, key=lambda v: (v.candidate_id, v.batch, v.seq))
    for i, v in enumerate(vols):
        if i:
            w(",")
        w(
            '{"candidate_id":%d,"batch":%d,"seq":%d,"high_school_id":%d}'
            % (v.candidate_id, v.batch, v.seq, v.high_school_id)
        )
    w("]")


def write_dataset_snapshot(ds: Dataset, path: str) -> tuple[str, int]:
    """写完整快照（含运行参数），返回 (文件 sha256, 压缩后字节数)。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
            writer = _HashWriter(gz)

            def w(text: str) -> None:
                writer.write(text.encode("utf-8"))

            w('{"params":')
            w(json.dumps(ds.params.to_dict(), ensure_ascii=False, sort_keys=True))
            w(",")
            _write_sections(w, ds)
            w("}")
            gz.flush()
            writer.flush()
    return writer.sha.hexdigest(), os.path.getsize(path)


def compute_input_hash(ds: Dataset) -> str:
    """只对输入数据做规范化哈希，不受运行参数和 trace_level 影响。"""
    h = hashlib.sha256()

    def w(text: str) -> None:
        h.update(text.encode("utf-8"))

    w("{")
    _write_sections(w, ds)
    w("}")
    return h.hexdigest()


def read_snapshot_meta(path: str) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "params": data.get("params", {}),
        "counts": {
            key: len(data.get(key, []))
            for key in (
                "high_schools", "middle_schools", "candidates",
                "plans", "qualifications", "volunteers",
            )
        },
    }
