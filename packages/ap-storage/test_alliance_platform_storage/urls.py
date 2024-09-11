from alliance_platform.storage.views import DownloadRedirectView
from alliance_platform.storage.views import GenerateUploadUrlView
from django.urls import path

app_name = "test_alliance_platform_storage"

urlpatterns = [
    path("download-file/", DownloadRedirectView.as_view()),
    path("generate-upload-url/", GenerateUploadUrlView.as_view()),
]
