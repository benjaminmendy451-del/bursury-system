from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("apply/<int:round_id>/", views.apply, name="apply"),
    path("applications/<int:pk>/", views.application_detail, name="application_detail"),
    path("documents/<int:pk>/", views.download_document, name="download_document"),
]
