
from django.db import models
from django.conf import settings


class Item(models.Model):

    class ReportType(models.TextChoices):
        LOST = 'LOST', 'Lost'
        FOUND = 'FOUND', 'Found'

    class Category(models.TextChoices):
        ELECTRONICS = 'ELECTRONICS', 'Electronics'
        DOCUMENTS = 'DOCUMENTS', 'Documents'
        CLOTHING = 'CLOTHING', 'Clothing'
        BAGS = 'BAGS', 'Bags'
        ACCESSORIES = 'ACCESSORIES', 'Accessories'
        KEYS = 'KEYS', 'Keys'
        STUDENT_ID = 'STUDENT_ID', 'Student ID'
        IDENTITY_DOCUMENT = 'IDENTITY_DOCUMENT', 'Identity Document'
        OTHER = 'OTHER', 'Other'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        RESOLVED = 'RESOLVED', 'Resolved'
        CLOSED = 'CLOSED', 'Closed'

    class Visibility(models.TextChoices):
        PUBLIC = 'PUBLIC', 'Public'
        PRIVATE = 'PRIVATE', 'Private'

    title = models.CharField(max_length=150)
    description = models.TextField()

    category = models.CharField(
        max_length=20,
        choices=Category.choices
    )

    report_type = models.CharField(
        max_length=5,
        choices=ReportType.choices
    )

    campus = models.CharField(max_length=100)
    building = models.CharField(max_length=100)
    specific_location = models.CharField(max_length=200)

    date_occurred = models.DateField()

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='item_reports'
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN
    )

    contains_sensitive_info = models.BooleanField(
        default=False
    )

    visibility = models.CharField(
        max_length=10,
        choices=Visibility.choices,
        default=Visibility.PUBLIC
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        sensitive_categories = [
            self.Category.STUDENT_ID,
            self.Category.IDENTITY_DOCUMENT,
        ]

        if (
            self.contains_sensitive_info
            or self.category in sensitive_categories
        ):
            self.visibility = self.Visibility.PRIVATE

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_report_type_display()}: {self.title}"
