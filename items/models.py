
from django.db import models
from django.conf import settings
from django.core.files.storage import FileSystemStorage


private_evidence_storage = FileSystemStorage(
    location=settings.BASE_DIR / 'private_uploads',
    base_url=None
)

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

    image = models.ImageField(
        upload_to='item_images/',
        blank=True,
        null=True
    )

    category = models.CharField(max_length=20, choices=Category.choices)
    report_type = models.CharField(max_length=5, choices=ReportType.choices)
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

    contains_sensitive_info = models.BooleanField(default=False)

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

        if self.category in sensitive_categories:
            self.contains_sensitive_info = True

        if self.contains_sensitive_info:
            self.visibility = self.Visibility.PRIVATE

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_report_type_display()}: {self.title}"


class Claim(models.Model):

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Review'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    item = models.ForeignKey(
        Item,
        on_delete=models.PROTECT,
        related_name='claims'
    )

    claimant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='item_claims'
    )

    explanation = models.TextField(
        help_text="Explain why you believe this item belongs to you."
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_claims'
    )

    admin_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Claim for {self.item.title} by {self.claimant}"

class ClaimEvidence(models.Model):

    claim = models.ForeignKey(
        Claim,
        on_delete=models.PROTECT,
        related_name='evidence'
    )

    image = models.ImageField(
        storage=private_evidence_storage,
        upload_to='claim_evidence/'
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Evidence for Claim #{self.claim.id}"

class ItemImage(models.Model):

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='additional_images'
    )

    image = models.ImageField(
        upload_to='item_images/additional/'
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Additional image for {self.item.title}"