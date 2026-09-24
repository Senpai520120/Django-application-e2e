from django.urls import path

from files import views

app_name = "files"

urlpatterns = [
    path("", views.BrowseView.as_view(), name="browse"),
    path("folder/new/", views.FolderCreateView.as_view(), name="folder_create"),
    path("upload/", views.UploadView.as_view(), name="upload"),
    path("rename/", views.RenameView.as_view(), name="rename"),
    path("delete/", views.DeleteView.as_view(), name="delete"),
    path("download/", views.DownloadView.as_view(), name="download"),
]
