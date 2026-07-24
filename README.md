# 陈家祠金牌导游 Agent

面向陈家祠静态知识快照的导游 Agent 原型。系统以本地 RAG 为事实边界，支持陈家祠历史、建筑格局、装饰工艺与单件装饰题材的可追溯讲解。

## 当前 RAG 链路

```text
Markdown 知识库 → 结构化分块 → BGE 稠密检索 + BM25 → RRF 融合
→ 条件 reranker → 带来源标注的导游回答
```

已实现的性能策略：装饰专名精确匹配快路、复杂问题条件重排、4 条候选池，以及明确知识问题的直接 RAG 路由。

## 本地运行

在已激活的虚拟环境中安装依赖并建立索引：

```cmd
pip install -r requirements.txt
python build_index.py
```

运行质量与性能检查：

```cmd
python -m unittest -v test_rag_ingestion.py test_rag_retrieval.py test_rag_evaluation.py test_agent_rag.py test_agent_profile.py
python rag_evaluation.py
python rag_benchmark.py
```

配置 `.env` 中的 `DEEPSEEK_API_KEY` 后，可测量完整 Agent 链路：

```cmd
python agent_profile.py "陈家祠是什么？"
```

## Git 与 Gitee

敏感配置只保存在本地 `.env`，不要提交。提交代码前运行：

```cmd
git status
git add .
git commit -m "docs: add project README"
git push
```

远端仓库：<https://gitee.com/balegezhua/cjctourist_agent>
