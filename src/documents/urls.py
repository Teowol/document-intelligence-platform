from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.DocumentListView.as_view(), name="list"),
    path("upload/", views.DocumentUploadView.as_view(), name="upload"),
    path("search/", views.DocumentSearchView.as_view(), name="search"),
    path("ask/", views.DocumentQAView.as_view(), name="ask"),
    path("<int:pk>/", views.DocumentDetailView.as_view(), name="detail"),
    path("<int:pk>/delete/", views.DocumentDeleteView.as_view(), name="delete"),
]
