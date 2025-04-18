from django.contrib import admin
from account.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

@admin.register(User)
class UserModelAdmin(BaseUserAdmin):
    list_display = ("id", "email", "first_name", "last_name", "company_name", "is_admin")
    list_filter = ("is_admin",)
    fieldsets = (
        ("User Credentials", {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "company_name")}),
        ("Permissions", {"fields": ("is_admin",)}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "company_name", "password1", "password2"),
        }),
    )
    search_fields = ("email",)
    ordering = ("email", "id")
    filter_horizontal = ()

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',),
        }