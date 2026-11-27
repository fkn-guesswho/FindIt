import secrets

from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.hashers import check_password, make_password

from .models import (
    Claim,
    PickupCode,
    Item,
    Handover,
    ItemAuditLog,
)


@transaction.atomic
def approve_claim(claim_id, reviewer, linked_lost_report=None):
    claim = Claim.objects.select_for_update().select_related(
        'item',
        'claimant'
    ).get(pk=claim_id)

    if claim.status != Claim.Status.PENDING:
        raise ValidationError(
            'Only pending claims can be approved.'
        )

    existing_approval = Claim.objects.filter(
        item=claim.item,
        status=Claim.Status.APPROVED
    ).exclude(pk=claim.pk).exists()

    if existing_approval:
        raise ValidationError(
            'Another claim for this item has already been approved.'
        )

    if linked_lost_report is not None:
        if linked_lost_report.report_type != Item.ReportType.LOST:
            raise ValidationError(
                'The linked report must be a lost-item report.'
            )

        if linked_lost_report.status != Item.Status.OPEN:
            raise ValidationError(
                'The linked lost report must still be open.'
            )

    claim.linked_lost_report = linked_lost_report
    claim.status = Claim.Status.APPROVED
    claim.reviewed_by = reviewer
    claim.reviewed_at = timezone.now()

    claim.save(update_fields=[
        'linked_lost_report',
        'status',
        'reviewed_by',
        'reviewed_at',
    ])

    pickup_code, raw_code = PickupCode.issue_for_claim(claim)

    email_subject = 'Your FindIt claim has been approved'

    email_message = (
        f'Hello {claim.claimant.username},\n\n'
        f'Your claim for "{claim.item.title}" has been approved.\n\n'
        f'Your pickup code is: {raw_code}\n\n'
        f'This code expires in {PickupCode.VALIDITY_DAYS} days '
        f'and can only be used once.\n\n'
        'Please bring your university identification when collecting '
        'your item. The custodian will verify your identity before '
        'releasing it.\n\n'
        'Keep this code private.\n\n'
        'FindIt Team'
    )

    transaction.on_commit(
        lambda: send_mail(
            email_subject,
            email_message,
            settings.DEFAULT_FROM_EMAIL,
            [claim.claimant.email],
            fail_silently=False,
        )
    )

    return claim, pickup_code


@transaction.atomic
def regenerate_pickup_code(claim_id, actor):
    if not (
        actor.is_superuser
        or actor.has_perm('items.can_confirm_custody')
    ):
        raise PermissionDenied(
            'You are not authorised to regenerate pickup codes.'
        )

    claim = (
        Claim.objects.select_for_update()
        .select_related('item', 'claimant')
        .get(pk=claim_id)
    )

    if claim.status != Claim.Status.APPROVED:
        raise ValidationError(
            'Only approved claims can have their pickup codes regenerated.'
        )

    if Handover.objects.filter(claim=claim).exists():
        raise ValidationError(
            'A pickup code cannot be regenerated after handover.'
        )

    pickup_code = (
        PickupCode.objects.select_for_update()
        .filter(claim=claim)
        .first()
    )

    if pickup_code is None:
        raise ValidationError(
            'No pickup code exists for this claim.'
        )

    raw_code = ''.join(
        secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
        for _ in range(12)
    )

    now = timezone.now()

    pickup_code.code_hash = make_password(raw_code)
    pickup_code.created_at = now
    pickup_code.expires_at = (
        now + timezone.timedelta(days=PickupCode.VALIDITY_DAYS)
    )
    pickup_code.used_at = None
    pickup_code.failed_attempts = 0
    pickup_code.is_locked = False

    pickup_code.save(update_fields=[
        'code_hash',
        'created_at',
        'expires_at',
        'used_at',
        'failed_attempts',
        'is_locked',
    ])

    ItemAuditLog.objects.create(
        item=claim.item,
        claim=claim,
        actor=actor,
        event_type=ItemAuditLog.EventType.PICKUP_CODE_REGENERATED,
        description=(
            f'A pickup code was regenerated for Claim #{claim.id}.'
        ),
        details={
            'pickup_code_regenerated': True,
            'previous_code_invalidated': True,
        }
    )

    email_subject = 'Your FindIt pickup code has been replaced'

    email_message = (
        f'Hello {claim.claimant.username},\n\n'
        f'A new pickup code has been generated for your approved claim '
        f'for "{claim.item.title}".\n\n'
        f'Your new pickup code is: {raw_code}\n\n'
        f'This code expires in {PickupCode.VALIDITY_DAYS} days '
        f'and can only be used once. Your previous code is no longer valid.\n\n'
        'Please bring your university identification when collecting '
        'your item. Keep this code private.\n\n'
        'FindIt Team'
    )

    if claim.claimant.email:
        transaction.on_commit(
            lambda: send_mail(
                email_subject,
                email_message,
                settings.DEFAULT_FROM_EMAIL,
                [claim.claimant.email],
                fail_silently=False,
            )
        )

    return pickup_code


