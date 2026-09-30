"""Admin configuration for travel API accounts."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Expose travel profile fields in the Django user admin."""

    fieldsets = DjangoUserAdmin.fieldsets + (
        ('Travel profile', {'fields': ('phone_number', 'preferred_currency')}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('Travel profile', {'fields': ('email', 'phone_number', 'preferred_currency')}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')
