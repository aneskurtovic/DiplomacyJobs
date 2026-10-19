from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.urls import reverse_lazy
from board import views
from board import candidate_views
from board.candidate_forms import CandidateAuthenticationForm
from board import editor
from board.feeds import JobsFeed

urlpatterns = [
    path("feed/", JobsFeed(), name="feed"),
    path("robots.txt", views.robots, name="robots"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
    path("health/", views.health, name="health"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("health/scrape/", views.scrape_health, name="scrape_health"),
    path("admin/", admin.site.urls),
    path("editor/", editor.dashboard, name="editor"),
    path("editor/jobs/<int:pk>/", editor.review_job, name="editor_job"),
]
urlpatterns += i18n_patterns(
    path("", views.jobs, name="jobs"),
    path("for-you/", candidate_views.for_you, name="for_you"),
    path("for-you/jobs/<int:pk>/not-relevant/", candidate_views.not_relevant, name="not_relevant"),
    path("jobs/<int:pk>/apply/", candidate_views.official_application, name="official_application"),
    path("account/register/", candidate_views.candidate_signup, name="candidate_signup"),
    path("account/activate/<uidb64>/<token>/", candidate_views.candidate_activate, name="candidate_activate"),
    path("account/login/", auth_views.LoginView.as_view(template_name="board/candidate_login.html", authentication_form=CandidateAuthenticationForm, redirect_authenticated_user=True), name="candidate_login"),
    path("account/logout/", auth_views.LogoutView.as_view(), name="candidate_logout"),
    path("account/profile/", candidate_views.candidate_profile, name="candidate_profile"),
    path("account/delete/", candidate_views.candidate_delete, name="candidate_delete"),
    path("account/password-reset/", candidate_views.candidate_password_reset, name="candidate_password_reset"),
    path("account/password-reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="board/candidate_password_reset_done.html"), name="candidate_password_reset_done"),
    path("account/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="board/candidate_password_reset_confirm.html", success_url=reverse_lazy("candidate_password_reset_complete")), name="password_reset_confirm"),
    path("account/reset/complete/", auth_views.PasswordResetCompleteView.as_view(template_name="board/candidate_password_reset_complete.html"), name="candidate_password_reset_complete"),
    path("account/alerts/unsubscribe/<str:token>/", candidate_views.candidate_unsubscribe, name="candidate_unsubscribe"),
    path("privacy/", candidate_views.candidate_privacy, name="candidate_privacy"),
    path("jobs/<int:pk>/", views.job_detail, name="job_short"),
    path("jobs/<int:pk>/report/", views.report, name="job_report"),
    path("jobs/<int:pk>/share.png", views.job_share_image, name="job_share_image"),
    path("jobs/<int:pk>/<slug:slug>/", views.job_detail, name="job"),
    path("report/", views.report, name="report"),
    path("sources/", views.sources, name="sources"),
    path("sources/<int:pk>/", views.organization, name="organization_short"),
    path("sources/<int:pk>/<slug:slug>/", views.organization, name="organization"),
    path("offline/", views.offline, name="offline"),
    prefix_default_language=False,
)
