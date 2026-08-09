from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "竞赛论文模板.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)


def register_fonts():
    candidates = [
        ("Song", Path(r"C:\Windows\Fonts\simsun.ttc")),
        ("Hei", Path(r"C:\Windows\Fonts\simhei.ttf")),
    ]
    for name, path in candidates:
        if path.exists():
            pdfmetrics.registerFont(TTFont(name, str(path)))
    if "Song" not in pdfmetrics.getRegisteredFontNames():
        raise RuntimeError("未找到宋体字体文件")
    if "Hei" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Hei", r"C:\Windows\Fonts\msyh.ttc"))


register_fonts()

PAGE_W, PAGE_H = A4
LEFT = RIGHT = 2.55 * cm
TOP = 2.25 * cm
BOTTOM = 2.05 * cm


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#777777"))
    canvas.setLineWidth(0.45)
    canvas.line(LEFT, PAGE_H - 1.55 * cm, PAGE_W - RIGHT, PAGE_H - 1.55 * cm)
    canvas.setFont("Song", 8)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawCentredString(PAGE_W / 2, 1.15 * cm, str(doc.page))
    canvas.restoreState()


doc = BaseDocTemplate(
    str(OUT),
    pagesize=A4,
    leftMargin=LEFT,
    rightMargin=RIGHT,
    topMargin=TOP,
    bottomMargin=BOTTOM,
    title="数学建模竞赛论文模板",
    author="Codex",
)
frame = Frame(LEFT, BOTTOM, PAGE_W - LEFT - RIGHT, PAGE_H - TOP - BOTTOM, id="body")
doc.addPageTemplates([PageTemplate(id="normal", frames=frame, onPage=footer)])

styles = getSampleStyleSheet()
body = ParagraphStyle(
    "BodyCN", parent=styles["BodyText"], fontName="Song", fontSize=10.5,
    leading=18, alignment=TA_JUSTIFY, firstLineIndent=21, spaceAfter=6,
)
body_noindent = ParagraphStyle(
    "BodyNoIndent", parent=body, firstLineIndent=0,
)
title = ParagraphStyle(
    "TitleCN", parent=styles["Title"], fontName="Hei", fontSize=18,
    leading=26, alignment=TA_CENTER, spaceAfter=18,
)
h1 = ParagraphStyle(
    "H1CN", parent=styles["Heading1"], fontName="Hei", fontSize=14,
    leading=22, alignment=TA_CENTER, spaceBefore=8, spaceAfter=12,
)
h2 = ParagraphStyle(
    "H2CN", parent=styles["Heading2"], fontName="Hei", fontSize=12,
    leading=19, alignment=TA_LEFT, spaceBefore=10, spaceAfter=6,
)
h3 = ParagraphStyle(
    "H3CN", parent=styles["Heading3"], fontName="Hei", fontSize=10.5,
    leading=17, alignment=TA_LEFT, spaceBefore=7, spaceAfter=4,
)
note = ParagraphStyle(
    "NoteCN", parent=body_noindent, fontSize=9, leading=15,
    textColor=colors.HexColor("#555555"), backColor=colors.HexColor("#F3F6F8"),
    borderColor=colors.HexColor("#9AA7B0"), borderWidth=0.5, borderPadding=7,
    spaceBefore=6, spaceAfter=9,
)
caption = ParagraphStyle(
    "CaptionCN", parent=body_noindent, fontSize=9, leading=14, alignment=TA_CENTER,
    spaceBefore=5, spaceAfter=8,
)
code = ParagraphStyle(
    "CodeCN", parent=body_noindent, fontName="Courier", fontSize=7.5,
    leading=11, leftIndent=8, rightIndent=8, backColor=colors.HexColor("#F6F6F6"),
    borderColor=colors.HexColor("#AAAAAA"), borderWidth=0.5, borderPadding=7,
)


def P(text, style=body):
    return Paragraph(text, style)