def complete_handover(
    claim_id,
    submitted_code,
    actor,
    identity_verified,
    verification_method,
    collector_identifier='',
    notes=''
):
    """
    Verify a claimant and complete the physical handover.

    Failed pickup-code attempts are committed separately so that
    raising a validation error cannot undo the attempt counter.
    """

    # Only administrators and designated custodians can perform handovers.
    if not (
        actor.is_superuser
        or actor.has_perm('items.can_confirm_custody')
    ):
        raise PermissionDenied(
            'You are not authorised to perform handovers.'
        )

    if not identity_verified:
        raise ValidationError(
            'The claimant identity must be verified before handover.'
        )

    # PHASE 1: Verify the code and persist failed attempts.
    verification_error = None

    with transaction.atomic():
        pickup_code = (
            PickupCode.objects.select_for_update()
            .filter(claim_id=claim_id)
            .first()
        )

        if pickup_code is None:
            verification_error = 'No pickup code exists for this claim.'

        elif pickup_code.is_locked:
            verification_error = (
                'This pickup code is locked after too many failed attempts.'
            )

        elif pickup_code.used_at is not None:
            verification_error = 'This pickup code has already been used.'

        elif pickup_code.expires_at <= timezone.now():
            verification_error = 'This pickup code has expired.'

        elif not check_password(
            submitted_code.strip(),
            pickup_code.code_hash
        ):
            pickup_code.failed_attempts += 1

            if pickup_code.failed_attempts >= PickupCode.MAX_ATTEMPTS:
                pickup_code.is_locked = True

            pickup_code.save(update_fields=[
                'failed_attempts',
                'is_locked',
            ])

            if pickup_code.is_locked:
                verification_error = (
                    'Incorrect pickup code. The code is now locked.'
                )
            else:
                remaining = (
                    PickupCode.MAX_ATTEMPTS
                    - pickup_code.failed_attempts
                )
                verification_error = (
                    f'Incorrect pickup code. {remaining} attempt(s) remaining.'
                )

    # Raise only after the transaction commits.
    if verification_error:
        raise ValidationError(verification_error)

    # PHASE 2: Perform the complete handover transaction.
    with transaction.atomic():

        claim = Claim.objects.select_for_update().get(
            pk=claim_id
        )

        item = Item.objects.select_for_update().get(
            pk=claim.item_id
        )

        pickup_code = PickupCode.objects.select_for_update().get(
            claim=claim
        )

        # Recheck everything while holding the locks.
        if claim.status != Claim.Status.APPROVED:
            raise ValidationError(
                'Only approved claims can be handed over.'
            )

        if item.report_type != Item.ReportType.FOUND:
            raise ValidationError(
                'Only found items can be handed over.'
            )

        if item.status != Item.Status.OPEN:
            raise ValidationError(
                'This item is no longer available for handover.'
            )

        if item.lifecycle_status != Item.LifecycleStatus.CLAIMED:
            raise ValidationError(
                'The item must have a claimed lifecycle status.'
            )

        if pickup_code.is_locked:
            raise ValidationError('This pickup code is locked.')

        if pickup_code.used_at is not None:
            raise ValidationError('This pickup code has already been used.')

        if pickup_code.expires_at <= timezone.now():
            raise ValidationError('This pickup code has expired.')

        if not check_password(
            submitted_code.strip(),
            pickup_code.code_hash
        ):
            raise ValidationError(
                'Pickup-code verification failed. Please try again.'
            )

        if Handover.objects.filter(claim=claim).exists():
            raise ValidationError(
                'A handover has already been recorded for this claim.'
            )

        # Lock and validate the explicitly linked lost report.
        lost_report = None

        if claim.linked_lost_report_id:
            lost_report = Item.objects.select_for_update().get(
                pk=claim.linked_lost_report_id
            )

            if lost_report.report_type != Item.ReportType.LOST:
                raise ValidationError(
                    'The linked report must be a lost-item report.'
                )

            if lost_report.status != Item.Status.OPEN:
                raise ValidationError(
                    'The linked lost report is no longer open.'
                )

        # Create the handover record.
        # Handover.save() validates the approved claim and item status.
        claim.item = item

        handover = Handover.objects.create(
            claim=claim,
            recorded_by=actor,
            identity_verified=True,
            verification_method=verification_method,
            collector_identifier=collector_identifier.strip(),
            notes=notes,
        )

        # Invalidate the pickup code.
        pickup_code.used_at = timezone.now()
        pickup_code.save(update_fields=['used_at'])

        # Advance the found item's lifecycle.
        item.transition_lifecycle(
            Item.LifecycleStatus.RETURNED
        )

        item.status = Item.Status.RESOLVED
        item.save(update_fields=['status', 'updated_at'])

        # Close the explicitly linked lost report, if one exists.
        if lost_report:
            lost_report.status = Item.Status.CLOSED
            lost_report.closed_by = actor
            lost_report.closed_at = timezone.now()
            lost_report.closure_reason = (
                'Closed following successful handover of recovered item '
                f'{item.reference_number}.'
            )

            lost_report.save(update_fields=[
                'status',
                'closed_by',
                'closed_at',
                'closure_reason',
                'updated_at',
            ])

        # Record the completed handover.
        ItemAuditLog.objects.create(
            item=item,
            claim=claim,
            handover=handover,
            actor=actor,
            event_type=ItemAuditLog.EventType.HANDOVER_COMPLETED,
            description=(
                f'Item {item.reference_number} was handed over to '
                f'{claim.claimant.username}.'
            ),
            details={
                'verification_method': verification_method,
                'identity_verified': True,
                'collector_identifier': collector_identifier.strip(),
                'pickup_code_used': True,
            }
        )

        # Record the found item's lifecycle change.
        ItemAuditLog.objects.create(
            item=item,
            claim=claim,
            handover=handover,
            actor=actor,
            event_type=ItemAuditLog.EventType.ITEM_RETURNED,
            description=(
                f'Item {item.reference_number} lifecycle changed '
                'to RETURNED.'
            ),
            details={
                'previous_lifecycle_status': 'CLAIMED',
                'new_lifecycle_status': 'RETURNED',
            }
        )

        # Record the linked lost-report closure.
        if lost_report:
            ItemAuditLog.objects.create(
                item=item,
                claim=claim,
                handover=handover,
                actor=actor,
                event_type=ItemAuditLog.EventType.LOST_REPORT_CLOSED,
                description=(
                    f'Linked lost report {lost_report.reference_number} '
                    'was closed after handover.'
                ),
                details={
                    'lost_report_id': lost_report.pk,
                    'lost_report_reference': lost_report.reference_number,
                    'new_status': 'CLOSED',
                }
            )

        return handover
