from __future__ import annotations

import re

from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build

PAID_EXPENSE_COLUMNS = "A:N"
REQUEST_ID_COLUMN = "N:N"


def _build_credentials():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if settings.GOOGLE_SERVICE_ACCOUNT_INFO:
        return service_account.Credentials.from_service_account_info(settings.GOOGLE_SERVICE_ACCOUNT_INFO, scopes=scopes)
    if settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        return service_account.Credentials.from_service_account_file(settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes)
    raise RuntimeError("Google 서비스 계정 설정이 없습니다.")


class GoogleSheetsService:
    def __init__(self):
        if not settings.GOOGLE_SHEET_ID:
            raise RuntimeError("GOOGLE_SHEET_ID 설정이 없습니다.")
        self.service = build("sheets", "v4", credentials=_build_credentials(), cache_discovery=False)
        self.sheet_name = settings.GOOGLE_SHEET_NAME

    def _range(self, columns: str = PAID_EXPENSE_COLUMNS, *, row: int | None = None) -> str:
        cell_range = columns
        if row is not None:
            end_column = columns.split(":")[-1]
            cell_range = f"A{row}:{end_column}{row}"
        if not self.sheet_name:
            return cell_range
        escaped_name = self.sheet_name.replace("'", "''")
        return f"'{escaped_name}'!{cell_range}"

    def _find_existing_row(self, request_id: int) -> str:
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=settings.GOOGLE_SHEET_ID, range=self._range(REQUEST_ID_COLUMN))
            .execute()
        )
        rows = result.get("values", [])
        for index, row in enumerate(rows, start=1):
            if row and row[0] == str(request_id):
                return f"row:{index}"
        return ""

    def _paid_expense_values(self, expense) -> list[list[str]]:
        return [[
            expense.expense_date.strftime("%m/%d/%Y"),
            expense.category.name,
            str(expense.amount_krw),
            "",
            "",
            expense.comment,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            str(expense.pk),
        ]]

    def _row_number_from_ref(self, row_ref: str) -> int | None:
        match = re.fullmatch(r"row:(\d+)", row_ref)
        if not match:
            return None
        return int(match.group(1))

    def _update_paid_expense_row(self, row_number: int, values: list[list[str]]) -> str:
        self.service.spreadsheets().values().update(
            spreadsheetId=settings.GOOGLE_SHEET_ID,
            range=self._range(PAID_EXPENSE_COLUMNS, row=row_number),
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()
        return f"row:{row_number}"

    def append_paid_expense(self, expense, *, force: bool = False) -> str:
        values = self._paid_expense_values(expense)

        if expense.google_sheet_row_ref and not force:
            return expense.google_sheet_row_ref
        if expense.google_sheet_row_ref and force:
            row_number = self._row_number_from_ref(expense.google_sheet_row_ref)
            if row_number:
                return self._update_paid_expense_row(row_number, values)

        existing = self._find_existing_row(expense.pk)
        if existing:
            row_number = self._row_number_from_ref(existing)
            if row_number:
                return self._update_paid_expense_row(row_number, values)
            return existing

        response = (
            self.service.spreadsheets()
            .values()
            .append(
                spreadsheetId=settings.GOOGLE_SHEET_ID,
                range=self._range(PAID_EXPENSE_COLUMNS),
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": values},
            )
            .execute()
        )
        updated_range = response.get("updates", {}).get("updatedRange", "")
        match = re.search(r"!(?:[A-Z]+)(\d+):", updated_range)
        if match:
            return f"row:{match.group(1)}"
        return updated_range or "appended"
