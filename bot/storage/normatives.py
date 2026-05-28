from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .backup import create_backup
from ..utils.files import atomic_write, ensure_directory


NORM_HEADERS = [
    "norm_id",
    "title",
    "description",
    "deadline",
    "is_active",
    "created_by",
    "created_at",
]

SUBMISSION_HEADERS = [
    "submission_id",
    "norm_id",
    "member_id",
    "file_type",
    "file_id",
    "comment",
    "submitted_at",
    "status",
]


@dataclass
class Norm:
    norm_id: int
    title: str
    description: str
    deadline: str
    is_active: bool
    created_by: int
    created_at: str

    def to_csv_row(self) -> dict[str, str]:
        return {
            "norm_id": str(self.norm_id),
            "title": self.title,
            "description": self.description,
            "deadline": self.deadline,
            "is_active": "true" if self.is_active else "false",
            "created_by": str(self.created_by),
            "created_at": self.created_at,
        }


@dataclass
class NormSubmission:
    submission_id: int
    norm_id: int
    member_id: int
    file_type: str
    file_id: str
    comment: str
    submitted_at: str
    status: str

    def to_csv_row(self) -> dict[str, str]:
        return {
            "submission_id": str(self.submission_id),
            "norm_id": str(self.norm_id),
            "member_id": str(self.member_id),
            "file_type": self.file_type,
            "file_id": self.file_id,
            "comment": self.comment,
            "submitted_at": self.submitted_at,
            "status": self.status,
        }


class NormsStorage:
    def __init__(self, path: Path, backups_dir: Path):
        self.path = path
        self.backups_dir = backups_dir
        ensure_directory(self.path.parent)

    def list_norms(self) -> list[Norm]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            return [self._row_to_norm(row) for row in reader]

    def save_norms(self, norms: Iterable[Norm]) -> None:
        create_backup(self.path, self.backups_dir)
        rows = [norm.to_csv_row() for norm in norms]
        atomic_write(self.path, self._render(rows, NORM_HEADERS), newline="")

    def next_id(self) -> int:
        return max((norm.norm_id for norm in self.list_norms()), default=0) + 1

    def _row_to_norm(self, row: dict[str, str]) -> Norm:
        return Norm(
            norm_id=int(row["norm_id"]),
            title=row["title"].strip(),
            description=row["description"].strip(),
            deadline=row.get("deadline", "").strip(),
            is_active=row["is_active"].strip().lower() == "true",
            created_by=int(row["created_by"]),
            created_at=row["created_at"].strip(),
        )

    def _render(self, rows: list[dict[str, str]], headers: list[str]) -> str:
        import io

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()


class NormSubmissionsStorage:
    def __init__(self, path: Path, backups_dir: Path):
        self.path = path
        self.backups_dir = backups_dir
        ensure_directory(self.path.parent)

    def list_submissions(self) -> list[NormSubmission]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            return [self._row_to_submission(row) for row in reader]

    def add(self, submission: NormSubmission) -> None:
        submissions = self.list_submissions()
        submissions.append(submission)
        submissions.sort(key=lambda item: item.submission_id)
        self._save(submissions)

    def next_id(self) -> int:
        return max((item.submission_id for item in self.list_submissions()), default=0) + 1

    def _save(self, submissions: Iterable[NormSubmission]) -> None:
        create_backup(self.path, self.backups_dir)
        rows = [submission.to_csv_row() for submission in submissions]
        atomic_write(self.path, self._render(rows), newline="")

    def _row_to_submission(self, row: dict[str, str]) -> NormSubmission:
        return NormSubmission(
            submission_id=int(row["submission_id"]),
            norm_id=int(row["norm_id"]),
            member_id=int(row["member_id"]),
            file_type=row["file_type"].strip(),
            file_id=row["file_id"].strip(),
            comment=row.get("comment", "").strip(),
            submitted_at=row["submitted_at"].strip(),
            status=row["status"].strip(),
        )

    def _render(self, rows: list[dict[str, str]]) -> str:
        import io

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=SUBMISSION_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()
