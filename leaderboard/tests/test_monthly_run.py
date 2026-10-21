import importlib.util
from pathlib import Path

from leaderboard.store import Store

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("monthly_run", REPO / "scripts" / "monthly_run.py")
monthly_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(monthly_run)

from conftest import TASKS_DIR  # noqa: E402


def test_monthly_run_batch_ingests_official_rows(tmp_path):
    config = {
        "label": "test-batch",
        "board": "official",
        "preliminary": True,
        "seeds": [42],
        "tasks": [{"dir": "sprint/sprint-data-001", "params": {"region": "north", "top_n": 3}}],
        "configs": [{"agent_name": "scripted-test", "model": "scripted"}],
    }
    report = monthly_run.run_batch(
        config, db_path=tmp_path / "board.db", tasks_root=TASKS_DIR, workdir=tmp_path / "work"
    )
    assert report["preliminary"] is True
    assert len(report["results"]) == 1
    row = report["results"][0]
    assert row["board"] if "board" in row else True
    assert row["n_tasks"] == 1 and row["n_runs"] == 1 and row["mean_score"] > 95
    store = Store(tmp_path / "board.db")
    official = store.latest_scores(board="official")
    assert len(official) == 1 and official[0]["id"] == row["score_id"]
    markdown = monthly_run.render_markdown(report)
    assert "PRELIMINARY" in markdown and "scripted-test" in markdown
