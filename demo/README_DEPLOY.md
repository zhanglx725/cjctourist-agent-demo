# 祠语智游 Streamlit 比赛演示部署

本目录是比赛演示前端。它只调用项目公开入口 `chat_public_turn(user_text, thread_id)`，不复制或修改路线、画像、知识库、TourState 与导游路由。

## 本地启动

```powershell
python -m pip install -r requirements-demo.txt
streamlit run demo/streamlit_app.py
```

## Streamlit Community Cloud

1. 将代码推送到 GitHub 的比赛分支。
2. 在 Community Cloud 创建应用，选择该仓库和对应分支。
3. Main file path 填 `demo/streamlit_app.py`。
4. Community Cloud 会读取根目录 `requirements.txt`；本项目已声明 Streamlit 依赖。
5. 在 Advanced settings 的 Secrets 中填写下列名称（不要提交 `secrets.toml`）：

```toml
DEEPSEEK_API_KEY = "由部署者填写"
DEMO_MODE = "true"
DEMO_MAX_TURNS = "20"
DEMO_MAX_INPUT_CHARS = "200"
DEMO_REQUEST_TIMEOUT_SECONDS = "45"
DEMO_SHOW_TECH_PANEL = "false"
DEMO_VIDEO_URL = ""
DEMO_ACCESS_CODE = ""
CJC_READ_ONLY_ROLLOUT_MODE = "read_only_active"
CJC_READ_ONLY_ROLLOUT_CAPABILITIES = "role_narration,role_qa"
PRODUCT_ROLE_ACTIVE_ENABLED = "true"
PRODUCT_ROLE_ACTIVE_STYLES = "neutral,child,family,student_research,professional,listen_only,mixed_group,dominant_ceo,cute_junior,ancient_scholar,warm_sister,bestie_chat,buddy_guide,exploration_game,photo_guide,hostel_scholar,xiguan_young_master,cantonese_storyteller"
PRODUCT_ROLE_ACTIVE_SCENES = "route_planning,route_opening,stop_guidance,tour_qa,qa_follow_up_detail"
PRODUCT_ROLE_ROLLOUT_PERCENTAGE = "100"
PRODUCT_ROLE_KILL_SWITCH = "false"
PRODUCT_ROLE_VALIDATION_LEVEL = "strict"
PRODUCT_ROLE_FALLBACK_POLICY = "legacy"
PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED = "false"
```

Streamlit 与 Studio 必须由项目同一套配置解析器读取上述 Active 环境变量；不要在前端另建 Active 规则。本地 PowerShell 中显式设置的 rollout 变量优先于部署 Secrets，避免旧 Secrets 将点位误降为 Shadow。API Key 仍优先从 Secrets 读取，且不会进入启动审计。切勿提交真实密钥或 `secrets.toml`。

## 本地点位 + QA Active 验收启动

PowerShell 必须在启动 Streamlit 的同一窗口执行：

```powershell
$env:CJC_READ_ONLY_ROLLOUT_MODE = "read_only_active"
$env:CJC_READ_ONLY_ROLLOUT_CAPABILITIES = "role_narration,role_qa"
$env:PRODUCT_ROLE_ACTIVE_ENABLED = "true"
$env:PRODUCT_ROLE_ACTIVE_STYLES = "neutral,child,family,student_research,professional,listen_only,mixed_group,dominant_ceo,cute_junior,ancient_scholar,warm_sister,bestie_chat,buddy_guide,exploration_game,photo_guide,hostel_scholar,xiguan_young_master,cantonese_storyteller"
$env:PRODUCT_ROLE_ACTIVE_SCENES = "route_planning,route_opening,stop_guidance,tour_qa,qa_follow_up_detail"
$env:PRODUCT_ROLE_ROLLOUT_PERCENTAGE = "100"
$env:PRODUCT_ROLE_KILL_SWITCH = "false"
$env:PRODUCT_ROLE_VALIDATION_LEVEL = "strict"
$env:PRODUCT_ROLE_FALLBACK_POLICY = "legacy"
$env:PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED = "true"

& .\.venv\Scripts\python.exe -m streamlit run demo\streamlit_app.py `
  --server.address 127.0.0.1 `
  --server.port 8502
```

自然话语开关当前只允许 `child`、`ancient_scholar`、`dominant_ceo` 的 compact 点位讲解试点；正式部署默认保持 `false`，人工验收时才显式开启。配置修改后必须重启 Streamlit 并新建会话。启动日志会输出 `role_rollout_startup_audit`，其中只包含能力、场景、风格、灰度、kill switch 和自然话语开关，不包含 API Key。

## 比赛演示检查

- 新建会话，选择古风书生、30 分钟、灰塑，点击“生成我的路线”。
- 到达时点击“我到了”，随后可点击“再讲详细一点”“完成本点”。
- 确认游客端仅显示自然语言正文，不显示技术 ID、密钥、Trace 或异常堆栈。
- 演示结束后可删除 Cloud Secrets 或关闭应用；如密钥曾暴露，应立即在供应商侧撤销并重建。
