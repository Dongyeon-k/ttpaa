from __future__ import annotations

import io
import mimetypes
from pathlib import Path

from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


def _build_credentials():
    scopes = ["https://www.googleapis.com/auth/drive.file"]
    if settings.GOOGLE_SERVICE_ACCOUNT_INFO:
        return service_account.Credentials.from_service_account_info(settings.GOOGLE_SERVICE_ACCOUNT_INFO, scopes=scopes)
    if settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        return service_account.Credentials.from_service_account_file(settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes)
    raise RuntimeError("Google 서비스 계정 설정이 없습니다.")


class GoogleDriveService:
    def __init__(self):
        self.service = build("drive", "v3", credentials=_build_credentials(), cache_discovery=False)

    def upload_expense_attachment(self, expense):
        if expense.google_drive_file_id and expense.google_drive_file_url:
            return {"file_id": expense.google_drive_file_id, "file_url": expense.google_drive_file_url}

        attachment = expense.primary_attachment
        if not attachment:
            return {"file_id": "", "file_url": ""}

        file_name = f"expense-{expense.pk}-{Path(attachment.original_filename).name}"
        content_type = attachment.mime_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream"

        with attachment.file.open("rb") as fp:
            media = MediaIoBaseUpload(io.BytesIO(fp.read()), mimetype=content_type, resumable=False)

        file_metadata = {"name": file_name}
        if settings.GOOGLE_DRIVE_FOLDER_ID:
            file_metadata["parents"] = [settings.GOOGLE_DRIVE_FOLDER_ID]

        created = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
            supportsAllDrives=True,
        ).execute()
        return {"file_id": created["id"], "file_url": created.get("webViewLink", "")}
