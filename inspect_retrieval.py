"""Print evidence returned by the built local hybrid index for manual QA."""

from rag_retrieval import ChenClanHybridRetriever


QUESTIONS = [
    "陈家祠的建筑布局有什么特点？",
    "百鸟朝凤是什么装饰？",
    "梁山聚义讲的是什么？",
    "灰塑是什么？",
    "陈家祠什么时候建成？",
]


if __name__ == "__main__":
    retriever = ChenClanHybridRetriever()
    print(f"已加载 {retriever.load()} 个知识块。")
    for question in QUESTIONS:
        print(f"\n问题：{question}")
        for rank, evidence in enumerate(retriever.search(question, limit=3), start=1):
            print(
                f"  {rank}. {evidence.document} / {' > '.join(evidence.title_path)}"
                f" | score={evidence.score:.4f} | {','.join(evidence.source_ids)}"
                f" | {','.join(evidence.retrieval_methods)}"
            )
            print(f"     {evidence.content[:160].replace(chr(10), ' ')}")
