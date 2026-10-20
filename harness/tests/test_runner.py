import json

from longrun.cli import main
from longrun.pricing import actual_cost, estimate_cost_range, load_pricing
from longrun.redact import redact_text, redact_transcript_file
from longrun.signing import build_submission, verify_submission

from conftest import TASKS_DIR


def test_pricing_estimate_and_actual():
    pricing = load_pricing()
    estimate = estimate_cost_range(model="anthropic/claude-opus-5.5", step_budget=100, pricing=pricing)
    # 400k tokens at 3:1 split: 300k * $4/M + 100k * $20/M = $3.20 at full budget.
    assert estimate == {"model": "anthropic/claude-opus-5.5", "low_usd": 0.8, "high_usd": 3.2}
    assert actual_cost(model="anthropic/claude-opus-5.5", input_tokens=300_000, output_tokens=100_000, pricing=pricing) == 3.2
    assert estimate_cost_range(model="unknown/model", step_budget=10, pricing=pricing) is None
    override = estimate_cost_range(model="unknown/model", step_budget=10, pricing=pricing, price_override=(1.0, 2.0))
    assert override is not None and override["high_usd"] > 0


def test_redaction_catches_key_shapes():
    text = (
        "key1 sk-abcdef0123456789abcdef and Bearer abcdef0123456789abcd plus "
        "AIzaSyA123456789012345678901234567 and ghp_abcdefghij0123456789abcd"
    )
    redacted, count = redact_text(text)
    assert count >= 4
    assert "sk-abcdef" not in redacted and "Bearer abcdef" not in redacted
    block = "-----BEGIN PRIVATE KEY-----\nMIIabc\n-----END PRIVATE KEY-----"
    redacted2, count2 = redact_text(block)
    assert count2 == 1 and "MIIabc" not in redacted2


def test_redact_transcript_file(tmp_path):
    source = tmp_path / "t.jsonl"
    source.write_text(json.dumps({"type": "note", "text": "leaked sk-abcdef0123456789abcdef here"}) + "\n", encoding="utf-8")
    dest = tmp_path / "t.redacted.jsonl"
    manifest = redact_transcript_file(source, dest)
    assert manifest["redactions"] == 1
    assert "sk-abcdef" not in dest.read_text(encoding="utf-8")


def _submission(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"type": "run_start"}\n', encoding="utf-8")
    run_record = {
        "run_id": "r1",
        "agent": {"name": "a", "model": "m", "profile": "standard"},
        "task_id": "sprint-data-001",
        "task_set": "0.1.0",
        "seed": 42,
        "totals": {"steps": 3},
        "end_reason": "deliverable",
    }
    score = {"tier": "checks", "total": 98.5, "criteria": {"correctness": {"score": 40}}, "checks": [{"id": "c", "passed": True, "score": 1.0}]}
    return build_submission(run_record=run_record, transcript_path=transcript, score=score)


def test_signing_roundtrip_and_tamper_detection(tmp_path):
    submission = _submission(tmp_path)
    assert verify_submission(submission) is True
    submission["score_claim"]["total"] = 100.0
    assert verify_submission(submission) is False


def test_signing_hmac_when_key_present(tmp_path, monkeypatch):
    monkeypatch.setenv("LONGRUN_HARNESS_KEY", "test-harness-key")
    submission = _submission(tmp_path)
    assert submission["signature"]["alg"] == "hmac-sha256"
    assert verify_submission(submission) is True


def test_cli_run_fails_before_step_one_without_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    code = main(["run", str(TASKS_DIR / "sprint-data-001"), "--model", "anthropic/claude-opus-5.5", "--out", str(tmp_path / "out")])
    assert code == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_cli_redact_command(tmp_path, capsys):
    source = tmp_path / "t.jsonl"
    source.write_text(json.dumps({"type": "note", "text": "xai-abcdef0123456789abcdef"}) + "\n", encoding="utf-8")
    dest = tmp_path / "out.jsonl"
    assert main(["redact", str(source), "--out", str(dest)]) == 0
    assert "[REDACTED]" in dest.read_text(encoding="utf-8")
