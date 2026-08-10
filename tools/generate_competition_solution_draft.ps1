$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$outputDir = Join-Path $workspace "data\chen_clan_academy\evaluation"
$docxPath = Join-Path $outputDir "参赛解决方案书初稿_祠语智游.docx"
$pdfPath = Join-Path $env:TEMP "参赛解决方案书初稿_祠语智游_校验.pdf"

$wdAlignLeft = 0
$wdAlignCenter = 1
$wdAlignRight = 2
$wdAlignJustify = 3
$wdPageBreak = 7
$wdSectionBreakNextPage = 2
$wdFormatDocumentDefault = 16
$wdExportFormatPDF = 17
$wdStatisticPages = 2
$wdCollapseEnd = 0
$wdLineSpaceMultiple = 5
$wdStyleNormal = -1
$wdStyleHeading1 = -2
$wdStyleHeading2 = -3
$wdStyleHeading3 = -4

function RGB([int]$r, [int]$g, [int]$b) { return $r + 256 * $g + 65536 * $b }

$blue = RGB 34 88 146
$darkBlue = RGB 20 52 86
$lightBlue = RGB 232 241 250
$paleGold = RGB 250 244 224
$gray = RGB 90 100 110
$lightGray = RGB 242 244 247
$white = RGB 255 255 255

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $word.Documents.Add()

