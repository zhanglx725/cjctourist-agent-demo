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
CJC_READ_ONLY_ROLLOUT_CAPABILITIES = "role_narration,presentation_content_plan"
ROLE_ACTIVE_ENABLED = "true"
ROLE_ACTIVE_STYLES = "neutral,child,ancient_scholar"
ROLE_ACTIVE_SCENES = "route_planning,route_opening,stop_guidance"
```

Streamlit 与 Studio 必须由项目同一套配置解析器读取上述 Active 环境变量；不要在前端另建 Active 规则。切勿提交真实密钥或 `secrets.toml`。

## 比赛演示检查

- 新建会话，选择古风书生、30 分钟、灰塑，点击“生成我的路线”。
- 到达时点击“我到了”，随后可点击“再讲详细一点”“完成本点”。
- 确认游客端仅显示自然语言正文，不显示技术 ID、密钥、Trace 或异常堆栈。
- 演示结束后可删除 Cloud Secrets 或关闭应用；如密钥曾暴露，应立即在供应商侧撤销并重建。
