from django.urls import path

from apps.chatbot.views import (
    ChatbotPageView,
    ChatbotSourcePageImageView,
    ChatbotSourcePageView,
    ConstitutionRawDataView,
    ConstitutionManageView,
    ReindexConstitutionView,
)

urlpatterns = [
    path("", ChatbotPageView.as_view(), name="chatbot"),
    path("sources/<int:pk>/", ChatbotSourcePageView.as_view(), name="chatbot-source-page"),
    path("sources/<int:pk>/image/", ChatbotSourcePageImageView.as_view(), name="chatbot-source-page-image"),
    path("manage/", ConstitutionManageView.as_view(), name="constitution-manage"),
    path("manage/raw/<int:pk>/", ConstitutionRawDataView.as_view(), name="constitution-raw-data"),
    path("manage/reindex/<int:pk>/", ReindexConstitutionView.as_view(), name="constitution-reindex"),
]
