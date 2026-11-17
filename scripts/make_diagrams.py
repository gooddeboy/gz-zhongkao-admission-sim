"""生成设计报告用的架构图、ER 图、流程图。

用法：
    python scripts/make_diagrams.py
输出：
    docs/images/architecture.png
    docs/images/er-diagram.png
    docs/images/flow.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

INK = "#1f2937"
MUTED = "#64748b"
BRAND = "#4f46e5"
CYAN = "#0ea5e9"
GREEN = "#059669"
AMBER = "#d97706"
LIGHT = "#f8fafc"
LINE = "#cbd5e1"


def box(ax, x, y, w, h, title, lines=(), color=BRAND, fill="#eef2ff", title_size=11, line_size=8.5):
    patch = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
        linewidth=1.2, edgecolor=color, facecolor=fill, zorder=2,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h - 0.18, title, ha="center", va="top",
            fontsize=title_size, fontweight="bold", color=color, zorder=3)
    if lines:
        ax.text(x + w / 2, y + h - 0.52, "\n".join(lines), ha="center", va="top",
                fontsize=line_size, color=INK, linespacing=1.55, zorder=3)


def arrow(ax, x1, y1, x2, y2, label="", color=MUTED, style="-|>", rad=0.0):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle=style, mutation_scale=12,
        linewidth=1.3, color=color, connectionstyle=f"arc3,rad={rad}", zorder=1,
    ))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.08, label, ha="center", va="bottom",
                fontsize=8, color=color, zorder=4)


def architecture():
    fig, ax = plt.subplots(figsize=(12, 7.2))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7.2)
    ax.axis("off")
    ax.text(0.3, 6.9, "系统总体架构", fontsize=17, fontweight="bold", color=INK)

    box(ax, 1.2, 5.55, 9.6, 1.0, "浏览器：原生 HTML / CSS / JavaScript 单页应用",
        ["数据管理 · 投档执行 · 结果查询 · 统计分析 · 滑档案例"], color=CYAN, fill="#ecfeff")
    box(ax, 1.2, 3.45, 4.6, 1.45, "FastAPI 应用层",
        ["REST API（/api/*）", "静态文件服务", "Pydantic 请求校验", "异常与错误码"], color=BRAND, fill="#eef2ff")
    box(ax, 6.2, 3.45, 4.6, 1.45, "投档引擎（纯内存）",
        ["梯度计算", "四批次投档", "名额隔离 / 结转", "一致性校验 verify_run"], color=GREEN, fill="#ecfdf5")
    box(ax, 1.2, 1.05, 4.6, 1.5, "SQLite 数据库",
        ["输入表：高中/初中/考生/计划/资格/志愿", "运行表：运行/计划状态/录取/结果", "日志：结转/事件/批次汇总"], color=AMBER, fill="#fffbeb")
    box(ax, 6.2, 1.05, 4.6, 1.5, "不可变快照与导出",
        ["gzip JSON 快照", "input_hash / snapshot_sha256", "CSV 导出", "历史运行可复现"], color="#7c3aed", fill="#f5f3ff")

    arrow(ax, 3.5, 5.55, 3.5, 4.9, "HTTP / JSON", CYAN)
    arrow(ax, 3.5, 4.9, 3.5, 5.55, "", CYAN)
    arrow(ax, 5.8, 4.15, 6.2, 4.15, "调用", BRAND)
    arrow(ax, 5.8, 3.7, 6.2, 3.7, "结果", GREEN)
    arrow(ax, 3.5, 3.45, 3.5, 2.55, "读写", AMBER)
    arrow(ax, 3.5, 2.55, 3.5, 3.45, "", AMBER)
    arrow(ax, 6.2, 2.8, 5.8, 2.8, "持久化", "#7c3aed")
    arrow(ax, 8.5, 3.45, 8.5, 2.55, "快照 / 导出", "#7c3aed")
    arrow(ax, 8.5, 2.55, 8.5, 3.45, "", "#7c3aed")

    ax.text(0.35, 0.35, "说明：引擎不直接依赖 Web 框架；同一引擎既用于数据库运行，也用于滑档案例的内存对照。",
            fontsize=8.5, color=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "architecture.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def er_diagram():
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.text(0.3, 7.7, "数据库 ER 图（简化）", fontsize=17, fontweight="bold", color=INK)

    # 输入实体
    box(ax, 0.5, 5.7, 2.2, 1.35, "高中", ["编号 / 名称", "类型 / 统招批次", "自主招生标志"], BRAND, "#eef2ff")
    box(ax, 3.1, 5.7, 2.2, 1.35, "初中", ["编号 / 名称", "区"], BRAND, "#eef2ff")
    box(ax, 5.7, 5.7, 2.2, 1.35, "考生", ["编号 / 姓名", "总分 / 同分序号", "所属初中"], BRAND, "#eef2ff")
    box(ax, 8.3, 5.7, 2.2, 1.35, "招生计划", ["批次 / 类别", "名额 / 控制线", "高中 / 初中"], BRAND, "#eef2ff")
    box(ax, 10.9, 5.7, 1.8, 1.35, "资格", ["状态 / 排名"], BRAND, "#eef2ff")

    # 关系实体
    box(ax, 1.8, 3.4, 2.4, 1.3, "志愿", ["批次 / 序号", "考生 / 高中"], CYAN, "#ecfeff")
    box(ax, 5.0, 3.4, 2.4, 1.3, "运行", ["编号 / 参数", "状态 / 版本", "快照 / 哈希"], GREEN, "#ecfdf5")
    box(ax, 8.2, 3.4, 2.4, 1.3, "计划状态", ["初始 / 转入", "转出 / 录取", "余额"], GREEN, "#ecfdf5")
    box(ax, 10.9, 3.4, 1.8, 1.3, "结转流水", ["来源 / 去向"], AMBER, "#fffbeb")

    # 结果实体
    box(ax, 0.5, 1.0, 2.6, 1.35, "录取明细", ["考生 / 计划", "批次 / 志愿", "分数 / 顺序"], "#7c3aed", "#f5f3ff")
    box(ax, 3.5, 1.0, 2.6, 1.35, "批次结果", ["状态 / 原因", "逐志愿明细"], "#7c3aed", "#f5f3ff")
    box(ax, 6.5, 1.0, 2.6, 1.35, "考生汇总", ["是否录取", "批次 / 高中", "最终原因"], "#7c3aed", "#f5f3ff")
    box(ax, 9.5, 1.0, 2.6, 1.35, "事件 / 快照", ["事件日志", "gzip 快照"], "#7c3aed", "#f5f3ff")

    # 连线
    arrow(ax, 1.6, 5.7, 2.7, 4.7, "设置计划", BRAND, rad=0.05)
    arrow(ax, 4.2, 5.7, 3.6, 4.7, "获得名额", BRAND, rad=-0.05)
    arrow(ax, 6.8, 5.7, 3.0, 4.7, "填报", CYAN, rad=0.05)
    arrow(ax, 7.8, 5.7, 4.0, 4.7, "目标", CYAN, rad=-0.05)
    arrow(ax, 9.4, 5.7, 5.2, 4.7, "生成状态", GREEN, rad=0.05)
    arrow(ax, 10.0, 5.7, 9.0, 4.7, "状态", GREEN, rad=-0.05)
    arrow(ax, 11.6, 5.7, 10.6, 4.7, "授予", BRAND, rad=-0.05)

    arrow(ax, 5.8, 3.4, 2.2, 2.35, "产生", "#7c3aed", rad=0.05)
    arrow(ax, 6.2, 3.4, 4.4, 2.35, "记录", "#7c3aed", rad=0.05)
    arrow(ax, 6.8, 3.4, 7.2, 2.35, "汇总", "#7c3aed", rad=-0.05)
    arrow(ax, 7.4, 3.4, 10.2, 2.35, "日志", "#7c3aed", rad=-0.1)
    arrow(ax, 9.4, 3.4, 10.6, 2.35, "持久化", "#7c3aed", rad=0.1)
    arrow(ax, 9.8, 4.05, 10.9, 4.05, "记录", AMBER)

    ax.text(0.35, 0.35, "说明：输入表保存当前数据版本；运行相关表按 run_id 隔离，历史运行结果不随输入修改而改变。",
            fontsize=8.5, color=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "er-diagram.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def flow():
    fig, ax = plt.subplots(figsize=(9.5, 10))
    ax.set_xlim(0, 9.5)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.text(0.3, 9.7, "投档执行流程", fontsize=17, fontweight="bold", color=INK)

    steps = [
        ("1. 数据校验", "error 拒绝运行；warning 提示", BRAND, "#eef2ff"),
        ("2. 创建运行", "写入 gzip 快照 + input_hash；锁定数据版本", CYAN, "#ecfeff"),
        ("3. 第一批 自主招生", "资格名单 + 考核排名 + 计划控制线", GREEN, "#ecfdf5"),
        ("4. 第一批结转", "剩余名额 → 本校第三批统招", AMBER, "#fffbeb"),
        ("5. 第二批 名额分配", "按（高中, 初中）校内竞争；梯度优先、志愿轮次", GREEN, "#ecfdf5"),
        ("6. 第二批结转", "按高中汇总剩余 → 本校第三批统招", AMBER, "#fffbeb"),
        ("7. 第三批 统招", "全市未录取考生；梯度优先、志愿轮次、分数/同分排序", GREEN, "#ecfdf5"),
        ("8. 第四批 统招", "规则同第三批；第三、四批余缺不互转", GREEN, "#ecfdf5"),
        ("9. 结果与统计", "录取明细、计划余额、结转流水、最低分/末位考生、导出", "#7c3aed", "#f5f3ff"),
    ]
    y = 8.9
    for i, (title, desc, color, fill) in enumerate(steps):
        box(ax, 1.2, y - 0.62, 6.8, 0.72, title, [desc], color, fill, title_size=10.5, line_size=8.2)
        if i < len(steps) - 1:
            arrow(ax, 4.6, y - 0.62, 4.6, y - 0.9, "", color)
        y -= 0.92

    ax.text(8.35, 8.55, "每批结束后\n更新计划余额\n并写事件日志", fontsize=8.5, color=MUTED, va="top")
    ax.text(8.35, 5.9, "运行完成 →\n锁定版本\n历史结果不变", fontsize=8.5, color=MUTED, va="top")
    ax.text(8.35, 3.2, "可执行\n一致性校验\nverify_run", fontsize=8.5, color=MUTED, va="top")
    fig.tight_layout()
    fig.savefig(OUT / "flow.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    architecture()
    er_diagram()
    flow()
    print("已生成：", OUT / "architecture.png", OUT / "er-diagram.png", OUT / "flow.png")
