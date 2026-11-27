
from django.db import models, transaction
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.hashers import make_password, check_password
from datetime import timedelta

import secrets

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

    class LifecycleStatus(models.TextChoices):
        REPORTED = 'REPORTED', 'Reported'
        IN_CUSTODY = 'IN_CUSTODY', 'In custody'
        CLAIMED = 'CLAIMED', 'Claimed'
        RETURNED = 'RETURNED', 'Returned'
        UNCLAIMED = 'UNCLAIMED', 'Unclaimed'
        DISPOSED = 'DISPOSED', 'Disposed'

    class Visibility(models.TextChoices):
        PUBLIC = 'PUBLIC', 'Public'
        PRIVATE = 'PRIVATE', 'Private'

    title = models.CharField(max_length=150)
    reference_number = models.CharField(
        max_length=16,
        unique=True,
        editable=False
    )

    colour = models.CharField(max_length=50, blank=True)

    brand = models.CharField(max_length=100, blank=True)

    distinguishing_marks = models.TextField(blank=True)

    private_identifying_details = models.TextField(blank=True)

    current_holding_location = models.CharField(
        max_length=200,
        blank=True
    )
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

    lifecycle_status = models.CharField(
        max_length=20,
        choices=LifecycleStatus.choices,
        blank=True,
        default=''
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
        reference_generated = False

        if not self.reference_number:
            prefix = (
                'LST' if self.report_type == self.ReportType.LOST
                else 'FND'
            )
            year = timezone.localdate().year

            while True:
                number = (
                    f"{prefix}-{year}-"
                    f"{secrets.randbelow(1_000_000):06d}"
                )

                if not Item.objects.filter(
                    reference_number=number
                ).exists():
                    self.reference_number = number
                    reference_generated = True
                    break

        sensitive_categories = [
            self.Category.STUDENT_ID,
            self.Category.IDENTITY_DOCUMENT,
        ]

        if self.category in sensitive_categories:
            self.contains_sensitive_info = True

        if reference_generated and kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = (
                set(kwargs['update_fields']) | {'reference_number'}
            )

        original_lifecycle = self.lifecycle_status

        if self.report_type == self.ReportType.LOST:
            self.lifecycle_status = ''
        elif not self.lifecycle_status:
            self.lifecycle_status = self.LifecycleStatus.REPORTED

        if (
            'update_fields' in kwargs
            and kwargs['update_fields'] is not None
            and self.lifecycle_status != original_lifecycle
        ):
            kwargs['update_fields'] = set(kwargs['update_fields']) | {
                'lifecycle_status'
            }

        super().save(*args, **kwargs)

    def transition_lifecycle(self, new_status):
        if self.report_type != self.ReportType.FOUND:
            raise ValidationError(
                'The found-item lifecycle cannot be used for lost reports.'
            )
        allowed_transitions = {
            self.LifecycleStatus.REPORTED: {
                self.LifecycleStatus.IN_CUSTODY,
            },
            self.LifecycleStatus.IN_CUSTODY: {
                self.LifecycleStatus.CLAIMED,
                self.LifecycleStatus.UNCLAIMED,
            },
            self.LifecycleStatus.CLAIMED: {
                self.LifecycleStatus.RETURNED,
            },
            self.LifecycleStatus.UNCLAIMED: {
                self.LifecycleStatus.DISPOSED,
            },
            self.LifecycleStatus.RETURNED: set(),
            self.LifecycleStatus.DISPOSED: set(),
        }

        if new_status == self.lifecycle_status:
            return

        if new_status not in allowed_transitions.get(
            self.lifecycle_status, set()
        ):
            raise ValidationError(
                f'Invalid lifecycle transition: '
                f'{self.lifecycle_status} → {new_status}'
            )

        self.lifecycle_status = new_status
        self.save(update_fields=['lifecycle_status', 'updated_at'])

    def __str__(self):
        return f"{self.get_report_type_display()}: {self.title}"


class CustodyRecord(models.Model):

    item = models.OneToOneField(
        Item,
        on_delete=models.PROTECT,
        related_name='custody_record'
    )

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='confirmed_item_custodies'
    )

    received_at = models.DateTimeField(auto_now_add=True)

    storage_location = models.CharField(max_length=200)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-received_at']

        permissions = [
            ('can_confirm_custody', 'Can confirm item custody'),
        ]

    def clean(self):
        super().clean()

        if self.item_id and self.item.report_type != Item.ReportType.FOUND:
            raise ValidationError(
                'Only found items can have a custody record.'
            )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self.full_clean()
            super().save(*args, **kwargs)

            item = Item.objects.select_for_update().get(
                pk=self.item_id
            )

            if item.lifecycle_status == Item.LifecycleStatus.REPORTED:
                item.transition_lifecycle(
                    Item.LifecycleStatus.IN_CUSTODY
                )

    def __str__(self):
        return f"Custody record for {self.item.title}"


