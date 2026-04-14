import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.core.models import NotificationLog

logger = logging.getLogger("ttpaa")


def _send_email(*, event_type: str, recipient: str, subject: str, body: str, related_label: str = "", related_object_id: str = ""):
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)
        NotificationLog.objects.create(
            event_type=event_type,
            recipient=recipient,
            subject=subject,
            body=body,
            related_label=related_label,
            related_object_id=related_object_id,
            success=True,
        )
    except Exception as exc:
        NotificationLog.objects.create(
            event_type=event_type,
            recipient=recipient,
            subject=subject,
            body=body,
            related_label=related_label,
            related_object_id=related_object_id,
            success=False,
            error_message=str(exc),
        )
        logger.exception("email_send_failed event=%s recipient=%s", event_type, recipient)


def notify_admins_of_submission(expense):
    subject = f"[TTPAA] 지출 요청 #{expense.pk} 제출"
    body = (
        f"{expense.requester.first_name or expense.requester.username} 님이 "
        f"{expense.amount_krw:,}원 지출 요청을 제출했습니다.\n"
        f"카테고리: {expense.category.name}\n"
        f"사유: {expense.comment or '-'}"
    )
    for recipient in settings.ADMIN_EMAILS:
        _send_email(
            event_type="expense_submitted",
            recipient=recipient,
            subject=subject,
            body=body,
            related_label="expenses.ExpenseRequest",
            related_object_id=str(expense.pk),
        )


def notify_request_status_changed(expense):
    if not expense.requester.email:
        return
    subject = f"[TTPAA] 지출 요청 #{expense.pk} 상태 변경: {expense.get_current_status_display()}"
    body = (
        f"요청 번호: {expense.pk}\n"
        f"현재 상태: {expense.get_current_status_display()}\n"
        f"관리자 메모: {expense.admin_note or '-'}\n"
        f"반려 사유: {expense.rejection_reason or '-'}\n"
        f"지급 메모: {expense.payment_memo or '-'}"
    )
    _send_email(
        event_type="expense_status_changed",
        recipient=expense.requester.email,
        subject=subject,
        body=body,
        related_label="expenses.ExpenseRequest",
        related_object_id=str(expense.pk),
    )
