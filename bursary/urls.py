from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.LockoutLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Password reset (emails a one-time link; uses the same email settings as notifications)
    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="registration/pw_reset_form.html",
        email_template_name="registration/pw_reset_email.txt",
        subject_template_name="registration/pw_reset_subject.txt"), name="password_reset"),
    path("password-reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="registration/pw_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="registration/pw_reset_confirm.html"), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="registration/pw_reset_complete.html"), name="password_reset_complete"),
    path("password-change/", auth_views.PasswordChangeView.as_view(
        template_name="registration/pw_change_form.html"), name="password_change"),
    path("password-change/done/", auth_views.PasswordChangeDoneView.as_view(
        template_name="registration/pw_change_done.html"), name="password_change_done"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("applications/<int:pk>/award-letter/", views.award_letter, name="award_letter"),
    path("apply/<int:round_id>/", views.apply, name="apply"),
    path("applications/<int:pk>/", views.application_detail, name="application_detail"),
    path("documents/<int:pk>/", views.download_document, name="download_document"),
    path("reports/", views.reports, name="reports"),
    path("reports/export/", views.reports_csv, name="reports_csv"),
    path("analytics/", views.analytics, name="analytics"),
]
