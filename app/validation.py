"""数据集校验。

校验分为 error 与 warning：
- error：数据不合法，不能创建投档运行；
- warning：数据可运行但存在风险或与任务书推荐口径不一致。

任务书要求的异常输入（重复考生、非法分数、重复志愿、无效计划、
重复同分序号）均作为 error 处理。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .engine import Dataset, VOLUNTEER_LIMITS


@dataclass
class ValidationIssue:
    level: str  # error | warning
    code: str
    message: str
    entity: str
    entity_id: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "entity": self.entity,
            "entity_id": self.entity_id,
        }


class DatasetValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        errors = [i.message for i in issues if i.level == "error"]
        super().__init__("；".join(errors) if errors else "数据校验失败")


def validate_dataset(ds: Dataset, raise_on_error: bool = False) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def add(level: str, code: str, message: str, entity: str, entity_id: Any = None) -> None:
        issues.append(ValidationIssue(level, code, message, entity, entity_id))

    # ---- 参数 ---------------------------------------------------------
    p = ds.params
    if p.delta <= 0:
        add("error", "PARAM_DELTA", "梯度间隔 Δ 必须大于 0", "params")
    if p.city_line < 0:
        add("error", "PARAM_CITY_LINE", "全市最低控制线不能为负数", "params")
    if p.g1 < p.city_line:
        add("error", "PARAM_G1", "第一梯度线不能低于全市最低控制线", "params")
    if p.g1 > 750:
        add("warning", "PARAM_G1_HIGH", "第一梯度线高于满分 750，第一梯度将无人", "params")

    # ---- 高中 ---------------------------------------------------------
    hs_codes: dict[str, int] = {}
    for h in ds.high_schools.values():
        if not h.code.strip():
            add("error", "HS_CODE", f"高中 {h.id} 编号为空", "high_school", h.id)
        elif h.code in hs_codes:
            add("error", "HS_CODE_DUP", f"高中编号重复：{h.code}", "high_school", h.id)
        else:
            hs_codes[h.code] = h.id
        if not h.name.strip():
            add("error", "HS_NAME", f"高中 {h.code} 名称为空", "high_school", h.id)
        if h.category not in ("示范性", "非示范"):
            add("error", "HS_CATEGORY", f"高中 {h.code} 类型必须为示范性或非示范", "high_school", h.id)
        if h.intake_batch not in (3, 4):
            add("error", "HS_BATCH", f"高中 {h.code} 统招接收批次必须为 3 或 4", "high_school", h.id)
        if h.intake_batch == 4 and h.has_autonomous:
            add("error", "HS_AUTONOMOUS", f"第四批高中 {h.code} 不能设置自主招生", "high_school", h.id)
        if h.total_plan < 0:
            add("error", "HS_TOTAL", f"高中 {h.code} 总计划不能为负数", "high_school", h.id)

    # ---- 初中 ---------------------------------------------------------
    ms_codes: dict[str, int] = {}
    for m in ds.middle_schools.values():
        if not m.code.strip():
            add("error", "MS_CODE", f"初中 {m.id} 编号为空", "middle_school", m.id)
        elif m.code in ms_codes:
            add("error", "MS_CODE_DUP", f"初中编号重复：{m.code}", "middle_school", m.id)
        else:
            ms_codes[m.code] = m.id
        if not m.name.strip():
            add("error", "MS_NAME", f"初中 {m.code} 名称为空", "middle_school", m.id)

    # ---- 考生 ---------------------------------------------------------
    cand_nos: dict[str, int] = {}
    score_tie: dict[tuple[int, int], int] = {}
    for c in ds.candidates.values():
        if not c.candidate_no.strip():
            add("error", "CAND_NO", f"考生 {c.id} 编号为空", "candidate", c.id)
        elif c.candidate_no in cand_nos:
            add("error", "CAND_NO_DUP", f"考生编号重复：{c.candidate_no}", "candidate", c.id)
        else:
            cand_nos[c.candidate_no] = c.id
        if not c.name.strip():
            add("error", "CAND_NAME", f"考生 {c.candidate_no} 姓名为空", "candidate", c.id)
        if c.middle_school_id not in ds.middle_schools:
            add("error", "CAND_MS", f"考生 {c.candidate_no} 所属初中不存在", "candidate", c.id)
        if not (0 <= c.score <= 750):
            add("error", "CAND_SCORE", f"考生 {c.candidate_no} 总分 {c.score} 非法（0-750）", "candidate", c.id)
        if c.tie_seq <= 0:
            add("error", "CAND_TIE", f"考生 {c.candidate_no} 同分序号必须为正整数", "candidate", c.id)
        key = (c.score, c.tie_seq)
        if key in score_tie:
            add(
                "error", "CAND_TIE_DUP",
                f"考生 {c.candidate_no} 与考生 {score_tie[key]} 同分且同分序号相同（{c.score}/{c.tie_seq}）",
                "candidate", c.id,
            )
        else:
            score_tie[key] = c.id
        if c.score < p.city_line:
            add(
                "warning", "CAND_BELOW_CITY",
                f"考生 {c.candidate_no} 总分 {c.score} 低于全市控制线，不参与录取",
                "candidate", c.id,
            )

    # ---- 招生计划 -----------------------------------------------------
    plan_keys: dict[tuple, int] = {}
    plans_by_high: dict[int, list] = defaultdict(list)
    for plan in ds.plans.values():
        h = ds.high_schools.get(plan.high_school_id)
        if h is None:
            add("error", "PLAN_HS", f"计划 {plan.id} 引用不存在的高中", "plan", plan.id)
            continue
        plans_by_high[h.id].append(plan)
        if plan.batch not in (1, 2, 3, 4):
            add("error", "PLAN_BATCH", f"计划 {plan.id} 批次非法", "plan", plan.id)
        if plan.initial_quota < 0:
            add("error", "PLAN_QUOTA", f"计划 {plan.id} 初始名额不能为负数", "plan", plan.id)
        if plan.control_line < p.city_line:
            add(
                "error", "PLAN_CONTROL",
                f"计划 {plan.id} 控制线 {plan.control_line} 低于全市最低控制线 {p.city_line}",
                "plan", plan.id,
            )
        expected_category = {1: "自主招生", 2: "名额分配", 3: "统招", 4: "统招"}.get(plan.batch)
        if expected_category and plan.category != expected_category:
            add(
                "warning", "PLAN_CATEGORY",
                f"计划 {plan.id} 类别 {plan.category} 与批次 {plan.batch} 推荐类别 {expected_category} 不一致",
                "plan", plan.id,
            )
        if plan.batch == 2:
            if plan.middle_school_id is None:
                add("error", "PLAN_MS", f"名额分配计划 {plan.id} 必须指定初中", "plan", plan.id)
            elif plan.middle_school_id not in ds.middle_schools:
                add("error", "PLAN_MS", f"计划 {plan.id} 引用不存在的初中", "plan", plan.id)
        elif plan.middle_school_id is not None:
            add("error", "PLAN_MS_NULL", f"计划 {plan.id} 非名额分配批次不能指定初中", "plan", plan.id)
        if plan.batch == 1 and not h.has_autonomous:
            add("error", "PLAN_AUTONOMOUS", f"高中 {h.code} 未获批自主招生，却存在第一批计划", "plan", plan.id)
        if plan.batch in (2, 3) and h.intake_batch != 3:
            add("error", "PLAN_INTAKE", f"高中 {h.code} 不在第三批招生，不能设置第 {plan.batch} 批计划", "plan", plan.id)
        if plan.batch == 4 and h.intake_batch != 4:
            add("error", "PLAN_INTAKE", f"高中 {h.code} 不在第四批招生，不能设置第四批计划", "plan", plan.id)
        key = (plan.high_school_id, plan.batch, plan.middle_school_id)
        if key in plan_keys:
            add("error", "PLAN_DUP", f"计划重复：高中 {h.code} 批次 {plan.batch} 初中 {plan.middle_school_id}", "plan", plan.id)
        else:
            plan_keys[key] = plan.id

    for h in ds.high_schools.values():
        if h.id not in plans_by_high:
            add("warning", "HS_NO_PLAN", f"高中 {h.code} 没有任何招生计划", "high_school", h.id)
            continue
        total = sum(pl.initial_quota for pl in plans_by_high[h.id])
        if h.total_plan > 0 and total != h.total_plan:
            add(
                "warning", "HS_PLAN_TOTAL",
                f"高中 {h.code} 总计划 {h.total_plan} 与各批计划合计 {total} 不一致",
                "high_school", h.id,
            )

    # ---- 自主招生资格 ------------------------------------------------
    qual_keys: set[tuple[int, int]] = set()
    qual_ranks: dict[tuple[int, int], int] = {}
    for q in ds.qualifications:
        c = ds.candidates.get(q.candidate_id)
        h = ds.high_schools.get(q.high_school_id)
        if c is None:
            add("error", "QUAL_CAND", f"资格记录引用不存在的考生 {q.candidate_id}", "qualification")
            continue
        if h is None:
            add("error", "QUAL_HS", f"资格记录引用不存在的高中 {q.high_school_id}", "qualification")
            continue
        if not h.has_autonomous:
            add("error", "QUAL_HS_AUTO", f"高中 {h.code} 未获批自主招生，不能有资格名单", "qualification", c.candidate_no)
        if q.status not in ("qualified", "disqualified"):
            add("error", "QUAL_STATUS", f"考生 {c.candidate_no} 资格状态非法", "qualification", c.candidate_no)
        key = (q.candidate_id, q.high_school_id)
        if key in qual_keys:
            add("error", "QUAL_DUP", f"考生 {c.candidate_no} 在高中 {h.code} 的资格记录重复", "qualification", c.candidate_no)
        qual_keys.add(key)
        if q.status == "qualified":
            if q.rank is None or q.rank <= 0:
                add("error", "QUAL_RANK", f"考生 {c.candidate_no} 已获资格但缺少有效考核排名", "qualification", c.candidate_no)
            else:
                rkey = (q.high_school_id, q.rank)
                if rkey in qual_ranks:
                    add(
                        "error", "QUAL_RANK_DUP",
                        f"高中 {h.code} 考核排名 {q.rank} 重复（考生 {c.candidate_no}）",
                        "qualification", c.candidate_no,
                    )
                else:
                    qual_ranks[rkey] = q.candidate_id

    # ---- 志愿 ---------------------------------------------------------
    vol_keys: set[tuple[int, int, int]] = set()
    vol_highs: set[tuple[int, int, int]] = set()
    for v in ds.volunteers:
        c = ds.candidates.get(v.candidate_id)
        h = ds.high_schools.get(v.high_school_id)
        if c is None:
            add("error", "VOL_CAND", f"志愿引用不存在的考生 {v.candidate_id}", "volunteer")
            continue
        if h is None:
            add("error", "VOL_HS", f"考生 {c.candidate_no} 的志愿引用不存在的高中", "volunteer", c.candidate_no)
            continue
        if v.batch not in VOLUNTEER_LIMITS:
            add("error", "VOL_BATCH", f"考生 {c.candidate_no} 志愿批次非法", "volunteer", c.candidate_no)
            continue
        if not (1 <= v.seq <= VOLUNTEER_LIMITS[v.batch]):
            add(
                "error", "VOL_SEQ",
                f"考生 {c.candidate_no} 第 {v.batch} 批志愿序号 {v.seq} 超出上限 {VOLUNTEER_LIMITS[v.batch]}",
                "volunteer", c.candidate_no,
            )
        key = (v.candidate_id, v.batch, v.seq)
        if key in vol_keys:
            add("error", "VOL_SEQ_DUP", f"考生 {c.candidate_no} 第 {v.batch} 批第 {v.seq} 志愿重复", "volunteer", c.candidate_no)
        vol_keys.add(key)
        hkey = (v.candidate_id, v.batch, v.high_school_id)
        if hkey in vol_highs:
            add("error", "VOL_HS_DUP", f"考生 {c.candidate_no} 在第 {v.batch} 批重复填报 {h.code}", "volunteer", c.candidate_no)
        vol_highs.add(hkey)

        if v.batch == 1:
            if not h.has_autonomous:
                add("error", "VOL_AUTONOMOUS", f"考生 {c.candidate_no} 第一批志愿 {h.code} 不参加自主招生", "volunteer", c.candidate_no)
            if (c.id, h.id) not in ds.qualification_map:
                add(
                    "warning", "VOL_NO_QUAL",
                    f"考生 {c.candidate_no} 填报 {h.code} 自主招生但不在资格名单内",
                    "volunteer", c.candidate_no,
                )
        elif v.batch in (2, 3):
            if h.intake_batch != 3:
                add("error", "VOL_INTAKE", f"考生 {c.candidate_no} 第 {v.batch} 批志愿 {h.code} 不在第三批招生", "volunteer", c.candidate_no)
            if v.batch == 2 and (h.id, c.middle_school_id) not in ds.plan_by_high_middle:
                add(
                    "warning", "VOL_NO_ALLOCATION",
                    f"考生 {c.candidate_no} 所属初中未获得 {h.code} 名额分配指标，该志愿不可用",
                    "volunteer", c.candidate_no,
                )
        elif v.batch == 4:
            if h.intake_batch != 4:
                add("error", "VOL_INTAKE", f"考生 {c.candidate_no} 第四批志愿 {h.code} 不在第四批招生", "volunteer", c.candidate_no)

    if raise_on_error and any(i.level == "error" for i in issues):
        raise DatasetValidationError(issues)
    return issues


def format_issues(issues: Iterable[ValidationIssue]) -> str:
    return "\n".join(f"[{i.level}] {i.message}" for i in issues)
