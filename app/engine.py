"""核心投档引擎。

实现任务书规定的四个批次：
1. 第一批 自主招生：资格名单 + 考核排名 + 计划控制线；
2. 第二批 名额分配：按（高中, 初中）分计划，校内竞争；
3. 第三批 统招：全市按梯度、志愿轮次投档；
4. 第四批 统招：规则同第三批。

关键规则：
- 严格按批次顺序执行，前批录取者退出后续批次；
- 同一批次内先处理高梯度，再处理低梯度；
- 同一梯度内先处理第一志愿，再处理第二志愿，依次类推；
- 同一计划、同一轮次内按总分降序、同分序号升序录取；
- 第二批只能在考生所属初中获得的名额内竞争；
- 第一批、第二批剩余名额各结转一次到第三批，第三、四批余缺不互转。
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

BATCH_NAMES = {
    1: "第一批（自主招生）",
    2: "第二批（名额分配）",
    3: "第三批（统招）",
    4: "第四批（统招）",
}

VOLUNTEER_LIMITS = {1: 1, 2: 3, 3: 6, 4: 6}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Params:
    year: int = 2026
    g1: int = 720
    delta: int = 40
    city_line: int = 600
    trace_level: str = "full"  # full | summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "g1": self.g1,
            "delta": self.delta,
            "city_line": self.city_line,
            "trace_level": self.trace_level,
        }


@dataclass(slots=True)
class HighSchool:
    id: int
    code: str
    name: str
    category: str  # 示范性 | 非示范
    intake_batch: int  # 3 | 4
    has_autonomous: bool
    total_plan: int = 0
    campus: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "category": self.category,
            "intake_batch": self.intake_batch,
            "has_autonomous": int(self.has_autonomous),
            "total_plan": self.total_plan,
            "campus": self.campus,
        }


@dataclass(slots=True)
class MiddleSchool:
    id: int
    code: str
    name: str
    district: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "district": self.district,
        }


@dataclass(slots=True)
class Candidate:
    id: int
    candidate_no: str
    name: str
    middle_school_id: int
    score: int
    tie_seq: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "candidate_no": self.candidate_no,
            "name": self.name,
            "middle_school_id": self.middle_school_id,
            "score": self.score,
            "tie_seq": self.tie_seq,
        }


@dataclass(slots=True)
class Plan:
    id: int
    high_school_id: int
    batch: int
    category: str  # 自主招生 | 名额分配 | 统招
    initial_quota: int
    control_line: int
    middle_school_id: Optional[int] = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "high_school_id": self.high_school_id,
            "batch": self.batch,
            "category": self.category,
            "initial_quota": self.initial_quota,
            "control_line": self.control_line,
            "middle_school_id": self.middle_school_id,
            "note": self.note,
        }


@dataclass(slots=True)
class Qualification:
    candidate_id: int
    high_school_id: int
    status: str  # qualified | disqualified
    rank: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "high_school_id": self.high_school_id,
            "status": self.status,
            "rank": self.rank,
        }


@dataclass(slots=True)
class Volunteer:
    candidate_id: int
    batch: int
    seq: int
    high_school_id: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "batch": self.batch,
            "seq": self.seq,
            "high_school_id": self.high_school_id,
        }


@dataclass
class Dataset:
    params: Params
    high_schools: dict[int, HighSchool] = field(default_factory=dict)
    middle_schools: dict[int, MiddleSchool] = field(default_factory=dict)
    candidates: dict[int, Candidate] = field(default_factory=dict)
    plans: dict[int, Plan] = field(default_factory=dict)
    qualifications: list[Qualification] = field(default_factory=list)
    volunteers: list[Volunteer] = field(default_factory=list)

    # 以下为索引，build_indexes() 后可用
    plans_by_batch: dict[int, list[Plan]] = field(default_factory=dict, repr=False)
    plan_by_high_batch: dict[tuple[int, int], Plan] = field(default_factory=dict, repr=False)
    plan_by_high_middle: dict[tuple[int, int], Plan] = field(default_factory=dict, repr=False)
    plans_by_middle: dict[int, list[Plan]] = field(default_factory=dict, repr=False)
    candidates_by_middle: dict[int, list[Candidate]] = field(default_factory=dict, repr=False)
    qualification_map: dict[tuple[int, int], Qualification] = field(default_factory=dict, repr=False)
    volunteer_map: dict[int, dict[tuple[int, int], Volunteer]] = field(default_factory=dict, repr=False)
    volunteers_by_batch_high: dict[tuple[int, int], list[Volunteer]] = field(default_factory=dict, repr=False)

    def build_indexes(self) -> "Dataset":
        self.plans_by_batch = defaultdict(list)
        self.plan_by_high_batch = {}
        self.plan_by_high_middle = {}
        self.plans_by_middle = defaultdict(list)
        self.candidates_by_middle = defaultdict(list)
        self.qualification_map = {}
        self.volunteer_map = defaultdict(dict)
        self.volunteers_by_batch_high = defaultdict(list)

        for plan in self.plans.values():
            self.plans_by_batch[plan.batch].append(plan)
            if plan.batch == 2:
                self.plan_by_high_middle[(plan.high_school_id, plan.middle_school_id)] = plan
                self.plans_by_middle[plan.middle_school_id].append(plan)
            else:
                self.plan_by_high_batch[(plan.high_school_id, plan.batch)] = plan

        for plan_list in self.plans_by_batch.values():
            plan_list.sort(key=lambda p: p.id)
        for plan_list in self.plans_by_middle.values():
            plan_list.sort(key=lambda p: p.id)

        for c in self.candidates.values():
            self.candidates_by_middle[c.middle_school_id].append(c)
        for c_list in self.candidates_by_middle.values():
            c_list.sort(key=lambda c: c.id)

        for q in self.qualifications:
            self.qualification_map[(q.candidate_id, q.high_school_id)] = q

        for v in self.volunteers:
            self.volunteer_map[v.candidate_id][(v.batch, v.seq)] = v
            if v.batch in (1, 3, 4):
                self.volunteers_by_batch_high[(v.batch, v.high_school_id)].append(v)

        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "params": self.params.to_dict(),
            "high_schools": [h.to_dict() for h in sorted(self.high_schools.values(), key=lambda x: x.id)],
            "middle_schools": [m.to_dict() for m in sorted(self.middle_schools.values(), key=lambda x: x.id)],
            "candidates": [c.to_dict() for c in sorted(self.candidates.values(), key=lambda x: x.id)],
            "plans": [p.to_dict() for p in sorted(self.plans.values(), key=lambda x: x.id)],
            "qualifications": [
                q.to_dict()
                for q in sorted(
                    self.qualifications,
                    key=lambda x: (x.high_school_id, x.rank if x.rank is not None else 10**9, x.candidate_id),
                )
            ],
            "volunteers": [
                v.to_dict()
                for v in sorted(self.volunteers, key=lambda x: (x.candidate_id, x.batch, x.seq))
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Dataset":
        ds = cls(params=Params(**data.get("params", {})))
        for row in data.get("high_schools", []):
            ds.high_schools[int(row["id"])] = HighSchool(
                id=int(row["id"]),
                code=row["code"],
                name=row["name"],
                category=row["category"],
                intake_batch=int(row["intake_batch"]),
                has_autonomous=bool(row.get("has_autonomous", 0)),
                total_plan=int(row.get("total_plan", 0)),
                campus=row.get("campus", ""),
            )
        for row in data.get("middle_schools", []):
            ds.middle_schools[int(row["id"])] = MiddleSchool(
                id=int(row["id"]),
                code=row["code"],
                name=row["name"],
                district=row.get("district", ""),
            )
        for row in data.get("candidates", []):
            ds.candidates[int(row["id"])] = Candidate(
                id=int(row["id"]),
                candidate_no=row["candidate_no"],
                name=row["name"],
                middle_school_id=int(row["middle_school_id"]),
                score=int(row["score"]),
                tie_seq=int(row["tie_seq"]),
            )
        for row in data.get("plans", []):
            ds.plans[int(row["id"])] = Plan(
                id=int(row["id"]),
                high_school_id=int(row["high_school_id"]),
                batch=int(row["batch"]),
                category=row["category"],
                initial_quota=int(row["initial_quota"]),
                control_line=int(row["control_line"]),
                middle_school_id=(
                    int(row["middle_school_id"]) if row.get("middle_school_id") is not None else None
                ),
                note=row.get("note", ""),
            )
        for row in data.get("qualifications", []):
            ds.qualifications.append(
                Qualification(
                    candidate_id=int(row["candidate_id"]),
                    high_school_id=int(row["high_school_id"]),
                    status=row["status"],
                    rank=int(row["rank"]) if row.get("rank") is not None else None,
                )
            )
        for row in data.get("volunteers", []):
            ds.volunteers.append(
                Volunteer(
                    candidate_id=int(row["candidate_id"]),
                    batch=int(row["batch"]),
                    seq=int(row["seq"]),
                    high_school_id=int(row["high_school_id"]),
                )
            )
        return ds.build_indexes()


# ---------------------------------------------------------------------------
# 梯度
# ---------------------------------------------------------------------------


def gradient_band(score: int, g1: int, delta: int, city_line: int) -> Optional[int]:
    """返回分数所在梯度（1 为最高），低于全市控制线返回 None。

    分数恰好等于某条梯度线时，归入该线对应的较高梯度。
    例如 G1=720, delta=40：720→1，719→2，680→2，679→3，640→3，600→4。
    """
    if score < city_line:
        return None
    if score >= g1:
        return 1
    return 2 + (g1 - score - 1) // delta


def max_gradient_band(g1: int, delta: int, city_line: int) -> int:
    """给定参数下可能出现的最低梯度编号。"""
    if city_line >= g1:
        return 1
    return 2 + (g1 - city_line - 1) // delta


def band_range_text(band: int, g1: int, delta: int, city_line: int) -> str:
    """返回梯度的分数区间说明。"""
    if band == 1:
        return f"总分 ≥ {g1}"
    low = max(city_line, g1 - (band - 1) * delta)
    high = g1 - (band - 2) * delta
    if band == max_gradient_band(g1, delta, city_line):
        return f"{low} ≤ 总分 < {high}"
    return f"{low} ≤ 总分 < {high}"


# ---------------------------------------------------------------------------
# 运行状态
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PlanState:
    plan_id: int
    initial_quota: int
    transferred_in: int = 0
    transferred_out: int = 0
    admitted_count: int = 0

    @property
    def effective_quota(self) -> int:
        return self.initial_quota + self.transferred_in

    @property
    def remaining(self) -> int:
        return self.effective_quota - self.transferred_out - self.admitted_count


@dataclass(slots=True)
class AdmissionRecord:
    candidate_id: int
    plan_id: int
    high_school_id: int
    middle_school_id: int
    batch: int
    volunteer_seq: int
    score: int
    tie_seq: int
    band: int
    admission_order: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "plan_id": self.plan_id,
            "high_school_id": self.high_school_id,
            "middle_school_id": self.middle_school_id,
            "batch": self.batch,
            "volunteer_seq": self.volunteer_seq,
            "score": self.score,
            "tie_seq": self.tie_seq,
            "band": self.band,
            "admission_order": self.admission_order,
        }


@dataclass(slots=True)
class TransferRecord:
    from_batch: int
    from_plan_id: int
    high_school_id: int
    middle_school_id: Optional[int]
    amount: int
    to_plan_id: int
    group_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_batch": self.from_batch,
            "from_plan_id": self.from_plan_id,
            "high_school_id": self.high_school_id,
            "middle_school_id": self.middle_school_id,
            "amount": self.amount,
            "to_plan_id": self.to_plan_id,
            "group_key": self.group_key,
        }


@dataclass(slots=True)
class CandidateBatchOutcome:
    candidate_id: int
    batch: int
    status: str  # ADMITTED | NOT_ADMITTED | SKIPPED | INELIGIBLE
    reason_code: str
    reason_text: str
    admitted_plan_id: Optional[int] = None
    detail: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "batch": self.batch,
            "status": self.status,
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "admitted_plan_id": self.admitted_plan_id,
            "detail": self.detail,
        }


@dataclass(slots=True)
class BatchResult:
    batch: int
    admissions: list[AdmissionRecord]
    outcomes: list[CandidateBatchOutcome]
    transfers: list[TransferRecord]
    events: list[dict[str, Any]]
    plan_states: dict[int, PlanState]

    @property
    def admitted_count(self) -> int:
        return len(self.admissions)


@dataclass(slots=True)
class RunResult:
    admissions: list[AdmissionRecord]
    outcomes: list[CandidateBatchOutcome]
    transfers: list[TransferRecord]
    events: list[dict[str, Any]]
    plan_states: dict[int, PlanState]
    batch_results: list[BatchResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------


class AdmissionEngine:
    """在内存数据集上执行投档。

    可传入已有的录取记录和计划状态，从而支持“按批执行”：
    每次只运行一个批次，外部持久化状态后再继续下一批。
    """

    def __init__(
        self,
        dataset: Dataset,
        admitted: Optional[dict[int, AdmissionRecord]] = None,
        plan_states: Optional[dict[int, PlanState]] = None,
        plan_orders: Optional[dict[int, int]] = None,
    ) -> None:
        self.ds = dataset
        if not self.ds.plans_by_batch:
            self.ds.build_indexes()
        self.params = dataset.params
        self.max_band = max_gradient_band(self.params.g1, self.params.delta, self.params.city_line)
        self.bands: dict[int, Optional[int]] = {
            c.id: gradient_band(c.score, self.params.g1, self.params.delta, self.params.city_line)
            for c in dataset.candidates.values()
        }
        self.admitted: dict[int, AdmissionRecord] = dict(admitted or {})
        self.states: dict[int, PlanState] = dict(plan_states or {})
        for plan in dataset.plans.values():
            self.states.setdefault(plan.id, PlanState(plan.id, plan.initial_quota))
        self._plan_orders: dict[int, int] = dict(plan_orders or {})
        if not plan_orders:
            for rec in self.admitted.values():
                self._plan_orders[rec.plan_id] = max(
                    self._plan_orders.get(rec.plan_id, 0), rec.admission_order
                )

        self._detail: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
        self._admissions: list[AdmissionRecord] = []
        self._transfers: list[TransferRecord] = []
        self._events: list[dict[str, Any]] = []

    # -- 对外接口 ---------------------------------------------------------

    def run_batch(self, batch: int) -> BatchResult:
        if batch not in (1, 2, 3, 4):
            raise ValueError(f"非法批次: {batch}")
        self._detail = defaultdict(dict)
        self._admissions = []
        self._transfers = []
        self._events = []

        self._event("batch_start", batch=batch, message=f"{BATCH_NAMES[batch]}开始投档")

        if batch == 1:
            self._run_autonomous()
            self._transfer_batch1()
        elif batch == 2:
            self._run_quota_allocation()
            self._transfer_batch2()
        else:
            self._run_unified(batch)

        outcomes = self._build_outcomes(batch)
        self._event(
            "batch_end",
            batch=batch,
            message=(
                f"{BATCH_NAMES[batch]}结束：录取 {len(self._admissions)} 人，"
                f"结转 {sum(t.amount for t in self._transfers)} 人"
            ),
        )
        return BatchResult(
            batch=batch,
            admissions=list(self._admissions),
            outcomes=outcomes,
            transfers=list(self._transfers),
            events=list(self._events),
            plan_states=dict(self.states),
        )

    def run_all(self) -> RunResult:
        all_admissions: list[AdmissionRecord] = []
        all_outcomes: list[CandidateBatchOutcome] = []
        all_transfers: list[TransferRecord] = []
        all_events: list[dict[str, Any]] = []
        batch_results: list[BatchResult] = []
        for batch in (1, 2, 3, 4):
            result = self.run_batch(batch)
            batch_results.append(result)
            all_admissions.extend(result.admissions)
            all_outcomes.extend(result.outcomes)
            all_transfers.extend(result.transfers)
            all_events.extend(result.events)
        return RunResult(
            admissions=all_admissions,
            outcomes=all_outcomes,
            transfers=all_transfers,
            events=all_events,
            plan_states=dict(self.states),
            batch_results=batch_results,
        )

    # -- 第一批 自主招生 ---------------------------------------------------

    def _run_autonomous(self) -> None:
        plans = self.ds.plans_by_batch.get(1, [])
        valid_high_ids = {p.high_school_id for p in plans}

        # 先处理没有对应计划的第一批志愿
        for v in self.ds.volunteers:
            if v.batch != 1:
                continue
            if v.candidate_id in self.admitted:
                continue
            if v.high_school_id not in valid_high_ids:
                c = self.ds.candidates[v.candidate_id]
                self._mark(
                    c,
                    v.seq,
                    "INVALID_PLAN",
                    "目标高中不参加第一批自主招生",
                    high_id=v.high_school_id,
                    batch=1,
                )

        for plan in plans:
            high_id = plan.high_school_id
            state = self.states[plan.id]
            eligible: list[tuple[int, Candidate, Volunteer]] = []
            vols = self.ds.volunteers_by_batch_high.get((1, high_id), [])
            for v in sorted(vols, key=lambda x: (x.candidate_id, x.seq)):
                c = self.ds.candidates[v.candidate_id]
                if c.id in self.admitted:
                    continue
                if self.bands[c.id] is None:
                    self._mark(
                        c, v.seq, "BELOW_CITY",
                        f"总分 {c.score} 低于全市控制线 {self.params.city_line}",
                        high_id=high_id, plan=plan,
                    )
                    continue
                q = self.ds.qualification_map.get((c.id, high_id))
                if q is None:
                    self._mark(
                        c, v.seq, "NO_QUALIFICATION",
                        "不在该校自主招生资格名单内",
                        high_id=high_id, plan=plan,
                    )
                    continue
                if q.status != "qualified":
                    self._mark(
                        c, v.seq, "DISQUALIFIED",
                        "自主招生资格状态为不合格",
                        high_id=high_id, plan=plan,
                    )
                    continue
                if q.rank is None:
                    self._mark(
                        c, v.seq, "NO_RANK",
                        "资格名单缺少考核排名",
                        high_id=high_id, plan=plan,
                    )
                    continue
                if c.score < plan.control_line:
                    self._mark(
                        c, v.seq, "BELOW_CONTROL",
                        f"总分 {c.score} 低于计划控制线 {plan.control_line}",
                        high_id=high_id, plan=plan,
                    )
                    continue
                eligible.append((q.rank, c, v))

            eligible.sort(key=lambda item: (item[0], item[1].candidate_no))
            for rank, c, v in eligible:
                if self.states[plan.id].remaining > 0:
                    self._admit(c, plan, v.seq, self.bands[c.id] or 1, extra={"qualification_rank": rank})
                else:
                    self._mark(
                        c, v.seq, "OUTRANKED",
                        f"考核排名第 {rank}，计划余额已满",
                        high_id=high_id, plan=plan, remaining=0,
                        extra={"qualification_rank": rank},
                    )

    # -- 第二批 名额分配 ---------------------------------------------------

    def _run_quota_allocation(self) -> None:
        plans = self.ds.plans_by_batch.get(2, [])
        if not plans:
            return

        for middle_id in sorted(self.ds.middle_schools):
            middle_plans = self.ds.plans_by_middle.get(middle_id, [])
            cands = self.ds.candidates_by_middle.get(middle_id, [])
            if not cands:
                continue

            band_map: dict[int, list[Candidate]] = defaultdict(list)
            for c in cands:
                if c.id in self.admitted:
                    continue
                band = self.bands[c.id]
                if band is not None:
                    band_map[band].append(c)

            stopped = False
            for band in range(1, self.max_band + 1):
                if stopped:
                    break
                if middle_plans and all(self.states[p.id].remaining <= 0 for p in middle_plans):
                    self._mark_unprocessed_band(middle_id, band, "BATCH_FULL", "本批次计划已满，未轮到该梯度")
                    stopped = True
                    break

                for seq in range(1, VOLUNTEER_LIMITS[2] + 1):
                    groups: dict[int, list[tuple[Candidate, Volunteer]]] = defaultdict(list)
                    for c in band_map.get(band, []):
                        if c.id in self.admitted:
                            continue
                        v = self.ds.volunteer_map[c.id].get((2, seq))
                        if v is None:
                            continue
                        plan = self.ds.plan_by_high_middle.get((v.high_school_id, middle_id))
                        if plan is None:
                            self._mark(
                                c, v.seq, "NO_ALLOCATION",
                                "所属初中未获得该高中的名额分配指标",
                                high_id=v.high_school_id,
                                batch=2,
                            )
                            continue
                        if c.score < self.params.city_line:
                            self._mark(
                                c, v.seq, "BELOW_CITY",
                                f"总分 {c.score} 低于全市控制线 {self.params.city_line}",
                                high_id=v.high_school_id, plan=plan,
                            )
                            continue
                        if c.score < plan.control_line:
                            self._mark(
                                c, v.seq, "BELOW_CONTROL",
                                f"总分 {c.score} 低于计划控制线 {plan.control_line}",
                                high_id=v.high_school_id, plan=plan,
                            )
                            continue
                        groups[plan.id].append((c, v))

                    for pid in sorted(groups):
                        plan = self.ds.plans[pid]
                        items = groups[pid]
                        items.sort(key=lambda item: (-item[0].score, item[0].tie_seq, item[0].candidate_no))
                        for c, v in items:
                            if self.states[plan.id].remaining > 0:
                                self._admit(c, plan, v.seq, self.bands[c.id] or band)
                            else:
                                self._mark(
                                    c, v.seq, "OUTRANKED",
                                    "校内竞争排序靠后，名额已被更高优先级考生占满",
                                    high_id=plan.high_school_id, plan=plan, remaining=0,
                                )

    # -- 第三、四批 统招 ---------------------------------------------------

    def _run_unified(self, batch: int) -> None:
        plans = self.ds.plans_by_batch.get(batch, [])
        if not plans:
            return
        plan_by_high = {p.high_school_id: p for p in plans}

        band_map: dict[int, list[Candidate]] = defaultdict(list)
        for c in self.ds.candidates.values():
            if c.id in self.admitted:
                continue
            band = self.bands[c.id]
            if band is not None:
                band_map[band].append(c)

        stopped = False
        for band in range(1, self.max_band + 1):
            if stopped:
                break
            if all(self.states[p.id].remaining <= 0 for p in plans):
                self._mark_all_unprocessed(batch, band, "BATCH_FULL", "本批次计划已满，未轮到该梯度")
                stopped = True
                break

            for seq in range(1, VOLUNTEER_LIMITS[batch] + 1):
                groups: dict[int, list[tuple[Candidate, Volunteer]]] = defaultdict(list)
                for c in band_map.get(band, []):
                    if c.id in self.admitted:
                        continue
                    v = self.ds.volunteer_map[c.id].get((batch, seq))
                    if v is None:
                        continue
                    plan = plan_by_high.get(v.high_school_id)
                    if plan is None:
                        self._mark(
                            c, v.seq, "INVALID_PLAN",
                            "目标高中不参加本批次招生",
                            high_id=v.high_school_id,
                            batch=batch,
                        )
                        continue
                    if c.score < plan.control_line:
                        self._mark(
                            c, v.seq, "BELOW_CONTROL",
                            f"总分 {c.score} 低于计划控制线 {plan.control_line}",
                            high_id=v.high_school_id, plan=plan,
                        )
                        continue
                    groups[plan.id].append((c, v))

                for pid in sorted(groups):
                    plan = self.ds.plans[pid]
                    items = groups[pid]
                    items.sort(key=lambda item: (-item[0].score, item[0].tie_seq, item[0].candidate_no))
                    for c, v in items:
                        if self.states[plan.id].remaining > 0:
                            self._admit(c, plan, v.seq, self.bands[c.id] or band)
                        else:
                            self._mark(
                                c, v.seq, "OUTRANKED",
                                "同梯度同志愿排序靠后，计划余额已满",
                                high_id=plan.high_school_id, plan=plan, remaining=0,
                            )

    # -- 结转 -------------------------------------------------------------

    def _transfer_batch1(self) -> None:
        for plan in self.ds.plans_by_batch.get(1, []):
            state = self.states[plan.id]
            amount = state.remaining
            if amount <= 0:
                continue
            target = self.ds.plan_by_high_batch.get((plan.high_school_id, 3))
            if target is None:
                self._event(
                    "transfer_error", batch=1,
                    message=f"高中 {plan.high_school_id} 第一批剩余 {amount} 人，但未找到第三批统招计划",
                )
                continue
            state.transferred_out += amount
            self.states[target.id].transferred_in += amount
            rec = TransferRecord(
                from_batch=1,
                from_plan_id=plan.id,
                high_school_id=plan.high_school_id,
                middle_school_id=None,
                amount=amount,
                to_plan_id=target.id,
                group_key=f"B1-H{plan.high_school_id}",
            )
            self._transfers.append(rec)
            self._event(
                "transfer", batch=1,
                message=(
                    f"第一批剩余 {amount} 人由高中 {self.ds.high_schools[plan.high_school_id].name} "
                    f"转入第三批计划"
                ),
                detail=rec.to_dict(),
            )

    def _transfer_batch2(self) -> None:
        by_high: dict[int, list[Plan]] = defaultdict(list)
        for plan in self.ds.plans_by_batch.get(2, []):
            by_high[plan.high_school_id].append(plan)

        for high_id in sorted(by_high):
            high_plans = by_high[high_id]
            total = sum(self.states[p.id].remaining for p in high_plans)
            if total <= 0:
                continue
            target = self.ds.plan_by_high_batch.get((high_id, 3))
            if target is None:
                self._event(
                    "transfer_error", batch=2,
                    message=f"高中 {high_id} 第二批剩余 {total} 人，但未找到第三批统招计划",
                )
                continue
            for plan in high_plans:
                amount = self.states[plan.id].remaining
                if amount <= 0:
                    continue
                self.states[plan.id].transferred_out += amount
                rec = TransferRecord(
                    from_batch=2,
                    from_plan_id=plan.id,
                    high_school_id=high_id,
                    middle_school_id=plan.middle_school_id,
                    amount=amount,
                    to_plan_id=target.id,
                    group_key=f"B2-H{high_id}",
                )
                self._transfers.append(rec)
            self.states[target.id].transferred_in += total
            self._event(
                "transfer", batch=2,
                message=(
                    f"第二批按高中汇总剩余 {total} 人，"
                    f"由 {self.ds.high_schools[high_id].name} 转入第三批计划"
                ),
                detail={
                    "high_school_id": high_id,
                    "amount": total,
                    "to_plan_id": target.id,
                    "sources": [
                        {"plan_id": p.id, "middle_school_id": p.middle_school_id, "amount": self.states[p.id].transferred_out}
                        for p in high_plans
                        if self.states[p.id].transferred_out > 0
                    ],
                },
            )

    # -- 录取与记录 -------------------------------------------------------

    def _admit(
        self,
        c: Candidate,
        plan: Plan,
        seq: int,
        band: int,
        extra: Optional[dict[str, Any]] = None,
    ) -> AdmissionRecord:
        state = self.states[plan.id]
        state.admitted_count += 1
        order = self._plan_orders.get(plan.id, 0) + 1
        self._plan_orders[plan.id] = order
        rec = AdmissionRecord(
            candidate_id=c.id,
            plan_id=plan.id,
            high_school_id=plan.high_school_id,
            middle_school_id=c.middle_school_id,
            batch=plan.batch,
            volunteer_seq=seq,
            score=c.score,
            tie_seq=c.tie_seq,
            band=band,
            admission_order=order,
        )
        self.admitted[c.id] = rec
        self._admissions.append(rec)
        high = self.ds.high_schools[plan.high_school_id]
        self._detail[c.id][seq] = {
            "seq": seq,
            "high_school_id": plan.high_school_id,
            "high_school_name": high.name,
            "plan_id": plan.id,
            "code": "ADMITTED",
            "text": f"被 {high.name} 录取（第 {seq} 志愿）",
            "remaining": state.remaining,
            "band": band,
            **(extra or {}),
        }
        self._event(
            "admit",
            batch=plan.batch,
            message=(
                f"{c.candidate_no} {c.name}（{c.score} 分）被 {high.name} 录取，"
                f"第 {seq} 志愿，计划余额 {state.remaining}"
            ),
            candidate_id=c.id,
            plan_id=plan.id,
            volunteer_seq=seq,
            band=band,
            remaining_before=state.remaining + 1,
            remaining_after=state.remaining,
            detail={**rec.to_dict(), "candidate_no": c.candidate_no, "candidate_name": c.name},
        )
        return rec

    def _mark(
        self,
        c: Candidate,
        seq: int,
        code: str,
        text: str,
        high_id: Optional[int] = None,
        plan: Optional[Plan] = None,
        remaining: Optional[int] = None,
        extra: Optional[dict[str, Any]] = None,
        batch: Optional[int] = None,
    ) -> None:
        if seq in self._detail[c.id]:
            return
        high_name = ""
        if high_id is not None and high_id in self.ds.high_schools:
            high_name = self.ds.high_schools[high_id].name
        elif plan is not None:
            high_name = self.ds.high_schools[plan.high_school_id].name
        event_batch = plan.batch if plan is not None else batch
        self._detail[c.id][seq] = {
            "seq": seq,
            "high_school_id": high_id if high_id is not None else (plan.high_school_id if plan else None),
            "high_school_name": high_name,
            "plan_id": plan.id if plan else None,
            "code": code,
            "text": text,
            "remaining": remaining,
            "band": self.bands[c.id],
            **(extra or {}),
        }
        if self.params.trace_level == "full":
            self._event(
                "skip",
                batch=event_batch,
                message=f"{c.candidate_no} 第 {seq} 志愿跳过：{text}",
                candidate_id=c.id,
                plan_id=plan.id if plan else None,
                volunteer_seq=seq,
                band=self.bands[c.id],
                remaining_after=remaining,
            )

    def _mark_unprocessed_band(self, middle_id: int, band: int, code: str, text: str) -> None:
        for c in self.ds.candidates_by_middle.get(middle_id, []):
            if c.id in self.admitted or self.bands[c.id] is None:
                continue
            if (self.bands[c.id] or 99) < band:
                continue
            for (b, seq), v in self.ds.volunteer_map[c.id].items():
                if b != 2:
                    continue
                self._mark(c, seq, code, text, high_id=v.high_school_id, batch=2)

    def _mark_all_unprocessed(self, batch: int, band: int, code: str, text: str) -> None:
        for c in self.ds.candidates.values():
            if c.id in self.admitted or self.bands[c.id] is None:
                continue
            if (self.bands[c.id] or 99) < band:
                continue
            for (b, seq), v in self.ds.volunteer_map[c.id].items():
                if b != batch:
                    continue
                self._mark(c, seq, code, text, high_id=v.high_school_id, batch=batch)

    def _event(self, event_type: str, **kwargs: Any) -> None:
        self._events.append({"type": event_type, **kwargs})

    # -- 生成批次结果 -----------------------------------------------------

    def _build_outcomes(self, batch: int) -> list[CandidateBatchOutcome]:
        outcomes: list[CandidateBatchOutcome] = []
        for c in sorted(self.ds.candidates.values(), key=lambda x: x.id):
            batch_vols = {
                seq: v
                for (b, seq), v in self.ds.volunteer_map.get(c.id, {}).items()
                if b == batch
            }
            details = self._detail.get(c.id, {})
            rec = self.admitted.get(c.id)

            # 补齐未记录的志愿
            for seq, v in batch_vols.items():
                if seq in details:
                    continue
                if rec is not None:
                    code, text = "NOT_REACHED", "前序志愿已录取，后续志愿不再投档"
                elif self.bands[c.id] is None:
                    code, text = "BELOW_CITY", f"总分 {c.score} 低于全市控制线 {self.params.city_line}"
                else:
                    code, text = "BATCH_FULL", "本批次计划已满，未轮到该考生所在梯度"
                details[seq] = {
                    "seq": seq,
                    "high_school_id": v.high_school_id,
                    "high_school_name": self.ds.high_schools[v.high_school_id].name,
                    "plan_id": None,
                    "code": code,
                    "text": text,
                    "remaining": None,
                    "band": self.bands[c.id],
                }

            # 已录取考生的后续志愿
            if rec is not None and rec.batch == batch:
                for seq in batch_vols:
                    if seq > rec.volunteer_seq and seq not in self._detail.get(c.id, {}):
                        details[seq] = {
                            "seq": seq,
                            "high_school_id": batch_vols[seq].high_school_id,
                            "high_school_name": self.ds.high_schools[batch_vols[seq].high_school_id].name,
                            "plan_id": None,
                            "code": "NOT_REACHED",
                            "text": "前序志愿已录取，后续志愿不再投档",
                            "remaining": None,
                            "band": self.bands[c.id],
                        }

            detail_list = [details[seq] for seq in sorted(details) if seq in batch_vols]
            detail_list.sort(key=lambda d: d["seq"])

            if rec is not None and rec.batch == batch:
                status = "ADMITTED"
                reason_code = "ADMITTED"
                reason_text = (
                    f"被 {self.ds.high_schools[rec.high_school_id].name} 录取"
                    f"（{BATCH_NAMES[batch]}，第 {rec.volunteer_seq} 志愿）"
                )
            elif rec is not None:
                status = "SKIPPED"
                reason_code = "ALREADY_ADMITTED"
                reason_text = (
                    f"前批次已录取（{BATCH_NAMES[rec.batch]}，"
                    f"{self.ds.high_schools[rec.high_school_id].name}），退出本批次"
                )
                for d in detail_list:
                    if d["code"] not in ("NOT_REACHED", "ALREADY_ADMITTED"):
                        d["code"] = "NOT_REACHED"
                        d["text"] = "前批次已录取，退出本批次"
            elif self.bands[c.id] is None:
                status = "INELIGIBLE"
                reason_code = "BELOW_CITY_LINE"
                reason_text = f"总分 {c.score} 低于全市公办高中最低控制线 {self.params.city_line}"
                for d in detail_list:
                    d["code"] = "BELOW_CITY"
                    d["text"] = reason_text
            else:
                status = "NOT_ADMITTED"
                reason_code, reason_text = self._summarize_reason(c, detail_list, bool(batch_vols))

            outcomes.append(
                CandidateBatchOutcome(
                    candidate_id=c.id,
                    batch=batch,
                    status=status,
                    reason_code=reason_code,
                    reason_text=reason_text,
                    admitted_plan_id=rec.plan_id if rec is not None and rec.batch == batch else None,
                    detail=detail_list,
                )
            )
        return outcomes

    def _summarize_reason(
        self, c: Candidate, details: list[dict[str, Any]], has_volunteer: bool
    ) -> tuple[str, str]:
        if not details:
            if not has_volunteer:
                return "NO_VOLUNTEER", "本批次未填报志愿"
            return "NOT_ADMITTED", "未被录取"
        codes = [d["code"] for d in details]
        if all(code == "BELOW_CITY" for code in codes):
            return "BELOW_CITY_LINE", f"总分 {c.score} 低于全市控制线 {self.params.city_line}"
        if all(code in ("BELOW_CITY", "BELOW_CONTROL") for code in codes):
            return "BELOW_PLAN_CONTROL_LINE", "所报计划控制线均未达到"
        if any(code in ("OUTRANKED", "PLAN_FULL", "BATCH_FULL") for code in codes):
            return "PLAN_FULL", "所报志愿计划余额已满，未被录取"
        if any(code == "NO_ALLOCATION" for code in codes):
            return "NO_ALLOCATION", "所属初中未获得所报高中的名额分配指标"
        if any(code == "NO_QUALIFICATION" for code in codes):
            return "NO_QUALIFICATION", "未进入所报高中的自主招生资格名单"
        if any(code == "DISQUALIFIED" for code in codes):
            return "DISQUALIFIED", "自主招生资格状态为不合格"
        if any(code == "INVALID_PLAN" for code in codes):
            return "INVALID_VOLUNTEER", "所报高中不参加本批次招生"
        if any(code == "BELOW_CONTROL" for code in codes):
            return "BELOW_PLAN_CONTROL_LINE", "部分志愿未达到计划控制线，其余志愿未录取"
        return "NOT_ADMITTED", "未被录取"


# ---------------------------------------------------------------------------
# 一致性校验
# ---------------------------------------------------------------------------


def verify_run(
    dataset: Dataset,
    plan_states: dict[int, PlanState],
    admissions: Iterable[AdmissionRecord],
) -> list[str]:
    """检查任务书要求的系统约束，返回错误信息列表。"""
    errors: list[str] = []
    admissions = list(admissions)
    seen: dict[int, AdmissionRecord] = {}
    per_plan: dict[int, list[AdmissionRecord]] = defaultdict(list)

    for rec in admissions:
        if rec.candidate_id in seen:
            errors.append(f"考生 {rec.candidate_id} 被重复录取")
        seen[rec.candidate_id] = rec
        per_plan[rec.plan_id].append(rec)

        c = dataset.candidates.get(rec.candidate_id)
        plan = dataset.plans.get(rec.plan_id)
        if c is None or plan is None:
            errors.append(f"录取记录引用不存在的考生或计划: {rec}")
            continue
        if rec.batch != plan.batch:
            errors.append(f"考生 {c.candidate_no} 录取批次与计划批次不一致")
        if rec.high_school_id != plan.high_school_id:
            errors.append(f"考生 {c.candidate_no} 录取高中与计划高中不一致")
        if plan.batch == 2 and rec.middle_school_id != plan.middle_school_id:
            errors.append(f"考生 {c.candidate_no} 使用了非所属初中的名额分配计划")
        if c.score < plan.control_line:
            errors.append(f"考生 {c.candidate_no} 低于计划控制线仍被录取")
        v = dataset.volunteer_map.get(c.id, {}).get((plan.batch, rec.volunteer_seq))
        if v is None or v.high_school_id != plan.high_school_id:
            errors.append(f"考生 {c.candidate_no} 的录取记录没有对应有效志愿")
        if plan.batch == 1:
            q = dataset.qualification_map.get((c.id, plan.high_school_id))
            if q is None or q.status != "qualified":
                errors.append(f"考生 {c.candidate_no} 无自主招生资格却被第一批录取")

    for plan in dataset.plans.values():
        state = plan_states.get(plan.id)
        if state is None:
            errors.append(f"计划 {plan.id} 缺少状态记录")
            continue
        admitted = len(per_plan.get(plan.id, []))
        if admitted != state.admitted_count:
            errors.append(
                f"计划 {plan.id} 已录取数不一致：明细 {admitted}，状态 {state.admitted_count}"
            )
        if state.admitted_count > state.effective_quota - state.transferred_out:
            errors.append(f"计划 {plan.id} 录取人数超过可用名额")
        if state.initial_quota + state.transferred_in - state.transferred_out != (
            state.admitted_count + state.remaining
        ):
            errors.append(f"计划 {plan.id} 名额平衡等式不成立")
        if state.remaining < 0:
            errors.append(f"计划 {plan.id} 计划余额为负")
        orders = sorted(r.admission_order for r in per_plan.get(plan.id, []))
        if orders and orders != list(range(1, len(orders) + 1)):
            errors.append(f"计划 {plan.id} 录取顺序不连续")

    return errors
