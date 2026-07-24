"""Measure a full Agent turn, including both LLM calls and local RAG."""

from __future__ import annotations

import json
import sys
import time

from agent_graph import chat_with_profile


def main() -> None:
    arguments = sys.argv[1:]
    runs = 2 if "--runs" not in arguments else int(arguments[arguments.index("--runs") + 1])
    question_parts = [
        argument
        for index, argument in enumerate(arguments)
        if argument != "--runs" and (index == 0 or arguments[index - 1] != "--runs")
    ]
    question = " ".join(question_parts).strip() or "陈家祠是什么？"
    for run in range(1, runs + 1):
        started = time.perf_counter()
        answer, metrics = chat_with_profile(question, thread_id=f"agent-profile-{run}")
        total = time.perf_counter() - started
        print(f"\nRun {run}/{runs} | Question: {question}")
        print(f"Total: {total:.2f}s")
        print("Node timings:")
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        print("Answer:")
        print(answer)


if __name__ == "__main__":
    main()