try {
    $sec = $doc.Sections.Item(1)
    $sec.PageSetup.PageWidth = $word.CentimetersToPoints(21)
    $sec.PageSetup.PageHeight = $word.CentimetersToPoints(29.7)
    $sec.PageSetup.TopMargin = $word.CentimetersToPoints(1.75)
    $sec.PageSetup.BottomMargin = $word.CentimetersToPoints(1.65)
    $sec.PageSetup.LeftMargin = $word.CentimetersToPoints(1.8)
    $sec.PageSetup.RightMargin = $word.CentimetersToPoints(1.8)
    $sec.PageSetup.HeaderDistance = $word.CentimetersToPoints(0.85)
    $sec.PageSetup.FooterDistance = $word.CentimetersToPoints(0.85)

    $normal = $doc.Styles.Item($wdStyleNormal)
    $normal.Font.NameFarEast = "微软雅黑"
    $normal.Font.Name = "Aptos"
    $normal.Font.Size = 10.5
    $normal.Font.Color = RGB 35 40 45
    $normal.ParagraphFormat.Alignment = $wdAlignJustify
    $normal.ParagraphFormat.LineSpacingRule = $wdLineSpaceMultiple
    $normal.ParagraphFormat.LineSpacing = 15.5
    $normal.ParagraphFormat.SpaceAfter = 5

    foreach ($n in 1..3) {
        $styleId = @($wdStyleHeading1, $wdStyleHeading2, $wdStyleHeading3)[$n - 1]
        $style = $doc.Styles.Item($styleId)
        $style.Font.NameFarEast = "微软雅黑"
        $style.Font.Name = "Aptos Display"
        $style.Font.Bold = $true
        $style.Font.Color = if ($n -eq 1) { $blue } else { $darkBlue }
        $style.Font.Size = if ($n -eq 1) { 17 } elseif ($n -eq 2) { 14 } else { 12 }
        $style.ParagraphFormat.SpaceBefore = if ($n -eq 1) { 8 } else { 5 }
        $style.ParagraphFormat.SpaceAfter = if ($n -eq 1) { 7 } else { 4 }
        $style.ParagraphFormat.KeepWithNext = $true
    }

    function EndRange {
        $r = $doc.Content
        $r.Collapse($wdCollapseEnd)
        return $r
    }

    function Add-DocParagraph {
        param(
            [Parameter(Position=0)][string]$text,
            [Parameter(Position=1)][string]$styleName = "Normal",
            [Parameter(Position=2)][int]$align = -1,
            [Parameter(Position=3)][bool]$bold = $false,
            [Parameter(Position=4)][int]$color = -1,
            [Parameter(Position=5)][double]$size = 0
        )
        $r = EndRange
        $r.InsertAfter($text)
        $r.InsertParagraphAfter()
        $p = $doc.Paragraphs.Item($doc.Paragraphs.Count - 1)
        $styleId = switch ($styleName) {
            "Heading 1" { $wdStyleHeading1 }
            "Heading 2" { $wdStyleHeading2 }
            "Heading 3" { $wdStyleHeading3 }
            default { $wdStyleNormal }
        }
        $p.Range.Style = $doc.Styles.Item($styleId)
        if ($align -ge 0) { $p.Alignment = $align }
        if ($bold) { $p.Range.Font.Bold = $true }
        if ($color -ge 0) { $p.Range.Font.Color = $color }
        if ($size -gt 0) { $p.Range.Font.Size = $size }
        return $p
    }

    function Add-Bullet([string]$text, [int]$level = 1) {
        $p = Add-DocParagraph $text
        $p.Range.ListFormat.ApplyBulletDefault()
        $p.LeftIndent = $word.CentimetersToPoints(0.55 * $level)
        $p.FirstLineIndent = $word.CentimetersToPoints(-0.25)
        $p.SpaceAfter = 2
    }

    function Add-Number([string]$text) {
        $p = Add-DocParagraph $text
        $p.Range.ListFormat.ApplyNumberDefault()
        $p.LeftIndent = $word.CentimetersToPoints(0.55)
        $p.FirstLineIndent = $word.CentimetersToPoints(-0.25)
        $p.SpaceAfter = 2
    }

    function Add-Callout([string]$title, [string]$text, [string]$tone = "blue") {
        $r = EndRange
        $table = $doc.Tables.Add($r, 1, 1)
        $table.AllowAutoFit = $true
        $cell = $table.Cell(1,1)
        $cell.Shading.BackgroundPatternColor = if ($tone -eq "gold") { $paleGold } else { $lightBlue }
        $cell.Range.Text = "$title`r$text"
        $cell.Range.Font.NameFarEast = "微软雅黑"
        $cell.Range.Font.Size = 10
        $cell.Range.Paragraphs.Item(1).Range.Font.Bold = $true
        $cell.Range.Paragraphs.Item(1).Range.Font.Color = $darkBlue
        $table.Borders.Enable = 0
        $table.Rows.SetLeftIndent($word.CentimetersToPoints(0.1), 0)
        $r2 = EndRange
        $r2.InsertParagraphAfter()
    }

    function Add-DiagramPlaceholder([string]$figure, [string]$purpose, [string]$layout, [string]$nodes, [string]$links, [string]$source, [string]$warning) {
        $r = EndRange
        $table = $doc.Tables.Add($r, 6, 2)
        $table.AllowAutoFit = $false
        $table.Columns.Item(1).Width = $word.CentimetersToPoints(2.6)
        $table.Columns.Item(2).Width = $word.CentimetersToPoints(13.8)
        $table.Cell(1,1).Merge($table.Cell(1,2))
        $table.Cell(1,1).Range.Text = "【待队友补图】$figure"
        $table.Cell(1,1).Shading.BackgroundPatternColor = $blue
        $table.Cell(1,1).Range.Font.Color = $white
        $table.Cell(1,1).Range.Font.Bold = $true
        $labels = @("表达目的", "推荐图式", "必须出现的节点", "连线与关系", "绘图依据")
        $values = @($purpose, $layout, $nodes, $links, "$source`r边界提醒：$warning")
        for ($i=0; $i -lt 5; $i++) {
            $table.Cell($i+2,1).Range.Text = $labels[$i]
            $table.Cell($i+2,1).Range.Font.Bold = $true
            $table.Cell($i+2,1).Shading.BackgroundPatternColor = $lightGray
            $table.Cell($i+2,2).Range.Text = $values[$i]
        }
        $table.Range.Font.NameFarEast = "微软雅黑"
        $table.Range.Font.Size = 9.2
        $table.Borders.OutsideColor = $blue
        $table.Borders.InsideColor = RGB 190 205 220
        $r2 = EndRange
        $r2.InsertParagraphAfter()
    }

    function Page-Break { (EndRange).InsertBreak($wdPageBreak) }

    # Header and footer
    $header = $sec.Headers.Item(1).Range
    $header.Text = "祠语智游｜AI+旅游休闲命题赛道｜解决方案书初稿"
    $header.Font.NameFarEast = "微软雅黑"
    $header.Font.Size = 8.5
    $header.Font.Color = $gray
    $header.ParagraphFormat.Alignment = $wdAlignRight
    $footer = $sec.Footers.Item(1).Range
    $footer.Text = "参赛原型 Demo　｜　"
    $footer.Font.NameFarEast = "微软雅黑"
    $footer.Font.Size = 8.5
    $footer.Font.Color = $gray
    $footer.ParagraphFormat.Alignment = $wdAlignCenter
    $footer.Collapse($wdCollapseEnd)
    $null = $footer.Fields.Add($footer, -1, "PAGE", $true)

    # Cover
    Add-DocParagraph "祠语智游" -styleName "Normal" -align $wdAlignCenter -bold $true -color $blue -size 28 | Out-Null
    Add-DocParagraph "多角色沉浸式非遗智能导游解决方案书" -styleName "Normal" -align $wdAlignCenter -bold $true -color $darkBlue -size 18 | Out-Null
    Add-DocParagraph "AI+旅游休闲命题赛道｜参赛初稿" -styleName "Normal" -align $wdAlignCenter -bold $false -color $gray -size 11 | Out-Null
    Add-DocParagraph "" | Out-Null
    Add-Callout "一句话定位" "面向文化场馆的全流程 AI 导游：像人工导游一样会规划、会讲解、能答疑、懂进度、会收束，并以中性清晰为核心、角色化表达为体验创新。"
    Add-DocParagraph "首个场景：广州陈家祠（原型 Demo）" -styleName "Normal" -align $wdAlignCenter -bold $true -color $darkBlue -size 12 | Out-Null
    Add-DocParagraph "版本基线：experiment/agent-orchestration-v2｜tested_commit 6c71a41" -styleName "Normal" -align $wdAlignCenter -bold $false -color $gray -size 9 | Out-Null
    Add-DocParagraph "文档状态：可继续补图、排版与转 PDF；最终提交须控制在 20 页以内" -styleName "Normal" -align $wdAlignCenter -bold $false -color $gray -size 9 | Out-Null
    Add-DocParagraph "独立高校学生团队｜不代表所在高校官方立场" -styleName "Normal" -align $wdAlignCenter -bold $false -color $gray -size 9 | Out-Null
    Page-Break

    Add-DocParagraph "目录与阅读说明" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "本方案按“用户价值—产品闭环—技术实现—比赛演示—推广路径”的顺序展开。当前版本用结构化补图框标出后续需要制作的架构图，队友可直接按节点与连线要求绘制。" | Out-Null
    $tocItems = @(
        "1. 项目摘要与命题契合", "2. 核心问题、目标用户与价值主张", "3. 全流程产品方案", "4. 核心功能与场景", "5. 总体技术架构", "6. Agent 编排与状态闭环", "7. 知识、问答与路线规划", "8. 角色化讲解与质量门", "9. 当前完成度与比赛演示范围", "10. 创新点与差异化优势", "11. 实施路径与可复制性", "12. 商业模式与可持续运营", "13. 预期效果与评估指标", "14. 风险边界、路线图与结语"
    )
    foreach ($item in $tocItems) { Add-Bullet $item }
    Add-Callout "事实口径" "已实现、已验证与比赛演示能力采用肯定表述；Shadow 能力、受限 Active 灰度和赛后规划分别标注。项目目前为原型 Demo，尚无外部场馆试点、真实运营数据或客户背书。" "gold"
    Page-Break

    Add-DocParagraph "1. 项目摘要与命题契合" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "1.1 项目摘要" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "“祠语智游”不是单点问答工具，而是一名贯穿游前、游中与游后的 AI 文化导游。项目以陈家祠为首个场景，根据游客的语言、可用时间、兴趣、讲解深度与角色偏好生成个性路线；进入场馆后持续掌握当前位置、已参观内容和剩余行程，完成路线开场、到站讲解、下一站引导、完成或跳过以及受控重规划。游客可在任意环节询问建筑、工艺、装饰、术语和当前点位内容，继续追问细节，也可查询开放时间、交通、购票等实用信息。" | Out-Null
    Add-DocParagraph "中性清晰讲解是核心主干，保证信息完整易懂；古风书生是角色化创新代表，将同一审核事实转化为更具情境感的路线说明、开场白与点位讲解；儿童友好、专业讲解、静听模式等策略进一步适配不同人群。游览结束后，系统依据实际参观内容生成总结、专属称号与祝福，并衔接经审核的周边美食和休息推荐，使一次参观形成有起点、有陪伴、有记忆的完整体验。" | Out-Null
    Add-DocParagraph "1.2 与“AI+旅游休闲”命题的契合" -styleName "Heading 2" | Out-Null
    Add-Bullet "智能行程规划：按时间、兴趣、讲解深度与合法空间路径组织路线。"
    Add-Bullet "AI 虚拟导游：覆盖路线开场、到站讲解、现场答疑、下一站引导与游后收束。"
    Add-Bullet "沉浸式体验创新：在不改变事实的前提下，以多种角色表达增强文化代入感。"
    Add-Bullet "智慧旅游线上服务：支持交通、开放时间、购票等实用问答及周边服务推荐。"
    Add-Callout "命题价值" "项目把人工导游“会规划、会讲解、能答疑、懂进度、会收束”的能力拆解为可运行、可追踪、可迁移的智能流程，契合广州文旅场景中“有温度的智能旅行体验”方向。"
    Page-Break

    Add-DocParagraph "2. 核心问题、目标用户与价值主张" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "2.1 核心问题" -styleName "Heading 2" | Out-Null
    Add-Bullet "传统自助参观内容多为固定展签或固定音频，难以随游客时间、兴趣和理解水平调整。"
    Add-Bullet "通用问答工具往往缺少“我在哪里、看过什么、下一站去哪”的游览状态，回答与路线割裂。"
    Add-Bullet "人工导游具有连续服务与情境表达优势，但服务容量、语言风格和个性化程度受人力约束。"
    Add-Bullet "文化讲解既需要生动，也必须受审核事实、空间规则和现场安全约束，不能靠自由生成替代专业内容。"
    Add-DocParagraph "2.2 目标用户" -styleName "Heading 2" | Out-Null
    Add-Bullet "自由行游客：希望在有限时间内获得清晰路线和随问随答的导览。"
    Add-Bullet "亲子与学生群体：需要更易懂、可观察、能激发兴趣的文化解释。"
    Add-Bullet "文化深度游客：关注工艺、建筑、故事脉络与更专业的表达。"
    Add-Bullet "场馆与景区运营方：希望提升数字导览覆盖率、内容一致性和游客体验。"
    Add-DocParagraph "2.3 价值主张" -styleName "Heading 2" | Out-Null
    Add-Callout "对游客" "一位能随行理解需求、记住进度、解释文化并给出下一步的 AI 导游。"
    Add-Callout "对场馆" "在审核知识与既有空间规则上增加智能编排和个性表达，而不是另建一套不可控内容。"
    Add-Callout "对文旅生态" "将场内导览自然延伸到交通、购票、周边餐饮与游后记忆，形成完整服务链。"
    Page-Break

    Add-DocParagraph "3. 全流程产品方案" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "产品围绕“游前—游中—游后”构建连续体验，核心不是一次回答，而是持续维护游客画像、路线状态、知识覆盖与当前情境。" | Out-Null
    Add-DocParagraph "3.1 游前：理解游客并形成可执行路线" -styleName "Heading 2" | Out-Null
    Add-Bullet "采集语言、时长、兴趣、讲解深度与角色偏好。"
    Add-Bullet "结合审核路线、空间关系与停留预算生成路线说明和首站提示。"
    Add-Bullet "保留中性清晰的稳定表达，并在比赛白名单中展示古风书生角色化路线与开场。"
    Add-DocParagraph "3.2 游中：边走、边讲、边问、边调整" -styleName "Heading 2" | Out-Null
    Add-Bullet "到站后依据审核对象和知识卡组织点位讲解。"
    Add-Bullet "任意环节可提问；当前点问答与“再讲详细一点”追问继承上下文。"
    Add-Bullet "完成、跳过、下一站和受控重规划由确定性状态机处理。"
    Add-Bullet "提供必要路线提示和安全拍照打卡建议。"
    Add-DocParagraph "3.3 游后：总结、成就与周边服务" -styleName "Heading 2" | Out-Null
    Add-Bullet "依据真实参观内容生成游览总结，不虚构未完成内容。"
    Add-Bullet "形成专属称号与祝福，强化文化记忆和分享意愿。"
    Add-Bullet "在游客确认后提供经审核的周边餐饮、饮品和休息推荐。"
    Add-DiagramPlaceholder "图1　游客全旅程闭环图" "一眼说明系统不是单点问答，而是贯穿游前、游中、游后的连续 AI 导游。" "横向三阶段泳道图；上层为游客行为，下层为系统能力。" "游前：画像采集、路线规划、角色选择；游中：开场、到站、讲解、问答、引路、完成/跳过；游后：总结、称号祝福、周边推荐。" "以 VisitorProfile、TourState、Coverage 三条贯穿线连接阶段；用回环箭头表示提问与受控重规划。" "competition_submission.md 与 competition_scope_and_demo_baseline.md" "问答 Active、navigation Active、全角色 Active 不得画成已开放能力。"
    Page-Break

    Add-DocParagraph "4. 核心功能与应用场景" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "4.1 个性路线与节奏控制" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "系统将游客可用时间、兴趣偏好、讲解深度与审核路线结合，生成包含停留顺序、预计时长、第一站和下一步动作的路线方案。路线推进与游客状态分离：讲解不会自动完成点位，问答也不会改变路线进度。" | Out-Null
    Add-DocParagraph "4.2 中性清晰讲解与角色化表达" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "中性清晰是所有模式的内容基线，负责把审核事实完整、准确、可理解地交付；角色化表达只改变语气、句式、节奏与组织方式。古风书生作为比赛展示角色，已覆盖路线规划、路线开场和审核点位讲解的受限 Active 演示。18 种风格已完成自动化 Shadow 验证，比赛不将其全部开放为 Active。" | Out-Null
    Add-DocParagraph "4.3 任意环节问答与连续追问" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "系统支持建筑、工艺、装饰、术语、当前点位以及开放时间、交通、购票等实用问答。角色化问答候选在 Shadow 中接受事实、安全和预算校验，游客仍看到旧版受控答案；“再讲详细一点”继承上一问的对象和证据范围，若缺少上下文则主动澄清。" | Out-Null
    Add-DocParagraph "4.4 位置、进度与路线控制" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "系统维护当前点、已参观点、剩余点和路线计划，支持到达、完成、跳过、下一站与受控重规划。空间引导只使用审核通过的路径，不把自由生成文本当作导航依据。" | Out-Null
    Add-DocParagraph "4.5 拍照、游后总结与周边推荐" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "拍照建议结合开阔位置、取景主题和禁止触摸等规则；游后总结基于真实覆盖内容形成称号与祝福；周边推荐展示名称、类别、地址与中性理由，并提示营业和现场信息需自行确认。" | Out-Null
    Add-Callout "典型应用场景" "博物馆与纪念馆自助导览、古建筑和历史街区深度游、非遗展馆研学、城市文化线路、文旅服务中心智能咨询。"
    Page-Break

    Add-DocParagraph "5. 总体技术架构" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "系统采用“确定性决策层 + 生成式表达层”的双层架构。确定性层负责路线、事实、空间、状态与安全规则；生成式层负责在受控 ContentPlan 内组织语言。两层之间通过结构化 Schema、事实 ID、预算和安全校验连接。" | Out-Null
    Add-DiagramPlaceholder "图2　系统总体技术架构图（必须补）" "展示从游客交互到 Agent 编排、知识与空间数据、角色生成、质量门和可观测性的完整技术栈。" "六层分层架构图。" "1 交互层：Web/Studio/未来小程序；2 Agent 编排层：LangGraph；3 决策层：语义路由、画像、路线、TourState；4 内容层：RAG、知识卡、空间图、周边 POI；5 表达层：ContentPlan、DeepSeek API、角色 Schema；6 质量与观测：验证器、fallback、Coverage、LangSmith Trace。" "游客请求自上而下；事实与路线从数据层进入决策层；ContentPlan 单向约束模型；验证失败回到旧链；审计信息横向写入观测层。" "agent_graph.py、rag_retrieval.py、route_planner.py、controlled_rollout.py、角色讲解与问答模块" "不得把模型画成直接修改 TourState、路线、数据库或调用任意工具。"
    Add-DocParagraph "5.1 关键技术组件" -styleName "Heading 2" | Out-Null
    Add-Bullet "Agent 框架：LangGraph 状态图，节点化组织画像、路由、路线、讲解、问答、导航和游后流程。"
    Add-Bullet "基座模型：DeepSeek API，用于受约束的讲解与角色表达生成。"
    Add-Bullet "检索：本地混合检索，BM25 与 BGE 向量召回经 RRF 融合，必要时条件重排。"
    Add-Bullet "空间规划：基于人工审核空间网络和 NetworkX 最短合法路径。"
    Add-Bullet "状态与审计：TourState、VisitorProfile、Coverage、结构化审计字段与 LangSmith Studio Trace。"
    Page-Break

    Add-DocParagraph "6. Agent 编排与状态闭环" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "Agent 的智能来自“先理解、再决策、后表达”的编排，而不是把所有任务交给一次自由生成。每个节点有清晰输入输出和可写状态边界。" | Out-Null
    Add-DiagramPlaceholder "图3　核心 Agent 工作流图（必须补）" "说明一次游览如何从输入进入语义归一、画像、路线、讲解、问答、导航和总结。" "纵向主流程 + 两个旁路（问答、失败回退）。" "visitor_welcome → semantic_normalization → visitor_onboarding/profile_collection → direct_route → route opening → stop_guidance → narration_content_plan → role generation → validation → commit → navigation → tour_event → visit_summary。旁路：tour_qa/qa_follow_up_detail；fallback：deterministic legacy chain。" "主流程实线；Shadow 审计虚线；Active 白名单粗线；失败路径红色回到旧链。" "agent_graph.py 与 competition_scope_and_demo_baseline.md" "不要画自由 Planner 接管、问答 Active 或重规划 Active。"
    Add-DocParagraph "6.1 三类核心状态" -styleName "Heading 2" | Out-Null
    Add-Bullet "VisitorProfile：语言、兴趣、讲解深度、角色偏好等长期会话信息，同线程保留、跨线程隔离。"
    Add-Bullet "TourState：当前点、已参观、剩余点、路线与推进控制；讲解和问答不得私自修改。"
    Add-Bullet "Coverage：记录已正式介绍的事实主题，避免重复计入，并为游后总结提供依据。"
    Add-DocParagraph "6.2 语义路由" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "系统对控制指令、问答、路线修改、模式选择和澄清请求进行优先级仲裁。确定性控制优先于自由问答，含多个操作的输入进入澄清，避免一句话造成部分状态写入。" | Out-Null
    Page-Break

    Add-DocParagraph "7. 知识、问答与路线规划" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "7.1 审核知识与混合检索" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "知识来源先经过人工整理与审核，形成可追踪的 Markdown 资料、结构化知识卡和向量索引。问答检索使用 BM25 与向量召回互补，经 RRF 融合，并根据需要进行重排；回答携带内部证据边界，但不会向游客泄漏 source_id、文件路径、URL 或原始 chunk。" | Out-Null
    Add-DiagramPlaceholder "图4　知识与受控问答链路" "解释系统为何既能回答文化知识和实用信息，又不把检索内容无约束暴露给模型。" "左到右数据流水线。" "官方/审核资料 → 清洗与结构化 → Markdown/知识卡/Chroma/BM25 → 混合召回 → RRF/条件重排 → Evidence Bundle → 旧版受控答案 → QA ContentPlan → 角色 Shadow 候选与验证。" "证据只进入受控答案与 ContentPlan；角色候选不得重新检索；验证失败保留旧答案。" "rag_retrieval.py、知识卡与 qa_role_shadow 相关模块" "项目无外部场馆授权背书时，不在图中标注“官方合作数据库”。"
    Add-DocParagraph "7.2 路线与空间规划" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "路线规划基于游客时间和兴趣选择审核路线，并在人工审核的空间网络上计算合法路径。系统区分“路线推荐”和“状态提交”：周边商户不会被写入馆内 route_stop_ids，模糊或混合修改请求先澄清。" | Out-Null
    Add-DiagramPlaceholder "图5　路线规划与空间约束图" "展示个性化不是模型凭空规划，而是画像驱动的确定性路线与合法路径计算。" "输入—决策—输出漏斗图。" "输入：时间、兴趣、深度、当前状态；决策：路线候选、时间预算、审核空间图、NetworkX 路径；输出：停留顺序、预计时长、下一站、现场不确定性提示。" "画像影响候选评分；空间图约束路径；TourState 控制执行；角色层只改写说明。" "route_planner.py、route_selection.py、tour_navigation.py" "不得声称具备实时室内定位或实时人流导航。"
    Page-Break

    Add-DocParagraph "8. 角色化讲解与质量门" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "8.1 表达创新的正确边界" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "角色化不是让模型重新写历史，而是把审核事实放入不同表达策略。中性清晰负责完整易懂；古风书生通过称呼、节奏和意象连接增强文化氛围；儿童友好缩短句子、降低观察任务难度；专业讲解提高术语组织密度；静听模式减少提问与互动。" | Out-Null
    Add-DocParagraph "8.2 ContentPlan—候选—验证—提交" -styleName "Heading 2" | Out-Null
    Add-DiagramPlaceholder "图6　角色讲解质量门与回退链路（必须补）" "突出项目最具差异化的技术：角色表达生动，但事实、预算、安全和状态仍可控。" "双通道门控流程图。" "旧链确定性事实/路线 → ContentPlan（fact_ids、required facts、budget、interaction_allowed）→ DeepSeek 角色候选 → Schema/事实边界/角色一致性/预算/内部字段/安全校验 → 通过：白名单 Active commit；失败：legacy fallback。" "Coverage 只在正式 commit 处提交一次；Shadow 只记录不接管；所有失败箭头回到完整旧正文。" "role narration generation/validation/commit、controlled_rollout.py、competition active tests" "不得画成所有 18 角色、所有场景均 Active；比赛 Active 仅限白名单。"
    Add-DocParagraph "8.3 比赛版本展示范围" -styleName "Heading 2" | Out-Null
    Add-Bullet "古风书生：路线规划 Active、路线开场 Active、两个审核充分点位的讲解 Active。"
    Add-Bullet "neutral、child、professional：点位讲解受限 Active 白名单。"
    Add-Bullet "角色化问答：tour_qa 与 qa_follow_up_detail 已完成 Shadow 验证，游客仍看到旧版安全答案。"
    Add-Bullet "其他角色和场景：保持 Shadow 或旧链，不在比赛中扩大接管范围。"
    Page-Break

    Add-DocParagraph "9. 当前完成度与比赛演示范围" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "9.1 当前阶段" -styleName "Heading 2" | Out-Null
    Add-Callout "项目阶段" "原型 Demo。核心游览闭环已可运行，尚无外部场馆试点、真实用户规模或商业订单。"
    $r = EndRange
    $table = $doc.Tables.Add($r, 8, 3)
    $headers = @("能力", "当前状态", "比赛展示口径")
    for ($c=1; $c -le 3; $c++) { $table.Cell(1,$c).Range.Text=$headers[$c-1]; $table.Cell(1,$c).Shading.BackgroundPatternColor=$blue; $table.Cell(1,$c).Range.Font.Color=$white; $table.Cell(1,$c).Range.Font.Bold=$true }
    $rows = @(
        @("路线与状态闭环", "已实现", "按时间兴趣规划、到站、完成、跳过、下一站与受控重规划"),
        @("中性清晰讲解", "已实现", "所有角色模式的稳定内容基线"),
        @("18 种角色", "Shadow 自动验证", "不宣称全部 Active；仅抽样展示高风险角色质量"),
        @("古风书生", "受限 Active", "路线规划、开场和两个审核点位"),
        @("角色化问答", "Shadow", "当前问答和连续追问，旧答案保留"),
        @("游后与周边", "已实现", "总结、称号祝福、经审核周边推荐"),
        @("工程验证", "1118/1118", "作为内部回归证据，不等同于外部运营效果" )
    )
    for ($i=0; $i -lt $rows.Count; $i++) { for ($c=0; $c -lt 3; $c++) { $table.Cell($i+2,$c+1).Range.Text=$rows[$i][$c] } }
    $table.Range.Font.NameFarEast="微软雅黑"; $table.Range.Font.Size=8.7; $table.Borders.Enable=1
    (EndRange).InsertParagraphAfter()
    Add-DocParagraph "9.2 建议比赛演示脚本" -styleName "Heading 2" | Out-Null
    Add-Number "游客输入中文、30 分钟、喜欢灰塑，选择古风书生。"
    Add-Number "系统给出角色化路线方案与开场白。"
    Add-Number "到达前院中部，展示角色化点位讲解与审核事实一致。"
    Add-Number "询问一个当前点知识问题并追问“再讲详细一点”，展示问答 Shadow 审计和旧答案保留。"
    Add-Number "完成本点并进入下一站，展示状态正确推进与 Coverage 仅提交一次。"
    Add-Number "结束游览，展示总结、专属称号祝福和周边推荐。"
    Page-Break

    Add-DocParagraph "10. 创新点与差异化优势" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "10.1 从“聊天机器人”到“全流程导游”" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "项目对标的是人工导游的连续服务能力，而非简单资料查询。路线、位置、讲解、问答、进度和游后服务在同一线程中协作，游客不需要每次重新说明情境。" | Out-Null
    Add-DocParagraph "10.2 中性清晰主干 + 角色表达创新" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "稳定的中性讲解保证核心内容；角色化不是装饰性语气包，而是受 ContentPlan 约束的表达层。古风书生等角色能影响路线说明、开场与点位讲解，同时不改变事实和路线。" | Out-Null
    Add-DocParagraph "10.3 事实、空间、状态与表达分权" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "确定性系统决定“去哪、讲什么、当前状态是什么、什么行为安全”，生成模型只决定“怎样表达”。这一分权使生动体验与文化准确性可以同时成立。" | Out-Null
    Add-DocParagraph "10.4 可追踪的质量门与失败回退" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "候选正文在公开前检查 Schema、事实 ID、预算、安全、角色一致性和内部字段；任何异常都会保留完整旧正文。Shadow—Active 灰度机制让新能力先观察再接管。" | Out-Null
    Add-DocParagraph "10.5 有温度的游后设计" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "基于真实参观内容生成称号和祝福，并衔接周边服务，使文化参观从一次信息消费转化为可回忆、可分享、可延伸的体验。" | Out-Null
    Add-Callout "差异化总结" "既有“像导游一样连续”的产品闭环，又有“像角色一样生动”的表达体验，还保留“像信息系统一样可控”的工程边界。"
    Page-Break

    Add-DocParagraph "11. 实施路径与可复制性" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "11.1 场馆接入方法" -styleName "Heading 2" | Out-Null
    Add-Number "资料盘点：收集场馆展签、官网、研究资料、开放与服务信息。"
    Add-Number "内容审核：整理工艺、建筑、对象、位置与安全规则，形成知识卡。"
    Add-Number "空间建模：建立点位和合法路径网络，确认入口、出口和不可达区域。"
    Add-Number "路线设计：按时间、兴趣和人群设置路线模板及停留预算。"
    Add-Number "导游编排：配置开场、讲解、问答、导航、完成和游后流程。"
    Add-Number "Shadow 验证：先观察角色候选、事实边界和预算，再逐步开放 Active。"
    Add-Number "运营更新：场馆资料、营业信息和推荐 POI 变更后重新审核发布。"
    Add-DiagramPlaceholder "图7　部署与场馆接入架构图" "说明方案如何从陈家祠原型复制到其他博物馆、古建景区和非遗展馆。" "左右两部分：部署架构 + 场馆接入流水线。" "前端 H5/未来小程序；API 与 LangGraph 服务；DeepSeek API；向量索引/知识卡/空间图/状态存储；LangSmith 观测。接入流水线：资料→审核→知识卡→空间图→路线→Shadow→发布。" "用户流量进入 API；模型与本地知识分离；内容更新经过审核；日志进入观测。" "当前代码模块与数据目录结构" "不要声称已完成小程序、云端正式部署、多场馆 SaaS 或实时定位。"
    Add-DocParagraph "11.2 实施周期建议" -styleName "Heading 2" | Out-Null
    Add-Bullet "第 1–2 周：资料与空间梳理、内容规范。"
    Add-Bullet "第 3–4 周：知识卡、路线模板和基础问答。"
    Add-Bullet "第 5–6 周：角色表达、质量门与场内联调。"
    Add-Bullet "第 7–8 周：小范围体验测试、运营培训与内容修订。"
    Page-Break

    Add-DocParagraph "12. 商业模式与可持续运营" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "当前项目尚未商业化，以下为可行模式设计，不作为已验证收入陈述。" | Out-Null
    Add-DocParagraph "12.1 面向场馆的服务模式" -styleName "Heading 2" | Out-Null
    Add-Bullet "项目制接入：知识整理、空间建模、路线设计、角色配置与前端集成。"
    Add-Bullet "年度软件服务：导览 Agent、内容后台、审计与数据看板。"
    Add-Bullet "内容运维：展陈变化、节庆路线、活动讲解和服务信息更新。"
    Add-Bullet "私有化或专有云部署：适配对数据和内容审核要求较高的场馆。"
    Add-DocParagraph "12.2 面向游客的增值可能" -styleName "Heading 2" | Out-Null
    Add-Bullet "基础导览免费，深度主题路线、家庭研学包或特色角色包作为增值内容。"
    Add-Bullet "与官方文创、活动预约和经审核周边服务形成合规转化，但推荐排序不以广告替代游客需求。"
    Add-DocParagraph "12.3 可持续运营机制" -styleName "Heading 2" | Out-Null
    Add-Bullet "场馆负责权威内容与更新确认，平台负责结构化、验证与发布工具。"
    Add-Bullet "通过问答缺口、路线完成率和回退原因发现内容维护需求。"
    Add-Bullet "新角色先 Shadow、后灰度、再开放，降低体验创新对稳定服务的冲击。"
    Add-Callout "当前融资口径" "团队现阶段无股权融资需求，优先完成比赛展示、原型打磨与场景验证。"
    Page-Break

    Add-DocParagraph "13. 预期效果与评估指标" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "项目尚无外部落地案例，因此本节给出试点后的评估框架，不虚构用户数据。" | Out-Null
    $r = EndRange
    $table = $doc.Tables.Add($r, 7, 3)
    $metrics = @(
        @("维度", "建议指标", "验证方式"),
        @("导览效率", "路线生成成功率、平均响应时间、路线完成率", "系统日志与用户任务测试"),
        @("内容质量", "事实一致率、内部字段泄漏率、回退率", "自动化质量门与人工抽检"),
        @("体验适配", "角色偏好选择率、讲解满意度、追问成功率", "问卷与行为统计"),
        @("文化传播", "重点工艺覆盖率、称号分享意愿、内容记忆度", "Coverage 与访后问卷"),
        @("运营价值", "咨询分流率、内容更新时效、热门问题缺口", "客服对照与运营看板"),
        @("安全稳定", "异常回退成功率、状态污染率、重复 Coverage", "故障注入与回归测试")
    )
    for ($i=0; $i -lt $metrics.Count; $i++) { for ($c=0; $c -lt 3; $c++) { $table.Cell($i+1,$c+1).Range.Text=$metrics[$i][$c] } }
    for ($c=1; $c -le 3; $c++) { $table.Cell(1,$c).Shading.BackgroundPatternColor=$blue; $table.Cell(1,$c).Range.Font.Color=$white; $table.Cell(1,$c).Range.Font.Bold=$true }
    $table.Range.Font.NameFarEast="微软雅黑"; $table.Range.Font.Size=9; $table.Borders.Enable=1
    (EndRange).InsertParagraphAfter()
    Add-DocParagraph "13.1 预期落地效果" -styleName "Heading 2" | Out-Null
    Add-Bullet "为散客提供接近人工导游连续性的自助体验，减少路线和信息焦虑。"
    Add-Bullet "为儿童、专业游客和偏好沉浸表达的人群提供差异化讲解。"
    Add-Bullet "帮助场馆沉淀结构化内容资产、问答缺口与游客兴趣数据。"
    Add-Bullet "在不替换场馆权威内容的前提下，提高数字导览的可维护性和复用性。"
    Page-Break

    Add-DocParagraph "14. 风险边界、路线图与结语" -styleName "Heading 1" | Out-Null
    Add-DocParagraph "14.1 当前边界" -styleName "Heading 2" | Out-Null
    Add-Bullet "不宣称已与陈家祠或其他场馆建立官方合作。"
    Add-Bullet "不宣称拥有真实试点用户、订单、收入或运营成效。"
    Add-Bullet "不将 Shadow 候选表述为游客已看到的 Active 能力。"
    Add-Bullet "不开放自由 Planner 直接修改路线、状态或事实。"
    Add-Bullet "不宣称已具备实时室内定位、语音交互或多场馆生产部署。"
    Add-DocParagraph "14.2 赛后路线图" -styleName "Heading 2" | Out-Null
    Add-Bullet "短期：完成三条 neutral/child/professional 端到端演示验收，冻结比赛版本。"
    Add-Bullet "中期：开展场馆小范围体验测试，完善内容后台、运营指标和移动端交互。"
    Add-Bullet "长期：在审核机制稳定后扩展多场馆、多语言、语音与更多角色 Active。"
    Add-DocParagraph "14.3 团队与分工补充位" -styleName "Heading 2" | Out-Null
    Add-Bullet "张丽轩：华南理工大学大数据管理与应用专业在读，参与需求梳理、方案设计、功能实现与测试验证。"
    Add-Bullet "队员 2：【待补：姓名、专业背景、项目贡献】"
    Add-Bullet "队员 3：【待补：姓名、专业背景、项目贡献】"
    Add-DocParagraph "结语" -styleName "Heading 2" | Out-Null
    Add-DocParagraph "祠语智游希望让数字导览不止“知道答案”，更能像一位可靠的导游那样理解游客、组织路线、讲清文化、回应问题、陪伴推进并留下记忆。项目以陈家祠为首个原型，已经搭建出可运行、可审计、可回退的完整技术闭环；下一步将以真实场景验证为重点，把这套方法沉淀为博物馆、古建景区和非遗展馆可复制的智能导游基础设施。" | Out-Null
    Add-Callout "交付前待办" "1）按图1–图7框架补齐架构图；2）补队员信息；3）补 Demo/代码链接；4）统一项目名称与视觉标识；5）最终 PDF 控制在 20 页以内并逐页校对。" "gold"

    $doc.Repaginate()
    $doc.SaveAs2($docxPath, $wdFormatDocumentDefault)
    $doc.ExportAsFixedFormat($pdfPath, $wdExportFormatPDF)
    $pages = $doc.ComputeStatistics($wdStatisticPages)
    Write-Output "DOCX=$docxPath"
    Write-Output "PDF=$pdfPath"
    Write-Output "PAGES=$pages"
}
finally {
    if ($doc) { $doc.Close($false) }
    if ($word) { $word.Quit() }
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
