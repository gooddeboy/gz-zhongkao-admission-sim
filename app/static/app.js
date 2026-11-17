/* 简化广州中考公办高中录取模拟系统 - 前端单页应用 */
(() => {
  "use strict";

  const App = {};
  window.App = App;

  const state = {
    meta: null,
    runs: [],
    options: { highs: [], middles: [] },
    data: { tab: "high-schools", page: 1, size: 20, q: "", batch: "", highId: "", middleId: "", status: "", candidateId: null, candidateNo: "" },
    run: null,
    progress: null,
    transfers: [],
    events: [],
    runPlans: null,
    runTab: "progress",
    runPlanBatch: "",
    runPlanPage: 1,
    resultsRunId: null,
    resultsTab: "candidate",
    stats: null,
    statsPlanFilter: "",
    statsPlanBatch: "",
    admissionsPage: 1,
    admissionsBatch: "",
    admissionsHigh: "",
    cases: [],
    caseResults: null,
  };

  const DATA_TABS = [
    ["high-schools", "高中"],
    ["middle-schools", "初中"],
    ["candidates", "考生"],
    ["plans", "招生计划"],
    ["qualifications", "自主招生资格"],
    ["volunteers", "志愿"],
  ];

  const ROUTE_NAMES = {
    overview: "概览",
    data: "数据管理",
    runs: "投档执行",
    results: "结果查询",
    stats: "统计分析",
    cases: "滑档案例",
    help: "帮助与规则",
  };

  const IMPORT_TEMPLATES = {
    "high-schools": "code,name,category,intake_batch,has_autonomous,total_plan,campus\nG901,测试示范高中,示范性,3,1,400,\nG902,测试普通高中,非示范,4,0,300,",
    "middle-schools": "code,name,district\nM901,测试初级中学,越秀区",
    candidates: "candidate_no,name,middle_school_code,score,tie_seq\nZK202690001,测试考生,M001,680,1",
    plans: "high_school_code,batch,category,initial_quota,control_line,middle_school_code,note\nG001,3,统招,100,492,,统招计划",
    qualifications: "candidate_no,high_school_code,status,rank\nZK2026000001,G001,qualified,1",
    volunteers: "candidate_no,batch,seq,high_school_code\nZK2026000001,3,1,G001",
  };

  // ---------------------------------------------------------------------
  // 基础工具
  // ---------------------------------------------------------------------
  async function api(path, options = {}) {
    const opts = { headers: { "Content-Type": "application/json" }, ...options };
    const res = await fetch(path, opts);
    let data = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      data = await res.json();
    } else {
      data = await res.text();
    }
    if (!res.ok) {
      const err = new Error((data && data.detail) || `请求失败（${res.status}）`);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (value) => (value === null || value === undefined || value === "" ? "—" : Number(value).toLocaleString("zh-CN"));
  const pct = (value) => (value === null || value === undefined ? "—" : `${(Number(value) * 100).toFixed(1)}%`);
  const num = (value) => (value === "" || value === null || value === undefined ? null : Number(value));
  const badge = (text, cls = "badge-muted") => `<span class="badge ${cls}">${esc(text)}</span>`;

  function toast(message, type = "") {
    const root = $("#toast-root");
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    root.appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  function showOverlay(text = "处理中…") {
    $("#overlay-text").textContent = text;
    $("#overlay").classList.remove("hidden");
  }
  function hideOverlay() {
    $("#overlay").classList.add("hidden");
  }

  function openModal({ title, body, okText = "保存", cancelText = "取消", wide = false, onOk, hideOk = false }) {
    const root = $("#modal-root");
    root.innerHTML = `
      <div class="modal-backdrop" id="modal-backdrop">
        <div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true">
          <div class="modal-head">
            <div class="modal-title">${esc(title)}</div>
            <button class="modal-close" type="button" aria-label="关闭">×</button>
          </div>
          <div class="modal-body">
            <div id="modal-error" class="alert bad hidden" style="margin-bottom:14px"></div>
            ${body}
          </div>
          <div class="modal-foot">
            <button class="btn" type="button" id="modal-cancel">${esc(cancelText)}</button>
            ${hideOk ? "" : `<button class="btn btn-primary" type="button" id="modal-ok">${esc(okText)}</button>`}
          </div>
        </div>
      </div>`;
    const close = () => { root.innerHTML = ""; };
    root.querySelector(".modal-close").onclick = close;
    $("#modal-cancel").onclick = close;
    $("#modal-backdrop").addEventListener("click", (e) => {
      if (e.target.id === "modal-backdrop") close();
    });
    const okBtn = $("#modal-ok");
    if (okBtn && onOk) {
      okBtn.onclick = async () => {
        okBtn.disabled = true;
        try {
          const result = await onOk();
          if (result !== false) close();
        } catch (err) {
          showModalError(err);
        } finally {
          okBtn.disabled = false;
        }
      };
    }
    document.addEventListener("keydown", function onKey(e) {
      if (e.key === "Escape") { close(); document.removeEventListener("keydown", onKey); }
    });
    return { close };
  }

  function showModalError(err) {
    const box = $("#modal-error");
    if (!box) { toast(err.message || "操作失败", "bad"); return; }
    let html = `<div><strong>操作失败：</strong>${esc(err.message || "未知错误")}</div>`;
    const data = err.data || {};
    if (Array.isArray(data.issues)) {
      html += `<ul class="notice-list">${data.issues.slice(0, 12).map((i) => `<li>[${esc(i.level)}] ${esc(i.message)}</li>`).join("")}</ul>`;
    }
    if (Array.isArray(data.errors)) {
      html += `<ul class="notice-list">${data.errors.slice(0, 12).map((e) => `<li>${esc(e)}</li>`).join("")}</ul>`;
    }
    box.innerHTML = html;
    box.classList.remove("hidden");
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function confirmDialog(title, message, onConfirm) {
    openModal({
      title,
      body: `<div class="alert info"><div>${esc(message)}</div></div>`,
      okText: "确认",
      onOk: onConfirm,
    });
  }

  function setView(html) {
    $("#view").innerHTML = html;
  }

  function renderError(err) {
    setView(`
      <div class="page-head"><div><h1 class="page-title">页面加载失败</h1><div class="page-sub">${esc(err.message || err)}</div></div></div>
      <div class="card"><div class="card-body"><button class="btn btn-primary" onclick="App.reload()">重试</button></div></div>`);
  }

  // ---------------------------------------------------------------------
  // 元数据 / 选项
  // ---------------------------------------------------------------------
  async function refreshMeta() {
    state.meta = await api("/api/meta");
    const m = state.meta;
    const b = $("#dataset-badge");
    b.textContent = `数据 v${m.meta.version} · ${m.meta.locked ? "已锁定" : "可编辑"}`;
    b.className = `badge ${m.meta.locked ? "badge-warn" : "badge-ok"}`;
  }

  async function loadOptions(force = false) {
    if (!force && state.options.highs.length && state.options.middles.length) return;
    const highs = [];
    let page = 1;
    while (true) {
      const res = await api(`/api/high-schools?page=${page}&size=200`);
      highs.push(...res.items);
      if (page >= res.pages) break;
      page += 1;
    }
    const middles = [];
    page = 1;
    while (true) {
      const res = await api(`/api/middle-schools?page=${page}&size=200`);
      middles.push(...res.items);
      if (page >= res.pages) break;
      page += 1;
    }
    state.options = { highs, middles };
  }

  const highOptions = (selected, emptyLabel = "全部高中") => {
    const opts = state.options.highs.map((h) => `<option value="${h.id}" ${String(h.id) === String(selected) ? "selected" : ""}>${esc(h.code)} · ${esc(h.name)}</option>`).join("");
    return `<option value="">${esc(emptyLabel)}</option>${opts}`;
  };
  const middleOptions = (selected, emptyLabel = "全部初中") => {
    const opts = state.options.middles.map((m) => `<option value="${m.id}" ${String(m.id) === String(selected) ? "selected" : ""}>${esc(m.code)} · ${esc(m.name)}</option>`).join("");
    return `<option value="">${esc(emptyLabel)}</option>${opts}`;
  };

  // ---------------------------------------------------------------------
  // 路由
  // ---------------------------------------------------------------------
  async function init() {
    try {
      await refreshMeta();
      window.addEventListener("hashchange", render);
      await render();
    } catch (err) {
      renderError(err);
    }
  }

  async function render() {
    const raw = (location.hash || "#/overview").replace(/^#\/?/, "");
    const parts = raw.split("/").filter(Boolean);
    const route = parts[0] || "overview";
    $$(".nav-item").forEach((a) => a.classList.toggle("active", a.dataset.route === route));
    $("#crumb").textContent = ROUTE_NAMES[route] || "概览";
    setView(`<div class="loading">加载中…</div>`);
    try {
      if (route === "overview") await renderOverview();
      else if (route === "data") await renderData(parts);
      else if (route === "runs") await renderRuns(parts);
      else if (route === "results") await renderResults(parts);
      else if (route === "stats") await renderStats(parts);
      else if (route === "cases") await renderCases(parts);
      else if (route === "help") renderHelp();
      else await renderOverview();
    } catch (err) {
      renderError(err);
    }
  }

  App.reload = () => render();
  App.goto = (hash) => { location.hash = hash; };

  // ---------------------------------------------------------------------
  // 概览
  // ---------------------------------------------------------------------
  function lockedBanner() {
    const m = state.meta && state.meta.meta;
    if (!m || !m.locked) return "";
    const run = state.meta.locked_run;
    return `<div class="alert">
      <div><strong>当前数据版本已锁定。</strong>运行 ${run ? esc(run.run_code) : "#" + m.locked_by_run_id} 已完成快照；
      为保证历史结果可复现，输入数据不能静默修改。需要修改时请创建新的数据版本。</div>
      <div class="spacer"></div>
      <button class="btn btn-sm" onclick="App.unlockDataset()">创建新数据版本</button>
    </div>`;
  }

  async function renderOverview() {
    const m = state.meta;
    const c = m.counts;
    const last = m.last_run;
    const params = m.defaults;
    const runs = await api("/api/runs?limit=6");
    const totalPlan = c.admission_plans;
    const locked = m.meta.locked;
    setView(`
      <div class="page-head">
        <div>
          <h1 class="page-title">录取模拟总览</h1>
          <div class="page-sub">按任务书简化规则实现：自主招生 → 名额分配 → 第三批统招 → 第四批统招；梯度优先、志愿轮次、名额隔离与结转均可追溯。</div>
        </div>
        <div class="actions">
          <button class="btn" onclick="App.openGenerate()">生成演示数据</button>
          <button class="btn btn-primary" onclick="App.openRunCreate()">新建投档运行</button>
        </div>
      </div>
      ${lockedBanner()}
      <div class="grid grid-5" style="margin-top:16px">
        <div class="card kpi"><div class="kpi-label">公办高中</div><div class="kpi-value">${fmt(c.high_schools)}</div><div class="kpi-foot">第三批 / 第四批</div></div>
        <div class="card kpi ok"><div class="kpi-label">初中学校</div><div class="kpi-value">${fmt(c.middle_schools)}</div><div class="kpi-foot">名额分配生源校</div></div>
        <div class="card kpi"><div class="kpi-label">考生</div><div class="kpi-value">${fmt(c.candidates)}</div><div class="kpi-foot">虚构数据</div></div>
        <div class="card kpi warn"><div class="kpi-label">招生计划</div><div class="kpi-value">${fmt(totalPlan)}</div><div class="kpi-foot">含自主招生 / 名额分配 / 统招</div></div>
        <div class="card kpi ${last && last.status === "completed" ? "ok" : ""}">
          <div class="kpi-label">最近运行</div>
          <div class="kpi-value" style="font-size:19px">${last ? esc(last.run_code) : "尚未运行"}</div>
          <div class="kpi-foot">${last ? `${esc(last.status_name)} · 已录取 ${fmt(last.admitted_count)} 人` : "建议先加载小数据集"}</div>
        </div>
      </div>

      <div class="grid grid-2" style="margin-top:16px">
        <div class="card">
          <div class="card-head"><div><div class="card-title">最近投档运行</div><div class="card-sub">每次运行都有独立快照，不会叠加旧录取</div></div><button class="btn btn-sm" onclick="App.goto('#/runs')">全部运行</button></div>
          <div class="card-body tight">
            ${runs.length ? `<div class="table-wrap"><table><thead><tr><th>运行编号</th><th>状态</th><th>进度</th><th>录取</th><th></th></tr></thead><tbody>
              ${runs.map((r) => `<tr><td class="mono">${esc(r.run_code)}</td><td>${runStatusBadge(r)}</td><td>第 ${r.current_batch} / 4 批</td><td>${fmt(r.admitted_count)}</td><td class="right"><button class="btn btn-xs" onclick="App.goto('#/runs/${r.id}')">打开</button></td></tr>`).join("")}
            </tbody></table></div>` : `<div class="empty"><strong>还没有运行记录</strong>先加载小数据集，再新建一次完整投档。</div>`}
          </div>
        </div>
        <div class="card">
          <div class="card-head"><div><div class="card-title">规则参数与梯度</div><div class="card-sub">G₁ = ${params.g1}，Δ = ${params.delta}，全市控制线 L = ${params.city_line}</div></div></div>
          <div class="card-body">
            <div class="bars">
              ${m.bands.map((b) => `<div class="bar-row"><div class="bar-label">第 ${b.band} 梯度</div><div class="bar-track"><div class="bar-fill" style="width:${Math.max(8, 100 - (b.band - 1) * 12)}%"></div></div><div class="bar-meta">${esc(b.range)}</div></div>`).join("")}
            </div>
            <div class="legend" style="margin-top:12px"><span><i style="background:var(--brand)"></i>分数越高，梯度越优先</span><span><i style="background:var(--line)"></i>低于 L 不参与录取</span></div>
          </div>
        </div>
      </div>

      <div class="grid grid-3" style="margin-top:16px">
        <div class="card"><div class="card-head"><div class="card-title">数据版本</div></div><div class="card-body">
          <div class="stat-line"><span>版本号</span><strong>v${m.meta.version}</strong></div>
          <div class="stat-line"><span>状态</span><strong>${locked ? "已锁定" : "可编辑"}</strong></div>
          <div class="stat-line"><span>最近更新</span><strong class="small">${esc(m.meta.updated_at || "—")}</strong></div>
          <div class="stat-line"><span>随机种子</span><strong>${esc(m.meta.generator_seed ?? "—")}</strong></div>
          <div class="stat-line"><span>快照哈希</span><strong class="mono small">${esc((m.meta.input_hash || "—").slice(0, 18))}…</strong></div>
        </div></div>
        <div class="card"><div class="card-head"><div class="card-title">快捷操作</div></div><div class="card-body">
          <div class="row" style="margin-bottom:10px"><button class="btn btn-primary" onclick="App.openRunCreate()">新建运行</button><button class="btn" onclick="App.openGenerate()">生成数据</button></div>
          <div class="row" style="margin-bottom:10px"><button class="btn" onclick="App.goto('#/data/candidates')">考生与志愿</button><button class="btn" onclick="App.goto('#/data/plans')">招生计划</button></div>
          <div class="row"><button class="btn" onclick="App.goto('#/stats')">统计分析</button><button class="btn" onclick="App.goto('#/cases')">滑档案例</button></div>
        </div></div>
        <div class="card"><div class="card-head"><div class="card-title">系统约束自检</div></div><div class="card-body">
          <ul class="notice-list">
            <li>每名考生每次运行最多录取一次</li>
            <li>每条计划录取人数不超过有效名额</li>
            <li>录取必须对应有效志愿并满足资格与分数要求</li>
            <li>初始名额 + 转入 − 转出 = 录取 + 余额</li>
            <li>汇总统计与明细一致</li>
          </ul>
          <button class="btn btn-sm" style="margin-top:10px" onclick="App.goto('#/help')">查看完整规则</button>
        </div></div>
      </div>
    `);
  }

  function runStatusBadge(run) {
    const map = {
      created: ["已创建", "badge-muted"],
      batch1_done: ["第一批完成", "badge-info"],
      batch2_done: ["第二批完成", "badge-info"],
      batch3_done: ["第三批完成", "badge-info"],
      completed: ["已完成", "badge-ok"],
      failed: ["失败", "badge-bad"],
    };
    const [text, cls] = map[run.status] || [run.status, "badge-muted"];
    return `<span class="badge ${cls}">${esc(text)}</span>`;
  }

  // ---------------------------------------------------------------------
  // 数据管理
  // ---------------------------------------------------------------------
  async function renderData(parts) {
    const tab = parts[1] || "high-schools";
    const valid = DATA_TABS.some(([key]) => key === tab);
    const nextTab = valid ? tab : "high-schools";
    if (state.data.tab !== nextTab) {
      state.data.tab = nextTab;
      state.data.page = 1;
      state.data.q = "";
      state.data.batch = "";
      state.data.highId = "";
      state.data.middleId = "";
      state.data.status = "";
      state.data.candidateId = null;
      state.data.candidateNo = "";
    }
    await loadOptions();
    setView(`
      <div class="page-head">
        <div><h1 class="page-title">数据管理</h1><div class="page-sub">录入、修改、导入与校验。所有写操作都会创建新的数据版本；若数据已被运行锁定，请先创建新数据版本。</div></div>
        <div class="actions"><button class="btn" onclick="App.openGenerate()">生成数据</button><button class="btn" onclick="App.validateData()">运行校验</button></div>
      </div>
      ${lockedBanner()}
      <div class="card" style="margin-top:16px">
        <div class="tabs">${DATA_TABS.map(([key, label]) => `<button class="tab ${state.data.tab === key ? "active" : ""}" onclick="App.goto('#/data/${key}')">${label}</button>`).join("")}</div>
        <div class="card-body">
          ${dataToolbar()}
          <div id="data-table" style="margin-top:12px"><div class="loading">加载数据…</div></div>
        </div>
      </div>
    `);
    await loadDataTable();
  }

  function dataToolbar() {
    const d = state.data;
    if (d.tab === "high-schools") {
      return `<div class="toolbar">
        <input type="search" id="data-q" placeholder="搜索编号 / 名称" value="${esc(d.q)}" onkeydown="if(event.key==='Enter')App.dataSearch()">
        <select onchange="App.setDataFilter('batch', this.value)"><option value="">全部统招批次</option><option value="3" ${d.batch === "3" ? "selected" : ""}>第三批</option><option value="4" ${d.batch === "4" ? "selected" : ""}>第四批</option></select>
        <button class="btn btn-sm" onclick="App.dataSearch()">搜索</button>
        <div class="spacer"></div>
        <button class="btn btn-primary btn-sm" onclick="App.openHighForm()">新增高中</button>
        <button class="btn btn-sm" onclick="App.openImport('high-schools')">导入 CSV</button>
      </div>`;
    }
    if (d.tab === "middle-schools") {
      return `<div class="toolbar">
        <input type="search" id="data-q" placeholder="搜索编号 / 名称" value="${esc(d.q)}" onkeydown="if(event.key==='Enter')App.dataSearch()">
        <button class="btn btn-sm" onclick="App.dataSearch()">搜索</button>
        <div class="spacer"></div>
        <button class="btn btn-primary btn-sm" onclick="App.openMiddleForm()">新增初中</button>
        <button class="btn btn-sm" onclick="App.openImport('middle-schools')">导入 CSV</button>
      </div>`;
    }
    if (d.tab === "candidates") {
      return `<div class="toolbar">
        <input type="search" id="data-q" placeholder="搜索考生编号 / 姓名" value="${esc(d.q)}" onkeydown="if(event.key==='Enter')App.dataSearch()">
        <select onchange="App.setDataFilter('batch', this.value)"><option value="">排序：默认</option><option value="score_desc" ${d.batch === "score_desc" ? "selected" : ""}>总分降序</option><option value="score_asc" ${d.batch === "score_asc" ? "selected" : ""}>总分升序</option></select>
        <button class="btn btn-sm" onclick="App.dataSearch()">搜索</button>
        <div class="spacer"></div>
        <button class="btn btn-primary btn-sm" onclick="App.openCandidateForm()">新增考生</button>
        <button class="btn btn-sm" onclick="App.openImport('candidates')">导入 CSV</button>
      </div>`;
    }
    if (d.tab === "plans") {
      return `<div class="toolbar">
        <select onchange="App.setDataFilter('batch', this.value)"><option value="">全部批次</option>${[1, 2, 3, 4].map((b) => `<option value="${b}" ${String(d.batch) === String(b) ? "selected" : ""}>第${b}批</option>`).join("")}</select>
        <select onchange="App.setDataFilter('highId', this.value)">${highOptions(d.highId)}</select>
        <input type="search" id="data-q" placeholder="搜索高中 / 初中" value="${esc(d.q)}" onkeydown="if(event.key==='Enter')App.dataSearch()">
        <button class="btn btn-sm" onclick="App.dataSearch()">搜索</button>
        <div class="spacer"></div>
        <button class="btn btn-primary btn-sm" onclick="App.openPlanForm()">新增计划</button>
        <button class="btn btn-sm" onclick="App.openImport('plans')">导入 CSV</button>
      </div>`;
    }
    if (d.tab === "qualifications") {
      return `<div class="toolbar">
        <select onchange="App.setDataFilter('highId', this.value)">${highOptions(d.highId)}</select>
        <select onchange="App.setDataFilter('status', this.value)"><option value="">全部状态</option><option value="qualified" ${d.status === "qualified" ? "selected" : ""}>合格</option><option value="disqualified" ${d.status === "disqualified" ? "selected" : ""}>不合格</option></select>
        <input type="search" id="data-q" placeholder="搜索考生 / 高中" value="${esc(d.q)}" onkeydown="if(event.key==='Enter')App.dataSearch()">
        <button class="btn btn-sm" onclick="App.dataSearch()">搜索</button>
        <div class="spacer"></div>
        <button class="btn btn-primary btn-sm" onclick="App.openQualificationForm()">新增资格</button>
        <button class="btn btn-sm" onclick="App.openImport('qualifications')">导入 CSV</button>
      </div>`;
    }
    return `<div class="toolbar">
      <select onchange="App.setDataFilter('batch', this.value)"><option value="">全部批次</option>${[1, 2, 3, 4].map((b) => `<option value="${b}" ${String(d.batch) === String(b) ? "selected" : ""}>第${b}批</option>`).join("")}</select>
      <input type="search" id="data-q" placeholder="搜索考生 / 高中" value="${esc(d.q)}" onkeydown="if(event.key==='Enter')App.dataSearch()">
      <button class="btn btn-sm" onclick="App.dataSearch()">搜索</button>
      ${d.candidateId ? `<span class="chip">考生筛选：${esc(d.candidateNo)} <button class="btn btn-xs" onclick="App.clearCandidateFilter()">清除</button></span>` : ""}
      <div class="spacer"></div>
      <button class="btn btn-primary btn-sm" onclick="App.openVolunteerForm()">新增志愿</button>
      <button class="btn btn-sm" onclick="App.openImport('volunteers')">导入 CSV</button>
    </div>`;
  }

  App.setDataFilter = (key, value) => {
    state.data[key] = value;
    state.data.page = 1;
    loadDataTable();
  };
  App.dataSearch = () => {
    const q = $("#data-q");
    state.data.q = q ? q.value.trim() : "";
    state.data.page = 1;
    loadDataTable();
  };
  App.dataPage = (page) => { state.data.page = page; loadDataTable(); };
  App.clearCandidateFilter = () => { state.data.candidateId = null; state.data.candidateNo = ""; loadDataTable(); };

  async function loadDataTable() {
    const box = $("#data-table");
    if (!box) return;
    box.innerHTML = `<div class="loading">加载数据…</div>`;
    const d = state.data;
    try {
      if (d.tab === "high-schools") {
        const qs = new URLSearchParams({ page: d.page, size: d.size, q: d.q });
        if (d.batch) qs.set("intake_batch", d.batch);
        const res = await api(`/api/high-schools?${qs}`);
        box.innerHTML = `<div class="table-wrap"><table><thead><tr><th>编号</th><th>名称</th><th>类型</th><th>统招批次</th><th>自主招生</th><th class="right">总计划</th><th></th></tr></thead><tbody>
          ${res.items.length ? res.items.map((r) => `<tr><td class="mono">${esc(r.code)}</td><td><strong>${esc(r.name)}</strong></td><td>${esc(r.category)}</td><td>第${r.intake_batch}批</td><td>${r.has_autonomous ? badge("是", "badge-ok") : badge("否")}</td><td class="right">${fmt(r.total_plan)}</td><td class="right table-actions"><button class="btn btn-xs" onclick="App.openHighForm(${r.id})">编辑</button><button class="btn btn-xs btn-danger" onclick="App.deleteEntity('high-schools', ${r.id}, '${esc(r.name)}')">删除</button></td></tr>`).join("") : `<tr><td colspan="7"><div class="empty"><strong>暂无高中</strong>可以新增、导入或生成演示数据。</div></td></tr>`}
        </tbody></table></div>${pagination(res, "dataPage")}`;
      } else if (d.tab === "middle-schools") {
        const qs = new URLSearchParams({ page: d.page, size: d.size, q: d.q });
        const res = await api(`/api/middle-schools?${qs}`);
        box.innerHTML = `<div class="table-wrap"><table><thead><tr><th>编号</th><th>名称</th><th>区</th><th></th></tr></thead><tbody>
          ${res.items.length ? res.items.map((r) => `<tr><td class="mono">${esc(r.code)}</td><td><strong>${esc(r.name)}</strong></td><td>${esc(r.district || "—")}</td><td class="right table-actions"><button class="btn btn-xs" onclick="App.openMiddleForm(${r.id})">编辑</button><button class="btn btn-xs btn-danger" onclick="App.deleteEntity('middle-schools', ${r.id}, '${esc(r.name)}')">删除</button></td></tr>`).join("") : `<tr><td colspan="4"><div class="empty"><strong>暂无初中</strong>可以新增、导入或生成演示数据。</div></td></tr>`}
        </tbody></table></div>${pagination(res, "dataPage")}`;
      } else if (d.tab === "candidates") {
        const sort = d.batch || "id";
        const qs = new URLSearchParams({ page: d.page, size: d.size, q: d.q, sort });
        const res = await api(`/api/candidates?${qs}`);
        box.innerHTML = `<div class="table-wrap"><table><thead><tr><th>编号</th><th>姓名</th><th>所属初中</th><th class="right">总分</th><th class="right">同分序号</th><th></th></tr></thead><tbody>
          ${res.items.length ? res.items.map((r) => `<tr><td class="mono">${esc(r.candidate_no)}</td><td><strong>${esc(r.name)}</strong></td><td>${esc(r.middle_school_name)}</td><td class="right"><strong>${r.score}</strong></td><td class="right">${r.tie_seq}</td><td class="right table-actions"><button class="btn btn-xs" onclick="App.openVolunteers(${r.id}, '${esc(r.candidate_no)}', '${esc(r.name)}')">志愿</button><button class="btn btn-xs" onclick="App.openCandidateForm(${r.id})">编辑</button><button class="btn btn-xs btn-danger" onclick="App.deleteEntity('candidates', ${r.id}, '${esc(r.name)}')">删除</button></td></tr>`).join("") : `<tr><td colspan="6"><div class="empty"><strong>暂无考生</strong>可以新增、导入或生成演示数据。</div></td></tr>`}
        </tbody></table></div>${pagination(res, "dataPage")}`;
      } else if (d.tab === "plans") {
        const qs = new URLSearchParams({ page: d.page, size: d.size, q: d.q });
        if (d.batch) qs.set("batch", d.batch);
        if (d.highId) qs.set("high_school_id", d.highId);
        const res = await api(`/api/plans?${qs}`);
        box.innerHTML = `<div class="table-wrap"><table><thead><tr><th>批次</th><th>高中</th><th>初中</th><th>类别</th><th class="right">初始名额</th><th class="right">控制线</th><th></th></tr></thead><tbody>
          ${res.items.length ? res.items.map((r) => `<tr><td>${badge(`第${r.batch}批`, "badge-info")}</td><td><strong>${esc(r.high_school_name)}</strong><div class="small muted">${esc(r.high_school_code)}</div></td><td>${r.middle_school_name ? esc(r.middle_school_name) : "—"}</td><td>${esc(r.category)}</td><td class="right">${fmt(r.initial_quota)}</td><td class="right">${fmt(r.control_line)}</td><td class="right table-actions"><button class="btn btn-xs" onclick="App.openPlanForm(${r.id})">编辑</button><button class="btn btn-xs btn-danger" onclick="App.deleteEntity('plans', ${r.id}, '计划 ${r.id}')">删除</button></td></tr>`).join("") : `<tr><td colspan="7"><div class="empty"><strong>暂无招生计划</strong>可以新增、导入或生成演示数据。</div></td></tr>`}
        </tbody></table></div>${pagination(res, "dataPage")}`;
      } else if (d.tab === "qualifications") {
        const qs = new URLSearchParams({ page: d.page, size: d.size, q: d.q });
        if (d.highId) qs.set("high_school_id", d.highId);
        if (d.status) qs.set("status", d.status);
        const res = await api(`/api/qualifications?${qs}`);
        box.innerHTML = `<div class="table-wrap"><table><thead><tr><th>高中</th><th>考生</th><th class="right">总分</th><th>状态</th><th class="right">考核排名</th><th></th></tr></thead><tbody>
          ${res.items.length ? res.items.map((r) => `<tr><td><strong>${esc(r.high_school_name)}</strong></td><td>${esc(r.candidate_no)} · ${esc(r.candidate_name)}</td><td class="right">${r.score}</td><td>${r.status === "qualified" ? badge("合格", "badge-ok") : badge("不合格", "badge-bad")}</td><td class="right">${r.rank ?? "—"}</td><td class="right table-actions"><button class="btn btn-xs" onclick="App.openQualificationForm(${r.id})">编辑</button><button class="btn btn-xs btn-danger" onclick="App.deleteEntity('qualifications', ${r.id}, '资格 ${r.id}')">删除</button></td></tr>`).join("") : `<tr><td colspan="6"><div class="empty"><strong>暂无资格记录</strong>自主招生资格名单可直接导入。</div></td></tr>`}
        </tbody></table></div>${pagination(res, "dataPage")}`;
      } else {
        const qs = new URLSearchParams({ page: d.page, size: d.size, q: d.q });
        if (d.batch) qs.set("batch", d.batch);
        if (d.candidateId) qs.set("candidate_id", d.candidateId);
        const res = await api(`/api/volunteers?${qs}`);
        box.innerHTML = `<div class="table-wrap"><table><thead><tr><th>考生</th><th>批次</th><th class="right">志愿序号</th><th>高中</th><th></th></tr></thead><tbody>
          ${res.items.length ? res.items.map((r) => `<tr><td>${esc(r.candidate_no)} · ${esc(r.candidate_name)}<div class="small muted">${r.score} 分</div></td><td>${badge(`第${r.batch}批`, "badge-info")}</td><td class="right">第 ${r.seq} 志愿</td><td><strong>${esc(r.high_school_name)}</strong><div class="small muted">${esc(r.high_school_code)}</div></td><td class="right table-actions"><button class="btn btn-xs" onclick="App.openVolunteerForm(${r.id})">编辑</button><button class="btn btn-xs btn-danger" onclick="App.deleteEntity('volunteers', ${r.id}, '志愿 ${r.id}')">删除</button></td></tr>`).join("") : `<tr><td colspan="5"><div class="empty"><strong>暂无志愿</strong>可以新增、导入或生成演示数据。</div></td></tr>`}
        </tbody></table></div>${pagination(res, "dataPage")}`;
      }
    } catch (err) {
      box.innerHTML = `<div class="alert bad">${esc(err.message)}</div>`;
    }
  }

  function pagination(res, handler) {
    if (!res || !res.total) return "";
    const pages = [];
    const start = Math.max(1, res.page - 2);
    const end = Math.min(res.pages, res.page + 2);
    for (let p = start; p <= end; p += 1) pages.push(p);
    return `<div class="pagination">
      <span>共 ${fmt(res.total)} 条 · 第 ${res.page} / ${res.pages} 页</span>
      <div class="pages">
        <button class="page-btn" ${res.page <= 1 ? "disabled" : ""} onclick="App.${handler}(${res.page - 1})">上一页</button>
        ${pages.map((p) => `<button class="page-btn ${p === res.page ? "active" : ""}" onclick="App.${handler}(${p})">${p}</button>`).join("")}
        <button class="page-btn" ${res.page >= res.pages ? "disabled" : ""} onclick="App.${handler}(${res.page + 1})">下一页</button>
      </div>
    </div>`;
  }

  // ---------------------------------------------------------------------
  // 数据表单
  // ---------------------------------------------------------------------
  App.openHighForm = async (id = null) => {
    await loadOptions();
    let row = {};
    if (id) row = await api(`/api/high-schools/${id}`);
    openModal({
      title: id ? "编辑高中" : "新增高中",
      body: `<form id="modal-form" class="form-grid">
        <div class="field"><label>高中编号</label><input name="code" required value="${esc(row.code || "")}" placeholder="如 G101"></div>
        <div class="field"><label>高中名称</label><input name="name" required value="${esc(row.name || "")}"></div>
        <div class="field"><label>类型</label><select name="category"><option ${row.category === "示范性" ? "selected" : ""}>示范性</option><option ${row.category === "非示范" ? "selected" : ""}>非示范</option></select></div>
        <div class="field"><label>统招接收批次</label><select name="intake_batch"><option value="3" ${row.intake_batch === 3 ? "selected" : ""}>第三批</option><option value="4" ${row.intake_batch === 4 ? "selected" : ""}>第四批</option></select></div>
        <div class="field"><label>自主招生</label><label class="chip"><input type="checkbox" name="has_autonomous" ${row.has_autonomous ? "checked" : ""}> 获批自主招生（仅第三批高中）</label></div>
        <div class="field"><label>总计划</label><input name="total_plan" type="number" min="0" value="${row.total_plan ?? 0}"></div>
        <div class="field full"><label>校区 / 备注</label><input name="campus" value="${esc(row.campus || "")}"></div>
      </form>`,
      onOk: async () => {
        const fd = new FormData($("#modal-form"));
        const payload = {
          code: fd.get("code"), name: fd.get("name"), category: fd.get("category"),
          intake_batch: Number(fd.get("intake_batch")), has_autonomous: fd.get("has_autonomous") === "on",
          total_plan: Number(fd.get("total_plan") || 0), campus: fd.get("campus") || "",
        };
        await api(id ? `/api/high-schools/${id}` : "/api/high-schools", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
        await refreshMeta();
        await loadOptions(true);
        await loadDataTable();
        toast("高中已保存", "ok");
      },
    });
  };

  App.openMiddleForm = async (id = null) => {
    let row = {};
    if (id) row = await api(`/api/middle-schools/${id}`);
    openModal({
      title: id ? "编辑初中" : "新增初中",
      body: `<form id="modal-form" class="form-grid">
        <div class="field"><label>初中编号</label><input name="code" required value="${esc(row.code || "")}" placeholder="如 M101"></div>
        <div class="field"><label>初中名称</label><input name="name" required value="${esc(row.name || "")}"></div>
        <div class="field full"><label>所属区</label><input name="district" value="${esc(row.district || "")}" placeholder="如 越秀区"></div>
      </form>`,
      onOk: async () => {
        const fd = new FormData($("#modal-form"));
        const payload = { code: fd.get("code"), name: fd.get("name"), district: fd.get("district") || "" };
        await api(id ? `/api/middle-schools/${id}` : "/api/middle-schools", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
        await refreshMeta();
        await loadOptions(true);
        await loadDataTable();
        toast("初中已保存", "ok");
      },
    });
  };

  App.openCandidateForm = async (id = null) => {
    await loadOptions();
    let row = {};
    if (id) row = await api(`/api/candidates/${id}`);
    openModal({
      title: id ? "编辑考生" : "新增考生",
      body: `<form id="modal-form" class="form-grid">
        <div class="field"><label>考生编号</label><input name="candidate_no" required value="${esc(row.candidate_no || "")}" placeholder="如 ZK2026000001"></div>
        <div class="field"><label>姓名（虚构）</label><input name="name" required value="${esc(row.name || "")}"></div>
        <div class="field"><label>所属初中</label><select name="middle_school_id" required>${middleOptions(row.middle_school_id, "请选择初中")}</select></div>
        <div class="field"><label>总分</label><input name="score" type="number" min="0" max="750" required value="${row.score ?? 600}"></div>
        <div class="field"><label>同分序号</label><input name="tie_seq" type="number" min="1" required value="${row.tie_seq ?? 1}"><div class="hint">同一总分内唯一，数值越小越优先</div></div>
      </form>`,
      onOk: async () => {
        const fd = new FormData($("#modal-form"));
        const payload = {
          candidate_no: fd.get("candidate_no"), name: fd.get("name"),
          middle_school_id: Number(fd.get("middle_school_id")), score: Number(fd.get("score")),
          tie_seq: Number(fd.get("tie_seq")),
        };
        await api(id ? `/api/candidates/${id}` : "/api/candidates", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
        await refreshMeta();
        await loadDataTable();
        toast("考生已保存", "ok");
      },
    });
  };

  App.openPlanForm = async (id = null) => {
    await loadOptions();
    let row = { batch: 3, category: "统招", initial_quota: 0, control_line: 492 };
    if (id) row = await api(`/api/plans/${id}`);
    openModal({
      title: id ? "编辑招生计划" : "新增招生计划",
      body: `<form id="modal-form" class="form-grid">
        <div class="field"><label>高中</label><select name="high_school_id" required>${highOptions(row.high_school_id, "请选择高中")}</select></div>
        <div class="field"><label>批次</label><select name="batch" onchange="App.syncPlanForm()">
          ${[1, 2, 3, 4].map((b) => `<option value="${b}" ${Number(row.batch) === b ? "selected" : ""}>第${b}批</option>`).join("")}
        </select></div>
        <div class="field"><label>类别</label><select name="category">
          ${["自主招生", "名额分配", "统招"].map((c) => `<option ${row.category === c ? "selected" : ""}>${c}</option>`).join("")}
        </select></div>
        <div class="field"><label>初始名额</label><input name="initial_quota" type="number" min="0" required value="${row.initial_quota ?? 0}"></div>
        <div class="field"><label>计划控制线</label><input name="control_line" type="number" min="0" required value="${row.control_line ?? 492}"></div>
        <div class="field" id="plan-middle-field"><label>名额分配初中</label><select name="middle_school_id">${middleOptions(row.middle_school_id, "仅第二批需要选择")}</select></div>
        <div class="field full"><label>备注</label><input name="note" value="${esc(row.note || "")}"></div>
      </form>`,
      onOk: async () => {
        const fd = new FormData($("#modal-form"));
        const batch = Number(fd.get("batch"));
        const payload = {
          high_school_id: Number(fd.get("high_school_id")), batch, category: fd.get("category"),
          initial_quota: Number(fd.get("initial_quota")), control_line: Number(fd.get("control_line")),
          middle_school_id: batch === 2 ? Number(fd.get("middle_school_id")) : null,
          note: fd.get("note") || "",
        };
        await api(id ? `/api/plans/${id}` : "/api/plans", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
        await refreshMeta();
        await loadDataTable();
        toast("招生计划已保存", "ok");
      },
    });
    App.syncPlanForm();
  };

  App.syncPlanForm = () => {
    const form = $("#modal-form");
    if (!form) return;
    const batch = Number(form.batch.value);
    const category = form.category;
    if (batch === 1) category.value = "自主招生";
    else if (batch === 2) category.value = "名额分配";
    else category.value = "统招";
    const field = $("#plan-middle-field");
    if (field) field.style.display = batch === 2 ? "" : "none";
  };

  App.openQualificationForm = async (id = null) => {
    await loadOptions();
    let row = { status: "qualified" };
    if (id) row = await api(`/api/qualifications/${id}`);
    openModal({
      title: id ? "编辑自主招生资格" : "新增自主招生资格",
      body: `<form id="modal-form" class="form-grid">
        <div class="field"><label>考生编号</label><input name="candidate_no" required value="${esc(row.candidate_no || "")}" placeholder="输入考生编号后自动匹配"></div>
        <div class="field"><label>高中</label><select name="high_school_id" required>${highOptions(row.high_school_id, "请选择高中")}</select></div>
        <div class="field"><label>资格状态</label><select name="status" onchange="App.syncQualForm()"><option value="qualified" ${row.status === "qualified" ? "selected" : ""}>合格</option><option value="disqualified" ${row.status === "disqualified" ? "selected" : ""}>不合格</option></select></div>
        <div class="field"><label>考核排名</label><input name="rank" type="number" min="1" value="${row.rank ?? ""}"><div class="hint">同一高中内唯一</div></div>
      </form>`,
      onOk: async () => {
        const fd = new FormData($("#modal-form"));
        const candidate = await resolveCandidate(fd.get("candidate_no"));
        const status = fd.get("status");
        const payload = {
          candidate_id: candidate.id, high_school_id: Number(fd.get("high_school_id")), status,
          rank: status === "qualified" ? Number(fd.get("rank")) : null,
        };
        await api(id ? `/api/qualifications/${id}` : "/api/qualifications", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
        await refreshMeta();
        await loadDataTable();
        toast("资格记录已保存", "ok");
      },
    });
  };

  App.syncQualForm = () => {
    const form = $("#modal-form");
    if (!form) return;
    form.rank.disabled = form.status.value !== "qualified";
    if (form.rank.disabled) form.rank.value = "";
  };

  App.openVolunteerForm = async (id = null, candidateId = null, candidateNo = "", candidateName = "") => {
    await loadOptions();
    let row = { batch: 3, seq: 1 };
    if (id) row = await api(`/api/volunteers/${id}`);
    let no = candidateNo || row.candidate_no || "";
    if (candidateId && !no) {
      const c = await api(`/api/candidates/${candidateId}`);
      no = c.candidate_no;
    }
    openModal({
      title: id ? "编辑志愿" : "新增志愿",
      body: `<form id="modal-form" class="form-grid">
        <div class="field"><label>考生编号</label><input name="candidate_no" required value="${esc(no)}" ${candidateId ? "readonly" : ""}></div>
        <div class="field"><label>高中</label><select name="high_school_id" required>${highOptions(row.high_school_id, "请选择高中")}</select></div>
        <div class="field"><label>批次</label><select name="batch" onchange="App.syncVolunteerForm()">${[1, 2, 3, 4].map((b) => `<option value="${b}" ${Number(row.batch) === b ? "selected" : ""}>第${b}批</option>`).join("")}</select></div>
        <div class="field"><label>志愿序号</label><input name="seq" type="number" min="1" max="6" required value="${row.seq ?? 1}"></div>
      </form>`,
      onOk: async () => {
        const fd = new FormData($("#modal-form"));
        const candidate = candidateId ? { id: candidateId } : await resolveCandidate(fd.get("candidate_no"));
        const payload = {
          candidate_id: candidate.id, batch: Number(fd.get("batch")),
          seq: Number(fd.get("seq")), high_school_id: Number(fd.get("high_school_id")),
        };
        await api(id ? `/api/volunteers/${id}` : "/api/volunteers", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
        await refreshMeta();
        await loadDataTable();
        if (state.data.tab === "volunteers") await loadDataTable();
        toast("志愿已保存", "ok");
      },
    });
  };

  App.syncVolunteerForm = () => {
    const form = $("#modal-form");
    if (!form) return;
    const limits = { 1: 1, 2: 3, 3: 6, 4: 6 };
    const batch = Number(form.batch.value);
    form.seq.max = limits[batch] || 6;
    if (Number(form.seq.value) > form.seq.max) form.seq.value = form.seq.max;
  };

  async function resolveCandidate(no) {
    const value = String(no || "").trim();
    if (!value) throw new Error("请填写考生编号");
    const res = await api(`/api/candidates?q=${encodeURIComponent(value)}&size=20`);
    const exact = res.items.find((c) => c.candidate_no === value);
    if (!exact) throw new Error(`未找到考生编号 ${value}`);
    return exact;
  }

  App.openVolunteers = async (candidateId, candidateNo, candidateName) => {
    const res = await api(`/api/volunteers?candidate_id=${candidateId}&size=200`);
    openModal({
      title: `志愿 · ${candidateNo} ${candidateName}`,
      wide: true,
      hideOk: true,
      body: `<div class="row-between" style="margin-bottom:12px">
        <div class="muted small">该考生共 ${res.total} 条志愿。批次与志愿序号由系统校验。</div>
        <button class="btn btn-primary btn-sm" onclick="App.openVolunteerForm(null, ${candidateId}, '${esc(candidateNo)}', '${esc(candidateName)}')">新增志愿</button>
      </div>
      <div class="table-wrap"><table><thead><tr><th>批次</th><th class="right">志愿序号</th><th>高中</th><th></th></tr></thead><tbody>
        ${res.items.length ? res.items.map((v) => `<tr><td>第${v.batch}批</td><td class="right">第 ${v.seq} 志愿</td><td><strong>${esc(v.high_school_name)}</strong> <span class="small muted">${esc(v.high_school_code)}</span></td><td class="right table-actions"><button class="btn btn-xs" onclick="App.openVolunteerForm(${v.id})">编辑</button><button class="btn btn-xs btn-danger" onclick="App.deleteVolunteerFromModal(${v.id}, ${candidateId}, '${esc(candidateNo)}', '${esc(candidateName)}')">删除</button></td></tr>`).join("") : `<tr><td colspan="4"><div class="empty">尚未填报志愿</div></td></tr>`}
      </tbody></table></div>`,
    });
  };

  App.deleteVolunteerFromModal = async (volId, candidateId, candidateNo, candidateName) => {
    await api(`/api/volunteers/${volId}`, { method: "DELETE" });
    await refreshMeta();
    toast("志愿已删除", "ok");
    App.openVolunteers(candidateId, candidateNo, candidateName);
  };

  App.deleteEntity = async (entity, id, name) => {
    confirmDialog("确认删除", `确定删除“${name}”吗？若该记录已被历史运行引用，系统会拒绝删除。`, async () => {
      await api(`/api/${entity}/${id}`, { method: "DELETE" });
      await refreshMeta();
      await loadDataTable();
      toast("已删除", "ok");
    });
  };

  App.validateData = async () => {
    showOverlay("正在校验数据…");
    try {
      const res = await api("/api/validate");
      hideOverlay();
      openModal({
        title: res.ok ? "数据校验通过" : "数据校验未通过",
        hideOk: true,
        wide: true,
        body: `<div class="alert ${res.ok ? "info" : "bad"}"><div>${res.ok ? "没有发现 error 级问题，可以创建运行。" : "存在 error 级问题，必须修复后才能运行。"}</div></div>
          <div class="grid grid-2" style="margin-top:14px">
            <div><div class="card-title" style="margin-bottom:8px">错误（${res.errors.length}）</div>
              ${res.errors.length ? `<ul class="notice-list">${res.errors.map((i) => `<li>${esc(i.message)}</li>`).join("")}</ul>` : `<div class="muted small">无</div>`}
            </div>
            <div><div class="card-title" style="margin-bottom:8px">警告（${res.warnings.length}）</div>
              ${res.warnings.length ? `<ul class="notice-list">${res.warnings.slice(0, 30).map((i) => `<li>${esc(i.message)}</li>`).join("")}</ul>` : `<div class="muted small">无</div>`}
            </div>
          </div>`,
      });
    } catch (err) {
      hideOverlay();
      toast(err.message, "bad");
    }
  };

  App.openImport = (entity) => {
    openModal({
      title: "CSV 批量导入",
      wide: true,
      body: `<div class="alert info"><div>导入采用全有或全无：任意一行校验失败则整体回滚。第一行为表头，UTF-8 编码。支持从 Excel 复制后粘贴为逗号分隔文本。</div></div>
        <div class="field" style="margin-top:12px"><label>CSV 内容</label><textarea id="import-csv" style="min-height:220px" class="mono">${esc(IMPORT_TEMPLATES[entity] || "")}</textarea></div>
        <div class="small muted" style="margin-top:8px">当前类型：${esc(entity)}</div>`,
      okText: "开始导入",
      onOk: async () => {
        const csv = $("#import-csv").value;
        if (!csv.trim()) throw new Error("CSV 内容不能为空");
        const res = await api(`/api/import/${entity}`, { method: "POST", body: JSON.stringify({ csv }) });
        await refreshMeta();
        await loadOptions(true);
        await loadDataTable();
        toast(`成功导入 ${res.imported} 条`, "ok");
      },
    });
  };

  // ---------------------------------------------------------------------
  // 数据生成 / 解锁
  // ---------------------------------------------------------------------
  App.openGenerate = () => {
    openModal({
      title: "生成虚构演示数据",
      wide: true,
      body: `<div class="alert"><div><strong>注意：</strong>生成新数据会清空当前输入，并删除历史运行与快照。此操作不可撤销。</div></div>
        <form id="modal-form" class="form-grid" style="margin-top:14px">
          <div class="field"><label>数据预设</label><select name="preset" onchange="App.toggleGenerateFields()">
            <option value="small">人工小数据集（2 初中 / 4 高中 / 17 考生）</option>
            <option value="medium">中等规模（100 初中 / 30 高中 / 3000 考生）</option>
            <option value="demo" selected>较大规模演示（300 初中 / 60 高中 / 2 万考生）</option>
            <option value="full">任务书加分规模（500 初中 / 150 高中 / 15 万考生）</option>
            <option value="custom">自定义规模</option>
          </select></div>
          <div class="field"><label>随机种子</label><input name="seed" type="number" value="2026"><div class="hint">相同种子生成相同数据</div></div>
          <div class="field custom-field" style="display:none"><label>初中数</label><input name="middle_count" type="number" value="100" min="1"></div>
          <div class="field custom-field" style="display:none"><label>高中数</label><input name="high_count" type="number" value="30" min="1"></div>
          <div class="field custom-field" style="display:none"><label>考生数</label><input name="candidate_count" type="number" value="3000" min="1"></div>
          <div class="field custom-field" style="display:none"><label>第一梯度线 G₁</label><input name="g1" type="number" value="712" min="0" max="750"></div>
          <div class="field custom-field" style="display:none"><label>全市控制线 L</label><input name="city_line" type="number" value="492" min="0" max="750"></div>
          <div class="field full"><label class="chip"><input type="checkbox" name="confirm_reset" checked> 我确认重置当前数据并删除历史运行</label></div>
        </form>`,
      okText: "生成数据",
      onOk: async () => {
        const fd = new FormData($("#modal-form"));
        const preset = fd.get("preset");
        const payload = {
          preset, seed: Number(fd.get("seed") || 2026), confirm_reset: fd.get("confirm_reset") === "on",
          middle_count: num(fd.get("middle_count")), high_count: num(fd.get("high_count")),
          candidate_count: num(fd.get("candidate_count")), g1: num(fd.get("g1")),
          city_line: num(fd.get("city_line")), delta: 40,
        };
        showOverlay("正在生成数据，15 万考生规模可能需要数秒…");
        try {
          const res = await api("/api/dataset/generate", { method: "POST", body: JSON.stringify(payload) });
          await refreshMeta();
          await loadOptions(true);
          hideOverlay();
          toast(`数据已生成：${fmt(res.counts.candidates)} 名考生`, "ok");
          location.hash = "#/overview";
          await render();
        } catch (err) {
          hideOverlay();
          throw err;
        }
      },
    });
  };

  App.toggleGenerateFields = () => {
    const form = $("#modal-form");
    if (!form) return;
    const isCustom = form.preset.value === "custom";
    $$(".custom-field", form).forEach((el) => { el.style.display = isCustom ? "" : "none"; });
  };

  App.unlockDataset = () => {
    confirmDialog(
      "创建新的数据版本",
      "将把数据版本号 +1 并解锁编辑。历史运行与快照会保留，但之后修改输入数据不会影响已完成的运行。",
      async () => {
        await api("/api/dataset/unlock", { method: "POST", body: JSON.stringify({ confirm: true }) });
        await refreshMeta();
        toast("已创建新的数据版本，可以编辑数据", "ok");
        await render();
      }
    );
  };

  // ---------------------------------------------------------------------
  // 投档运行
  // ---------------------------------------------------------------------
  async function renderRuns(parts) {
    if (parts[1]) {
      await renderRunDetail(Number(parts[1]));
      return;
    }
    const runs = await api("/api/runs?limit=100");
    state.runs = runs;
    setView(`
      <div class="page-head">
        <div><h1 class="page-title">投档执行</h1><div class="page-sub">支持按批执行与完整运行。每次运行保存输入快照，结果独立存储；同一数据可以重复运行并得到一致结果。</div></div>
        <div class="actions"><button class="btn btn-primary" onclick="App.openRunCreate()">新建运行</button><button class="btn" onclick="App.goto('#/runs')">刷新</button></div>
      </div>
      ${lockedBanner()}
      <div class="card" style="margin-top:16px">
        <div class="card-head"><div><div class="card-title">运行记录</div><div class="card-sub">点击“打开”查看批次进度、计划余额与结转流水</div></div></div>
        <div class="card-body tight">
          ${runs.length ? `<div class="table-wrap"><table><thead><tr><th>运行编号</th><th>规则参数</th><th>状态</th><th>进度</th><th class="right">录取人数</th><th>创建时间</th><th></th></tr></thead><tbody>
            ${runs.map((r) => `<tr><td class="mono">${esc(r.run_code)}</td><td class="small">G₁ ${r.g1} · Δ ${r.delta} · L ${r.city_line} · ${r.trace_level === "full" ? "完整追踪" : "摘要"}</td><td>${runStatusBadge(r)}</td><td>第 ${r.current_batch} / 4 批</td><td class="right"><strong>${fmt(r.admitted_count)}</strong></td><td class="small muted">${esc(r.created_at)}</td><td class="right"><button class="btn btn-sm btn-primary" onclick="App.goto('#/runs/${r.id}')">打开</button></td></tr>`).join("")}
          </tbody></table></div>` : `<div class="empty"><strong>还没有投档运行</strong>先准备数据，再新建一次运行。</div>`}
        </div>
      </div>
    `);
  }

  App.openRunCreate = async () => {
    const d = state.meta.defaults;
    openModal({
      title: "新建投档运行",
      body: `<form id="modal-form" class="form-grid">
        <div class="field"><label>第一梯度线 G₁</label><input name="g1" type="number" min="0" max="750" value="${d.g1}" required></div>
        <div class="field"><label>梯度间隔 Δ</label><input name="delta" type="number" min="1" max="200" value="${d.delta}" required></div>
        <div class="field"><label>全市最低控制线 L</label><input name="city_line" type="number" min="0" max="750" value="${d.city_line}" required></div>
        <div class="field"><label>追踪级别</label><select name="trace_level"><option value="summary">摘要（大数据推荐）</option><option value="full">完整（记录逐志愿原因）</option></select></div>
        <div class="field full"><label>备注</label><input name="note" placeholder="如：小数据集人工对照 / 演示运行"></div>
      </form>
      <div class="alert info" style="margin-top:14px"><div>创建运行会锁定当前数据版本并写入快照。运行完成后若需修改输入，请创建新的数据版本。</div></div>`,
      okText: "创建并锁定数据",
      onOk: async () => {
        const fd = new FormData($("#modal-form"));
        const payload = {
          g1: Number(fd.get("g1")), delta: Number(fd.get("delta")),
          city_line: Number(fd.get("city_line")), trace_level: fd.get("trace_level"),
          note: fd.get("note") || "",
        };
        const run = await api("/api/runs", { method: "POST", body: JSON.stringify(payload) });
        await refreshMeta();
        toast(`运行 ${run.run_code} 已创建`, "ok");
        location.hash = `#/runs/${run.id}`;
      },
    });
  };

  async function renderRunDetail(runId) {
    const [run, progress, transfers] = await Promise.all([
      api(`/api/runs/${runId}`),
      api(`/api/runs/${runId}/progress`),
      api(`/api/runs/${runId}/transfers`),
    ]);
    state.run = run;
    state.progress = progress;
    state.transfers = transfers;
    if (state.runTab === "plans") {
      let plansUrl = `/api/runs/${runId}/plans?page=${state.runPlanPage}&size=100`;
      if (state.runPlanBatch) plansUrl += `&batch=${state.runPlanBatch}`;
      state.runPlans = await api(plansUrl);
    }
    if (state.runTab === "events") {
      let eventsUrl = `/api/runs/${runId}/events?limit=300`;
      if (state.runPlanBatch) eventsUrl += `&batch=${state.runPlanBatch}`;
      state.events = await api(eventsUrl);
    }
    const canRun = !["completed", "failed"].includes(run.status);
    setView(`
      <div class="page-head">
        <div>
          <h1 class="page-title">运行 ${esc(run.run_code)}</h1>
          <div class="page-sub">G₁ ${run.g1} · Δ ${run.delta} · L ${run.city_line} · 追踪 ${run.trace_level === "full" ? "完整" : "摘要"} · 数据版本 v${run.dataset_version}</div>
        </div>
        <div class="actions">
          ${canRun ? `<button class="btn btn-primary" onclick="App.executeNext(${run.id})">执行下一批</button><button class="btn btn-cyan" onclick="App.executeAll(${run.id})">完整运行</button>` : `<span class="badge badge-ok">运行已完成</span>`}
          <button class="btn" onclick="App.verifyRun(${run.id})">一致性校验</button>
          <a class="btn" href="/api/runs/${run.id}/snapshot">下载输入快照</a>
        </div>
      </div>
      ${run.status === "failed" ? `<div class="alert bad"><div><strong>运行失败：</strong>${esc(run.error_message || "未知错误")}</div></div>` : ""}
      <div class="card" style="margin-top:16px"><div class="card-body">
        <div class="stepper">
          ${[1, 2, 3, 4].map((b) => {
            const done = run.current_batch >= b;
            const current = !done && run.current_batch + 1 === b && canRun;
            const admitted = (progress.batches.find((x) => x.batch === b) || {}).admitted_count || 0;
            return `<div class="step ${done ? "done" : current ? "current" : "pending"}">
              <div class="step-no">${done ? "已完成" : current ? "进行中" : "待执行"}</div>
              <div class="step-name">第${b}批 ${b === 1 ? "自主招生" : b === 2 ? "名额分配" : "统招"}</div>
              <div class="step-meta">已录取 ${fmt(admitted)} 人</div>
            </div>`;
          }).join("")}
        </div>
      </div></div>

      <div class="grid grid-4" style="margin-top:16px">
        ${progress.plan_batches.map((b) => `<div class="card kpi ${b.remaining_total > 0 ? "warn" : "ok"}"><div class="kpi-label">第${b.batch}批计划</div><div class="kpi-value" style="font-size:21px">${fmt(b.admitted_total)} / ${fmt(b.initial_total + b.in_total)}</div><div class="kpi-foot">余额 ${fmt(b.remaining_total)} · 转入 ${fmt(b.in_total)} · 转出 ${fmt(b.out_total)}</div></div>`).join("")}
      </div>

      <div class="card" style="margin-top:16px">
        <div class="tabs">
          ${[["progress", "批次进度"], ["plans", "计划余额"], ["transfers", "结转流水"], ["events", "事件日志"]].map(([k, label]) => `<button class="tab ${state.runTab === k ? "active" : ""}" onclick="App.runTab('${k}')">${label}</button>`).join("")}
        </div>
        <div class="card-body">${runTabBody(run)}</div>
      </div>
    `);
  }

  function runTabBody(run) {
    if (state.runTab === "progress") {
      return `<div class="table-wrap"><table><thead><tr><th>批次</th><th class="right">处理考生</th><th class="right">录取</th><th class="right">结转转出</th><th class="right">仍有余额计划</th><th>完成时间</th></tr></thead><tbody>
        ${state.progress.batches.length ? state.progress.batches.map((b) => `<tr><td><strong>第${b.batch}批</strong></td><td class="right">${fmt(b.processed_candidates)}</td><td class="right">${fmt(b.admitted_count)}</td><td class="right">${fmt(b.transfer_out)}</td><td class="right">${fmt(b.remaining_plans)}</td><td class="small muted">${esc(b.finished_at)}</td></tr>`).join("") : `<tr><td colspan="6"><div class="empty">尚未执行任何批次</div></td></tr>`}
      </tbody></table></div>
      <div class="alert info" style="margin-top:14px"><div>执行顺序固定为第 1 → 2 → 3 → 4 批。第一批、第二批结束后分别把剩余名额转入第三批；第三、第四批余缺不互转。</div></div>`;
    }
    if (state.runTab === "plans") {
      const res = state.runPlans;
      return `<div class="toolbar" style="margin-bottom:12px">
        <select onchange="App.runPlanBatchChange(this.value)"><option value="">全部批次</option>${[1, 2, 3, 4].map((b) => `<option value="${b}" ${String(state.runPlanBatch) === String(b) ? "selected" : ""}>第${b}批</option>`).join("")}</select>
        <span class="small muted">共 ${fmt(res ? res.total : 0)} 条计划</span>
      </div>
      ${res && res.items.length ? `<div class="table-wrap"><table><thead><tr><th>批次</th><th>高中 / 初中</th><th class="right">初始</th><th class="right">转入</th><th class="right">转出</th><th class="right">有效</th><th class="right">录取</th><th class="right">余额</th><th class="right">最低分</th><th>末位考生</th></tr></thead><tbody>
        ${res.items.map((p) => `<tr><td>第${p.batch}批</td><td><strong>${esc(p.high_school_name)}</strong>${p.middle_school_name ? `<div class="small muted">${esc(p.middle_school_name)}</div>` : ""}</td><td class="right">${p.initial_quota}</td><td class="right">${p.transferred_in}</td><td class="right">${p.transferred_out}</td><td class="right"><strong>${p.effective_quota}</strong></td><td class="right">${p.admitted_count}</td><td class="right">${p.remaining > 0 ? `<span class="badge badge-warn">${p.remaining}</span>` : p.remaining}</td><td class="right">${p.min_score ?? "无"}</td><td class="small">${p.last_admitted ? `${esc(p.last_admitted.candidate_no)} · ${p.last_admitted.score} 分 · 第${p.last_admitted.volunteer_seq}志愿` : "无"}</td></tr>`).join("")}
      </tbody></table></div>${pagination(res, "runPlanPage")}` : `<div class="empty"><strong>暂无计划状态</strong>请先执行批次。</div>`}`;
    }
    if (state.runTab === "transfers") {
      return state.transfers.length ? `<div class="table-wrap"><table><thead><tr><th>来源批次</th><th>高中</th><th>来源初中</th><th class="right">人数</th><th>去向</th><th>分组</th></tr></thead><tbody>
        ${state.transfers.slice(0, 500).map((t) => `<tr><td>第${t.from_batch}批</td><td><strong>${esc(t.high_school_name)}</strong></td><td>${esc(t.middle_school_name || "—")}</td><td class="right"><strong>${t.amount}</strong></td><td>第${t.to_batch}批计划 #${t.to_plan_id}</td><td class="mono small">${esc(t.group_key)}</td></tr>`).join("")}
      </tbody></table></div>${state.transfers.length > 500 ? `<div class="small muted" style="margin-top:8px">仅显示前 500 条，共 ${fmt(state.transfers.length)} 条。</div>` : ""}` : `<div class="empty"><strong>暂无结转流水</strong>第一批、第二批结束后会生成结转记录。</div>`;
    }
    return state.events.length ? `<div class="toolbar" style="margin-bottom:12px"><select onchange="App.runPlanBatchChange(this.value)"><option value="">全部批次</option>${[1, 2, 3, 4].map((b) => `<option value="${b}" ${String(state.runPlanBatch) === String(b) ? "selected" : ""}>第${b}批</option>`).join("")}</select><span class="small muted">最近 ${state.events.length} 条事件</span></div>
      <div class="table-wrap"><table><thead><tr><th>批次</th><th>类型</th><th>说明</th><th class="right">余额</th><th>时间</th></tr></thead><tbody>
        ${state.events.map((e) => `<tr><td>${e.batch ? `第${e.batch}批` : "—"}</td><td>${badge(e.event_type, e.event_type === "admit" ? "badge-ok" : e.event_type === "transfer" ? "badge-info" : "badge-muted")}</td><td class="small">${esc(e.message || "")}</td><td class="right">${e.remaining_after ?? "—"}</td><td class="small muted">${esc(e.created_at)}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty"><strong>暂无事件日志</strong>摘要模式只记录录取与结转事件；完整模式还会记录逐志愿跳过原因。</div>`;
  }

  App.runTab = async (tab) => {
    state.runTab = tab;
    state.runPlanPage = 1;
    await renderRunDetail(state.run.id);
  };
  App.runPlanBatchChange = async (value) => {
    state.runPlanBatch = value;
    state.runPlanPage = 1;
    await renderRunDetail(state.run.id);
  };
  App.runPlanPage = async (page) => {
    state.runPlanPage = page;
    await renderRunDetail(state.run.id);
  };

  App.executeNext = async (runId) => {
    showOverlay("正在执行下一批投档…");
    try {
      await api(`/api/runs/${runId}/execute-next`, { method: "POST" });
      await refreshMeta();
      hideOverlay();
      toast("批次执行完成", "ok");
      await renderRunDetail(runId);
    } catch (err) {
      hideOverlay();
      toast(err.message, "bad");
    }
  };

  App.executeAll = async (runId) => {
    showOverlay("正在完整运行四个批次，较大数据可能需要数秒…");
    try {
      await api(`/api/runs/${runId}/execute-all`, { method: "POST" });
      await refreshMeta();
      hideOverlay();
      toast("完整投档已完成", "ok");
      await renderRunDetail(runId);
    } catch (err) {
      hideOverlay();
      toast(err.message, "bad");
    }
  };

  App.verifyRun = async (runId) => {
    showOverlay("正在校验运行一致性…");
    try {
      const res = await api(`/api/runs/${runId}/verify`);
      hideOverlay();
      openModal({
        title: res.ok ? "一致性校验通过" : "一致性校验失败",
        hideOk: true,
        wide: true,
        body: res.ok
          ? `<div class="alert info"><div>已检查：考生唯一录取、计划不超额、名额平衡等式、录取对应有效志愿、汇总与明细一致。</div></div>`
          : `<div class="alert bad"><div>发现 ${res.errors.length} 个问题：</div></div><ul class="notice-list">${res.errors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>`,
      });
    } catch (err) {
      hideOverlay();
      toast(err.message, "bad");
    }
  };

  // ---------------------------------------------------------------------
  // 结果查询
  // ---------------------------------------------------------------------
  async function renderResults(parts) {
    const runs = await api("/api/runs?limit=100");
    state.runs = runs;
    const completed = runs.filter((r) => r.current_batch > 0);
    if (!state.resultsRunId && completed.length) state.resultsRunId = completed[0].id;
    if (parts[1] && ["candidate", "plan", "admissions"].includes(parts[1])) state.resultsTab = parts[1];
    const run = runs.find((r) => r.id === Number(state.resultsRunId));
    if (!run) {
      setView(`<div class="page-head"><div><h1 class="page-title">结果查询</h1><div class="page-sub">尚无运行结果，请先完成一次投档。</div></div></div>
        <div class="card"><div class="card-body"><button class="btn btn-primary" onclick="App.goto('#/runs')">去投档执行</button></div></div>`);
      return;
    }
    setView(`
      <div class="page-head">
        <div><h1 class="page-title">结果查询</h1><div class="page-sub">按考生、计划、高中或初中查询录取去向、志愿处理情况与未录取原因。</div></div>
        <div class="actions">
          <select style="min-width:280px" onchange="App.selectResultsRun(this.value)">
            ${runs.map((r) => `<option value="${r.id}" ${r.id === run.id ? "selected" : ""}>${esc(r.run_code)} · 第${r.current_batch}/4批 · ${esc(r.status_name)}</option>`).join("")}
          </select>
        </div>
      </div>
      <div class="card">
        <div class="tabs">
          <button class="tab ${state.resultsTab === "candidate" ? "active" : ""}" onclick="App.resultsTab('candidate')">按考生</button>
          <button class="tab ${state.resultsTab === "plan" ? "active" : ""}" onclick="App.resultsTab('plan')">按高中 / 计划</button>
          <button class="tab ${state.resultsTab === "admissions" ? "active" : ""}" onclick="App.resultsTab('admissions')">录取名单</button>
        </div>
        <div class="card-body" id="results-body">加载中…</div>
      </div>
    `);
    await loadResultsBody();
  }

  App.selectResultsRun = (id) => {
    state.resultsRunId = Number(id);
    state.admissionsPage = 1;
    renderResults([]);
  };
  App.resultsTab = (tab) => {
    state.resultsTab = tab;
    location.hash = `#/results/${tab}`;
    loadResultsBody();
  };

  async function loadResultsBody() {
    const box = $("#results-body");
    if (!box) return;
    const runId = state.resultsRunId;
    if (state.resultsTab === "candidate") {
      box.innerHTML = `<div class="toolbar" style="margin-bottom:14px">
        <input type="search" id="candidate-lookup" placeholder="输入考生编号，如 ZK2026000001 或 C1" style="width:320px" onkeydown="if(event.key==='Enter')App.lookupCandidate()">
        <button class="btn btn-primary" onclick="App.lookupCandidate()">查询</button>
        <span class="small muted">也可以输入姓名片段搜索</span>
      </div>
      <div id="candidate-result"><div class="empty"><strong>输入考生编号查询</strong>系统会展示四个批次的处理结果、每个志愿的原因与最终录取去向。</div></div>`;
    } else if (state.resultsTab === "plan") {
      await loadOptions();
      box.innerHTML = `<div class="toolbar" style="margin-bottom:14px">
        <select id="result-high" style="min-width:300px">${highOptions("", "全部高中")}</select>
        <button class="btn btn-primary" onclick="App.loadPlanResults()">查询计划</button>
        <a class="btn" href="/api/runs/${runId}/export/plans">导出计划统计 CSV</a>
      </div>
      <div id="plan-results"><div class="empty"><strong>选择高中查询计划</strong>可查看每条计划的有效名额、余额、最低录取分与末位考生。</div></div>`;
      await loadPlanResults();
    } else {
      box.innerHTML = `<div class="toolbar" style="margin-bottom:14px">
        <select id="adm-batch" onchange="App.admissionsFilter()"><option value="">全部批次</option>${[1, 2, 3, 4].map((b) => `<option value="${b}" ${String(state.admissionsBatch) === String(b) ? "selected" : ""}>第${b}批</option>`).join("")}</select>
        <select id="adm-high" onchange="App.admissionsFilter()">${highOptions(state.admissionsHigh, "全部高中")}</select>
        <a class="btn" href="/api/runs/${runId}/export/admissions">导出录取名单 CSV</a>
        <a class="btn" href="/api/runs/${runId}/export/candidates">导出考生结果 CSV</a>
      </div>
      <div id="admissions-table"><div class="loading">加载录取名单…</div></div>`;
      await loadAdmissions();
    }
  }

  App.lookupCandidate = async () => {
    const q = $("#candidate-lookup").value.trim();
    if (!q) { toast("请输入考生编号或姓名", "warn"); return; }
    const box = $("#candidate-result");
    box.innerHTML = `<div class="loading">查询中…</div>`;
    try {
      const data = await api(`/api/runs/${state.resultsRunId}/candidate-lookup?no=${encodeURIComponent(q)}`);
      box.innerHTML = renderCandidateResult(data);
    } catch (err) {
      const res = await api(`/api/candidates?q=${encodeURIComponent(q)}&size=10`);
      if (!res.items.length) {
        box.innerHTML = `<div class="alert bad"><div>未找到考生“${esc(q)}”。</div></div>`;
        return;
      }
      box.innerHTML = `<div class="card"><div class="card-head"><div class="card-title">匹配到 ${res.items.length} 名考生</div></div><div class="card-body tight"><div class="table-wrap"><table><thead><tr><th>编号</th><th>姓名</th><th>初中</th><th class="right">总分</th><th></th></tr></thead><tbody>
        ${res.items.map((c) => `<tr><td class="mono">${esc(c.candidate_no)}</td><td>${esc(c.name)}</td><td>${esc(c.middle_school_name)}</td><td class="right">${c.score}</td><td class="right"><button class="btn btn-sm btn-primary" onclick="App.showCandidateResult(${c.id})">查看结果</button></td></tr>`).join("")}
      </tbody></table></div></div></div>`;
    }
  };

  App.showCandidateResult = async (candidateId) => {
    const box = $("#candidate-result");
    box.innerHTML = `<div class="loading">加载考生结果…</div>`;
    try {
      const data = await api(`/api/runs/${state.resultsRunId}/candidate/${candidateId}`);
      box.innerHTML = renderCandidateResult(data);
    } catch (err) {
      box.innerHTML = `<div class="alert bad">${esc(err.message)}</div>`;
    }
  };

  function renderCandidateResult(data) {
    const c = data.candidate;
    const s = data.summary;
    const admission = data.admission;
    return `<div class="grid grid-2">
      <div class="card"><div class="card-head"><div><div class="card-title">${esc(c.name)} · ${esc(c.candidate_no)}</div><div class="card-sub">${esc(c.middle_school_name)} · 总分 ${c.score} · 同分序号 ${c.tie_seq}</div></div>
        ${s.admitted ? badge("已录取", "badge-ok") : badge("未录取", "badge-bad")}</div>
        <div class="card-body">
          ${admission ? `<div class="alert info"><div><strong>录取去向：</strong>${esc(admission.high_school_name)}（${esc(admission.batch_name || "第" + admission.batch + "批")}，第 ${admission.volunteer_seq} 志愿）<br><span class="small">计划 #${admission.plan_id} · ${esc(admission.category)} · 录取顺序 ${admission.admission_order}</span></div></div>` : `<div class="alert bad"><div><strong>最终结果：</strong>${esc(s.final_reason_text)}</div></div>`}
          <div class="stat-line"><span>是否录取</span><strong>${s.admitted ? "是" : "否"}</strong></div>
          <div class="stat-line"><span>录取批次</span><strong>${s.admitted_batch ? `第${s.admitted_batch}批` : "—"}</strong></div>
          <div class="stat-line"><span>录取高中</span><strong>${esc(s.admitted_high_school_id ? (admission ? admission.high_school_name : "—") : "—")}</strong></div>
          <div class="stat-line"><span>结果说明</span><strong class="small">${esc(s.final_reason_text)}</strong></div>
        </div>
      </div>
      <div class="card"><div class="card-head"><div><div class="card-title">志愿填报</div><div class="card-sub">共 ${data.volunteers.length} 条</div></div></div><div class="card-body tight">
        ${data.volunteers.length ? `<div class="table-wrap"><table><thead><tr><th>批次</th><th class="right">序号</th><th>高中</th></tr></thead><tbody>
          ${data.volunteers.map((v) => `<tr><td>第${v.batch}批</td><td class="right">${v.seq}</td><td><strong>${esc(v.high_school_name)}</strong></td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">未填报志愿</div>`}
      </div></div>
    </div>
    <div class="card" style="margin-top:16px"><div class="card-head"><div><div class="card-title">四批次处理过程</div><div class="card-sub">${data.batch_results.some((b) => b.detail_available) ? "逐志愿原因已记录" : "当前运行使用摘要模式，仅显示批次级原因"}</div></div></div><div class="card-body">
      ${data.batch_results.length ? `<div class="timeline">${data.batch_results.map((b) => `<div class="tl-item ${b.status === "ADMITTED" ? "ok" : b.status === "NOT_ADMITTED" ? "bad" : "info"}">
        <div class="tl-dot">${b.batch}</div>
        <div class="tl-body">
          <div class="tl-title">${esc(b.batch_name)} · ${b.status === "ADMITTED" ? "已录取" : b.status === "SKIPPED" ? "前批已录取" : b.status === "INELIGIBLE" ? "不具资格" : "未录取"}</div>
          <div class="tl-text">${esc(b.reason_text)}</div>
          ${b.detail && b.detail.length ? `<div class="table-wrap" style="margin-top:8px"><table><thead><tr><th class="right">志愿</th><th>高中</th><th>处理结果</th><th class="right">当时余额</th></tr></thead><tbody>
            ${b.detail.map((d) => `<tr><td class="right">${d.seq}</td><td>${esc(d.high_school_name || "—")}</td><td class="small">${esc(d.text || d.code)}</td><td class="right">${d.remaining ?? "—"}</td></tr>`).join("")}
          </tbody></table></div>` : ""}
        </div>
      </div>`).join("")}</div>` : `<div class="empty">该批次尚未执行</div>`}
    </div></div>`;
  }

  async function loadPlanResults() {
    const box = $("#plan-results");
    if (!box) return;
    const highId = $("#result-high") ? $("#result-high").value : "";
    box.innerHTML = `<div class="loading">加载计划…</div>`;
    let plansUrl = `/api/runs/${state.resultsRunId}/plans?page=1&size=100`;
    if (highId) plansUrl += `&high_school_id=${highId}`;
    const res = await api(plansUrl);
    box.innerHTML = res.items.length ? `<div class="table-wrap"><table><thead><tr><th>批次</th><th>高中 / 初中</th><th class="right">有效</th><th class="right">录取</th><th class="right">余额</th><th class="right">最低分</th><th>末位考生</th><th></th></tr></thead><tbody>
      ${res.items.map((p) => `<tr><td>第${p.batch}批</td><td><strong>${esc(p.high_school_name)}</strong>${p.middle_school_name ? `<div class="small muted">${esc(p.middle_school_name)}</div>` : ""}</td><td class="right">${p.effective_quota}</td><td class="right">${p.admitted_count}</td><td class="right">${p.remaining}</td><td class="right">${p.min_score ?? "无"}</td><td class="small">${p.last_admitted ? `${esc(p.last_admitted.candidate_no)} · ${p.last_admitted.score} 分 · 第${p.last_admitted.volunteer_seq}志愿` : "无"}</td><td class="right"><button class="btn btn-xs" onclick="App.showPlanAdmissions(${p.plan_id})">名单</button></td></tr>`).join("")}
    </tbody></table></div>` : `<div class="empty"><strong>没有匹配的计划</strong>请更换高中筛选。</div>`;
  }
  App.loadPlanResults = loadPlanResults;

  App.showPlanAdmissions = async (planId) => {
    const res = await api(`/api/runs/${state.resultsRunId}/admissions?plan_id=${planId}&size=500`);
    openModal({
      title: `计划 #${planId} 录取名单`,
      wide: true,
      hideOk: true,
      body: res.items.length ? `<div class="table-wrap"><table><thead><tr><th class="right">顺序</th><th>考生</th><th class="right">总分</th><th class="right">同分序号</th><th class="right">志愿</th><th>初中</th></tr></thead><tbody>
        ${res.items.map((a) => `<tr><td class="right">${a.admission_order}</td><td><strong>${esc(a.candidate_no)}</strong> · ${esc(a.candidate_name)}</td><td class="right">${a.score}</td><td class="right">${a.tie_seq}</td><td class="right">第${a.volunteer_seq}志愿</td><td>${esc(a.middle_school_name)}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">该计划无人录取</div>`,
    });
  };

  App.admissionsFilter = () => {
    state.admissionsBatch = $("#adm-batch").value;
    state.admissionsHigh = $("#adm-high").value;
    state.admissionsPage = 1;
    loadAdmissions();
  };
  App.admissionsPage = (page) => { state.admissionsPage = page; loadAdmissions(); };

  async function loadAdmissions() {
    const box = $("#admissions-table");
    if (!box) return;
    box.innerHTML = `<div class="loading">加载录取名单…</div>`;
    const qs = new URLSearchParams({ page: state.admissionsPage, size: 50 });
    if (state.admissionsBatch) qs.set("batch", state.admissionsBatch);
    if (state.admissionsHigh) qs.set("high_school_id", state.admissionsHigh);
    const res = await api(`/api/runs/${state.resultsRunId}/admissions?${qs}`);
    box.innerHTML = res.items.length ? `<div class="table-wrap"><table><thead><tr><th>批次</th><th>考生</th><th class="right">总分</th><th class="right">同分</th><th>高中</th><th>初中</th><th class="right">志愿</th><th class="right">计划内顺序</th></tr></thead><tbody>
      ${res.items.map((a) => `<tr><td>第${a.batch}批</td><td><strong>${esc(a.candidate_no)}</strong> · ${esc(a.candidate_name)}</td><td class="right">${a.score}</td><td class="right">${a.tie_seq}</td><td>${esc(a.high_school_name)}</td><td>${esc(a.middle_school_name)}</td><td class="right">第${a.volunteer_seq}志愿</td><td class="right">${a.admission_order}</td></tr>`).join("")}
    </tbody></table></div>${pagination(res, "admissionsPage")}` : `<div class="empty"><strong>没有录取记录</strong>该筛选条件下无人录取。</div>`;
  }

  // ---------------------------------------------------------------------
  // 统计
  // ---------------------------------------------------------------------
  async function renderStats(parts) {
    const runs = await api("/api/runs?limit=100");
    state.runs = runs;
    const completed = runs.filter((r) => r.current_batch > 0);
    if (!state.resultsRunId && completed.length) state.resultsRunId = completed[0].id;
    const run = runs.find((r) => r.id === Number(state.resultsRunId)) || completed[0];
    if (!run) {
      setView(`<div class="page-head"><div><h1 class="page-title">统计分析</h1><div class="page-sub">尚无运行结果，请先完成一次投档。</div></div></div><div class="card"><div class="card-body"><button class="btn btn-primary" onclick="App.goto('#/runs')">去投档执行</button></div></div>`);
      return;
    }
    state.resultsRunId = run.id;
    const stats = await api(`/api/runs/${run.id}/stats`);
    state.stats = stats;
    setView(`
      <div class="page-head">
        <div><h1 class="page-title">统计分析</h1><div class="page-sub">招生计划完成率、录取人数、分数分布、各计划最低录取分与末位考生。统计口径与明细分离。</div></div>
        <div class="actions">
          <select style="min-width:280px" onchange="App.selectStatsRun(this.value)">${runs.map((r) => `<option value="${r.id}" ${r.id === run.id ? "selected" : ""}>${esc(r.run_code)} · 第${r.current_batch}/4批</option>`).join("")}</select>
          <a class="btn" href="/api/runs/${run.id}/export/plans">导出计划统计</a>
          <a class="btn" href="/api/runs/${run.id}/export/high_schools">导出高中统计</a>
          <a class="btn" href="/api/runs/${run.id}/export/score_distribution">导出分数分布</a>
        </div>
      </div>
      <div id="stats-body"></div>
    `);
    renderStatsBody();
  }

  App.selectStatsRun = (id) => {
    state.resultsRunId = Number(id);
    renderStats([]);
  };

  function renderStatsBody() {
    const s = state.stats;
    if (!s) return;
    const sum = s.summary;
    const maxBand = Math.max(...s.bands.map((b) => b.total), 1);
    const maxHist = Math.max(...s.histogram.map((b) => b.total), 1);
    const plans = s.plan_stats.filter((p) => {
      const q = state.statsPlanFilter.toLowerCase();
      const matchQ = !q || `${p.high_school_name} ${p.high_school_code} ${p.middle_school_name || ""}`.toLowerCase().includes(q);
      const matchB = !state.statsPlanBatch || String(p.batch) === String(state.statsPlanBatch);
      return matchQ && matchB;
    }).slice(0, 200);
    $("#stats-body").innerHTML = `
      <div class="grid grid-5">
        <div class="card kpi"><div class="kpi-label">考生总数</div><div class="kpi-value">${fmt(sum.total_candidates)}</div><div class="kpi-foot">有效（≥L）${fmt(sum.eligible_candidates)}</div></div>
        <div class="card kpi ok"><div class="kpi-label">录取人数</div><div class="kpi-value">${fmt(sum.admitted_candidates)}</div><div class="kpi-foot">考生录取率 ${pct(sum.candidate_admission_rate)}</div></div>
        <div class="card kpi bad"><div class="kpi-label">未录取</div><div class="kpi-value">${fmt(sum.unadmitted_candidates)}</div><div class="kpi-foot">可在结果查询中查看原因</div></div>
        <div class="card kpi warn"><div class="kpi-label">计划完成率</div><div class="kpi-value">${pct(sum.plan_completion_rate)}</div><div class="kpi-foot">初始 ${fmt(sum.total_initial)} · 转入 ${fmt(sum.total_transferred_in)} · 转出 ${fmt(sum.total_transferred_out)} · 余额 ${fmt(sum.total_remaining)}</div></div>
        <div class="card kpi"><div class="kpi-label">最低录取分</div><div class="kpi-value">${sum.min_admitted_score ?? "无"}</div><div class="kpi-foot">全校最低不等于末位考生分数</div></div>
      </div>

      <div class="grid grid-2" style="margin-top:16px">
        <div class="card"><div class="card-head"><div><div class="card-title">梯度分布</div><div class="card-sub">各梯度考生数、录取数与录取率</div></div></div><div class="card-body">
          <div class="bars">${s.bands.map((b) => `<div class="bar-row"><div class="bar-label">${b.band ? `第${b.band}梯度` : "低于 L"}</div><div class="bar-track"><div class="bar-fill ${b.band ? "" : "ok"}" style="width:${Math.max(2, (b.total / maxBand) * 100)}%"></div></div><div class="bar-meta">${esc(b.range)} · ${fmt(b.total)}人 / 录取 ${fmt(b.admitted)}</div></div>`).join("")}</div>
        </div></div>
        <div class="card"><div class="card-head"><div><div class="card-title">分数分布（20 分一段）</div><div class="card-sub">总人数与录取人数</div></div></div><div class="card-body">
          <div class="bars" style="max-height:330px;overflow:auto">${s.histogram.map((b) => `<div class="bar-row"><div class="bar-label">${esc(b.range)}</div><div class="bar-track"><div class="bar-fill" style="width:${Math.max(1, (b.total / maxHist) * 100)}%"></div></div><div class="bar-meta">${fmt(b.total)} / 录取 ${fmt(b.admitted)}</div></div>`).join("")}</div>
        </div></div>
      </div>

      <div class="card" style="margin-top:16px"><div class="card-head"><div><div class="card-title">高中统计</div><div class="card-sub">学校总体统计与分批统计分开计算；最低录取分与末位考生分别计算</div></div></div><div class="card-body tight">
        <div class="table-wrap" style="max-height:420px"><table><thead><tr><th>高中</th><th>类型</th><th class="right">初始</th><th class="right">有效</th><th class="right">录取</th><th class="right">余额</th><th class="right">完成率</th><th class="right">最低分</th><th>末位考生</th></tr></thead><tbody>
          ${s.high_stats.map((h) => `<tr><td><strong>${esc(h.high_school_name)}</strong><div class="small muted">${esc(h.high_school_code)} · 第${h.intake_batch}批 · 初始 ${fmt(h.total_initial)} · 转入 ${fmt(h.total_in)} · 转出 ${fmt(h.total_out)}</div></td><td>${esc(h.category)}</td><td class="right">${fmt(h.total_initial)}</td><td class="right">${fmt(h.total_effective)}</td><td class="right">${fmt(h.total_admitted)}</td><td class="right">${fmt(h.total_remaining)}</td><td class="right">${pct(h.completion_rate)}</td><td class="right">${h.min_score ?? "无"}</td><td class="small">${h.last_admitted ? `${esc(h.last_admitted.candidate_no)} · ${h.last_admitted.score} 分 · 第${h.last_admitted.volunteer_seq}志愿` : "无"}</td></tr>`).join("")}
        </tbody></table></div>
      </div></div>

      <div class="card" style="margin-top:16px"><div class="card-head"><div><div class="card-title">计划级统计</div><div class="card-sub">共 ${fmt(s.plan_stats.length)} 条计划；下方最多显示 200 条，可用筛选缩小范围</div></div>
        <div class="toolbar"><input type="search" placeholder="搜索高中 / 初中" value="${esc(state.statsPlanFilter)}" oninput="App.filterPlanStats(this.value)" style="width:220px"><select onchange="App.filterPlanBatch(this.value)"><option value="">全部批次</option>${[1, 2, 3, 4].map((b) => `<option value="${b}" ${String(state.statsPlanBatch) === String(b) ? "selected" : ""}>第${b}批</option>`).join("")}</select></div>
      </div><div class="card-body tight"><div class="table-wrap" style="max-height:520px"><table><thead><tr><th>批次</th><th>高中 / 初中</th><th class="right">有效</th><th class="right">录取</th><th class="right">余额</th><th class="right">最低分</th><th>末位考生</th><th class="right">末位志愿</th><th class="right">末位同分序号</th></tr></thead><tbody>
        ${plans.length ? plans.map((p) => `<tr><td>第${p.batch}批</td><td><strong>${esc(p.high_school_name)}</strong>${p.middle_school_name ? `<div class="small muted">${esc(p.middle_school_name)}</div>` : ""}</td><td class="right">${fmt(p.effective_quota)}</td><td class="right">${fmt(p.admitted_count)}</td><td class="right">${fmt(p.remaining)}</td><td class="right">${p.min_score ?? "无"}</td><td class="small">${p.last_admitted ? `${esc(p.last_admitted.candidate_no)} · ${esc(p.last_admitted.name)} · ${p.last_admitted.score} 分` : "无"}</td><td class="right">${p.last_admitted ? p.last_admitted.volunteer_seq : "—"}</td><td class="right">${p.last_admitted ? p.last_admitted.tie_seq : "—"}</td></tr>`).join("") : `<tr><td colspan="9"><div class="empty">没有匹配的计划</div></td></tr>`}
      </tbody></table></div></div></div>

      <div class="grid grid-2" style="margin-top:16px">
        <div class="card"><div class="card-head"><div><div class="card-title">未录取原因分布</div><div class="card-sub">按最终结果代码统计</div></div></div><div class="card-body tight"><div class="table-wrap"><table><thead><tr><th>原因</th><th>说明</th><th class="right">人数</th></tr></thead><tbody>
          ${s.reasons.length ? s.reasons.map((r) => `<tr><td class="mono small">${esc(r.code)}</td><td class="small">${esc(r.text)}</td><td class="right"><strong>${fmt(r.count)}</strong></td></tr>`).join("") : `<tr><td colspan="3"><div class="empty">全部考生均已录取</div></td></tr>`}
        </tbody></table></div></div></div>
        <div class="card"><div class="card-head"><div><div class="card-title">结转汇总</div><div class="card-sub">第一批、第二批剩余名额转入第三批</div></div></div><div class="card-body tight"><div class="table-wrap"><table><thead><tr><th>来源批次</th><th class="right">流水条数</th><th class="right">转入人数</th></tr></thead><tbody>
          ${s.transfers.length ? s.transfers.map((t) => `<tr><td>第${t.from_batch}批</td><td class="right">${fmt(t.count)}</td><td class="right"><strong>${fmt(t.amount)}</strong></td></tr>`).join("") : `<tr><td colspan="3"><div class="empty">没有结转</div></td></tr>`}
        </tbody></table></div></div></div>
      </div>
    `;
  }

  App.filterPlanStats = (value) => {
    state.statsPlanFilter = value;
    renderStatsBody();
  };
  App.filterPlanBatch = (value) => {
    state.statsPlanBatch = value;
    renderStatsBody();
  };

  // ---------------------------------------------------------------------
  // 滑档案例
  // ---------------------------------------------------------------------
  async function renderCases() {
    const cases = await api("/api/cases/slip");
    state.cases = cases;
    setView(`
      <div class="page-head">
        <div><h1 class="page-title">高分滑档案例与志愿调整对照</h1><div class="page-sub">保持成绩、招生计划和其他考生志愿不变，仅调整高分考生的志愿，重新完整投档并对比结果。</div></div>
      </div>
      <div class="grid grid-2">
        ${cases.map((c) => `<div class="card"><div class="card-head"><div><div class="card-title">${esc(c.title)}</div><div class="card-sub">重点考生 ${esc(c.focus_candidate_no)}</div></div><button class="btn btn-primary btn-sm" onclick="App.runCase('${esc(c.key)}')">运行对照</button></div><div class="card-body"><p class="muted" style="margin:0">${esc(c.description)}</p></div></div>`).join("")}
      </div>
      <div id="case-results" style="margin-top:16px">${state.caseResults ? "" : `<div class="card"><div class="card-body"><div class="empty"><strong>尚未运行对照</strong>点击任一案例的“运行对照”，系统会分别执行基线与调整后的完整四批投档。</div></div></div>`}</div>
    `);
    if (state.caseResults) renderCaseResults();
  }

  App.runCase = async (key) => {
    showOverlay("正在运行基线与调整后的完整投档…");
    try {
      const res = await api("/api/cases/slip/run", { method: "POST", body: JSON.stringify({ key }) });
      state.caseResults = res;
      hideOverlay();
      toast("对照运行完成", "ok");
      renderCaseResults();
    } catch (err) {
      hideOverlay();
      toast(err.message, "bad");
    }
  };

  function renderCaseResults() {
    const box = $("#case-results");
    if (!box || !state.caseResults) return;
    box.innerHTML = state.caseResults.map((r) => {
      const bf = r.baseline.focus;
      const af = r.adjusted.focus;
      const bc = bf.candidate;
      const ac = af.candidate;
      return `<div class="card" style="margin-top:16px">
        <div class="card-head"><div><div class="card-title">${esc(r.title)}</div><div class="card-sub">${esc(r.description)}</div></div>${badge("仅调整 " + r.focus_candidate_no + " 的志愿", "badge-info")}</div>
        <div class="card-body">
          <div class="split">
            <div class="card"><div class="card-head"><div><div class="card-title">基线：调整前</div><div class="card-sub">${esc(bc.name)} · ${bc.score} 分 · ${esc(bc.middle_school_name)}</div></div>${bc.admitted ? badge(`第${bc.admitted_batch}批录取`, "badge-ok") : badge("未录取", "badge-bad")}</div>
              <div class="card-body">
                <div class="stat-line"><span>录取结果</span><strong>${bc.admitted ? `${esc(bc.admitted_high_school_name)} · 第${bc.admitted_volunteer_seq}志愿` : "全部批次结束仍未录取"}</strong></div>
                <div class="table-wrap" style="margin-top:8px"><table><thead><tr><th>批次</th><th class="right">志愿</th><th>高中</th></tr></thead><tbody>${bf.volunteers.map((v) => `<tr><td>第${v.batch}批</td><td class="right">${v.seq}</td><td>${esc(v.high_school_name)}</td></tr>`).join("")}</tbody></table></div>
              </div></div>
            <div class="card"><div class="card-head"><div><div class="card-title">调整后</div><div class="card-sub">${esc(ac.name)} · ${ac.score} 分 · ${esc(ac.middle_school_name)}</div></div>${ac.admitted ? badge(`第${ac.admitted_batch}批录取`, "badge-ok") : badge("未录取", "badge-bad")}</div>
              <div class="card-body">
                <div class="stat-line"><span>录取结果</span><strong>${ac.admitted ? `${esc(ac.admitted_high_school_name)} · 第${ac.admitted_volunteer_seq}志愿` : "全部批次结束仍未录取"}</strong></div>
                <div class="table-wrap" style="margin-top:8px"><table><thead><tr><th>批次</th><th class="right">志愿</th><th>高中</th></tr></thead><tbody>${af.volunteers.map((v) => `<tr><td>第${v.batch}批</td><td class="right">${v.seq}</td><td>${esc(v.high_school_name)}</td></tr>`).join("")}</tbody></table></div>
              </div></div>
          </div>

          <div class="card" style="margin-top:16px"><div class="card-head"><div><div class="card-title">录取结果变化</div><div class="card-sub">保持其他条件不变，仅调整 ${esc(r.focus_candidate_no)} 的志愿后，受影响考生</div></div></div><div class="card-body tight"><div class="table-wrap"><table><thead><tr><th>考生</th><th class="right">总分</th><th>调整前</th><th>调整后</th></tr></thead><tbody>
            ${r.comparison.changes.length ? r.comparison.changes.map((c) => `<tr><td><strong>${esc(c.candidate_no)}</strong> · ${esc(c.name)}</td><td class="right">${c.score}</td><td>${c.baseline.admitted ? `${esc(c.baseline.high_school)} · 第${c.baseline.batch}批` : badge("未录取", "badge-bad")}</td><td>${c.adjusted.admitted ? `${esc(c.adjusted.high_school)} · 第${c.adjusted.batch}批` : badge("未录取", "badge-bad")}</td></tr>`).join("") : `<tr><td colspan="4"><div class="empty">没有考生录取结果发生变化</div></td></tr>`}
          </tbody></table></div></div></div>

          <div class="split" style="margin-top:16px">
            ${[["基线", bf], ["调整后", af]].map(([label, focus]) => `<div class="card"><div class="card-head"><div><div class="card-title">${label} · 四批次处理</div><div class="card-sub">${esc(focus.candidate.name)}</div></div></div><div class="card-body">
              <div class="timeline">${focus.candidate.batch_results.map((b) => `<div class="tl-item ${b.status === "ADMITTED" ? "ok" : b.status === "NOT_ADMITTED" ? "bad" : "info"}"><div class="tl-dot">${b.batch}</div><div class="tl-body"><div class="tl-title">${esc(b.batch_name)} · ${b.status === "ADMITTED" ? "已录取" : b.status === "SKIPPED" ? "前批已录取" : "未录取"}</div><div class="tl-text">${esc(b.reason_text)}</div></div></div>`).join("")}</div>
            </div></div>`).join("")}
          </div>

          <div class="alert info" style="margin-top:16px"><div><strong>人工推演：</strong>见 <span class="mono">docs/测试材料.md</span> 的“滑档案例”章节。系统运行结果应与人工推演一致；对照实验说明志愿顺序/保底志愿对滑档的影响，同时展示对其他考生的挤出效应。</div></div>
        </div>
      </div>`;
    }).join("");
  }

  // ---------------------------------------------------------------------
  // 帮助
  // ---------------------------------------------------------------------
  function renderHelp() {
    setView(`
      <div class="page-head"><div><h1 class="page-title">帮助与规则</h1><div class="page-sub">本页说明任务书的简化规则、投档顺序、统计口径与系统约束。完整设计见 docs/设计报告.docx。</div></div></div>
      <div class="help-grid">
        <div class="card"><div class="card-head"><div class="card-title">批次与志愿上限</div></div><div class="card-body">
          <div class="table-wrap"><table><thead><tr><th>批次</th><th>内容</th><th class="right">志愿上限</th></tr></thead><tbody>
            <tr><td>第一批</td><td>自主招生：资格名单 + 考核排名 + 计划控制线</td><td class="right">1</td></tr>
            <tr><td>第二批</td><td>名额分配：按（高中, 初中）分计划，校内竞争</td><td class="right">3</td></tr>
            <tr><td>第三批</td><td>示范性公办高中统招</td><td class="right">6</td></tr>
            <tr><td>第四批</td><td>非示范公办高中统招</td><td class="right">6</td></tr>
          </tbody></table></div>
          <p class="small muted" style="margin-bottom:0">严格按批次顺序执行；前批录取者立即退出后续批次。</p>
        </div></div>
        <div class="card"><div class="card-head"><div class="card-title">梯度与投档顺序</div></div><div class="card-body">
          <ul class="notice-list">
            <li>第一梯度：总分 ≥ G₁；第二梯度：G₁−Δ ≤ 总分 &lt; G₁；以此类推，最后一档截至 L。</li>
            <li>分数恰好等于梯度线时，归入较高梯度；低于 L 不参与录取。</li>
            <li>同一批次先处理高梯度，再处理低梯度；同一梯度先处理第一志愿，再处理第二志愿。</li>
            <li>同一计划、同一轮次内按总分降序、同分序号升序录取。</li>
            <li>不能先为每名考生依次扫描全部志愿再处理下一人。</li>
          </ul>
        </div></div>
        <div class="card"><div class="card-head"><div class="card-title">名额分配与结转</div></div><div class="card-body">
          <ul class="notice-list">
            <li>第二批考生只能竞争其所属初中获得的名额，不同初中名额不得互相挤占。</li>
            <li>第一批结束后，各高中自主招生剩余名额转入本校第三批统招计划。</li>
            <li>第二批结束后，先按高中汇总各初中剩余名额，再转入本校第三批统招计划。</li>
            <li>第三、第四批余缺不互转；有效计划 = 初始计划 + 转入数。</li>
            <li>每次运行从初始状态重新计算，结转只发生一次，不叠加。</li>
          </ul>
        </div></div>
        <div class="card"><div class="card-head"><div class="card-title">统计口径</div></div><div class="card-body">
          <ul class="notice-list">
            <li>最低录取分 = 该计划已录取考生总分的最小值。</li>
            <li>末位考生 = 按该计划实际录取顺序最后录取的人，另报总分、志愿序号、同分序号。</li>
            <li>两者分别计算，末位考生分数可能高于最低录取分；无人录取显示“无”，不能用 0 分代替。</li>
            <li>学校总体统计与分批、分类计划统计分开。</li>
          </ul>
        </div></div>
        <div class="card"><div class="card-head"><div class="card-title">系统约束</div></div><div class="card-body">
          <ul class="notice-list">
            <li>每名考生每次模拟最多录取一次。</li>
            <li>每条计划录取人数不超过有效名额。</li>
            <li>每条录取记录对应有效志愿并满足资格与分数要求。</li>
            <li>初始名额 + 转入 − 转出 = 已录取 + 剩余。</li>
            <li>汇总统计与明细一致；运行后可执行“一致性校验”。</li>
          </ul>
        </div></div>
        <div class="card"><div class="card-head"><div class="card-title">数据与复现</div></div><div class="card-body">
          <ul class="notice-list">
            <li>每次运行保存 gzip JSON 输入快照与 SHA-256，历史结果不可变。</li>
            <li>运行完成后数据版本锁定；修改输入需“创建新数据版本”。</li>
            <li>重新运行创建独立运行编号，不叠加旧录取。</li>
            <li>演示数据使用固定随机种子，可重复生成；全部为虚构数据。</li>
            <li>REST API 文档：<a href="/docs" target="_blank">/docs</a></li>
          </ul>
        </div></div>
      </div>
    `);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
