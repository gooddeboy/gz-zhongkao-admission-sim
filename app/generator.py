"""可重复生成的虚构演示数据。

- small：读取人工设计的小数据集 fixtures/small_main.json；
- demo：500 所初中、150 所公办高中、2 万名考生；
- full：500 所初中、150 所公办高中、15 万名考生（任务书加分项规模）。

所有随机过程使用固定种子，生成结果可重复。数据全部为虚构，
不使用任何真实考生个人信息。
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

from .engine import (
    Candidate,
    Dataset,
    HighSchool,
    MiddleSchool,
    Params,
    Plan,
    Qualification,
    Volunteer,
    max_gradient_band,
)

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURE_DIR = BASE_DIR / "data" / "fixtures"

DISTRICTS = [
    "越秀区", "荔湾区", "海珠区", "天河区", "白云区", "黄埔区",
    "番禺区", "花都区", "南沙区", "从化区", "增城区",
]
SURNAMES = list("陈李黄张刘梁罗何吴林周郭冯邓许谢曾钟叶谭赖欧杨朱蔡徐孙马高胡余潘卢唐岑彭蒋韦黎宋郑梁冯")
GIVEN = [
    "晨", "曦", "悦", "然", "敏", "洋", "磊", "雨", "桐", "楠", "浩", "琳", "峰", "月", "凯", "静",
    "晴", "轩", "宇", "欣", "怡", "嘉", "俊", "杰", "思", "远", "博", "文", "武", "安", "宁", "乐",
    "子", "涵", "睿", "琪", "瑶", "婷", "倩", "雪", "冰", "清", "海", "涛", "鹏", "飞", "龙", "虎",
    "家", "国", "志", "明", "亮", "华", "建", "强", "伟", "芳", "丽", "娜", "秀", "英", "慧", "颖",
]


def load_fixture(name: str) -> Dataset:
    path = FIXTURE_DIR / (name if name.endswith(".json") else name + ".json")
    with open(path, "r", encoding="utf-8") as f:
        return Dataset.from_dict(json.load(f))


def save_fixture(ds: Dataset, path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ds.to_dict(), f, ensure_ascii=False, indent=2)


def _clamp(value: int, low: int = 250, high: int = 750) -> int:
    return max(low, min(high, value))


def _weighted_sample(
    items: list[Any], weights: list[float], k: int, rng: random.Random
) -> list[Any]:
    """按权重不放回抽样。"""
    items = list(items)
    weights = list(weights)
    chosen: list[Any] = []
    for _ in range(min(k, len(items))):
        total = sum(weights)
        if total <= 0:
            break
        r = rng.random() * total
        acc = 0.0
        for i, w in enumerate(weights):
            acc += w
            if r <= acc:
                chosen.append(items.pop(i))
                weights.pop(i)
                break
    return chosen


def _distribute(total: int, weights: list[float], rng: random.Random) -> list[int]:
    """把整数 total 按权重分配到 len(weights) 个对象，每个至少 1。"""
    n = len(weights)
    if n == 0:
        return []
    if total <= n:
        return [1] * total + [0] * (n - total)
    base = [1] * n
    remaining = total - n
    s = sum(weights)
    if s <= 0:
        weights = [1.0] * n
        s = float(n)
    raw = [remaining * w / s for w in weights]
    floors = [int(math.floor(x)) for x in raw]
    used = sum(floors)
    result = [base[i] + floors[i] for i in range(n)]
    leftover = remaining - used
    order = sorted(range(n), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in order[:leftover]:
        result[i] += 1
    return result


def _make_name(rng: random.Random) -> str:
    return rng.choice(SURNAMES) + rng.choice(GIVEN) + (rng.choice(GIVEN) if rng.random() < 0.35 else "")


def generate_dataset(
    seed: int = 2026,
    middle_count: int = 500,
    high_count: int = 150,
    candidate_count: int = 20000,
    year: int = 2026,
    g1: int = 712,
    delta: int = 40,
    city_line: int = 492,
    auto_g1: bool = False,
) -> Dataset:
    rng = random.Random(seed)
    if middle_count < 1 or high_count < 1 or candidate_count < 1:
        raise ValueError("学校数和考生数必须为正整数")

    # ---- 初中 ---------------------------------------------------------
    middle_schools: dict[int, MiddleSchool] = {}
    middle_quality: dict[int, float] = {}
    for i in range(1, middle_count + 1):
        district = DISTRICTS[(i - 1) % len(DISTRICTS)]
        quality = min(1.3, max(0.75, rng.gauss(1.0, 0.12)))
        middle_schools[i] = MiddleSchool(
            id=i, code=f"M{i:03d}",
            name=f"{district}第{(i - 1) // len(DISTRICTS) + 1:02d}初级中学",
            district=district,
        )
        middle_quality[i] = quality

    # ---- 高中 ---------------------------------------------------------
    high_schools: dict[int, HighSchool] = {}
    high_prestige: dict[int, float] = {}
    batch3_count = max(1, int(high_count * 2 / 3))
    batch4_count = high_count - batch3_count
    for i in range(1, high_count + 1):
        is_batch3 = i <= batch3_count
        district = DISTRICTS[(i - 1) % len(DISTRICTS)]
        if is_batch3:
            total = rng.randint(300, 800)
            has_auto = rng.random() < 0.6
            prestige = min(1.0, max(0.35, rng.gauss(0.68, 0.18)))
            category = "示范性"
            intake = 3
            name = f"{district}第{(i - 1) // len(DISTRICTS) + 1:02d}示范性高中"
        else:
            total = rng.randint(200, 500)
            has_auto = False
            prestige = min(0.75, max(0.15, rng.gauss(0.42, 0.15)))
            category = "非示范"
            intake = 4
            name = f"{district}第{(i - 1) // len(DISTRICTS) + 1:02d}普通高中"
        high_schools[i] = HighSchool(
            id=i, code=f"G{i:03d}", name=name, category=category,
            intake_batch=intake, has_autonomous=has_auto, total_plan=total,
        )
        high_prestige[i] = prestige

    # ---- 考生 ---------------------------------------------------------
    middle_ids = list(middle_schools.keys())
    middle_weights = [middle_quality[i] ** 2 for i in middle_ids]
    assigned = rng.choices(middle_ids, weights=middle_weights, k=candidate_count)
    candidates: dict[int, Candidate] = {}
    score_counts: dict[int, int] = defaultdict(int)
    for i in range(1, candidate_count + 1):
        mid = assigned[i - 1]
        q = middle_quality[mid]
        roll = rng.random()
        if roll < 0.10:
            score = rng.gauss(705, 32)
        elif roll < 0.20:
            score = rng.gauss(505, 45)
        else:
            score = rng.gauss(600 + (q - 1.0) * 40, 78)
        score = _clamp(int(round(score)))
        score_counts[score] += 1
        candidates[i] = Candidate(
            id=i, candidate_no=f"ZK{year}{i:06d}", name=_make_name(rng),
            middle_school_id=mid, score=score, tie_seq=score_counts[score],
        )

    if auto_g1:
        sorted_scores = sorted((c.score for c in candidates.values()), reverse=True)
        idx = max(0, math.ceil(len(sorted_scores) * 0.10) - 1)
        g1 = sorted_scores[idx]
        g1 = max(g1, city_line)

    params = Params(year=year, g1=g1, delta=delta, city_line=city_line, trace_level="summary")
    max_band = max_gradient_band(g1, delta, city_line)

    # ---- 招生计划 -----------------------------------------------------
    plans: dict[int, Plan] = {}
    alloc_by_middle: dict[int, list[tuple[int, int]]] = defaultdict(list)
    plan_id = 1
    for h in high_schools.values():
        if h.intake_batch == 4:
            plans[plan_id] = Plan(
                id=plan_id, high_school_id=h.id, batch=4, category="统招",
                initial_quota=h.total_plan, control_line=city_line,
                note=f"{h.name}第四批统招",
            )
            plan_id += 1
            continue

        auto_quota = max(1, round(h.total_plan * 0.10)) if h.has_autonomous else 0
        quota_total = round(h.total_plan * 0.50)
        if auto_quota + quota_total >= h.total_plan:
            quota_total = max(0, h.total_plan - auto_quota - 1)
        batch3_initial = h.total_plan - auto_quota - quota_total

        if auto_quota > 0:
            plans[plan_id] = Plan(
                id=plan_id, high_school_id=h.id, batch=1, category="自主招生",
                initial_quota=auto_quota, control_line=city_line,
                note=f"{h.name}自主招生",
            )
            plan_id += 1

        if quota_total > 0:
            k = min(middle_count, max(3, min(150, quota_total // 8)))
            weights = [middle_quality[m] ** 2 for m in middle_ids]
            chosen = _weighted_sample(middle_ids, weights, k, rng)
            quotas = _distribute(quota_total, [middle_quality[m] for m in chosen], rng)
            for m, q in zip(chosen, quotas):
                if q <= 0:
                    continue
                plans[plan_id] = Plan(
                    id=plan_id, high_school_id=h.id, batch=2, category="名额分配",
                    initial_quota=q, control_line=city_line, middle_school_id=m,
                    note=f"{h.name}→{middle_schools[m].name}",
                )
                alloc_by_middle[m].append((h.id, q))
                plan_id += 1

        if batch3_initial > 0:
            plans[plan_id] = Plan(
                id=plan_id, high_school_id=h.id, batch=3, category="统招",
                initial_quota=batch3_initial, control_line=city_line,
                note=f"{h.name}第三批统招",
            )
            plan_id += 1

    # ---- 自主招生资格 -------------------------------------------------
    qualifications: list[Qualification] = []
    eligible_ids = [c.id for c in candidates.values() if c.score >= city_line]
    batch1_plans = [p for p in plans.values() if p.batch == 1]
    for plan in batch1_plans:
        if not eligible_ids:
            break
        qcount = min(len(eligible_ids), max(plan.initial_quota * 3, plan.initial_quota + 5))
        chosen = rng.sample(eligible_ids, qcount)
        ranks = list(range(1, qcount + 1))
        rng.shuffle(ranks)
        for cid, rank in zip(chosen, ranks):
            qualifications.append(
                Qualification(candidate_id=cid, high_school_id=plan.high_school_id, status="qualified", rank=rank)
            )
        # 少量不合格记录，便于演示资格状态过滤
        chosen_set = set(chosen)
        pool = [cid for cid in eligible_ids if cid not in chosen_set]
        if pool:
            for cid in rng.sample(pool, min(5, len(pool))):
                qualifications.append(
                    Qualification(candidate_id=cid, high_school_id=plan.high_school_id, status="disqualified", rank=None)
                )

    # ---- 志愿 ---------------------------------------------------------
    volunteers: list[Volunteer] = []
    batch1_filled: set[int] = set()

    # 第一批
    for q in qualifications:
        if q.status != "qualified":
            continue
        if q.candidate_id in batch1_filled:
            continue
        if rng.random() < 0.55:
            volunteers.append(Volunteer(candidate_id=q.candidate_id, batch=1, seq=1, high_school_id=q.high_school_id))
            batch1_filled.add(q.candidate_id)

    # 第三批偏好：按梯度准备候选高中列表
    batch3_highs = [h for h in high_schools.values() if h.intake_batch == 3]
    batch4_highs = [h for h in high_schools.values() if h.intake_batch == 4]
    pref_by_band: dict[int, list[int]] = {}
    for band in range(1, max_band + 1):
        target = 1.0 - (band - 1) * 0.13
        ranked = sorted(
            batch3_highs,
            key=lambda h: abs(high_prestige[h.id] - target) + rng.random() * 0.30,
        )
        pref_by_band[band] = [h.id for h in ranked[: min(30, len(ranked))]]

    batch4_pref = [h.id for h in batch4_highs]
    rng.shuffle(batch4_pref)

    for c in candidates.values():
        # 第二批：只能从本校获得的名额中选
        allocs = alloc_by_middle.get(c.middle_school_id, [])
        if allocs and rng.random() < 0.65:
            k = rng.choices([1, 2, 3], weights=[0.45, 0.35, 0.20])[0]
            k = min(k, len(allocs))
            items = [a[0] for a in allocs]
            weights = [a[1] * (0.5 + high_prestige[a[0]]) for a in allocs]
            chosen = _weighted_sample(items, weights, k, rng)
            chosen.sort(key=lambda hid: high_prestige[hid] + rng.random() * 0.25, reverse=True)
            for seq, hid in enumerate(chosen, start=1):
                volunteers.append(Volunteer(candidate_id=c.id, batch=2, seq=seq, high_school_id=hid))

        # 第三批：梯度匹配的偏好高中
        band = None
        if c.score >= city_line:
            if c.score >= g1:
                band = 1
            else:
                band = 2 + (g1 - c.score - 1) // delta
        if band is not None and band <= max_band:
            prob = 0.90 if band <= 4 else 0.70
            if rng.random() < prob:
                k = rng.choices([1, 2, 3, 4, 5, 6], weights=[0.12, 0.16, 0.20, 0.20, 0.17, 0.15])[0]
                pool = pref_by_band.get(band, [])
                k = min(k, len(pool))
                chosen = rng.sample(pool[: min(12, len(pool))], k) if k else []
                chosen.sort(key=lambda hid: pool.index(hid) + rng.random() * 0.8)
                for seq, hid in enumerate(chosen, start=1):
                    volunteers.append(Volunteer(candidate_id=c.id, batch=3, seq=seq, high_school_id=hid))

        # 第四批：低分考生更倾向填保底
        if batch4_pref:
            prob = 0.35 if c.score >= g1 else (0.55 if c.score >= g1 - 2 * delta else 0.75)
            if rng.random() < prob:
                k = rng.choices([1, 2, 3, 4, 5, 6], weights=[0.18, 0.20, 0.20, 0.18, 0.14, 0.10])[0]
                k = min(k, len(batch4_pref))
                chosen = rng.sample(batch4_pref[: min(20, len(batch4_pref))], k) if k else []
                for seq, hid in enumerate(chosen, start=1):
                    volunteers.append(Volunteer(candidate_id=c.id, batch=4, seq=seq, high_school_id=hid))

    ds = Dataset(
        params=params,
        high_schools=high_schools,
        middle_schools=middle_schools,
        candidates=candidates,
        plans=plans,
        qualifications=qualifications,
        volunteers=volunteers,
    )
    return ds.build_indexes()


PRESETS: dict[str, dict[str, Any]] = {
    "small": {"middle_count": 2, "high_count": 4, "candidate_count": 17, "g1": 720, "city_line": 600},
    "medium": {"middle_count": 100, "high_count": 30, "candidate_count": 3000, "g1": 712, "city_line": 492},
    "demo": {"middle_count": 300, "high_count": 60, "candidate_count": 20000, "g1": 712, "city_line": 492},
    "full": {"middle_count": 500, "high_count": 150, "candidate_count": 150000, "g1": 712, "city_line": 492},
}


def generate_preset(preset: str, seed: int = 2026) -> Dataset:
    if preset == "small":
        return load_fixture("small_main")
    if preset not in PRESETS:
        raise ValueError(f"未知预设：{preset}")
    cfg = PRESETS[preset]
    return generate_dataset(
        seed=seed,
        middle_count=cfg["middle_count"],
        high_count=cfg["high_count"],
        candidate_count=cfg["candidate_count"],
        g1=cfg["g1"],
        delta=40,
        city_line=cfg["city_line"],
        auto_g1=False,
    )
