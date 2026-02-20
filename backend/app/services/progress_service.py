"""In-memory document processing progress tracker."""
from typing import Dict, Optional


class ProgressTracker:
    """Track document processing progress in memory."""

    _progress: Dict[str, Dict] = {}

    STEPS = [
        {"key": "reading", "label": "Lecture du fichier", "pct": 10},
        {"key": "extracting_text", "label": "Extraction du texte", "pct": 30},
        {"key": "extracting_images", "label": "Extraction des images", "pct": 50},
        {"key": "chunking", "label": "Découpage en chunks", "pct": 65},
        {"key": "anonymizing", "label": "Anonymisation", "pct": 75},
        {"key": "indexing", "label": "Indexation vectorielle", "pct": 90},
        {"key": "completed", "label": "Terminé", "pct": 100},
        {"key": "failed", "label": "Échec", "pct": -1},
    ]

    @classmethod
    def start(cls, document_id: str, filename: str) -> None:
        cls._progress[document_id] = {
            "document_id": document_id,
            "filename": filename,
            "step": "reading",
            "step_label": "Lecture du fichier",
            "progress": 10,
        }

    @classmethod
    def update(cls, document_id: str, step_key: str) -> None:
        step = next((s for s in cls.STEPS if s["key"] == step_key), None)
        if not step:
            return
        if document_id in cls._progress:
            cls._progress[document_id].update({
                "step": step["key"],
                "step_label": step["label"],
                "progress": step["pct"],
            })

    @classmethod
    def fail(cls, document_id: str, error: str) -> None:
        if document_id in cls._progress:
            cls._progress[document_id].update({
                "step": "failed",
                "step_label": f"Échec: {error[:120]}",
                "progress": -1,
            })

    @classmethod
    def get(cls, document_id: str) -> Optional[Dict]:
        return cls._progress.get(document_id)

    @classmethod
    def get_for_project(cls, project_docs: list[str]) -> list[Dict]:
        return [cls._progress[d] for d in project_docs if d in cls._progress]

    @classmethod
    def remove(cls, document_id: str) -> None:
        cls._progress.pop(document_id, None)
