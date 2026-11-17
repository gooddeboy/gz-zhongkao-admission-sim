"""FastAPI 应用：REST API + 静态前端。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import Body, Depends, FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .cases import case_list, run_case
from .db import (
    DEFAULT_DB_PATH,
    SNAPSHOT_DIR,
    AppError,
    DataConflictError,
    DatasetLockedError,
    NotFoundError,
    RunStateError,
    connect,
    create_run,
    dataset_counts,
    execute_all,
    execute_batch,
    get_meta,
    get_run,
    init_db,
    list_runs,
    load_dataset,
    replace_dataset,
    run_progress,
    unlock_dataset,
    verify_run_db,
)
from .engine import BATCH_NAMES, Params, band_range_text, max_gradient_band
from .generator import PRESETS, generate_dataset, generate_preset, load_fixture
from .importer import (
    CsvImportError,
    import_candidates,
    import_high_schools,
    import_middle_schools,
    import_plans,
    import_qualifications,
    import_volunteers,
)
from .repository import (
    create_candidate,
    create_high_school,
    create_middle_school,
    create_plan,
    create_qualification,
    create_volunteer,
    delete_candidate,
    delete_high_school,
    delete_middle_school,
    delete_plan,
    delete_qualification,
    delete_volunteer,
    get_candidate,
    get_high_school,
    get_middle_school,
    get_plan,
    get_qualification,
    get_volunteer,
    list_candidates,
    list_high_schools,
    list_middle_schools,
    list_plans,
    list_qualifications,
    list_volunteers,
    update_candidate,
    update_high_school,
    update_middle_school,
    update_plan,
    update_qualification,
    update_volunteer,
    validate_current,
)
from .stats import (
    candidate_result,
    compute_stats,
    export_csv,
    list_admissions,
    list_events,
    list_run_candidates,
    list_transfers,
    plan_balances,
)
from .validation import DatasetValidationError, ValidationIssue

STATIC_DIR = Path(__file__).resolve().parent / "static"


class RunCreate(BaseModel):
    year: Optional[int] = None
    g1: int = Field(712, ge=0, le=750)
    delta: int = Field(40, gt=0, le=200)
    city_line: int = Field(492, ge=0, le=750)
    trace_level: str = "summary"
    note: str = ""


class GenerateRequest(BaseModel):
    preset: str = "demo"
    seed: int = 2026
    middle_count: Optional[int] = None
    high_count: Optional[int] = None
    candidate_count: Optional[int] = None
    g1: Optional[int] = None
    delta: int = 40
    city_line: Optional[int] = None
    auto_g1: bool = False
    confirm_reset: bool = False


class UnlockRequest(BaseModel):
    confirm: bool = False


class ImportRequest(BaseModel):
    csv: str


class CaseRunRequest(BaseModel):
    key: Optional[str] = None


def create_app(
    db_path: str | os.PathLike[str] = DEFAULT_DB_PATH,
    snapshot_dir: str | os.PathLike[str] = SNAPSHOT_DIR,
) -> FastAPI:
    app = FastAPI(
        title="简化广州中考公办高中录取模拟系统",
        description="课程设计：四批次投档、名额分配、梯度志愿、计划结转与结果统计。",
        version=__version__,
    )
    app.state.db_path = str(db_path)
    app.state.snapshot_dir = str(snapshot_dir)

    bootstrap = connect(db_path)
    init_db(bootstrap)
    bootstrap.close()

    def get_db():
        conn = connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    # ---- 异常处理 -----------------------------------------------------
    @app.exception_handler(DatasetLockedError)
    async def _locked(_request, exc: DatasetLockedError):
        return JSONResponse(status_code=409, content={"detail": str(exc), "code": "DATASET_LOCKED"})

    @app.exception_handler(DataConflictError)
    async def _conflict(_request, exc: DataConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc), "code": "DATA_CONFLICT"})

    @app.exception_handler(RunStateError)
    async def _run_state(_request, exc: RunStateError):
        return JSONResponse(status_code=409, content={"detail": str(exc), "code": "RUN_STATE"})

    @app.exception_handler(NotFoundError)
    async def _not_found(_request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc), "code": "NOT_FOUND"})

    @app.exception_handler(DatasetValidationError)
    async def _validation(_request, exc: DatasetValidationError):
        return JSONResponse(
            status_code=400,
            content={
                "detail": "数据校验失败",
                "code": "VALIDATION_ERROR",
                "issues": [i.to_dict() for i in exc.issues],
            },
        )

    @app.exception_handler(CsvImportError)
    async def _import(_request, exc: CsvImportError):
        return JSONResponse(
            status_code=400,
            content={"detail": "CSV 导入失败", "code": "IMPORT_ERROR", "errors": exc.errors},
        )

    @app.exception_handler(AppError)
    async def _app_error(_request, exc: AppError):
        return JSONResponse(status_code=400, content={"detail": str(exc), "code": "APP_ERROR"})

    @app.exception_handler(sqlite3.IntegrityError)
    async def _integrity(_request, exc: sqlite3.IntegrityError):
        return JSONResponse(
            status_code=400,
            content={"detail": f"数据库约束冲突：{exc}", "code": "INTEGRITY_ERROR"},
        )

    @app.exception_handler(ValueError)
    async def _value(_request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc), "code": "VALUE_ERROR"})

    # ---- 基础信息 -----------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    @app.get("/api/meta")
    def meta(conn: sqlite3.Connection = Depends(get_db)):
        m = get_meta(conn)
        counts = dataset_counts(conn)
        runs = list_runs(conn, 1)
        defaults = {
            "year": m["year"],
            "g1": m.get("default_g1", 712),
            "delta": m.get("default_delta", 40),
            "city_line": m.get("default_city_line", 492),
        }
        max_band = max_gradient_band(defaults["g1"], defaults["delta"], defaults["city_line"])
        bands = [
            {
                "band": b,
                "range": band_range_text(b, defaults["g1"], defaults["delta"], defaults["city_line"]),
            }
            for b in range(1, max_band + 1)
        ]
        locked_run = get_run(conn, m["locked_by_run_id"]) if m.get("locked_by_run_id") else None
        return {
            "meta": m,
            "counts": counts,
            "defaults": defaults,
            "bands": bands,
            "presets": [
                {"key": "small", "name": "人工小数据集（17 人）", "counts": PRESETS["small"]},
                {"key": "medium", "name": "中等规模（3 千人）", "counts": PRESETS["medium"]},
                {"key": "demo", "name": "较大规模演示（300 初中 / 60 高中 / 2 万考生）", "counts": PRESETS["demo"]},
                {"key": "full", "name": "任务书加分规模（15 万人）", "counts": PRESETS["full"]},
            ],
            "last_run": runs[0] if runs else None,
            "locked_run": locked_run,
        }

    @app.post("/api/dataset/generate")
    def generate(body: GenerateRequest, conn: sqlite3.Connection = Depends(get_db)):
        meta_row = get_meta(conn)
        counts = dataset_counts(conn)
        has_data = any(counts.values())
        if (meta_row["locked"] or has_data) and not body.confirm_reset:
            raise DataConflictError("已有数据或数据已锁定；生成新数据会清空输入并删除历史运行，请确认后重试")
        if meta_row["locked"]:
            unlock_dataset(conn)

        if body.preset == "small":
            ds = load_fixture("small_main")
            seed = None
            note = "人工设计小数据集"
        elif body.preset in ("medium", "demo", "full"):
            ds = generate_preset(body.preset, seed=body.seed)
            seed = body.seed
            note = f"预设 {body.preset}，随机种子 {body.seed}"
        elif body.preset == "custom":
            if not body.middle_count or not body.high_count or not body.candidate_count:
                raise ValueError("自定义数据必须提供初中数、高中数和考生数")
            ds = generate_dataset(
                seed=body.seed,
                middle_count=body.middle_count,
                high_count=body.high_count,
                candidate_count=body.candidate_count,
                g1=body.g1 if body.g1 is not None else 712,
                delta=body.delta,
                city_line=body.city_line if body.city_line is not None else 492,
                auto_g1=body.auto_g1,
            )
            seed = body.seed
            note = f"自定义生成，随机种子 {body.seed}"
        else:
            raise ValueError(f"未知预设：{body.preset}")

        new_counts = replace_dataset(conn, ds, seed=seed, delete_runs=True, note=note)
        return {
            "counts": new_counts,
            "meta": get_meta(conn),
            "params": ds.params.to_dict(),
            "note": note,
        }

    @app.post("/api/dataset/unlock")
    def unlock(body: UnlockRequest, conn: sqlite3.Connection = Depends(get_db)):
        if not body.confirm:
            raise ValueError("请确认创建新的数据版本")
        return {"meta": unlock_dataset(conn)}

    @app.get("/api/validate")
    def validate(conn: sqlite3.Connection = Depends(get_db)):
        return validate_current(conn)

    # ---- 高中 ---------------------------------------------------------
    @app.get("/api/high-schools")
    def high_schools(
        page: int = 1, size: int = 20, q: str = "", intake_batch: Optional[int] = None,
        category: str = "", conn: sqlite3.Connection = Depends(get_db),
    ):
        return list_high_schools(conn, page, size, q, intake_batch, category)

    @app.post("/api/high-schools")
    def high_school_create(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return create_high_school(conn, payload)

    @app.get("/api/high-schools/{high_id}")
    def high_school_get(high_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return get_high_school(conn, high_id)

    @app.put("/api/high-schools/{high_id}")
    def high_school_update(high_id: int, payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return update_high_school(conn, high_id, payload)

    @app.delete("/api/high-schools/{high_id}")
    def high_school_delete(high_id: int, conn: sqlite3.Connection = Depends(get_db)):
        delete_high_school(conn, high_id)
        return {"ok": True}

    # ---- 初中 ---------------------------------------------------------
    @app.get("/api/middle-schools")
    def middle_schools(
        page: int = 1, size: int = 20, q: str = "", district: str = "",
        conn: sqlite3.Connection = Depends(get_db),
    ):
        return list_middle_schools(conn, page, size, q, district)

    @app.post("/api/middle-schools")
    def middle_school_create(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return create_middle_school(conn, payload)

    @app.get("/api/middle-schools/{middle_id}")
    def middle_school_get(middle_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return get_middle_school(conn, middle_id)

    @app.put("/api/middle-schools/{middle_id}")
    def middle_school_update(middle_id: int, payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return update_middle_school(conn, middle_id, payload)

    @app.delete("/api/middle-schools/{middle_id}")
    def middle_school_delete(middle_id: int, conn: sqlite3.Connection = Depends(get_db)):
        delete_middle_school(conn, middle_id)
        return {"ok": True}

    # ---- 考生 ---------------------------------------------------------
    @app.get("/api/candidates")
    def candidates(
        page: int = 1, size: int = 20, q: str = "", middle_school_id: Optional[int] = None,
        min_score: Optional[int] = None, max_score: Optional[int] = None, sort: str = "id",
        conn: sqlite3.Connection = Depends(get_db),
    ):
        return list_candidates(conn, page, size, q, middle_school_id, min_score, max_score, sort)

    @app.post("/api/candidates")
    def candidate_create(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return create_candidate(conn, payload)

    @app.get("/api/candidates/{candidate_id}")
    def candidate_get(candidate_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return get_candidate(conn, candidate_id)

    @app.put("/api/candidates/{candidate_id}")
    def candidate_update(candidate_id: int, payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return update_candidate(conn, candidate_id, payload)

    @app.delete("/api/candidates/{candidate_id}")
    def candidate_delete(candidate_id: int, conn: sqlite3.Connection = Depends(get_db)):
        delete_candidate(conn, candidate_id)
        return {"ok": True}

    # ---- 招生计划 -----------------------------------------------------
    @app.get("/api/plans")
    def plans(
        page: int = 1, size: int = 50, batch: Optional[int] = None,
        high_school_id: Optional[int] = None, middle_school_id: Optional[int] = None,
        q: str = "", conn: sqlite3.Connection = Depends(get_db),
    ):
        return list_plans(conn, page, size, batch, high_school_id, middle_school_id, q)

    @app.post("/api/plans")
    def plan_create(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return create_plan(conn, payload)

    @app.get("/api/plans/{plan_id}")
    def plan_get(plan_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return get_plan(conn, plan_id)

    @app.put("/api/plans/{plan_id}")
    def plan_update(plan_id: int, payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return update_plan(conn, plan_id, payload)

    @app.delete("/api/plans/{plan_id}")
    def plan_delete(plan_id: int, conn: sqlite3.Connection = Depends(get_db)):
        delete_plan(conn, plan_id)
        return {"ok": True}

    # ---- 资格 ---------------------------------------------------------
    @app.get("/api/qualifications")
    def qualifications(
        page: int = 1, size: int = 50, high_school_id: Optional[int] = None,
        status: str = "", q: str = "", conn: sqlite3.Connection = Depends(get_db),
    ):
        return list_qualifications(conn, page, size, high_school_id, status, q)

    @app.post("/api/qualifications")
    def qualification_create(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return create_qualification(conn, payload)

    @app.get("/api/qualifications/{qual_id}")
    def qualification_get(qual_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return get_qualification(conn, qual_id)

    @app.put("/api/qualifications/{qual_id}")
    def qualification_update(qual_id: int, payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return update_qualification(conn, qual_id, payload)

    @app.delete("/api/qualifications/{qual_id}")
    def qualification_delete(qual_id: int, conn: sqlite3.Connection = Depends(get_db)):
        delete_qualification(conn, qual_id)
        return {"ok": True}

    # ---- 志愿 ---------------------------------------------------------
    @app.get("/api/volunteers")
    def volunteers(
        page: int = 1, size: int = 50, candidate_id: Optional[int] = None,
        batch: Optional[int] = None, high_school_id: Optional[int] = None, q: str = "",
        conn: sqlite3.Connection = Depends(get_db),
    ):
        return list_volunteers(conn, page, size, candidate_id, batch, high_school_id, q)

    @app.post("/api/volunteers")
    def volunteer_create(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return create_volunteer(conn, payload)

    @app.get("/api/volunteers/{vol_id}")
    def volunteer_get(vol_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return get_volunteer(conn, vol_id)

    @app.put("/api/volunteers/{vol_id}")
    def volunteer_update(vol_id: int, payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_db)):
        return update_volunteer(conn, vol_id, payload)

    @app.delete("/api/volunteers/{vol_id}")
    def volunteer_delete(vol_id: int, conn: sqlite3.Connection = Depends(get_db)):
        delete_volunteer(conn, vol_id)
        return {"ok": True}

    # ---- CSV 导入 -----------------------------------------------------
    IMPORTERS = {
        "high-schools": import_high_schools,
        "middle-schools": import_middle_schools,
        "candidates": import_candidates,
        "plans": import_plans,
        "qualifications": import_qualifications,
        "volunteers": import_volunteers,
    }

    @app.post("/api/import/{entity}")
    def import_csv(entity: str, body: ImportRequest, conn: sqlite3.Connection = Depends(get_db)):
        fn = IMPORTERS.get(entity)
        if fn is None:
            raise NotFoundError(f"不支持的导入类型：{entity}")
        result = fn(conn, body.csv)
        return {**result, "validation": validate_current(conn)}

    # ---- 运行 ---------------------------------------------------------
    @app.post("/api/runs")
    def run_create(body: RunCreate, conn: sqlite3.Connection = Depends(get_db)):
        meta_row = get_meta(conn)
        year = body.year or meta_row["year"]
        params = Params(
            year=year, g1=body.g1, delta=body.delta, city_line=body.city_line,
            trace_level=body.trace_level,
        )
        run = create_run(conn, params, note=body.note, snapshot_dir=app.state.snapshot_dir)
        return run

    @app.get("/api/runs")
    def runs(limit: int = 50, conn: sqlite3.Connection = Depends(get_db)):
        return list_runs(conn, min(200, max(1, limit)))

    @app.get("/api/runs/{run_id}")
    def run_get(run_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return get_run(conn, run_id)

    @app.post("/api/runs/{run_id}/execute-next")
    def run_execute_next(run_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return execute_batch(conn, run_id)

    @app.post("/api/runs/{run_id}/execute-all")
    def run_execute_all(run_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return execute_all(conn, run_id)

    @app.get("/api/runs/{run_id}/progress")
    def progress(run_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return run_progress(conn, run_id)

    @app.get("/api/runs/{run_id}/verify")
    def verify(run_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return verify_run_db(conn, run_id)

    @app.get("/api/runs/{run_id}/candidates")
    def run_candidates(
        run_id: int, page: int = 1, size: int = 20, q: str = "", status: str = "",
        batch: Optional[int] = None, conn: sqlite3.Connection = Depends(get_db),
    ):
        return list_run_candidates(conn, run_id, page, size, q, status, batch)

    @app.get("/api/runs/{run_id}/candidate/{candidate_id}")
    def run_candidate(run_id: int, candidate_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return candidate_result(conn, run_id, candidate_id)

    @app.get("/api/runs/{run_id}/candidate-lookup")
    def run_candidate_lookup(run_id: int, no: str, conn: sqlite3.Connection = Depends(get_db)):
        row = conn.execute("SELECT id FROM candidates WHERE candidate_no = ?", (no,)).fetchone()
        if row is None:
            raise NotFoundError(f"考生编号不存在：{no}")
        return candidate_result(conn, run_id, row["id"])

    @app.get("/api/runs/{run_id}/admissions")
    def run_admissions(
        run_id: int, page: int = 1, size: int = 50, batch: Optional[int] = None,
        high_school_id: Optional[int] = None, middle_school_id: Optional[int] = None,
        plan_id: Optional[int] = None, q: str = "", conn: sqlite3.Connection = Depends(get_db),
    ):
        return list_admissions(
            conn, run_id, page, size, batch, high_school_id, middle_school_id, plan_id, q
        )

    @app.get("/api/runs/{run_id}/plans")
    def run_plans(
        run_id: int, batch: Optional[int] = None, high_school_id: Optional[int] = None,
        middle_school_id: Optional[int] = None, page: int = 1, size: int = 100,
        conn: sqlite3.Connection = Depends(get_db),
    ):
        return plan_balances(conn, run_id, batch, high_school_id, middle_school_id, page, size)

    @app.get("/api/runs/{run_id}/transfers")
    def run_transfers(run_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return list_transfers(conn, run_id)

    @app.get("/api/runs/{run_id}/events")
    def run_events(
        run_id: int, limit: int = 200, event_type: str = "", batch: Optional[int] = None,
        conn: sqlite3.Connection = Depends(get_db),
    ):
        return list_events(conn, run_id, limit, event_type, batch)

    @app.get("/api/runs/{run_id}/stats")
    def run_stats(run_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return compute_stats(conn, run_id)

    @app.get("/api/runs/{run_id}/export/{kind}")
    def run_export(run_id: int, kind: str, conn: sqlite3.Connection = Depends(get_db)):
        filename, data = export_csv(conn, run_id, kind)
        return Response(
            content=data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )

    @app.get("/api/runs/{run_id}/snapshot")
    def run_snapshot(run_id: int, conn: sqlite3.Connection = Depends(get_db)):
        run = get_run(conn, run_id)
        path = run.get("snapshot_path")
        if not path or not os.path.exists(path):
            raise NotFoundError("该运行的输入快照文件不存在")
        return FileResponse(
            path, media_type="application/gzip", filename=os.path.basename(path)
        )

    # ---- 滑档案例 -----------------------------------------------------
    @app.get("/api/cases/slip")
    def slip_cases():
        return case_list()

    @app.post("/api/cases/slip/run")
    def slip_run(body: CaseRunRequest):
        return run_case(body.key)

    # ---- 静态前端 -----------------------------------------------------
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse({"detail": "前端文件未找到，请访问 /docs 查看 API"}, status_code=404)

    @app.get("/favicon.ico")
    def favicon():
        return Response(status_code=204)

    return app


app = create_app()
