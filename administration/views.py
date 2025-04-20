from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from administration.models import Slides, ContactForm, NewsletterLeads
from administration.serializers import SlidesSerializer, ContactFormSerializer, NewsletterLeadsSerializer
from backend_praco.renderers import CustomRenderer

class SlidesViewSet(viewsets.ModelViewSet):
    queryset = Slides.objects.all()
    serializer_class = SlidesSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    renderer_classes = [CustomRenderer]

    def perform_create(self, serializer):
        serializer.save()

class ContactFormViewSet(viewsets.ModelViewSet):
    queryset = ContactForm.objects.all()
    serializer_class = ContactFormSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomRenderer]


    def perform_create(self, serializer):
        serializer.save()

class NewsletterLeadsViewSet(viewsets.ModelViewSet):
    queryset = NewsletterLeads.objects.all()
    serializer_class = NewsletterLeadsSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomRenderer]

    def perform_create(self, serializer):
        serializer.save()