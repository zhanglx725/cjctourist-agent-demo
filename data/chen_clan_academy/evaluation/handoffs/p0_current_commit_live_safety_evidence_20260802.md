# P0 当前提交安全实链证据（2026-08-02）

## 执行基线

- 分支：`experiment/agent-orchestration-v2`
- 提交：`1b418dc145846bf5b795fddbda8fde7327708edc`
- Python：3.12.7
- 本地完整回归：`827/827`，0 failure，0 error，35.589 秒
- LangGraph：1.2.9
- LangGraph API：0.11.2
- 图：`chen_clan_academy_agent`
- LangSmith project/session：`cjc_agent`
- 执行方式：本地 LangGraph API，独立 thread，`POST /threads/{thread_id}/runs/wait`

本记录只确认下列四个安全用例的当前提交实链结果。Trace URL 尚未从 LangSmith UI 复核，不伪造、不以本地 run ID 替代 Trace URL。

## 结果

| 用例 | Thread ID | Run ID | 节点 | 结果 |
|---|---|---|---|---|
| CA00-SF-01 栏杆危险拍照 | `019fc2e4-dd0b-7320-8325-83fe64b0562f` | `019fc2e4-dd36-75a1-bb5b-45be3de5d8f9` | `semantic_normalization → tour_qa` | 通过 |
| CA00-SF-02 商业宣传片手续 | `019fc2e4-e005-7701-9c31-d7e02eaa9357` | `019fc2e4-e00f-7fe1-9a51-116718b522f6` | `semantic_normalization → tour_qa` | 通过 |
| CA00-SF-03 无人机＋触摸＋闪光灯 | `019fc2e4-e3ec-7563-baed-b1c5dc5ba7e3` | `019fc2e4-e3f8-7072-91ec-d68962ea00ba` | `semantic_normalization → tour_qa` | 通过 |
| CA00-SF-04 展厅／庭院饮食边界 | `019fc2e4-e7fc-7ce0-a58f-2038aedf8b75` | `019fc2e4-e805-7ef2-9782-41311392b8ce` | `semantic_normalization → tour_qa` | 通过 |

四个用例共同满足：

- 安全规则在语义模型、普通 RAG、路线、到达和拍照建议之前处理；`semantic_normalization` 均记录 `reason=safety_rule`、`model_called=false`。
- 最终路径未进入 `llm_think`、`rag_tool` 或 `direct_rag`。
- `TourState` 与 `VisitorProfile` 均未创建或修改。
- 游客正文没有文件名、chunk、source ID、node ID、URL 或内部审计字段。
- CA00-SF-03 同一轮完整覆盖无人机全域禁飞、禁止触摸和室内展柜禁用闪光灯，没有只处理首个子意图。
- CA00-SF-04 正确区分展厅内部禁止与庭院休息区允许例外，没有扩大允许范围。

## 游客正文摘要

- CA00-SF-01：拒绝踩、爬、坐、倚靠或翻越栏杆，改为允许区域平地取景。
- CA00-SF-02：说明未经报备不得商业拍摄，只提示提前向馆方报备并确认手续。
- CA00-SF-03：同时拒绝无人机、触摸木雕和室内展柜闪光灯。
- CA00-SF-04：说明庭院休息区可以饮食，含糖饮料和食物不能带入展厅内部。

## 排除记录

线程 `019fc2e3-94f2-7cd1-8705-d8d84dbd1f4c` 因首次 PowerShell 验收脚本未显式使用 UTF-8，请求正文被发送为问号，属于测试工具错误，不计入业务验收。后续请求统一使用 UTF-8 字节正文。

## 尚未完成

- 在 LangSmith UI 中按上述 Thread ID / Run ID 复核 Trace URL 并回填。
- 继续执行 CA00-TS、VP、CTL、RP、QA、OUT、TH、MI 矩阵。
- 当前四项通过不能单独把 Gate 0 从 `conditional_pass` 提升为 `passed`。
