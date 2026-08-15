# 产品功能状态矩阵

## 使用规则

本文件是比赛资料冻结后的产品开发状态表，与 `end.md` 配套使用。

状态枚举：

```text
planned      已规划，尚未实现
implemented  已实现，尚未完成完整验证
shadow       已接入只读候选或审计，不接管游客正文
active       已允许接管游客正文，但仍可能处于灰度
verified     自动化与规定的人工验收均完成
blocked      存在已记录的外部或技术阻塞
```

状态只能依据代码、自动测试和已保存的人工验收证据更新；不得用计划或推测替代完成证据。

## 当前产品基线

```text
baseline_commit: 92cb458
regression_baseline: 1170/1170 passed_by_operator
baseline_date: 2026-08-15
development_mode: full_product_functionality
competition_materials: frozen
```

## 功能矩阵

| 能力 | 状态 | 当前边界 | 下一验收门 |
|---|---|---|---|
| 审核知识与混合检索 | implemented | 单场馆本地知识与对象级证据 | 知识版本化和第二场馆验证 |
| 语义归一与意图仲裁 | implemented | 已进入确定性 Graph 主链 | 产品场景扩展回归 |
| VisitorProfile | implemented | 线程级语言、时长、兴趣、深度和角色偏好 | 隐私、导出和删除策略 |
| 审核路线规划 | implemented | 陈家祠审核路线 | 产品配置和多场馆数据模型 |
| TourState | implemented | 到达、完成、跳过、下一站和结束 | 定位候选与地图一致性 |
| 受控重规划 | implemented | Proposal、确认和 freshness | 角色化说明 Active |
| 点位确定性讲解 | verified | E5、审核事实和 Coverage | 长讲解分轮输出 |
| 18 风格点位讲解 | active | 有限 Active；失败回退旧链 | 产品策略替代比赛白名单 |
| 角色化路线规划 | active | 现有白名单与配置控制 | 产品策略和全角色验证 |
| 角色化路线开场 | active | 现有白名单与配置控制 | 产品策略和全角色验证 |
| 角色化问答 | shadow | 候选、校验和审计；不接管正文 | QA 专用校验和 Active commit |
| 角色化引路 | shadow | 只读角色候选 | 路径事实专属校验和 Active commit |
| 角色化结束语 | shadow | 只读角色候选 | Coverage 专属校验和 Active commit |
| 角色化重规划说明 | shadow | Proposal 审计，不改路线 | freshness 与 Active commit |
| 全流程角色连续性 | implemented | 核心角色自动化覆盖；fallback 保留角色 | 全 18 风格和真实 Thread 人工验收 |
| 长讲解预算自适应 | planned | 超预算时安全回退 | full/compact/split/fallback 矩阵 |
| 语音导游 | planned | 尚未接入 | TTS、ASR、中断和续播测试 |
| 二维码/NFC 定位 | planned | 尚未接入 | 到达候选和 TourState 校验 |
| 可视化地图 | planned | 审核空间图已存在 | 地图状态与路线同步 |
| AI 识物镜 | planned | 对象级审核注册表已存在 | 识别候选、置信度和确认闭环 |
| 历史场景叠影 | planned | 尚未接入 | 依据等级与复原标识 |
| 数字游览护照 | planned | TourState、Coverage 和称号可复用 | 真实行为绑定和隐私验收 |
| 文化关系图 | planned | 可复用审核实体关系 | 只展示审核关系 |
| AI 摄影导演 | planned | 已有审核拍照建议 | 相机、站位和安全验证 |
| 家庭协作与研学 | planned | 已有儿童和研学表达基础 | 多人状态与未成年人隐私 |
| 场馆 CMS | planned | 当前由仓库文件维护 | 草稿、审核、发布和回滚 |
| 多场馆/多租户 | planned | 当前仅陈家祠 | 第二场馆、租户隔离和快速接入 |
| 商业化与计费 | planned | 尚未实现 | 套餐、成本归集和真实试点 |
| 无障碍 | planned | 部分语言和表达策略 | WCAG、轮椅、听障和视障旅程 |
| 多语言产品化 | implemented | 中英文部分能力 | 粤语、术语表和跨语言一致性 |
| 生产级部署 | planned | 本地 LangGraph/Streamlit 开发环境 | CI/CD、监控、降级和灾备 |

## 阶段状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| 阶段 0：固定产品开发基线 | implemented | 冻结提交存在；路线图、状态矩阵和标签待最终固化 |
| 阶段 1：产品级能力配置与场景校验重构 | planned | 下一开发阶段 |
| 阶段 2：长讲解预算自适应与分轮输出 | planned | 依赖阶段 1 场景合同 |
| 阶段 3：角色化问答 Active | planned | 依赖 QA 专用校验器 |
| 阶段 4：引路、结束语与重规划说明 Active | planned | 依赖产品策略和场景校验器 |
| 阶段 5：角色连续性与语音 | planned | 依赖完整角色链 |
| 阶段 6：定位与地图 | planned | 可在阶段 5 后并行拆分 |
| 阶段 7：AI 识物镜 | planned | 依赖对象注册表与图片资产治理 |
| 阶段 8：创意游客体验 | planned | 依赖定位、Coverage 和产品前端 |
| 阶段 9：场馆 CMS | planned | 进入平台化开发 |
| 阶段 10：多场馆/多租户 | planned | 依赖 CMS 数据模型 |
| 阶段 11：商业化与计费 | planned | 依赖多租户和真实试点 |
| 阶段 12：无障碍、多语言与安全 | planned | 各阶段持续建设，最终统一验收 |
| 阶段 13：生产部署与规模验证 | planned | 产品发布门 |

## 更新记录

- 2026-08-15：以 `92cb458` 和 `1170/1170` 回归结果建立产品状态矩阵。
