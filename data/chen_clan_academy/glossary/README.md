# 陈家祠双语术语卡

本目录保存面向研究型游客与多语言导览的规范中文术语、拼音与英文表达。术语卡聚焦建筑制度、构件、工艺、材料、技法、保护与文化概念；具体路线点位名称属于 `stops/` 的点位讲解卡，不属于本词表。当前 `rag_ingestion.py` 不读取本目录。

## 数据文件

- `glossary_zh_en_v0.yaml`：第一批术语卡。
- `research_references.md`：用于澄清易混工艺术语的学术参考登记；未完成完整书目信息和内容摘录前，不可作为已核验定义的唯一依据。
- `glossary_retrieval_rules_v0.yaml`：术语领域到知识文件、问题意图和回答策略的检索索引。

## 使用规则

1. `zh`、`source_ids` 与 `verified_at` 记录术语在陈家祠资料中的事实依据。
2. `en` 为导览用推荐表达；首次出现时，英文讲解应保留 `zh` 和 `pinyin`。
3. `translation_status=reviewed` 才能作为默认英文表达；`draft` 只能供人工审阅，不进入面向游客的自动输出。
4. `discouraged_translations` 记录容易造成误解或不适合作为唯一译名的表达，不表示绝对错误。
5. `domain` 是受控领域字段，供后续按问题领域过滤术语；当前允许值为：`institution_and_site`、`clan_and_education`、`heritage_designation`、`architectural_layout`、`architectural_components`、`decorative_materials`、`sculptural_techniques`、`decorative_crafts`、`conservation`、`ritual_and_ancestral`、`decorative_subjects_and_inscriptions`、`narrative_and_legends`。
6. 新术语必须有稳定 `term_id`，并引用 `sources/source_registry.md` 中已登记的来源编号。
7. `research_reference_ids` 仅指向本目录的学术参考登记，用于记录定义、辨析和译法的待核验依据；它不替代 `source_ids`。
8. 术语命中后，检索器按 `domain` 读取 `glossary_retrieval_rules_v0.yaml` 的默认规则；只对需要特殊别名、关联术语或更窄回答边界的术语另建覆盖规则。

## 后续接入

完成首批英文讲解验收后，再由专用术语查询函数按 `term_id` 或 `zh` 读取本目录；不要将整份词表直接混入当前中文事实 RAG。
