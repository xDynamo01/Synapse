from __future__ import annotations

import csv
import json
from pathlib import Path

from synapse.security.guards import validate_file_path


TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".jsx", ".tsx", ".java",
    ".html", ".css", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sh",
    ".bat", ".ps1", ".c", ".cpp", ".h", ".rs", ".go", ".rb", ".php", ".sql",
}


class FileAnalyzer:
    def __init__(self, max_bytes: int, max_chars: int):
        self.max_bytes = max_bytes
        self.max_chars = max_chars

    def load(self, path_text: str) -> dict:
        path = validate_file_path(path_text)
        size = path.stat().st_size
        if size > self.max_bytes:
            raise ValueError(f"File too large ({size} bytes). Limit is {self.max_bytes} bytes.")
        ext = path.suffix.lower()
        if ext == ".pdf":
            text = self._read_pdf(path)
        elif ext == ".docx":
            text = self._read_docx(path)
        elif ext == ".json":
            text = json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2, ensure_ascii=False)
        elif ext == ".csv":
            text = self._read_csv(path)
        elif ext in TEXT_EXTENSIONS or not ext:
            text = path.read_text(encoding="utf-8", errors="replace")
        else:
            raise ValueError(f"Unsupported file type: {ext}")
        truncated = len(text) > self.max_chars
        return {
            "name": path.name,
            "path": str(path),
            "extension": ext,
            "size_bytes": size,
            "content": text[: self.max_chars],
            "truncated": truncated,
            "chunks": self.chunk_text(text[: self.max_chars]),
        }

    def _read_pdf(self, path: Path) -> str:
        import pypdf

        reader = pypdf.PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()

    def _read_docx(self, path: Path) -> str:
        from docx import Document

        doc = Document(str(path))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()

    def _read_csv(self, path: Path) -> str:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            rows = list(csv.reader(handle))
        return "\n".join(",".join(row) for row in rows[:500])

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 4000, overlap: int = 300) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start : start + chunk_size])
            start += max(1, chunk_size - overlap)
        return chunks
