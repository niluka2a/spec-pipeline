"""
Audit Logger
Captures every pipeline event: spec versions, AI prompts/responses,
approvals, generated outputs, and validation results.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, run_id: str | None = None, log_dir: str = "audit_logs"):
        self.run_id = run_id or str(uuid.uuid4())[:8]
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.log_path = self.log_dir / f"run_{self.run_id}.json"
        self.entries: list[dict[str, Any]] = []
        self._write({"event": "pipeline_started", "run_id": self.run_id})

    def _write(self, data: dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            **data,
        }
        self.entries.append(entry)
        self.log_path.write_text(json.dumps(self.entries, indent=2), encoding="utf-8")

    def log_spec(self, spec: dict[str, Any], path: str) -> None:
        self._write({
            "event": "spec_loaded",
            "spec_path": path,
            "spec_version": spec.get("spec_version", "unknown"),
            "feature_id": spec.get("feature_id", "unknown"),
            "feature_name": spec.get("feature_name", "unknown"),
            "acceptance_criteria_count": len(spec.get("acceptance_criteria", [])),
        })

    def log_ai_interaction(
        self,
        stage: str,
        prompt: str,
        response: str,
        model: str,
    ) -> None:
        self._write({
            "event": "ai_interaction",
            "stage": stage,
            "model": model,
            "prompt_length": len(prompt),
            "response_length": len(response),
            "prompt": prompt,
            "response": response,
        })

    def log_approval(
        self,
        stage: str,
        approved: bool,
        approver: str = "human-cli",
    ) -> None:
        self._write({
            "event": "approval",
            "stage": stage,
            "approved": approved,
            "approver": approver,
        })

    def log_generated_file(
        self,
        file_path: str,
        file_type: str,
        content_length: int,
    ) -> None:
        self._write({
            "event": "file_generated",
            "file_path": file_path,
            "file_type": file_type,
            "content_length": content_length,
        })

    def log_quality_gate(self, gate_name: str, passed: bool, output: str) -> None:
        self._write({
            "event": "quality_gate",
            "gate_name": gate_name,
            "passed": passed,
            "output": output[:2000],  # truncate very long outputs
        })

    def log_pipeline_result(self, success: bool, summary: str) -> None:
        self._write({
            "event": "pipeline_completed",
            "success": success,
            "summary": summary,
        })
        print(f"\n[audit] Full run log saved to: {self.log_path}")
