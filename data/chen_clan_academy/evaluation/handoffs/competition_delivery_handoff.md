# 比赛交付交接

## 1. 当前比赛版本

本节直接以 [competition_scope_and_demo_baseline.md](competition_scope_and_demo_baseline.md) 为比赛范围与对外口径来源，不重新分析或扩大功能范围。

```text
当前分支: experiment/agent-orchestration-v2
当前提交: 6c71a41
完整回归结果: 1118/1118 passed_by_operator
```

- 已经 Active 的角色与场景：`ancient_scholar` 的 `route_planning`、`route_opening`、`stop_guidance`；`child` 与 `neutral` 的白名单审核点位 `stop_guidance`。
- 仍处于 Shadow 的能力：其余角色/场景的角色正文候选、18 种角色目录与审计、角色化 `tour_qa` 与 `qa_follow_up_detail`、引路、游览结束、路线与重规划 proposal 审计。
- 当前展示主线：古风书生选择 → 30 分钟路线规划 → 角色化开场 → 到达前院中部 → 角色化点位讲解 → 受控问答的 Shadow 审计 → 完成本点或前往下一站；儿童友好作差异化补充，中性清晰作为稳定兜底。

## 2. 现有比赛文档

| 文件名 | 用途 | 当前状态 | 下一步 |
|---|---|---|---|
| `competition_scope_and_demo_baseline.md` | 参赛功能标杆、展示范围与对外口径 | existing | 所有材料按此核对，不扩大宣传范围 |
| `../competition_submission.md` | 项目介绍初稿 | existing | 按官方模板整理、审校表述 |
| `../祠语智游_参赛解决方案书初稿.md` | 项目计划书/解决方案书初稿 | existing | 补图后排版为正式 PDF |
| `../祠语智游_技术架构说明初稿.md` | 技术说明初稿 | existing | 精简为 1–3 页技术架构说明 |
| 视频脚本 | 演示视频脚本与分镜 | not_created | 围绕古风书生主线编写并录制 |
| `../../../../demo/README_DEPLOY.md` | Demo 部署说明 | existing | 修复本地环境、完成部署步骤 |
| 证据索引 | 汇总测试、截图与展示证据 | not_created | 建立图片、测试结果和视频素材索引 |

## 3. 正式提交前还缺什么

- 比赛官方模板和最终提交要求；
- 将 Markdown 初稿按官方模板排版为正式 PDF；
- 建议准备 6 张核心图片：
  1. 项目架构图；
  2. 游览状态流程图；
  3. 证据到角色正文流程图；
  4. Streamlit 主界面；
  5. 古风书生路线规划、开场、点位讲解组合图；
  6. 安全拒绝、回退和测试结果组合图；
- 完成 Streamlit 前端与部署，取得在线 Demo URL；
- 视频录制、旁白、字幕与剪辑，取得视频 URL；
- 最终 PDF URL、全部链接检查与报名提交。

## 4. Streamlit 进度

```text
前端文件: completed（本地未提交工作区）
本地可启动: pending
真实调用 Agent: completed（薄适配层调用 chat(user_text, thread_id)）
Secrets: pending
已部署: pending
在线 URL: pending
还缺: 修复本地 Python/Streamlit 环境、安装演示依赖、配置 Secrets、冒烟验证、部署并记录 URL
```

## 5. 视频进度

| 项目 | 状态 |
|---|---|
| 脚本 | not_started |
| 录屏 | not_started |
| 旁白 | not_started |
| 字幕 | not_started |
| 剪辑 | not_started |
| 上传 | not_started |
| 公开视频链接 | not_started |

## 6. 队友下一步顺序

1. 获取比赛官方模板和提交要求
2. 完成并部署 Streamlit
3. 取得在线 Demo 链接
4. 准备 6 张核心图片
5. 录制古风书生主线视频
6. 按官方模板整理正式文书
7. 将 Markdown 内容排版为 PDF
8. 上传视频和 PDF
9. 汇总所有成果链接
10. 最终检查并报名提交

## 7. 群内简短通知

比赛功能开发已冻结，当前文档以 Markdown 初稿为主，后续请严格按官方模板制作 PDF。请优先补齐 6 张核心图片、完成 Streamlit 环境配置与部署、取得在线链接，并录制剪辑古风书生主线视频。除已列范围外，请勿自行扩大功能或宣传口径；对外材料以比赛功能标杆和本交接为准。
