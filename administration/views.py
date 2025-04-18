from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from administration.models import Slides, ContactForm, NewsletterLeads
from administration.serializers import SlidesSerializer, ContactFormSerializer, NewsletterLeadsSerializer

class SlidesViewSet(viewsets.ModelViewSet):
    queryset = Slides.objects.all()
    serializer_class = SlidesSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        serializer.save()

class ContactFormViewSet(viewsets.ModelViewSet):
    queryset = ContactForm.objects.all()
    serializer_class = ContactFormSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        serializer.save()

class NewsletterLeadsViewSet(viewsets.ModelViewSet):
    queryset = NewsletterLeads.objects.all()
    serializer_class = NewsletterLeadsSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        serializer.save()