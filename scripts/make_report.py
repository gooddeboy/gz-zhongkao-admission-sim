"""生成课程设计报告 docs/设计报告.docx。

用法：
    python scripts/make_report.py
依赖：
    python-docx
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "images"
OUT = ROOT / "docs" / "设计报告.docx"

FONT = "微软雅黑"
MONO = "Consolas"
INK = RGBColor(0x1F, 0x29, 0x37)
BRAND = RGBColor(0x4F, 0x46, 0xE5)
MUTED = RGBColor(0x64, 0x74, 0x8B)


def set_cell_shading(cell, color: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def set_east_asian(run, font_name: str = FONT) -> None:
    run.font.name = font_name
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), font_name)


def style_document(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = INK
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    normal.paragraph_format.line_spacing = 1.45
    normal.paragraph_format.space_after = Pt(4)

    for level, size, color in ((1, 17, BRAND), (2, 13.5, INK), (3, 11.5, INK)):
        style = doc.styles[f"Heading {level}"]
        style.font.name = FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color
        style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        style.paragraph_format.space_before = Pt(12 if level == 1 else 9)
        style.paragraph_format.space_after = Pt(6)


def add_page_number(section) -> None:
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("第 ")
    run.font.size = Pt(9)
    run.font.color.rgb = MUTED
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run2 = p.add_run()
    run2._r.append(fld_begin)
    run2._r.append(instr)
    run2._r.append(fld_end)
    run3 = p.add_run(" 页")
    run3.font.size = Pt(9)
    run3.font.color.rgb = MUTED


def add_caption(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.font.size = Pt(9)
    run.font.color.rgb = MUTED
    set_east_asian(run)
    p.paragraph_format.space_after = Pt(10)


def add_image(doc: Document, name: str, caption: str, width_cm: float = 15.5) -> None:
    path = IMG / name
    if not path.exists():
        return
    doc.add_picture(str(path), width=Cm(width_cm))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_caption(doc, caption)


def add_table(doc: Document, headers, rows, widths=None, font_size: float = 9) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(str(h))
        run.bold = True
        run.font.size = Pt(font_size)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        set_east_asian(run)
        set_cell_shading(hdr[i], "4F46E5")
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            run = p.add_run(str(value))
            run.font.size = Pt(font_size)
            set_east_asian(run)
    if widths:
        for i, width in enumerate(widths):
            for row in table.rows:
                row.cells[i].width = Cm(width)
    doc.add_paragraph()


def add_bullets(doc: Document, items) -> None:
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        run = p.add_run(item)
        run.font.size = Pt(10.5)
        set_east_asian(run)


def add_code(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.4)
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    run.font.name = MONO
    run.font.size = Pt(8.3)
    run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), "F3F4F6")
    pPr.append(shd)


def cover(doc: Document) -> None:
    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("软件系统开发实践")
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = MUTED
    set_east_asian(run)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("课程设计报告")
    run.font.size = Pt(30)
    run.font.bold = True
    run.font.color.rgb = BRAND
    set_east_asian(run)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("简化广州中考公办高中录取模拟系统")
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = INK
    set_east_asian(run)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("四批次投档 · 梯度志愿 · 名额分配 · 计划结转 · 结果统计")
    run.font.size = Pt(11)
    run.font.color.rgb = MUTED
    set_east_asian(run)

    for _ in range(4):
        doc.add_paragraph()

    info = [
        ("课程名称", "软件系统开发实践"),
        ("项目名称", "简化广州中考公办高中录取模拟系统"),
        ("组别 / 成员", "（请填写实际组别、成员姓名与学号）"),
        ("指导教师", "（请填写）"),
        ("完成日期", "2026 年 11 月"),
    ]
    table = doc.add_table(rows=0, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for k, v in info:
        cells = table.add_row().cells
        cells[0].text = ""
        cells[1].text = ""
        r1 = cells[0].paragraphs[0].add_run(k)
        r1.font.size = Pt(10.5)
        r1.font.bold = True
        r1.font.color.rgb = MUTED
        set_east_asian(r1)
        r2 = cells[1].paragraphs[0].add_run(v)
        r2.font.size = Pt(10.5)
        set_east_asian(r2)
        cells[0].width = Cm(3.6)
        cells[1].width = Cm(9.5)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("本报告中的姓名、学校、考号均为虚构数据，仅用于教学模拟。")
    run.font.size = Pt(9)
    run.font.color.rgb = MUTED
    set_east_asian(run)
    doc.add_page_break()


def toc(doc: Document) -> None:
    doc.add_heading("目  录", level=1)
    items = [
        "1 需求分析",
        "2 总体设计",
        "3 数据库设计",
        "4 核心算法",
        "5 系统实现",
        "6 测试与验证",
        "7 部署与使用",
        "8 团队分工与阶段计划",
        "9 总结与改进",
        "附录 A 规则参数与梯度",
        "附录 B 主要 API 清单",
        "附录 C AI 使用说明",
    ]
    for item in items:
        p = doc.add_paragraph()
        run = p.add_run(item)
        run.font.size = Pt(11)
        set_east_asian(run)
        p.paragraph_format.space_after = Pt(2)
    p = doc.add_paragraph()
    run = p.add_run("说明：本目录为手工目录；如需页码，可在 Word 中使用“引用 → 目录”自动生成。")
    run.font.size = Pt(9)
    run.font.color.rgb = MUTED
    set_east_asian(run)
    doc.add_page_break()


def abstract(doc: Document) -> None:
    doc.add_heading("摘  要", level=1)
    text = (
        "本课程设计实现了一个简化广州中考公办高中录取模拟系统。系统以任务书规定的四批次规则为核心："
        "第一批自主招生按资格名单、考核排名和计划控制线录取；第二批名额分配按（高中, 初中）分计划，"
        "考生只能在校内竞争本人所属初中的名额；第三批、第四批统招按梯度优先、志愿轮次、总分降序、"
        "同分序号升序执行。第一批和第二批剩余名额分别结转至第三批统招计划，第三、第四批余缺不互转。"
        "系统采用 Python + FastAPI + SQLite + 原生前端实现，提供数据管理、CSV 导入与校验、按批/完整投档、"
        "计划余额与结转流水、考生结果解释、统计分析、CSV 导出以及两个高分滑档案例的志愿调整对照。"
        "每次运行保存 gzip JSON 输入快照和 SHA-256，运行完成后锁定数据版本，保证历史结果可复现、"
        "不叠加旧录取。系统通过 45 项 pytest 自动化测试和人工逐轮推演对照，覆盖梯度、志愿、同分、边界、"
        "自主招生、跨批次排除、名额隔离、结转、不足额、统计口径、异常输入和重复运行等场景。"
    )
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)
    p.paragraph_format.line_spacing = 1.6

    p = doc.add_paragraph()
    run = p.add_run("关键词：")
    run.bold = True
    run.font.size = Pt(10.5)
    set_east_asian(run)
    run2 = p.add_run("中考录取；梯度志愿；名额分配；四批次投档；计划结转；SQLite；FastAPI")
    run2.font.size = Pt(10.5)
    set_east_asian(run2)
    doc.add_page_break()


def chapter_requirements(doc: Document) -> None:
    doc.add_heading("1 需求分析", level=1)
    doc.add_heading("1.1 背景与目标", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "广州中考公办高中录取涉及批次、梯度、志愿、名额分配和控制线等多重规则。本课程设计以该业务为背景，"
        "要求完成一个可运行、可验证的软件系统，重点考察需求分析、数据建模、投档规则实现、软件测试和团队协作。"
        "系统不追求完整复现现实政策，而是严格按照任务书的简化规则实现，并以人工小数据集和自动化测试作为验收依据。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)

    doc.add_heading("1.2 范围与简化", level=2)
    add_table(
        doc,
        ["项目", "本系统处理"],
        [
            ("招生对象", "全部考生视为具有公办高中报考资格，不区分户籍、随迁子女、应往届和学籍年限"),
            ("招生地域", "不区分区内、区外、跨区生；不设区外生比例"),
            ("成绩与优先条件", "不考虑政策加分、同等条件优先录取、参考科目等级；总分直接作为投档分"),
            ("学校与计划", "只模拟公办普通高中；每所高中只在第三批或第四批之一设置统招"),
            ("第一批", "只保留自主招生；资格与考核排名直接输入"),
            ("第二批", "保留名额分配到初中；直接录入分配表，不模拟电脑派位"),
            ("其他流程", "不模拟退档、放弃录取、报到注册、正式补录"),
        ],
        widths=[3.6, 12.2],
    )

    doc.add_heading("1.3 用户与用例", level=2)
    add_table(
        doc,
        ["角色", "主要用例"],
        [
            ("数据管理员", "维护高中、初中、考生、计划、资格、志愿；CSV 导入；数据校验；生成演示数据"),
            ("招生办操作员", "新建运行；按批执行/完整运行；查看进度、计划余额、结转流水；一致性校验"),
            ("查询用户", "按考生/高中/计划/批次查询录取去向、志愿处理过程与未录取原因；导出名单"),
            ("分析人员", "查看完成率、分数分布、最低录取分、末位考生；运行滑档案例对照"),
        ],
        widths=[3.6, 12.2],
    )

    doc.add_heading("1.4 规则清单", level=2)
    add_table(
        doc,
        ["规则", "要点"],
        [
            ("批次与志愿", "第一批 1 个、第二批 3 个、第三批 6 个、第四批 6 个；严格按批次顺序执行"),
            ("梯度", "G₁ 以上为第 1 梯度；每降 Δ 为下一梯度；最后一档截至 L；等于梯度线归入较高梯度"),
            ("自主招生", "资格合格 + 达到计划控制线，按考核排名录取；排名同一高中内唯一"),
            ("名额分配", "按（高中, 初中）分计划；只能竞争本人初中的名额；不同初中不互相挤占"),
            ("统招", "先梯度、再志愿轮次；同一计划同一轮次按总分降序、同分序号升序"),
            ("结转", "第一批剩余→第三批；第二批按高中汇总剩余→第三批；第三、四批余缺不互转"),
            ("统计", "最低录取分与末位考生分别计算；无人录取显示“无”；学校总体与分批统计分开"),
            ("版本", "运行保存快照并锁定数据；已完成运行的输入不得静默修改；重复运行不叠加"),
        ],
        widths=[3.0, 12.8],
    )


def chapter_design(doc: Document) -> None:
    doc.add_heading("2 总体设计", level=1)
    doc.add_heading("2.1 系统架构", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "系统采用浏览器/服务器结构，前端为原生单页应用，后端为 FastAPI，投档引擎为纯内存模块，"
        "SQLite 保存输入数据、运行结果、日志和快照索引。引擎不依赖 Web 框架，因此既可用于数据库运行，"
        "也可直接用于滑档案例的基线与调整后对照。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)
    add_image(doc, "architecture.png", "图 2-1 系统总体架构")

    doc.add_heading("2.2 技术选型与理由", level=2)
    add_table(
        doc,
        ["层次", "技术", "选择理由"],
        [
            ("后端", "Python 3.13 + FastAPI", "类型清晰、自动生成 OpenAPI 文档、开发效率高；便于编写测试"),
            ("数据库", "SQLite", "零配置、单文件、可离线复现；适合课程设计与单机演示"),
            ("投档引擎", "纯 Python 内存计算", "规则集中、易测试；同一引擎复用于案例对照"),
            ("前端", "原生 HTML/CSS/JavaScript", "无需 Node 构建链，降低部署复杂度；单页应用足够覆盖功能"),
            ("测试", "pytest + TestClient", "覆盖引擎单元测试与 API 集成测试；可在 CI 中重复执行"),
        ],
        widths=[2.6, 4.6, 8.6],
    )

    doc.add_heading("2.3 模块划分", level=2)
    add_table(
        doc,
        ["模块", "文件", "职责"],
        [
            ("投档引擎", "app/engine.py", "梯度、四批投档、名额隔离、结转、录取顺序、一致性校验"),
            ("数据校验", "app/validation.py", "输入数据 error/warning 校验"),
            ("数据库与运行编排", "app/db.py", "连接、表结构、数据版本、快照、运行创建与批次执行"),
            ("数据维护", "app/repository.py", "输入数据 CRUD、分页查询"),
            ("CSV 导入", "app/importer.py", "全有或全无导入、行级错误提示"),
            ("数据生成", "app/generator.py", "可重复生成的虚构数据、四类预设"),
            ("统计与导出", "app/stats.py", "结果查询、计划余额、统计、CSV 导出"),
            ("滑档案例", "app/cases.py", "基线与志愿调整后的内存对照"),
            ("Web 应用", "app/main.py", "REST API、静态前端、异常处理"),
        ],
        widths=[3.0, 4.4, 8.4],
    )

    doc.add_heading("2.4 数据流与版本控制", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "输入数据先经过校验；创建运行后写入 gzip JSON 快照、计算输入哈希并锁定当前数据版本；"
        "每个批次执行时加载数据、重建或恢复计划状态、运行引擎、写入录取/结果/日志/结转，并更新计划余额；"
        "批次完成后更新运行状态。运行结束后结果与快照保持不可变，修改输入必须创建新的数据版本。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)
    add_image(doc, "flow.png", "图 2-2 投档执行流程", width_cm=12.5)


def chapter_database(doc: Document) -> None:
    doc.add_heading("3 数据库设计", level=1)
    doc.add_heading("3.1 ER 图", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "数据库分为输入表与运行表两组。输入表保存当前数据版本；运行表以 run_id 隔离，保存计划状态、录取明细、"
        "考生结果、结转流水、事件日志、批次汇总和输入快照。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)
    add_image(doc, "er-diagram.png", "图 3-1 数据库 ER 图（简化）")

    doc.add_heading("3.2 主要表结构", level=2)
    add_table(
        doc,
        ["表", "作用", "关键字段/约束"],
        [
            ("high_schools", "高中", "code 唯一；category、intake_batch、has_autonomous、total_plan"),
            ("middle_schools", "初中", "code 唯一；district"),
            ("candidates", "考生", "candidate_no 唯一；UNIQUE(score, tie_seq)；score 0–750"),
            ("admission_plans", "招生计划", "批次、类别、名额、控制线、名额分配初中；唯一计划键"),
            ("autonomous_qualifications", "自主招生资格", "状态、考核排名；同一高中排名唯一"),
            ("volunteers", "志愿", "批次、序号、目标高中；防重复序号与重复高中"),
            ("sim_runs", "运行", "规则参数、状态、数据版本、输入哈希、快照"),
            ("run_plan_state", "计划状态", "初始、转入、转出、录取、余额"),
            ("run_admissions", "录取明细", "UNIQUE(run_id, candidate_id)；计划内顺序唯一"),
            ("run_candidate_results", "批次结果", "状态、原因、逐志愿明细"),
            ("run_candidate_summary", "考生汇总", "是否录取、批次、高中、最终原因"),
            ("run_transfers", "结转流水", "来源批次/计划、去向计划、人数"),
            ("run_events", "事件日志", "录取、跳过、结转、批次开始/结束"),
            ("run_snapshots", "输入快照", "路径、SHA-256、大小"),
        ],
        widths=[4.2, 3.4, 8.2],
        font_size=8.5,
    )

    doc.add_heading("3.3 关键约束与平衡等式", level=2)
    add_bullets(
        doc,
        [
            "每名考生每次运行最多录取一次：UNIQUE(run_id, candidate_id)，引擎同时跳过已录取考生。",
            "每条计划录取人数不超过可用名额：引擎在录取前检查 remaining > 0，运行后再由 verify_run 校验。",
            "录取必须对应有效志愿：校验批次、志愿序号、目标高中与计划一致。",
            "名额平衡：初始名额 + 转入 − 转出 = 已录取 + 剩余。",
            "汇总与明细一致：统计从录取明细和计划状态重新聚合，并与状态核对。",
            "第三、第四批余缺不互转：引擎不生成 3→4 或 4→3 的结转记录。",
        ],
    )

    doc.add_heading("3.4 数据版本与快照", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "dataset_meta 记录数据版本、锁定状态、输入哈希和推荐规则参数。创建运行后，系统写入 gzip JSON 快照，"
        "计算只包含输入数据的 input_hash，并锁定版本；快照文件的 SHA-256 单独保存用于完整性校验。"
        "input_hash 不包含 G₁/Δ/L 和追踪级别，因此同一数据可以用不同规则参数重复运行。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)


def chapter_algorithm(doc: Document) -> None:
    doc.add_heading("4 核心算法", level=1)
    doc.add_heading("4.1 梯度计算", level=2)
    p = doc.add_paragraph()
    run = p.add_run("梯度计算是投档顺序的基础，公式如下：")
    run.font.size = Pt(10.5)
    set_east_asian(run)
    add_code(
        doc,
        "if score < L: return None\n"
        "if score >= G1: return 1\n"
        "return 2 + (G1 - score - 1) // delta",
    )
    p = doc.add_paragraph()
    run = p.add_run(
        "分数恰好等于梯度线时归入较高梯度：例如 G₁=720、Δ=40、L=600 时，720→1，719→2，680→2，"
        "679→3，640→3，639→4，600→4，599 不参与录取。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)

    doc.add_heading("4.2 四批次投档", level=2)
    add_table(
        doc,
        ["批次", "处理范围", "排序依据", "志愿上限"],
        [
            ("第一批", "填报该校、资格合格、达到计划控制线", "考核排名升序", "1"),
            ("第二批", "本初中获得名额的考生", "梯度 → 志愿序号 → 总分/同分序号", "3"),
            ("第三批", "全市未录取、达到 L 的考生", "梯度 → 志愿序号 → 总分/同分序号", "6"),
            ("第四批", "全市未录取、达到 L 的考生", "梯度 → 志愿序号 → 总分/同分序号", "6"),
        ],
        widths=[2.2, 6.0, 6.0, 1.6],
    )
    add_code(
        doc,
        "for batch in (1, 2, 3, 4):\n"
        "    for band in 1..max_band:                 # 高梯度优先\n"
        "        if all plans of this batch are full: break\n"
        "        for seq in 1..volunteer_limit:       # 同梯度内志愿轮次\n"
        "            groups = group_by_plan(candidates in band with volunteer seq)\n"
        "            for plan in groups:\n"
        "                sort by (-score, tie_seq, candidate_no)\n"
        "                admit top (plan.remaining)",
    )

    doc.add_heading("4.3 名额分配与结转", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "第二批按初中独立处理：每个（高中, 初中）有独立计划，考生只能竞争本人初中的名额。"
        "第二批结束后，先按高中汇总各初中剩余名额，再转入本校第三批统招计划。第一批剩余名额同样转入第三批。"
        "结转只发生一次；每次运行从初始状态重建计划状态，因此重复运行不会叠加。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)
    add_code(
        doc,
        "for plan in batch1_plans:\n"
        "    amount = plan.initial + plan.in - plan.out - plan.admitted\n"
        "    target = batch3_plan[plan.high_school]\n"
        "    plan.out += amount\n"
        "    target.in += amount\n"
        "    log_transfer(1, plan, target, amount)\n"
        "\n"
        "for high in highs_with_batch2:\n"
        "    total = sum(plan.remaining for plan in high.batch2_plans)\n"
        "    target = batch3_plan[high]\n"
        "    for plan in high.batch2_plans:\n"
        "        plan.out += plan.remaining\n"
        "        log_transfer(2, plan, target, plan.remaining)\n"
        "    target.in += total",
    )

    doc.add_heading("4.4 为什么不能按总分逐人扫描全部志愿", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "如果先按总分从高到低逐人扫描全部志愿，会得到“分数绝对优先”的结果，破坏任务书要求的梯度优先和"
        "同梯度志愿优先。例如，同梯度内 690 分第一志愿考生应先于 710 分第二志愿考生录取；高梯度 730 分"
        "第二志愿考生应先于低梯度 700 分第一志愿考生录取。本系统按“批次 → 梯度 → 志愿轮次 → 计划内排序”"
        "执行，先确定轮次，再在同一轮次内按分数排序，符合规则。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)

    doc.add_heading("4.5 复杂度与边界", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "设考生数 N、志愿数 V、计划数 P、梯度数 B、志愿轮次上限 S。梯度计算 O(N)；统招批次最坏 "
        "O(B·S·N log N)，实际因计划满额提前停止；名额分配按初中分组后同量级；空间 O(N+V+P)。"
        "2 万考生演示数据完整四批投档约 3 秒。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)
    add_table(
        doc,
        ["边界情况", "处理"],
        [
            ("分数等于梯度线", "归入较高梯度"),
            ("分数低于 L", "不参与录取，记录原因"),
            ("计划余额为 0", "本轮次全部标记 OUTRANKED/PLAN_FULL"),
            ("本批计划全部满额", "后续梯度不再扫描，标记 BATCH_FULL"),
            ("无人填报", "保留余额，不强行录取"),
            ("前批已录取", "退出后续批次，标记 SKIPPED/ALREADY_ADMITTED"),
            ("第二批无对应名额", "标记 NO_ALLOCATION，不影响其他志愿"),
            ("重复运行", "新运行从初始状态重建，不叠加"),
        ],
        widths=[5.0, 10.8],
    )


def chapter_implementation(doc: Document) -> None:
    doc.add_heading("5 系统实现", level=1)
    doc.add_heading("5.1 后端 API", level=2)
    add_table(
        doc,
        ["分组", "主要接口", "说明"],
        [
            ("基础", "GET /api/meta、GET /api/health", "数据版本、计数、推荐参数、梯度"),
            ("数据", "GET/POST/PUT/DELETE /api/high-schools 等", "高中、初中、考生、计划、资格、志愿 CRUD"),
            ("导入", "POST /api/import/{entity}", "CSV 全有或全无导入"),
            ("校验", "GET /api/validate", "error/warning 校验"),
            ("运行", "POST /api/runs、/execute-next、/execute-all", "创建运行、按批/完整执行"),
            ("进度", "GET /api/runs/{id}/progress、/plans、/transfers、/events", "计划余额、结转、日志"),
            ("结果", "GET /api/runs/{id}/candidate/{cid}、/admissions", "考生解释、录取名单"),
            ("统计", "GET /api/runs/{id}/stats、/export/{kind}", "统计与 CSV 导出"),
            ("案例", "GET /api/cases/slip、POST /api/cases/slip/run", "滑档案例对照"),
        ],
        widths=[2.2, 7.0, 6.6],
        font_size=8.5,
    )

    doc.add_heading("5.2 前端界面", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "前端为原生单页应用，包含概览、数据管理、投档执行、结果查询、统计分析、滑档案例和帮助七个页面。"
        "表格支持分页、搜索和筛选；运行页展示批次步骤条、计划余额、结转流水和事件日志；"
        "结果页展示考生四批次时间线与逐志愿原因；统计页展示梯度分布、分数分布、高中/计划统计和导出。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)
    add_image(doc, "01-overview.png", "图 5-1 系统总览")
    add_image(doc, "02-run-detail.png", "图 5-2 投档运行详情")
    add_image(doc, "04-candidate-result.png", "图 5-3 考生结果与逐志愿原因")
    add_image(doc, "03-stats.png", "图 5-4 统计分析")
    add_image(doc, "05-slip-case.png", "图 5-5 滑档案例志愿调整对照")
    add_image(doc, "06-data-plans.png", "图 5-6 数据管理")

    doc.add_heading("5.3 数据生成与导入", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "系统提供 small、medium、demo、full 四类预设，分别对应 17 人、3 千人、2 万人、15 万人；"
        "所有随机过程使用固定种子，生成结果可重复。CSV 导入采用全有或全无策略，任一行失败则整体回滚，"
        "并返回行号与原因。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)

    doc.add_heading("5.4 快照、锁定与导出", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "每次运行写入 gzip JSON 快照，保存 input_hash 和 snapshot_sha256；运行创建后锁定数据版本，"
        "所有写操作返回 409，必须创建新数据版本才能修改。结果支持录取名单、计划统计、高中统计、初中统计、"
        "考生结果、分数分布、未录取原因等 CSV 导出。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)


def chapter_testing(doc: Document) -> None:
    doc.add_heading("6 测试与验证", level=1)
    doc.add_heading("6.1 测试策略", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "测试遵循“先人工预期、后系统实现”的原则：先设计小数据集并逐轮推演，把预期写入 expected JSON 和测试材料；"
        "再实现引擎并用自动化测试对照。测试分为引擎单元测试、API 集成测试、异常输入测试和浏览器端到端验证。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)

    doc.add_heading("6.2 小数据集与人工预期", level=2)
    add_table(
        doc,
        ["项目", "设置"],
        [
            ("参数", "G₁=720，Δ=40，L=600"),
            ("初中 / 高中", "2 所初中；4 所高中（G01/G02/G03 第三批，G04 第四批）"),
            ("考生", "17 人，覆盖 720/719/680/679/640/639/600/599 边界分数和同分序号"),
            ("计划", "10 条，1–4 人；G01 总计划 5，G02 总计划 8，G03 1，G04 4"),
            ("资格", "G01 4 人、G02 4 人（含 1 人不合格）"),
            ("志愿", "41 条，覆盖四个批次、志愿轮次和未填志愿情形"),
        ],
        widths=[4.0, 11.8],
    )
    add_table(
        doc,
        ["批次", "人工预期录取人数", "录取考生"],
        [
            ("第一批", "3", "C01→G01、C02→G02、C09→G02"),
            ("第二批", "5", "C04→G01、C06→G01、C05→G02、C16→G01、C10→G02"),
            ("第三批", "6", "C17→G03、C03→G01、C11→G02、C08→G02、C07→G02、C12→G02"),
            ("第四批", "2", "C13→G04、C14→G04"),
            ("未录取", "1", "C15（599 < 600）"),
        ],
        widths=[2.2, 3.4, 10.2],
    )
    add_table(
        doc,
        ["计划", "初始", "转入", "转出", "录取", "余额"],
        [
            ("第一批 G01", "1", "0", "0", "1", "0"),
            ("第一批 G02", "3", "0", "1", "2", "0"),
            ("第二批 G01-M01", "2", "0", "0", "2", "0"),
            ("第二批 G01-M02", "1", "0", "0", "1", "0"),
            ("第二批 G02-M01", "2", "0", "1", "1", "0"),
            ("第二批 G02-M02", "1", "0", "0", "1", "0"),
            ("第三批 G01", "1", "0", "0", "1", "0"),
            ("第三批 G02", "2", "2", "0", "4", "0"),
            ("第三批 G03", "1", "0", "0", "1", "0"),
            ("第四批 G04", "4", "0", "0", "2", "2"),
        ],
        widths=[4.6, 2.2, 2.2, 2.2, 2.2, 2.2],
    )
    p = doc.add_paragraph()
    run = p.add_run(
        "全局核对：初始 18 + 转入 2 − 转出 2 = 18；已录取 16 + 余额 2 = 18。"
        "G02 第三批最低录取分 640（C08），末位考生 C12（660，第 2 志愿，同分序号 1），"
        "说明最低分与末位考生必须分别计算。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)

    doc.add_heading("6.3 必测场景矩阵", level=2)
    add_table(
        doc,
        ["场景", "预期", "测试"],
        [
            ("梯度优先", "高梯度后志愿先于低梯度前志愿", "test_gradient_priority"),
            ("同梯度志愿优先", "低分第一志愿先于高分第二志愿", "test_same_gradient_volunteer_priority"),
            ("分数与同分顺序", "同梯度同志愿先比总分，再比同分序号", "test_same_score_uses_tie_sequence"),
            ("边界分数", "720/719/680/640/600 进入对应梯度，599 不参与", "test_boundary_scores"),
            ("自主招生", "无资格、未达线不能录取；按排名竞争", "test_autonomous_qualification"),
            ("跨批次排除", "前批录取者不占后续计划", "test_cross_batch_exclusion"),
            ("名额隔离", "只能用所属初中名额", "test_quota_allocation_isolation"),
            ("名额结转", "余额进入第三批，重复执行不叠加", "test_quota_transfer_happens_once"),
            ("不足额与空结果", "不强行录满", "test_underfill_and_empty_plan"),
            ("统计口径", "最低分与末位考生不同", "test_stepwise_run_progress_verify_stats"),
            ("异常输入", "重复考生/非法分数/重复志愿等拒绝", "test_validation.py"),
            ("可重复运行", "同一快照结果一致，独立存储", "test_run_repeatable_and_independent"),
        ],
        widths=[3.6, 8.0, 5.2],
        font_size=8.5,
    )

    doc.add_heading("6.4 高分滑档案例", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        "案例一：C1 700 分第三批第一志愿 H2、第二志愿 H1；同梯度 C2 690 分第一志愿 H1，先占满 H1；"
        "C1 第一志愿 H2 被 715 分 C3 占满，第三批落选，第四批被 H3 录取。只把 C1 第三批志愿改为 H1 在前，"
        "C1 第三批被 H1 录取；C2 被挤出，C5 因 C1 不再占用第四批名额而录取。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)
    p = doc.add_paragraph()
    run = p.add_run(
        "案例二：C1 710 分只填 H2、H1 两所热门高中且不填第四批，两个志愿均被占满，全部批次结束仍未录取；"
        "只给 C1 增加第四批 H3 志愿，C1 即被 H3 录取。两个案例均保持成绩、计划和其他考生志愿不变，"
        "仅调整高分考生志愿，并展示对其他考生的挤出效应。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)

    doc.add_heading("6.5 大规模与性能", level=2)
    add_table(
        doc,
        ["预设", "初中", "高中", "考生", "用途"],
        [
            ("small", "2", "4", "17", "人工推演"),
            ("medium", "100", "30", "3,000", "开发调试"),
            ("demo", "300", "60", "20,000", "课堂演示"),
            ("full", "500", "150", "150,000", "加分规模"),
        ],
        widths=[2.4, 2.4, 2.4, 3.2, 5.0],
    )
    p = doc.add_paragraph()
    run = p.add_run(
        "本机实测 2 万考生（60 高中、300 初中、约 11.8 万志愿）生成约 2.4 秒，完整四批投档约 3 秒，"
        "统计查询约 0.6 秒；所有计划满足名额平衡等式。15 万考生建议使用摘要追踪模式。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)

    doc.add_heading("6.6 测试结果", level=2)
    p = doc.add_paragraph()
    run = p.add_run("执行命令：")
    run.font.size = Pt(10.5)
    set_east_asian(run)
    add_code(doc, "python -m pytest -q\n# 45 passed in 1.56s")
    add_bullets(
        doc,
        [
            "45 项自动化测试全部通过；",
            "小数据集实际录取 16 人、未录取 1 人，与人工预期一致；",
            "第一批、第二批各结转 1 人，第三批 G02 有效计划 4 人；",
            "G02 第三批最低分 640、末位考生 C12/660/第 2 志愿；",
            "一致性校验 verify_run 无错误；",
            "重复运行两次结果一致，运行结果独立存储。",
        ],
    )


def chapter_deployment(doc: Document) -> None:
    doc.add_heading("7 部署与使用", level=1)
    doc.add_heading("7.1 环境与启动", level=2)
    add_code(
        doc,
        "cd zhongkao-admission\n"
        "python -m pip install -r requirements.txt\n"
        "python run.py\n"
        "# 浏览器打开 http://127.0.0.1:8000",
    )
    p = doc.add_paragraph()
    run = p.add_run(
        "系统无需 Node、无需外部数据库；首次启动自动创建 data/admission.db 和 data/snapshots/。"
        "API 文档位于 /docs。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)

    doc.add_heading("7.2 演示流程", level=2)
    add_bullets(
        doc,
        [
            "生成“人工小数据集”，参数 G₁=720、Δ=40、L=600，追踪级别选“完整”；",
            "新建运行并“完整运行”，四批录取人数应为 3/5/6/2；",
            "在结果查询输入 C07，查看第二批校内竞争落选、第三批第二志愿录取；",
            "输入 C15，查看低于全市控制线的未录取原因；",
            "在统计分析查看最低分与末位考生差异、计划完成率 16/18；",
            "在滑档案例运行“案例一”，查看 C1 从第四批变为第三批录取及挤出效应。",
        ],
    )

    doc.add_heading("7.3 已知限制", level=2)
    add_bullets(
        doc,
        [
            "教学模拟，不完整复现现实政策；",
            "不模拟退档、放弃录取、报到注册和正式补录；",
            "单机单用户，无登录、权限和并发控制；",
            "15 万人完整追踪会显著增加数据库体积，建议使用摘要模式；",
            "历史运行与当前数据通过快照关联，跨版本查询需先选择对应运行。",
        ],
    )


def chapter_team(doc: Document) -> None:
    doc.add_heading("8 团队分工与阶段计划", level=1)
    p = doc.add_paragraph()
    run = p.add_run(
        "最新版任务书允许每组 1–8 人，本组为 3 人。下表姓名、学号请替换为真实信息；"
        "贡献占比为建议值，须根据实际投入调整，合计 100%。Git 提交作者应与分工表一致，"
        "不得伪造协作记录。"
    )
    run.font.size = Pt(10.5)
    run.font.color.rgb = RGBColor(0x8A, 0x1C, 0x1C)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)
    add_table(
        doc,
        ["成员", "角色", "负责模块", "建议占比"],
        [
            ("组长（待填写）", "项目经理 / 核心算法 / 系统集成",
             "需求与规则、投档引擎、运行编排、快照与版本、Git 与最终集成", "40%"),
            ("成员B（待填写）", "数据建模 / 数据管理 / 测试",
             "ER 图与表结构、CRUD 与导入、数据校验、数据生成、pytest 测试", "30%"),
            ("成员C（待填写）", "前端 / 统计与结果 / 文档部署",
             "Web 界面、结果查询、统计导出、滑档案例页面、部署与演示材料", "30%"),
        ],
        widths=[3.6, 4.0, 8.0, 1.8],
        font_size=8.8,
    )
    add_table(
        doc,
        ["阶段", "主要工作", "负责人", "交付物"],
        [
            ("需求与计划", "研读任务书、范围、用例、规则、分工", "组长", "需求与规则清单、阶段计划"),
            ("建模与预测试", "ER 图、表结构、伪代码、小数据集与人工推演", "成员B / 组长", "数据库设计、人工预期"),
            ("核心实现", "梯度、四批投档、名额隔离、结转、校验", "组长", "引擎与单元测试"),
            ("系统集成", "API、数据库、生成、导入、快照、导出", "组长 / 成员B", "可运行后端"),
            ("前端与联调", "数据管理、运行、结果、统计、案例", "成员C", "可演示 Web 系统"),
            ("测试与修复", "必测场景、边界/异常、重复运行、性能", "成员B / 组长", "测试材料、缺陷修复"),
            ("文档与交付", "设计报告、部署说明、演示脚本、Git 整理", "成员C / 组长", "最终提交包"),
        ],
        widths=[3.0, 6.4, 2.4, 4.2],
    )


def chapter_summary(doc: Document) -> None:
    doc.add_heading("9 总结与改进", level=1)
    p = doc.add_paragraph()
    run = p.add_run(
        "本系统完成了任务书要求的核心流程：四批次投档、梯度优先、志愿轮次、同分排序、自主招生、名额分配隔离、"
        "计划结转、结果解释、统计与导出，并通过小数据集人工推演和 45 项自动化测试验证。"
        "实现过程中的主要难点是：保证“同梯度志愿优先”与“不同梯度梯度优先”的轮次顺序；"
        "第二批按初中隔离名额并按高中汇总结转；在按批执行时正确恢复计划状态；以及保证历史运行与输入版本的可复现性。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)
    p = doc.add_paragraph()
    run = p.add_run(
        "后续可改进方向：增加多用户与权限；支持多年度、多版本数据并行；增加更丰富的统计图表；"
        "将引擎进一步抽象为规则配置；增加压力测试与数据库索引优化；补充更多现实业务场景的对照分析。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)


def appendices(doc: Document) -> None:
    doc.add_page_break()
    doc.add_heading("附录 A 规则参数与梯度", level=1)
    add_table(
        doc,
        ["梯度", "分数区间", "说明"],
        [
            ("第 1 梯度", "≥G₁", "分数等于 G₁ 归入第 1 梯度"),
            ("第 2 梯度", "G₁−Δ ≤ 总分 < G₁", "分数等于 G₁−Δ 归入第 2 梯度"),
            ("第 3 梯度", "G₁−2Δ ≤ 总分 < G₁−Δ", "依次类推"),
            ("……", "……", "最后一档截至 L"),
            ("不参与", "<L", "低于全市最低控制线"),
        ],
        widths=[3.2, 6.4, 6.2],
    )
    p = doc.add_paragraph()
    run = p.add_run(
        "小数据集：G₁=720，Δ=40，L=600，梯度为 ≥720、680–719、640–679、600–639。"
        "演示数据：G₁=712，Δ=40，L=492，梯度为 ≥712、672–711、632–671、592–631、552–591、512–551、492–511。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)

    doc.add_heading("附录 B 主要 API 清单", level=1)
    add_table(
        doc,
        ["方法", "路径", "说明"],
        [
            ("GET", "/api/meta", "数据版本、计数、推荐参数、梯度"),
            ("POST", "/api/dataset/generate", "生成演示数据"),
            ("POST", "/api/dataset/unlock", "创建新数据版本"),
            ("GET", "/api/validate", "数据校验"),
            ("GET/POST/PUT/DELETE", "/api/high-schools 等", "输入数据 CRUD"),
            ("POST", "/api/import/{entity}", "CSV 导入"),
            ("POST", "/api/runs", "创建运行"),
            ("POST", "/api/runs/{id}/execute-next", "执行下一批"),
            ("POST", "/api/runs/{id}/execute-all", "完整运行"),
            ("GET", "/api/runs/{id}/progress", "批次进度与计划余额"),
            ("GET", "/api/runs/{id}/candidate/{cid}", "考生结果与原因"),
            ("GET", "/api/runs/{id}/stats", "统计"),
            ("GET", "/api/runs/{id}/export/{kind}", "CSV 导出"),
            ("GET", "/api/cases/slip", "滑档案例列表"),
            ("POST", "/api/cases/slip/run", "运行滑档案例对照"),
        ],
        widths=[4.2, 7.0, 4.6],
        font_size=8.5,
    )

    doc.add_heading("附录 C AI 使用说明", level=1)
    p = doc.add_paragraph()
    run = p.add_run(
        "本项目在需求梳理、代码草稿、测试用例和文档排版中使用 AI 辅助；人工完成小数据集与逐轮推演、"
        "滑档案例设计、测试结果核对和浏览器端到端验证。所有规则实现以任务书为准，测试预期未使用系统输出反向填充。"
        "详细说明见 docs/AI使用说明.md。"
    )
    run.font.size = Pt(10.5)
    set_east_asian(run)
    p.paragraph_format.first_line_indent = Cm(0.74)


def main() -> None:
    doc = Document()
    section = doc.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(2.3)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.3)
    style_document(doc)
    add_page_number(section)

    cover(doc)
    toc(doc)
    abstract(doc)
    chapter_requirements(doc)
    chapter_design(doc)
    chapter_database(doc)
    chapter_algorithm(doc)
    chapter_implementation(doc)
    chapter_testing(doc)
    chapter_deployment(doc)
    chapter_team(doc)
    chapter_summary(doc)
    appendices(doc)

    doc.save(OUT)
    print("已生成：", OUT)


if __name__ == "__main__":
    main()
