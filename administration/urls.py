from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SlidesViewSet, ContactFormViewSet, NewsletterLeadsViewSet

router = DefaultRouter()
router.register(r'slides', SlidesViewSet)
router.register(r'contact', ContactFormViewSet)
router.register(r'newsletter', NewsletterLeadsViewSet)

urlpatterns = [
    path('', include(router.urls)),
]