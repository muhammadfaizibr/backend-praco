from django.contrib import admin
from administration.models import Slides, ContactForm, NewsletterLeads

@admin.register(Slides)
class SlidesAdmin(admin.ModelAdmin):
    list_display = ('id', 'alt_text', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('alt_text',)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

@admin.register(ContactForm)
class ContactFormAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'subject', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('full_name', 'email', 'subject')

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }

@admin.register(NewsletterLeads)
class NewsletterLeadsAdmin(admin.ModelAdmin):
    list_display = ('email', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('email',)

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }