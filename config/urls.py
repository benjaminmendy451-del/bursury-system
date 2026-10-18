from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Bursary Committee"
admin.site.site_title = "Bursary Management"
admin.site.index_title = "Review applications and manage bursary rounds"

# Uploaded documents hold personal data (IDs, family income), so they are NOT
# served from a public /media/ URL. They are only reachable through the
# login-protected view at /documents/<id>/ (see bursary/views.py).
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("bursary.urls")),
]
