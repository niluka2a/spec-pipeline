"""Reusable file system service for pipeline-generated artifacts."""

from pathlib import Path

from pipeline.audit import AuditLogger


class FileService:
    """Handles writing files and logging generation metadata."""

    def __init__(self, audit_logger: AuditLogger) -> None:
        self._audit_logger = audit_logger

    def write_file(
        self,
        path: str,
        content: str,
        file_type: str = "implementation",
        display_icon: str = "📄",
    ) -> None:
        """Write a single file to disk and record it in the audit log."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        self._audit_logger.log_generated_file(
            str(file_path),
            file_type,
            len(content),
        )

        print(
            f"  {display_icon}  Written: {file_path} "
            f"({len(content)} chars)"
        )

    def write_files(
        self,
        files: dict[str, str],
        file_type: str = "implementation",
        display_icon: str = "📄",
    ) -> None:
        """Write a collection of files to disk."""
        for path, content in files.items():
            self.write_file(
                path,
                content,
                file_type=file_type,
                display_icon=display_icon,
            )
