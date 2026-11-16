"""Evaluation harness: the task set measures the four guarantees."""
from pathlib import Path

from governed_shared_memory.evaluation import run_evaluation

TASKS = Path(__file__).resolve().parent.parent / "data" / "eval_tasks.json"


def test_task_file_loads():
    report = run_evaluation(TASKS)
    assert len(report.task_results) == 8  # 1 + 1 + 1 + 3 + 1 + 1 questions
    assert report.planted_conflicts == 2
    assert report.leak_attempts == 1


def test_recall_is_perfect_on_handwritten_tasks():
    report = run_evaluation(TASKS)
    assert report.recall_at_k == 1.0


def test_all_planted_conflicts_flagged():
    report = run_evaluation(TASKS)
    assert report.contradiction_recall == 1.0


def test_leak_attempt_blocked():
    report = run_evaluation(TASKS)
    assert report.leak_blocked_rate == 1.0


def test_no_stale_record_leaks_into_results():
    report = run_evaluation(TASKS)
    assert report.stale_leak_rate == 0.0


def test_summary_keys():
    report = run_evaluation(TASKS)
    summary = report.summary()
    for key in ("questions", "recall_at_k", "contradiction_recall",
                "leak_blocked_rate", "stale_leak_rate"):
        assert key in summary
