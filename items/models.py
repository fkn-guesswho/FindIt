
from django.db import models, transaction
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ValidationError
from django.utils import timezone


# Private storage for ownership claim evidence.
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

    contains_sensitive_info = models.BooleanField(default=False)

    visibility = models.CharField(
        max_length=10,
        choices=Visibility.choices,
        default=Visibility.PUBLIC
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closed_item_reports'
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    closure_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']



    def save(self, *args, **kwargs):
        sensitive_categories = [
            self.Category.STUDENT_ID,
            self.Category.IDENTITY_DOCUMENT,
        ]

        if self.category in sensitive_categories:
           self.contains_sensitive_info = True

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
        help_text='Explain why you believe this item belongs to you.'
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
        return f"Claim #{self.pk} - {self.item.title}"


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
        return f"Evidence for Claim #{self.claim_id}"


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



class Handover(models.Model):

    claim = models.OneToOneField(
        Claim,
        on_delete=models.PROTECT,
        related_name='handover'
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recorded_handovers'
    )

    identity_verified = models.BooleanField(default=False)

    handed_over_at = models.DateTimeField(auto_now_add=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-handed_over_at']

    def clean(self):
        super().clean()

        if self.claim_id:
            if self.claim.status != Claim.Status.APPROVED:
                raise ValidationError(
                    'Only approved claims can have a handover.'
                )

            if self.claim.item.status != Item.Status.OPEN:
                raise ValidationError(
                    'Only open items can have a handover.'
                )

        if not self.identity_verified:
            raise ValidationError(
                'The claimant identity must be verified before handover.'
            )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self.full_clean()
            super().save(*args, **kwargs)

            item = self.claim.item
            item.status = Item.Status.RESOLVED
            item.save(update_fields=['status', 'updated_at'])

    def __str__(self):
        return f"Handover for Claim #{self.claim_id}"



class ClosureRequest(models.Model):

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Review'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    item = models.ForeignKey(
        Item,
        on_delete=models.PROTECT,
        related_name='closure_requests'
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='closure_requests'
    )

    reason = models.TextField(
        help_text='Explain why this report should be closed.'
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
        related_name='reviewed_closure_requests'
    )

    admin_closure_reason = models.TextField(blank=True)
    review_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Closure request #{self.pk} - {self.item.title}"

    def review(
        self,
        reviewer,
        decision,
        review_notes='',
        admin_closure_reason=''
    ):
        if decision not in [
            self.Status.APPROVED,
            self.Status.REJECTED,
        ]:
            raise ValidationError('Invalid closure request decision.')

        with transaction.atomic():

            closure = ClosureRequest.objects.select_for_update().get(
                pk=self.pk
            )

            if closure.status != self.Status.PENDING:
                raise ValidationError(
                    'This closure request has already been reviewed.'
                )

            item = Item.objects.select_for_update().get(
                pk=closure.item_id
            )

            if decision == self.Status.APPROVED:

                if item.status != Item.Status.OPEN:
                    raise ValidationError(
                        'Only open reports can be closed.'
                    )

                item.status = Item.Status.CLOSED
                item.closed_by = reviewer
                item.closed_at = timezone.now()
                item.closure_reason = (
                    admin_closure_reason.strip()
                    or closure.reason
                )

                item.save(update_fields=[
                    'status',
                    'closed_by',
                    'closed_at',
                    'closure_reason',
                    'updated_at',
                ])

            closure.status = decision
            closure.reviewed_by = reviewer
            closure.reviewed_at = timezone.now()
            closure.review_notes = review_notes
            closure.admin_closure_reason = admin_closure_reason

            closure.save(update_fields=[
                'status',
                'reviewed_by',
                'reviewed_at',
                'review_notes',
                'admin_closure_reason',
            ])

            self.status = closure.status
            self.reviewed_by = closure.reviewed_by
            self.reviewed_at = closure.reviewed_at
            self.review_notes = closure.review_notes
            self.admin_closure_reason = closure.admin_closure_reason
