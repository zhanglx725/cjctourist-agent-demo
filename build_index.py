"""Build the local persistent Chen Clan Academy snapshot index."""

from rag_retrieval import ChenClanHybridRetriever


if __name__ == "__main__":
    retriever = ChenClanHybridRetriever()
    print(f"已建立 {retriever.build()} 个知识块的本地索引：{retriever.index_dir}")