class ItemMatch(models.Model):

    lost_item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='lost_matches'
    )

    found_item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='found_matches'
    )

    similarity_score = models.FloatField()

    is_dismissed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-similarity_score']
        constraints = [
            models.UniqueConstraint(
                fields=['lost_item', 'found_item'],
                name='unique_lost_found_match'
            ),
        ]

    def clean(self):
        super().clean()

        if self.lost_item_id and self.found_item_id:
            if self.lost_item.report_type != Item.ReportType.LOST:
                raise ValidationError(
                    'The first item must be a lost report.'
                )

            if self.found_item.report_type != Item.ReportType.FOUND:
                raise ValidationError(
                    'The second item must be a found report.'
                )

            if self.lost_item.category != self.found_item.category:
                raise ValidationError(
                    'Matched items must have the same category.'
                )

        if not 0 <= self.similarity_score <= 1:
            raise ValidationError(
                'Similarity score must be between 0 and 1.'
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.lost_item.reference_number} - "
            f"{self.found_item.reference_number}"
        )


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

    linked_lost_report = models.ForeignKey(
        Item,
        on_delete=models.PROTECT,
        related_name='claims_for_recovered_item',
        null=True,
        blank=True,
        limit_choices_to={'report_type': 'LOST'},
        help_text=(
            'Lost report explicitly confirmed by the custodian '
            'as belonging to this claimant.'
        )
    )

    claimant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='item_claims'
    )

    explanation = models.TextField(
        help_text='Explain why you believe this item belongs to you.'
    )

    hidden_detail_answer = models.TextField(
        blank=True,
        default='',
        help_text='Describe the hidden identifying detail of the item.'
    )

    other_identifying_features = models.TextField(
        blank=True,
        default='',
        help_text='Describe at least one other feature that helps identify the item.'
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

        constraints = [
            models.UniqueConstraint(
                fields=['item'],
                condition=models.Q(status='APPROVED'),
                name='unique_approved_claim_per_item'
            )
        ]

    def clean(self):
        super().clean()

        if self.linked_lost_report_id:
            lost_report = self.linked_lost_report

            if lost_report.report_type != Item.ReportType.LOST:
                raise ValidationError(
                    'The linked report must be a lost-item report.'
                )

            if lost_report.status != Item.Status.OPEN:
                raise ValidationError(
                    'The linked lost report must still be open.'
                )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            item = Item.objects.select_for_update().get(
                pk=self.item_id
            )

            self.full_clean()
            super().save(*args, **kwargs)

            if (
                self.status == self.Status.APPROVED
                and item.lifecycle_status == Item.LifecycleStatus.IN_CUSTODY
            ):
                item.transition_lifecycle(
                    Item.LifecycleStatus.CLAIMED
                )

    def __str__(self):
        return f"Claim #{self.pk} - {self.item.title}"

class PickupCode(models.Model):

    claim = models.OneToOneField(
        Claim,
        on_delete=models.PROTECT,
        related_name='pickup_code'
    )

    code_hash = models.CharField(max_length=128)

    created_at = models.DateTimeField(auto_now_add=True)

    expires_at = models.DateTimeField()

    used_at = models.DateTimeField(
        null=True,
        blank=True
    )

    failed_attempts = models.PositiveSmallIntegerField(default=0)

    is_locked = models.BooleanField(default=False)

    MAX_ATTEMPTS = 5
    VALIDITY_DAYS = 7

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def issue_for_claim(cls, claim):
        if claim.status != Claim.Status.APPROVED:
            raise ValidationError(
                'Pickup codes can only be issued for approved claims.'
            )

        if cls.objects.filter(claim=claim).exists():
            raise ValidationError(
                'A pickup code has already been issued for this claim.'
            )

        raw_code = ''.join(
            secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
            for _ in range(12)
        )

        pickup_code = cls.objects.create(
            claim=claim,
            code_hash=make_password(raw_code),
            expires_at=timezone.now() + timedelta(days=cls.VALIDITY_DAYS)
        )

        return pickup_code, raw_code

    def __str__(self):
        return f"Pickup code for Claim #{self.claim_id}"

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

    class VerificationMethod(models.TextChoices):
        PICKUP_CODE_AND_ID = (
            'PICKUP_CODE_AND_ID',
            'Pickup code and university ID'
        )
        RECOVERED_ID_CARD = (
            'RECOVERED_ID_CARD',
            'Recovered ID card and account verification'
        )
        ALTERNATIVE_ESCALATED = (
            'ALTERNATIVE_ESCALATED',
            'Alternative verification with administrator escalation'
        )

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

    verification_method = models.CharField(
        max_length=30,
        choices=VerificationMethod.choices,
        null=True,
        blank=True
    )

    collector_identifier = models.CharField(
        max_length=100,
        blank=True,
        help_text='Collector admission number or staff number, where applicable.'
    )

    notes = models.TextField(blank=True)

    handed_over_at = models.DateTimeField(auto_now_add=True)

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

            if (
                self.claim.item.lifecycle_status
                != Item.LifecycleStatus.CLAIMED
            ):
                raise ValidationError(
                    'The item must have a claimed lifecycle status.'
                )

        if not self.identity_verified:
            raise ValidationError(
                'The claimant identity must be verified before handover.'
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Handover for Claim #{self.claim_id}"


class ItemAuditLog(models.Model):

    class EventType(models.TextChoices):
        HANDOVER_COMPLETED = (
            'HANDOVER_COMPLETED',
            'Handover completed'
        )
        ITEM_RETURNED = (
            'ITEM_RETURNED',
            'Item returned'
        )
        LOST_REPORT_CLOSED = (
            'LOST_REPORT_CLOSED',
            'Linked lost report closed'
        )
        PICKUP_CODE_REGENERATED = (
            'PICKUP_CODE_REGENERATED',
            'Pickup code regenerated'
        )

    item = models.ForeignKey(
        Item,
        on_delete=models.PROTECT,
        related_name='audit_logs'
    )

    claim = models.ForeignKey(
        Claim,
        on_delete=models.PROTECT,
        related_name='audit_logs',
        null=True,
        blank=True
    )

    handover = models.ForeignKey(
        Handover,
        on_delete=models.PROTECT,
        related_name='audit_logs',
        null=True,
        blank=True
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='item_audit_events'
    )

    event_type = models.CharField(
        max_length=30,
        choices=EventType.choices
    )

    description = models.TextField()

    details = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                'Audit records cannot be modified.'
            )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            'Audit records cannot be deleted.'
        )

    def __str__(self):
        return f"{self.event_type} - {self.item.reference_number}"


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

class MatchingConfiguration(models.Model):
    id = models.PositiveSmallIntegerField(
        primary_key=True,
        default=1,
        editable=False
    )

    threshold = models.FloatField(
        default=0.50,
        validators=[
            MinValueValidator(0.0),
            MaxValueValidator(1.0),
        ],
        help_text='Minimum similarity score required for a match (0.00–1.00).'
    )

    class Meta:
        verbose_name = 'Matching Configuration'
        verbose_name_plural = 'Matching Configuration'

    def __str__(self):
        return f'Matching threshold: {self.threshold:.2f}'
