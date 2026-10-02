from django.contrib import admin
from django.urls import path
from board import views

urlpatterns = [
    path("", views.jobs, name="jobs"),
    path("sources/", views.sources, name="sources"),
    path("health/", views.health, name="health"),
    path("admin/", admin.site.urls),
]
