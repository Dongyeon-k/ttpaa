from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.expenses.models import ExpenseCategory


class Command(BaseCommand):
    help = "개발용 기본 계정과 지출 카테고리를 생성합니다."

    def handle(self, *args, **options):
        user_model = get_user_model()
        defaults = [
            ("교우회 활동비", 10),
            ("교우회 모임지출", 20),
            ("결혼 축하기", 30),
            ("근조기", 40),
            ("학부 지원", 50),
        ]
        for name, order in defaults:
            ExpenseCategory.objects.update_or_create(name=name, defaults={"sort_order": order, "is_active": True})

        admin_user, created = user_model.objects.get_or_create(
            username="admin",
            defaults={
                "first_name": "관리자",
                "email": "admin@example.com",
                "role": "admin",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin_user.set_password("ChangeMe123!")
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("admin / ChangeMe123! 계정을 생성했습니다."))
        else:
            updated_fields = []
            for field, value in {"role": "admin", "is_staff": True, "is_superuser": True}.items():
                if getattr(admin_user, field) != value:
                    setattr(admin_user, field, value)
                    updated_fields.append(field)
            if updated_fields:
                admin_user.save(update_fields=updated_fields)
                self.stdout.write(self.style.SUCCESS("기존 admin 계정을 슈퍼유저로 업데이트했습니다."))

        if not user_model.objects.filter(username="member").exists():
            user_model.objects.create_user(
                username="member",
                password="ChangeMe123!",
                first_name="구성원",
                email="member@example.com",
                role="member",
            )
            self.stdout.write(self.style.SUCCESS("member / ChangeMe123! 계정을 생성했습니다."))

        self.stdout.write(self.style.SUCCESS("기본 시드 데이터 준비가 완료되었습니다."))
