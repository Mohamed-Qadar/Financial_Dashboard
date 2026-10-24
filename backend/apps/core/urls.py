from django.urls import path

from apps.core.views import LivenessView, ReadinessView

urlpatterns = [
    path("health/", LivenessView.as_view(), name="health-live"),
    path("health/ready/", ReadinessView.as_view(), name="health-ready"),
]
