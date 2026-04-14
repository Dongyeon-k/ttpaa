from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import HttpResponseForbidden


class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_portal_admin

    def handle_no_permission(self):
        return HttpResponseForbidden("관리자만 접근할 수 있습니다.")


def user_is_admin(user) -> bool:
    return user.is_authenticated and user.is_portal_admin
