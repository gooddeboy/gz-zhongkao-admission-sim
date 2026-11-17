-- 简化广州中考公办高中录取模拟系统
-- SQLite 数据库结构（v1.0）
-- 说明：
--   1. 输入表保存当前数据版本；每次投档运行保存不可变快照与独立结果；
--   2. 运行结果表以 run_id 隔离，重新运行不会叠加旧录取；
--   3. run_plan_state 记录初始名额、转入、转出、已录取、余额，满足名额平衡等式。

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dataset_meta (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    year                INTEGER NOT NULL DEFAULT 2026,
    version             INTEGER NOT NULL DEFAULT 1,
    updated_at          TEXT    NOT NULL,
    locked              INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1)),
    locked_by_run_id    INTEGER,
    input_hash          TEXT,
    generator_seed      INTEGER,
    default_g1          INTEGER NOT NULL DEFAULT 712,
    default_delta       INTEGER NOT NULL DEFAULT 40,
    default_city_line   INTEGER NOT NULL DEFAULT 492,
    note                TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS high_schools (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT    NOT NULL UNIQUE,
    name                TEXT    NOT NULL,
    category            TEXT    NOT NULL CHECK (category IN ('示范性', '非示范')),
    intake_batch        INTEGER NOT NULL CHECK (intake_batch IN (3, 4)),
    has_autonomous      INTEGER NOT NULL DEFAULT 0 CHECK (has_autonomous IN (0, 1)),
    total_plan          INTEGER NOT NULL DEFAULT 0 CHECK (total_plan >= 0),
    campus              TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS middle_schools (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT    NOT NULL UNIQUE,
    name                TEXT    NOT NULL,
    district            TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS candidates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_no        TEXT    NOT NULL UNIQUE,
    name                TEXT    NOT NULL,
    middle_school_id    INTEGER NOT NULL REFERENCES middle_schools(id),
    score               INTEGER NOT NULL CHECK (score BETWEEN 0 AND 750),
    tie_seq             INTEGER NOT NULL CHECK (tie_seq > 0),
    UNIQUE (score, tie_seq)
);

CREATE TABLE IF NOT EXISTS admission_plans (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    year                INTEGER NOT NULL,
    high_school_id      INTEGER NOT NULL REFERENCES high_schools(id),
    batch               INTEGER NOT NULL CHECK (batch BETWEEN 1 AND 4),
    category            TEXT    NOT NULL,
    initial_quota       INTEGER NOT NULL CHECK (initial_quota >= 0),
    control_line        INTEGER NOT NULL CHECK (control_line >= 0),
    middle_school_id    INTEGER REFERENCES middle_schools(id),
    note                TEXT    NOT NULL DEFAULT '',
    CHECK (
        (batch = 2 AND middle_school_id IS NOT NULL)
        OR (batch <> 2 AND middle_school_id IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_plan_key
    ON admission_plans (year, high_school_id, batch, COALESCE(middle_school_id, -1));

CREATE TABLE IF NOT EXISTS autonomous_qualifications (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    year                INTEGER NOT NULL,
    candidate_id        INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    high_school_id      INTEGER NOT NULL REFERENCES high_schools(id),
    status              TEXT    NOT NULL CHECK (status IN ('qualified', 'disqualified')),
    rank                INTEGER,
    CHECK (status = 'disqualified' OR rank IS NOT NULL),
    UNIQUE (year, candidate_id, high_school_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_qual_rank
    ON autonomous_qualifications (year, high_school_id, rank)
    WHERE rank IS NOT NULL;

CREATE TABLE IF NOT EXISTS volunteers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    year                INTEGER NOT NULL,
    candidate_id        INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    batch               INTEGER NOT NULL CHECK (batch BETWEEN 1 AND 4),
    seq                 INTEGER NOT NULL CHECK (seq BETWEEN 1 AND 6),
    high_school_id      INTEGER NOT NULL REFERENCES high_schools(id),
    UNIQUE (year, candidate_id, batch, seq),
    UNIQUE (year, candidate_id, batch, high_school_id)
);

CREATE TABLE IF NOT EXISTS sim_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_code            TEXT    NOT NULL UNIQUE,
    year                INTEGER NOT NULL,
    g1                  INTEGER NOT NULL,
    delta               INTEGER NOT NULL,
    city_line           INTEGER NOT NULL,
    trace_level         TEXT    NOT NULL DEFAULT 'summary' CHECK (trace_level IN ('full', 'summary')),
    status              TEXT    NOT NULL DEFAULT 'created' CHECK (
        status IN ('created', 'batch1_done', 'batch2_done', 'batch3_done', 'completed', 'failed')
    ),
    current_batch       INTEGER NOT NULL DEFAULT 0 CHECK (current_batch BETWEEN 0 AND 4),
    dataset_version     INTEGER NOT NULL,
    input_hash          TEXT    NOT NULL,
    snapshot_path       TEXT,
    snapshot_sha256     TEXT,
    parent_run_id       INTEGER,
    note                TEXT    NOT NULL DEFAULT '',
    error_message       TEXT,
    created_at          TEXT    NOT NULL,
    finished_at         TEXT
);

CREATE TABLE IF NOT EXISTS run_plan_state (
    run_id              INTEGER NOT NULL REFERENCES sim_runs(id) ON DELETE CASCADE,
    plan_id             INTEGER NOT NULL REFERENCES admission_plans(id),
    initial_quota       INTEGER NOT NULL,
    transferred_in      INTEGER NOT NULL DEFAULT 0,
    transferred_out     INTEGER NOT NULL DEFAULT 0,
    admitted_count      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, plan_id)
);

CREATE TABLE IF NOT EXISTS run_admissions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES sim_runs(id) ON DELETE CASCADE,
    candidate_id        INTEGER NOT NULL REFERENCES candidates(id),
    plan_id             INTEGER NOT NULL REFERENCES admission_plans(id),
    high_school_id      INTEGER NOT NULL,
    middle_school_id    INTEGER NOT NULL,
    batch               INTEGER NOT NULL,
    volunteer_seq       INTEGER NOT NULL,
    score               INTEGER NOT NULL,
    tie_seq             INTEGER NOT NULL,
    band                INTEGER NOT NULL,
    admission_order     INTEGER NOT NULL,
    created_at          TEXT    NOT NULL,
    UNIQUE (run_id, candidate_id),
    UNIQUE (run_id, plan_id, admission_order)
);

CREATE INDEX IF NOT EXISTS ix_adm_run_batch ON run_admissions (run_id, batch);
CREATE INDEX IF NOT EXISTS ix_adm_run_high ON run_admissions (run_id, high_school_id);
CREATE INDEX IF NOT EXISTS ix_adm_run_middle ON run_admissions (run_id, middle_school_id);

CREATE TABLE IF NOT EXISTS run_candidate_results (
    run_id              INTEGER NOT NULL REFERENCES sim_runs(id) ON DELETE CASCADE,
    candidate_id        INTEGER NOT NULL REFERENCES candidates(id),
    batch               INTEGER NOT NULL,
    status              TEXT    NOT NULL,
    reason_code         TEXT    NOT NULL,
    reason_text         TEXT    NOT NULL,
    admitted_plan_id    INTEGER,
    detail_json         TEXT,
    PRIMARY KEY (run_id, candidate_id, batch)
);

CREATE INDEX IF NOT EXISTS ix_ccr_run_status ON run_candidate_results (run_id, status);

CREATE TABLE IF NOT EXISTS run_candidate_summary (
    run_id                  INTEGER NOT NULL REFERENCES sim_runs(id) ON DELETE CASCADE,
    candidate_id            INTEGER NOT NULL REFERENCES candidates(id),
    admitted                INTEGER NOT NULL DEFAULT 0 CHECK (admitted IN (0, 1)),
    admitted_batch          INTEGER,
    admitted_plan_id        INTEGER,
    admitted_high_school_id INTEGER,
    admitted_volunteer_seq  INTEGER,
    final_reason_code       TEXT    NOT NULL DEFAULT 'NOT_STARTED',
    final_reason_text       TEXT    NOT NULL DEFAULT '未开始投档',
    PRIMARY KEY (run_id, candidate_id)
);

CREATE INDEX IF NOT EXISTS ix_ccs_run_admitted ON run_candidate_summary (run_id, admitted);

CREATE TABLE IF NOT EXISTS run_transfers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES sim_runs(id) ON DELETE CASCADE,
    from_batch          INTEGER NOT NULL,
    from_plan_id        INTEGER NOT NULL,
    high_school_id      INTEGER NOT NULL,
    middle_school_id    INTEGER,
    amount              INTEGER NOT NULL CHECK (amount > 0),
    to_plan_id          INTEGER NOT NULL,
    group_key           TEXT    NOT NULL DEFAULT '',
    created_at          TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_transfer_run ON run_transfers (run_id, from_batch);

CREATE TABLE IF NOT EXISTS run_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES sim_runs(id) ON DELETE CASCADE,
    batch               INTEGER,
    event_type          TEXT    NOT NULL,
    candidate_id        INTEGER,
    plan_id             INTEGER,
    volunteer_seq       INTEGER,
    band                INTEGER,
    remaining_before    INTEGER,
    remaining_after     INTEGER,
    message             TEXT,
    detail_json         TEXT,
    created_at          TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_event_run ON run_events (run_id, id);

CREATE TABLE IF NOT EXISTS run_batch_summary (
    run_id              INTEGER NOT NULL REFERENCES sim_runs(id) ON DELETE CASCADE,
    batch               INTEGER NOT NULL,
    processed_candidates INTEGER NOT NULL DEFAULT 0,
    admitted_count      INTEGER NOT NULL DEFAULT 0,
    transfer_out        INTEGER NOT NULL DEFAULT 0,
    remaining_plans     INTEGER NOT NULL DEFAULT 0,
    started_at          TEXT,
    finished_at         TEXT,
    PRIMARY KEY (run_id, batch)
);

CREATE TABLE IF NOT EXISTS run_snapshots (
    run_id              INTEGER PRIMARY KEY REFERENCES sim_runs(id) ON DELETE CASCADE,
    path                TEXT    NOT NULL,
    sha256              TEXT    NOT NULL,
    size_bytes          INTEGER NOT NULL,
    created_at          TEXT    NOT NULL
);

-- 便于查询的输入索引
CREATE INDEX IF NOT EXISTS ix_cand_middle ON candidates (middle_school_id);
CREATE INDEX IF NOT EXISTS ix_cand_score ON candidates (score);
CREATE INDEX IF NOT EXISTS ix_plan_high_batch ON admission_plans (high_school_id, batch);
CREATE INDEX IF NOT EXISTS ix_qual_high ON autonomous_qualifications (high_school_id, rank);
CREATE INDEX IF NOT EXISTS ix_vol_cand ON volunteers (candidate_id, batch, seq);
CREATE INDEX IF NOT EXISTS ix_vol_batch_high ON volunteers (batch, high_school_id);
