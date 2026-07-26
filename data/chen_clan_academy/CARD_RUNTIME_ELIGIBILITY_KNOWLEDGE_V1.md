# D0-K 卡片运行资格审计（v1）

本补充说明对应 `card_runtime_eligibility_knowledge_v1.yaml`，只声明首版运行资格，不修改术语卡、研究摘要卡或比较卡的既有 ID、正文和字段。清单缺失记录的默认结果是 `disabled`。

## 审计结果

| 卡片类型 | enabled | attributed_only | disabled | 合计 |
| --- | ---: | ---: | ---: | ---: |
| 术语卡 | 48 | 0 | 34 | 82 |
| 研究摘要卡 | 0 | 9 | 11 | 20 |
| 比较卡 | 0 | 8 | 0 | 8 |
| 合计 | 48 | 17 | 45 | 110 |

- 首批可用：48 条 `translation_status=reviewed` 的术语卡，可用于中文定义、拼音、已审核英文表达与检索提示；任何具体现场事实仍须由基础 RAG 或已审核点位证据支持。
- 仅可归因使用：9 条 `status=reviewed` 的研究摘要卡，以及 8 条比较卡。研究卡必须显式表述为论文作者/研究的观点；比较卡仅限 `study`、`professional`、`explicit_research_comparison`，不得进入普通游客模式。
- 禁用：34 条英文草稿术语卡（当前标准未能证明中文定义已独立审核）；8 条 `background` 研究卡；3 条虽标为 `reviewed` 但自身仍明确要求补齐来源、页码、题材或点位复核的研究卡。

## 规划—实现冲突

| 冲突卡片 | 现有字段 | 无法判断的原因 | 最小兼容方案 | 推荐方案 |
| --- | --- | --- | --- | --- |
| `research_014_cold_lane_ventilation` | `status=reviewed`，但限制字段说明作者、年份和结论页码未可靠提取 | “专题通过”不等于书目和结论的事实核验 | 清单中设为 `disabled/pending`，不改原卡 | 人工核对原始 PDF 后再审计 |
| `research_017_grey_plaster_process_and_viewing` | `status=reviewed`，但限制字段要求核对学位单位、年份和章节页码 | 来源可追溯性尚未闭合 | 设为 `disabled/pending` | 完成书目信息、具体部位和章节页码复核后，评估为 `attributed_only` |
| `research_019_stone_platform_and_railings` | `status=reviewed`，但限制字段称书目信息、题材定名和点位待复核，且写明当前仅限研究草稿 | 审核索引的“专题通过”与单卡运行限制冲突 | 设为 `disabled/pending` | 核对原始论文及馆方/现场资料后重新评估 |

## 尚待人工决定

1. 34 条英文草稿术语的中文定义是否已由独立人工审核；未确认前不能启用。
2. 研究摘要卡的 `reviewed` 是否应拆分为“研究主题通过”和“可运行事实通过”。
3. 研究卡的点位、题材名称和馆方事实由谁、以何种来源完成复核。
4. 比较卡若要服务普通游客，需要另建 `confirmed` / `cautious` 证据层，不能放宽现有 `research_only` 卡。

## 校验

```powershell
& 'D:\acaconda\python.exe' -m unittest -v test_card_runtime_eligibility.py
```

测试覆盖完整覆盖、唯一性、受控枚举、启用卡来源、英文草稿门禁、背景研究卡门禁、比较卡普通游客门禁、待核验事实门禁和缺失记录默认禁用。
