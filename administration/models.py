from django.db import models

class Slides(models.Model):
    image = models.ImageField(upload_to='slides/')
    alt_text = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Slide'
        verbose_name_plural = 'Slides'

    def __str__(self):
        return f"Slide {self.id}"

class ContactForm(models.Model):
    email = models.EmailField()
    full_name = models.CharField(max_length=100)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Contact from {self.full_name}"

class NewsletterLeads(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email