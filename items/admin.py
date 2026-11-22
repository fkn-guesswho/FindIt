
from django.contrib import admin
from .models import Item


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'report_type',
        'category',
        'campus',
        'building',
        'status',
        'reported_by',
        'created_at',
    )

    list_filter = (
        'report_type',
        'category',
        'status',
        'campus',
    )

    search_fields = (
        'title',
        'description',
        'building',
        'specific_location',
        'reported_by__username',
    )
