from django.urls import path

from apps.core import views

urlpatterns = [
    # App pages
    path("home", views.HomeView.as_view(), name="home"),
    path("settings", views.UserSettingsView.as_view(), name="settings"),
    path(
        "agents/<int:installation_id>/settings",
        views.AgentInstallationSettingsView.as_view(),
        name="agent_installation_settings",
    ),
    path("admin-panel", views.AdminPanelView.as_view(), name="admin_panel"),
    # Utils
    path("resend-confirmation/", views.resend_confirmation_email, name="resend_confirmation"),
    path("api-key/rotate/", views.rotate_api_key, name="rotate_api_key"),
    path(
        "agent-installations/create/",
        views.create_agent_installation,
        name="create_agent_installation",
    ),

]
