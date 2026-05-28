from __future__ import annotations

from datetime import datetime

import pytz

from ..storage.normatives import Norm, NormSubmission, NormsStorage, NormSubmissionsStorage


class NormativesService:
    def __init__(self, norms: NormsStorage, submissions: NormSubmissionsStorage, timezone: str):
        self.norms = norms
        self.submissions = submissions
        self.timezone = timezone

    def update_settings(self, *, timezone: str | None = None) -> None:
        if timezone:
            self.timezone = timezone

    def list_active_norms(self) -> list[Norm]:
        return [norm for norm in self.norms.list_norms() if norm.is_active]

    def list_norms(self) -> list[Norm]:
        return self.norms.list_norms()

    def get_norm(self, norm_id: int) -> Norm | None:
        return next((norm for norm in self.norms.list_norms() if norm.norm_id == norm_id), None)

    def add_norm(self, *, title: str, description: str, deadline: str, created_by: int) -> Norm:
        norm = Norm(
            norm_id=self.norms.next_id(),
            title=title.strip(),
            description=description.strip(),
            deadline=deadline.strip(),
            is_active=True,
            created_by=created_by,
            created_at=self._now(),
        )
        norms = self.norms.list_norms()
        norms.append(norm)
        self.norms.save_norms(norms)
        return norm

    def delete_norm(self, norm_id: int) -> bool:
        norms = self.norms.list_norms()
        updated = [norm for norm in norms if norm.norm_id != norm_id]
        if len(updated) == len(norms):
            return False
        self.norms.save_norms(updated)
        return True

    def submit(
        self,
        *,
        norm_id: int,
        member_id: int,
        file_type: str,
        file_id: str,
        comment: str,
    ) -> NormSubmission:
        submission = NormSubmission(
            submission_id=self.submissions.next_id(),
            norm_id=norm_id,
            member_id=member_id,
            file_type=file_type,
            file_id=file_id,
            comment=comment.strip(),
            submitted_at=self._now(),
            status="new",
        )
        self.submissions.add(submission)
        return submission

    def list_submissions(self, limit: int = 20) -> list[NormSubmission]:
        items = self.submissions.list_submissions()
        items.sort(key=lambda item: item.submission_id, reverse=True)
        return items[:limit]

    def _now(self) -> str:
        return datetime.now(pytz.timezone(self.timezone)).isoformat(timespec="minutes")
