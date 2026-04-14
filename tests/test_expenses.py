from datetime import date
from unittest.mock import patch

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.expenses.models import ExpenseCategory, ExpenseRequest
from apps.expenses.services import sync_paid_request


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ADMIN_EMAILS=["admin@example.com"],
)
class ExpenseFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin",
            password="pass12345",
            role="admin",
            first_name="관리자",
            email="admin@example.com",
        )
        self.member = User.objects.create_user(
            username="member",
            password="pass12345",
            role="member",
            first_name="구성원",
            email="member@example.com",
        )
        self.category = ExpenseCategory.objects.create(name="행사비", sort_order=10)

    def test_member_can_submit_reimbursement(self):
        self.client.login(username="member", password="pass12345")
        upload = SimpleUploadedFile("receipt.jpg", b"binarydata", content_type="image/jpeg")
        response = self.client.post(
            reverse("expense-create"),
            {
                "expense_date": "2026-04-10",
                "category": self.category.pk,
                "amount_krw": 15000,
                "comment": "회의 간식비",
                "attachment": upload,
            },
        )
        self.assertRedirects(response, reverse("expense-my-list"))
        expense = ExpenseRequest.objects.get()
        self.assertEqual(expense.current_status, ExpenseRequest.STATUS_SUBMITTED)
        self.assertEqual(expense.attachments.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_admin_can_approve_request(self):
        expense = ExpenseRequest.objects.create(
            requester=self.member,
            expense_date=date(2026, 4, 10),
            category=self.category,
            amount_krw=20000,
        )
        self.client.login(username="admin", password="pass12345")
        self.client.post(reverse("expense-transition", args=[expense.pk, "under_review"]), {"note": "검토 시작"})
        response = self.client.post(reverse("expense-transition", args=[expense.pk, "approved"]), {"note": "승인"})
        expense.refresh_from_db()
        self.assertRedirects(response, reverse("expense-admin-detail", args=[expense.pk]))
        self.assertEqual(expense.current_status, ExpenseRequest.STATUS_APPROVED)
        self.assertEqual(expense.admin_note, "승인")

    def test_admin_can_reject_request(self):
        expense = ExpenseRequest.objects.create(
            requester=self.member,
            expense_date=date(2026, 4, 10),
            category=self.category,
            amount_krw=12000,
            current_status=ExpenseRequest.STATUS_UNDER_REVIEW,
        )
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("expense-transition", args=[expense.pk, "rejected"]),
            {"rejection_reason": "증빙 부족", "note": "재제출 필요"},
        )
        expense.refresh_from_db()
        self.assertRedirects(response, reverse("expense-admin-detail", args=[expense.pk]))
        self.assertEqual(expense.current_status, ExpenseRequest.STATUS_REJECTED)
        self.assertEqual(expense.rejection_reason, "증빙 부족")

    @patch("apps.expenses.services.GoogleSheetsService")
    @patch("apps.expenses.services.GoogleDriveService")
    def test_mark_paid_triggers_google_sync(self, drive_cls, sheets_cls):
        drive_cls.return_value.upload_expense_attachment.return_value = {"file_id": "file-1", "file_url": "https://drive.test/file-1"}
        sheets_cls.return_value.append_paid_expense.return_value = "row:5"
        expense = ExpenseRequest.objects.create(
            requester=self.member,
            expense_date=date(2026, 4, 10),
            category=self.category,
            amount_krw=33000,
            current_status=ExpenseRequest.STATUS_APPROVED,
        )
        expense.attachments.create(
            file=SimpleUploadedFile("receipt.jpg", b"binarydata", content_type="image/jpeg"),
            original_filename="receipt.jpg",
            mime_type="image/jpeg",
            file_size=10,
        )
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("expense-transition", args=[expense.pk, "paid"]),
            {"payment_date": "2026-04-11", "payment_memo": "계좌이체"},
        )
        expense.refresh_from_db()
        self.assertRedirects(response, reverse("expense-admin-detail", args=[expense.pk]))
        self.assertEqual(expense.current_status, ExpenseRequest.STATUS_PAID)
        self.assertEqual(expense.sync_state, ExpenseRequest.SYNC_SUCCESS)
        self.assertEqual(expense.google_sheet_row_ref, "row:5")

    @patch("apps.expenses.services.GoogleSheetsService")
    @patch("apps.expenses.services.GoogleDriveService")
    def test_duplicate_sync_is_prevented(self, drive_cls, sheets_cls):
        drive_cls.return_value.upload_expense_attachment.return_value = {"file_id": "file-2", "file_url": "https://drive.test/file-2"}
        sheets_service = sheets_cls.return_value
        sheets_service.append_paid_expense.return_value = "row:8"
        expense = ExpenseRequest.objects.create(
            requester=self.member,
            expense_date=date(2026, 4, 10),
            category=self.category,
            amount_krw=33000,
            current_status=ExpenseRequest.STATUS_PAID,
            payment_date=date(2026, 4, 11),
            sync_state=ExpenseRequest.SYNC_PENDING,
        )
        expense.attachments.create(
            file=SimpleUploadedFile("receipt.jpg", b"binarydata", content_type="image/jpeg"),
            original_filename="receipt.jpg",
            mime_type="image/jpeg",
            file_size=10,
        )

        sync_paid_request(expense)
        expense.refresh_from_db()
        self.assertEqual(expense.sync_state, ExpenseRequest.SYNC_SUCCESS)
        sync_paid_request(expense)
        self.assertEqual(sheets_service.append_paid_expense.call_count, 1)

    @patch("services.google_sheets.service_account.Credentials.from_service_account_info")
    @patch("services.google_sheets.build")
    @override_settings(
        GOOGLE_SERVICE_ACCOUNT_INFO={"client_email": "test@example.com", "token_uri": "https://oauth2.googleapis.com/token"},
        GOOGLE_SERVICE_ACCOUNT_FILE="",
        GOOGLE_SHEET_ID="sheet-1",
        GOOGLE_SHEET_NAME="지출 정산",
    )
    def test_google_sheets_updates_existing_row(self, build_mock, credentials_mock):
        from services.google_sheets import GoogleSheetsService

        service = build_mock.return_value
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.update.return_value.execute.return_value = {}
        expense = ExpenseRequest.objects.create(
            requester=self.member,
            expense_date=date(2026, 4, 10),
            category=self.category,
            amount_krw=33000,
            current_status=ExpenseRequest.STATUS_PAID,
            payment_date=date(2026, 4, 11),
            payment_memo="계좌이체",
        )
        values_api.get.return_value.execute.return_value = {"values": [["id"], [str(expense.pk)]]}

        row_ref = GoogleSheetsService().append_paid_expense(expense)

        self.assertEqual(row_ref, "row:2")
        values_api.append.assert_not_called()
        values_api.update.assert_called_once()
        self.assertEqual(values_api.update.call_args.kwargs["range"], "'지출 정산'!A2:N2")
        self.assertEqual(values_api.update.call_args.kwargs["body"]["values"][0][:6], [
            "04/10/2026",
            "행사비",
            "33000",
            "",
            "",
            "",
        ])

    def test_member_cannot_access_admin_queue(self):
        self.client.login(username="member", password="pass12345")
        response = self.client.get(reverse("expense-admin-queue"))
        self.assertEqual(response.status_code, 403)