def heading(text, level=1):
    return Paragraph(text, {1: h1, 2: h2, 3: h3}[level])


def placeholder(text):
    return Paragraph("填写提示：" + text, note)


def standard_table(data, widths=None):
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="CENTER")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Hei"),
        ("FONTNAME", (0, 1), (-1, -1), "Song"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEADING", (0, 0), (-1, -1), 14),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF1")),
        ("LINEABOVE", (0, 0), (-1, 0), 1.1, colors.HexColor("#333333")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#333333")),
        ("LINEBELOW", (0, -1), (-1, -1), 1.1, colors.HexColor("#333333")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


story = []

# Page 1: title, abstract and keywords
story += [Spacer(1, 0.25 * cm), Paragraph("基于【核心方法】的【研究对象】优化与决策", title)]
story += [heading("摘　要", 1)]
story += [placeholder("摘要建议控制在600-900字，按照“背景与目标-方法-分问题结果-结论”组织；必须给出关键数值，避免只写过程。")]
for label, text in [
    ("研究背景与目标", "针对【实际场景】中的【核心矛盾】，本文基于【数据来源与规模】，建立【总体模型框架】，解决【若干任务】。"),
    ("问题一", "提取【指标】，采用【评价/预测方法】得到【核心结果及数值】，并通过【检验方法】验证稳健性。"),
    ("问题二", "建立【优化模型】，在【主要约束】下，以【目标函数】为目标，得到【方案及关键指标】。"),
    ("问题三", "在前述模型基础上加入【新偏好或新约束】，比较优化前后【成本、效率、风险】的变化。"),
    ("问题四", "构建【扩展或情景模型】，给出【建议方案】及【敏感性/可行性结论】。"),
]:
    story.append(P(f"<b>{label}：</b>{text}"))
story += [Spacer(1, 0.2 * cm), P("<b>关键词：</b>【关键词1】；【关键词2】；【关键词3】；【关键词4】；【关键词5】", body_noindent)]
story += [PageBreak()]

# Page 2
story += [heading("一、问题重述", 1), heading("1.1 问题背景", 2)]
story += [placeholder("用自己的语言说明行业背景、研究对象、现存困难和建模价值，不要大段照抄赛题。")]
story += [P("【描述研究场景、相关主体、数据条件和现实约束。说明为什么该问题值得研究，以及定量模型能够支持哪些决策。】")]
story += [heading("1.2 问题要求", 2)]
story += [P("（1）问题一：【用一句话概括输入、任务和输出。】", body_noindent),
          P("（2）问题二：【明确需要建立的模型及评价指标。】", body_noindent),
          P("（3）问题三：【说明新增偏好、约束或情景。】", body_noindent),
          P("（4）问题四：【说明扩展预测、优化或决策要求。】", body_noindent)]
story += [heading("二、问题分析", 1), placeholder("先写总体逻辑，再分问题说明模型选择依据；突出问题之间的数据流和递进关系。")]
story += [heading("2.1 总体分析", 2), P("本文形成“数据预处理-特征构建-模型求解-方案评价-敏感性分析”的技术路线。各问题共享统一的数据口径和符号体系，后续问题复用前一问题的核心结果。")]
flow = standard_table([
    ["原始数据", "数据清洗", "特征/参数", "评价或预测", "优化决策", "检验与建议"],
    ["附件及公开数据", "缺失值/异常值", "指标与约束", "模型一", "模型二", "稳健性分析"],
], [2.25*cm]*6)
story += [flow, Paragraph("图1　总体建模流程示意", caption), PageBreak()]

# Page 3
story += [heading("三、模型假设", 1), placeholder("每条假设都应服务于后文模型，并说明其合理性或适用边界。")]
for i, t in enumerate([
    "赛题所给数据真实可靠，观测口径在研究期内保持一致。",
    "未被模型显式考虑的外部环境因素在短期内保持稳定。",
    "同一类对象具有可比性，必要的量纲差异已通过标准化消除。",
    "优化周期内资源容量、成本参数和业务规则按题设执行。",
    "随机扰动相互独立，或其相关性已通过情景/鲁棒处理体现。",
], 1):
    story.append(P(f"{i}. {t}", body_noindent))
story += [heading("四、符号说明", 1)]
symbols = [["符号", "含义", "单位"], ["i,j,t", "对象、方案与时间下标", "-"], ["x_it", "第t期对对象i的决策量", "按题意"], ["c_i", "对象i的单位成本", "元/单位"], ["r_i", "对象i的风险或损耗率", "%"], ["F(x)", "模型目标函数", "-"], ["Ω", "可行域或约束集合", "-"]]
story += [standard_table(symbols, [2.6*cm, 9.1*cm, 2.3*cm]), Paragraph("表1　主要符号说明", caption)]
story += [placeholder("正文首次出现的符号仍需解释；符号表只保留高频核心符号。"), PageBreak()]

# Page 4
story += [heading("五、数据预处理与描述性分析", 1), heading("5.1 数据来源与字段说明", 2)]
story += [P("说明附件、公开数据或调研数据的来源、样本量、时间跨度、字段含义和数据权限。")]
data_table = [["数据表", "样本量", "时间跨度", "主要字段", "用途"], ["数据集A", "【N】", "【起止时间】", "【字段】", "问题一"], ["数据集B", "【N】", "【起止时间】", "【字段】", "问题二至四"]]
story += [standard_table(data_table, [2.4*cm, 2*cm, 2.8*cm, 4.1*cm, 2.7*cm]), Paragraph("表2　数据来源与用途", caption)]
story += [heading("5.2 数据清洗", 2), P("依次处理缺失值、重复值、异常值和单位不一致问题。所有删改规则应给出阈值或统计依据，并保留处理前后样本量对比。")]
story += [heading("5.3 描述性统计", 2), placeholder("至少展示能支持建模选择的分布、趋势、相关性或分组差异，不要堆砌无关图表。")]
stats = [["指标", "均值", "标准差", "最小值", "中位数", "最大值"], ["指标1", "【 】", "【 】", "【 】", "【 】", "【 】"], ["指标2", "【 】", "【 】", "【 】", "【 】", "【 】"]]
story += [standard_table(stats, [2.8*cm]+[2.25*cm]*5), Paragraph("表3　描述性统计结果", caption), PageBreak()]

# Page 5
story += [heading("六、问题一模型的建立与求解", 1), heading("6.1 指标体系或变量构建", 2)]
story += [P("根据问题目标，从【规模、效率、稳定性、风险等】维度构建指标。说明每个指标的业务意义、正负向属性及计算公式。")]
indicators = [["一级维度", "指标", "属性", "计算方式"], ["维度A", "指标A1", "正向", "【公式/定义】"], ["维度B", "指标B1", "负向", "【公式/定义】"], ["维度C", "指标C1", "正向", "【公式/定义】"]]
story += [standard_table(indicators, [3*cm, 3.1*cm, 2.2*cm, 5.7*cm]), Paragraph("表4　指标体系", caption)]
story += [heading("6.2 模型建立", 2), P("给出标准化、权重计算和综合评分公式。公式后逐项解释符号、参数与取值范围。")]
story += [P("目标函数示例：　min F(x) = Σ c_i x_i + λR(x)", body_noindent), P("约束集合示例：　x ∈ Ω，且满足容量、需求、逻辑和非负约束。", body_noindent)]
story += [heading("6.3 求解步骤", 2), P("步骤1：数据标准化；步骤2：估计参数；步骤3：计算模型结果；步骤4：排序或筛选；步骤5：稳健性检验。")]
story += [heading("6.4 结果分析", 2), placeholder("结果部分必须写清数值、排序、业务含义和异常对象；不要只说“效果较好”。"), PageBreak()]

# Page 6
story += [heading("七、问题二模型的建立与求解", 1), heading("7.1 决策变量与目标函数", 2)]
story += [P("定义决策变量x_it，并说明其与实际方案的对应关系。目标函数可包含成本、风险、损耗、服务水平等，并说明多目标转化方法。")]
story += [heading("7.2 约束条件", 2)]
constraints = [["约束类型", "数学表达", "实际含义"], ["需求约束", "【表达式】", "满足每期最低需求"], ["容量约束", "【表达式】", "不超过资源上限"], ["库存/平衡约束", "【表达式】", "相邻时期状态递推"], ["取值约束", "【表达式】", "非负、整数或0-1条件"]]
story += [standard_table(constraints, [3.1*cm, 5.3*cm, 5.6*cm]), Paragraph("表5　模型约束", caption)]
story += [heading("7.3 求解算法", 2), P("说明采用线性规划、整数规划、启发式算法或仿真方法的原因，给出编码方式、参数设置、停止条件和计算平台。")]
params = [["参数", "取值", "设置依据"], ["种群/样本规模", "【 】", "规模与精度折中"], ["迭代次数", "【 】", "收敛曲线"], ["随机种子", "【 】", "保证可复现"]]
story += [standard_table(params, [4*cm, 3*cm, 7*cm]), Paragraph("表6　算法参数设置", caption), PageBreak()]

# Page 7
story += [heading("八、问题三与问题四的扩展模型", 1), heading("8.1 问题三：新增偏好或约束", 2)]
story += [P("在问题二基准模型上加入【材料偏好、风险偏好、公平性、碳排放或服务水平】等因素。明确哪些变量、目标或约束发生改变。")]
story += [heading("8.2 方案前后对比", 2)]
compare = [["指标", "基准方案", "改进方案", "变化率", "结论"], ["总成本", "【 】", "【 】", "【 】", "【 】"], ["风险/损耗", "【 】", "【 】", "【 】", "【 】"], ["资源利用率", "【 】", "【 】", "【 】", "【 】"]]
story += [standard_table(compare, [3*cm, 2.6*cm, 2.6*cm, 2.5*cm, 3.3*cm]), Paragraph("表7　方案对比", caption)]
story += [heading("8.3 问题四：情景预测或能力提升", 2), P("使用历史分布、预测模型或情景参数估计未来边界，设置保守、基准和乐观情景，分别给出可执行方案。")]
scenes = [["情景", "关键参数", "目标值", "方案表现"], ["保守", "【 】", "【 】", "【 】"], ["基准", "【 】", "【 】", "【 】"], ["乐观", "【 】", "【 】", "【 】"]]
story += [standard_table(scenes, [3*cm, 3.7*cm, 3.2*cm, 4.1*cm]), Paragraph("表8　情景分析", caption), PageBreak()]

# Page 8
story += [heading("九、模型检验与敏感性分析", 1), heading("9.1 正确性与可行性检验", 2)]
story += [P("检查约束是否全部满足、单位是否一致、结果是否处于合理范围，并用基准方法或历史样本进行对照。")]
checks = [["检验项目", "检验方法", "结果", "是否通过"], ["约束可行性", "逐项回代", "【 】", "是/否"], ["历史拟合", "误差指标", "【 】", "是/否"], ["重复运行稳定性", "均值与变异系数", "【 】", "是/否"]]
story += [standard_table(checks, [3.4*cm, 4.2*cm, 3.5*cm, 2.9*cm]), Paragraph("表9　模型检验结果", caption)]
story += [heading("9.2 敏感性分析", 2), P("选择对结论有实质影响的参数，在合理区间内变化，观察目标函数、关键决策量和可行性的变化。")]
sens = [["参数变化", "-20%", "-10%", "基准", "+10%", "+20%"], ["目标函数", "【 】", "【 】", "【 】", "【 】", "【 】"], ["关键指标", "【 】", "【 】", "【 】", "【 】", "【 】"]]
story += [standard_table(sens, [2.8*cm]+[2.25*cm]*5), Paragraph("表10　敏感性分析结果", caption)]
story += [placeholder("用曲线图或表格解释参数变化是否改变核心结论，并指出模型稳定区间。"), PageBreak()]

# Page 9
story += [heading("十、模型评价与推广", 1), heading("10.1 模型优点", 2)]
for t in ["指标或变量具有明确业务含义，模型结构可解释。", "同时考虑多期、多主体或多约束，方案具有可执行性。", "通过重复实验、敏感性分析或外部样本验证了稳健性。"]:
    story.append(P("• " + t, body_noindent))
story += [heading("10.2 模型不足", 2)]
for t in ["部分参数依赖历史数据，结构变化时需要重新估计。", "随机性、相关性或极端事件的描述仍可进一步完善。", "启发式算法不能从理论上保证全局最优。"]:
    story.append(P("• " + t, body_noindent))
story += [heading("10.3 改进与推广", 2), P("可引入鲁棒优化、随机规划、贝叶斯更新、组合赋权或多目标优化，并推广至【相似行业或地区】。")]
story += [heading("十一、结论与建议", 1), placeholder("用3-5条可落地结论收束全文，每条同时包含结论、数值和行动建议。")]
for i in range(1, 5):
    story.append(P(f"{i}. 【核心结论】；关键数值为【 】；建议【具体行动】。", body_noindent))
story += [PageBreak()]

# Page 10
story += [heading("参考文献", 1), placeholder("优先引用教材、经典论文、官方报告和权威数据库；正文引用与文末条目必须一一对应。")]
refs = [
    "[1] 作者. 书名[M]. 出版地: 出版社, 年份.",
    "[2] 作者. 论文题目[J]. 期刊名, 年份, 卷(期): 起止页码.",
    "[3] Author A, Author B. Article title[J]. Journal, Year, Volume(Issue): Pages.",
    "[4] 机构名称. 报告或数据集名称[EB/OL]. 发布日期/引用日期.",
    "[5] 软件或算法官方文档[CP/OL]. 版本号, 访问日期.",
]
for r in refs:
    story.append(P(r, body_noindent))
story += [Spacer(1, 0.5 * cm), heading("AI工具使用说明（如赛事要求）", 2), P("说明AI工具的使用环节、人工核验方式和责任边界，不得虚构数据、模型结果或参考文献。")]
story += [PageBreak()]

# Page 11
story += [heading("附录", 1), heading("支撑材料说明", 2)]
support = [["附件名称", "说明"], ["附件1 原始数据.xlsx", "题目提供或收集的原始数据"], ["附件A 结果数据.xlsx", "各问题完整数值结果"], ["problem1.py", "问题一数据处理与模型代码"], ["problem2.py", "问题二优化求解代码"], ["problem3.py", "问题三扩展模型代码"], ["problem4.py", "问题四情景分析代码"]]
story += [standard_table(support, [5.7*cm, 8.3*cm]), Paragraph("表11　支撑材料说明", caption)]
story += [heading("1　问题一程序代码", 2), P("以下位置插入完整、可复现的程序代码；大型数据表建议作为独立附件提交。")]
story += [Paragraph("# problem1.py<br/>import pandas as pd<br/><br/>def main():<br/>&nbsp;&nbsp;&nbsp;&nbsp;# Load data, calculate metrics, and save results<br/>&nbsp;&nbsp;&nbsp;&nbsp;pass<br/><br/>if __name__ == '__main__':<br/>&nbsp;&nbsp;&nbsp;&nbsp;main()", code)]
story += [heading("2　问题二程序代码", 2), P("【插入问题二完整代码】"), heading("3　问题三程序代码", 2), P("【插入问题三完整代码】"), heading("4　问题四程序代码", 2), P("【插入问题四完整代码】")]

doc.build(story)
print(OUT)
