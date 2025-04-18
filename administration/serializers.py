from rest_framework import serializers
from administration.models import Slides, ContactForm, NewsletterLeads

class SlidesSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(max_length=None, use_url=True)
    
    class Meta:
        model = Slides
        fields = ['id', 'image', 'alt_text', 'created_at']

class ContactFormSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactForm
        fields = ['id', 'email', 'full_name', 'subject', 'message', 'created_at']

class NewsletterLeadsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterLeads
        fields = ['id', 'email', 'created_at']