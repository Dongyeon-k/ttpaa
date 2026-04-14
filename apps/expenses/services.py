from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.expenses.models import ExpenseRequest, ExpenseStatusHistory, SyncLog
from services.google_drive import GoogleDriveService
from services.google_sheets import GoogleSheetsService
from services.notifications import notify_admins_of_submission, notify_request_status_changed

logger = logging.getLogger("ttpaa")


def create_expense_request(*, form, requester) -> ExpenseRequest:
    with transaction.atomic():
        expense = form.save(commit=False)
        expense.requester = requester
        expense.current_status = ExpenseRequest.STATUS_SUBMITTED
        expense.sync_state = ExpenseRequest.SYNC_NOT_READY
        expense.save()

        attachment = form.cleaned_data.get("attachment")
        if attachment:
            expense.attachments.create(
                file=attachment,
                original_filename=attachment.name,
                mime_type=getattr(attachment, "content_type", "") or "application/octet-stream",
                file_size=attachment.size,
            )

        ExpenseStatusHistory.objects.create(
            request=expense,
            from_status="",
            to_status=ExpenseRequest.STATUS_SUBMITTED,
            changed_by=requester,
            note="요청이 제출되었습니다.",
        )

    notify_admins_of_submission(expense)
    logger.info("expense_submitted request_id=%s user=%s", expense.pk, requester.pk)
    return expense


@transaction.atomic
def transition_expense(
    *,
    expense: ExpenseRequest,
    to_status: str,
    actor,
    note: str = "",
    rejection_reason: str = "",
    payment_date=None,
    payment_memo: str = "",
) -> ExpenseRequest:
    expense = ExpenseRequest.objects.select_for_update().get(pk=expense.pk)
    from_status = expense.current_status

    allowed = {
        ExpenseRequest.STATUS_SUBMITTED: {ExpenseRequest.STATUS_UNDER_REVIEW, ExpenseRequest.STATUS_REJECTED},
        ExpenseRequest.STATUS_UNDER_REVIEW: {ExpenseRequest.STATUS_APPROVED, ExpenseRequest.STATUS_REJECTED},
        ExpenseRequest.STATUS_APPROVED: {ExpenseRequest.STATUS_PAID},
        ExpenseRequest.STATUS_REJECTED: set(),
        ExpenseRequest.STATUS_PAID: set(),
    }
    if to_status not in allowed.get(from_status, set()):
        raise ValueError("허용되지 않은 상태 전환입니다.")

    expense.current_status = to_status
    if note:
        expense.admin_note = note
    if to_status == ExpenseRequest.STATUS_REJECTED:
        expense.rejection_reason = rejection_reason
        expense.sync_state = ExpenseRequest.SYNC_NOT_READY
    if to_status == ExpenseRequest.STATUS_PAID:
        expense.payment_date = payment_date or timezone.localdate()
        expense.payment_memo = payment_memo
        expense.paid_by = actor
        expense.sync_state = ExpenseRequest.SYNC_PENDING
    expense.save()

    ExpenseStatusHistory.objects.create(
        request=expense,
        from_status=from_status,
        to_status=to_status,
        changed_by=actor,
        note=note or rejection_reason or payment_memo,
    )

    notify_request_status_changed(expense)
    logger.info(
        "expense_status_changed request_id=%s from=%s to=%s actor=%s",
        expense.pk,
        from_status,
        to_status,
        actor.pk,
    )
    return expense


def sync_paid_request(expense: ExpenseRequest, *, force: bool = False) -> ExpenseRequest:
    with transaction.atomic():
        expense = ExpenseRequest.objects.select_for_update().get(pk=expense.pk)
        if expense.current_status != ExpenseRequest.STATUS_PAID:
            raise ValueError("지급 완료 상태에서만 동기화할 수 있습니다.")
        if expense.sync_state == ExpenseRequest.SYNC_SUCCESS and not force:
            SyncLog.objects.create(
                request=expense,
                service=SyncLog.SERVICE_COMBINED,
                status=SyncLog.STATUS_SKIPPED,
                action="retry_sync",
                message="이미 동기화가 완료되었습니다.",
            )
            return expense

        expense.sync_state = ExpenseRequest.SYNC_PENDING
        expense.sync_error = ""
        expense.save(update_fields=["sync_state", "sync_error", "updated_at"])

        drive_service = GoogleDriveService()
        sheets_service = GoogleSheetsService()

        try:
            if expense.primary_attachment:
                drive_result = drive_service.upload_expense_attachment(expense)
                expense.google_drive_file_id = drive_result["file_id"]
                expense.google_drive_file_url = drive_result["file_url"]
                SyncLog.objects.create(
                    request=expense,
                    service=SyncLog.SERVICE_DRIVE,
                    status=SyncLog.STATUS_SUCCESS,
                    action="upload_attachment",
                    message=expense.google_drive_file_url,
                )

            row_ref = sheets_service.append_paid_expense(expense, force=force)
            expense.google_sheet_row_ref = row_ref
            expense.sync_state = ExpenseRequest.SYNC_SUCCESS
            expense.synced_at = timezone.now()
            expense.sync_error = ""
            expense.save()
            SyncLog.objects.create(
                request=expense,
                service=SyncLog.SERVICE_SHEETS,
                status=SyncLog.STATUS_SUCCESS,
                action="append_paid_expense",
                message=row_ref,
            )
            logger.info("expense_synced request_id=%s row=%s", expense.pk, row_ref)
            return expense
        except Exception as exc:
            expense.sync_state = ExpenseRequest.SYNC_FAILED
            expense.sync_error = str(exc)
            expense.save(update_fields=["sync_state", "sync_error", "updated_at"])
            SyncLog.objects.create(
                request=expense,
                service=SyncLog.SERVICE_COMBINED,
                status=SyncLog.STATUS_FAILED,
                action="sync_paid_request",
                message=str(exc),
            )
            logger.exception("expense_sync_failed request_id=%s", expense.pk)
            raise
