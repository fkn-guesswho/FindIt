from django.contrib.admin.helpers import ActionForm
from django.contrib import admin, messages
from django import forms
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html
from django.core.exceptions import ValidationError

from .models import (
    Item,
    Claim,
    ClaimEvidence,
    ItemImage,
    Handover,
    ClosureRequest,
)

class ItemClosureActionForm(ActionForm):
    closure_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Explain why these reports are being closed...'
        }),
        label='Administrative closure reason'
    )

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):

    list_display = (
        'title',
        'report_type',
        'category',
        'campus',
        'building',
        'status',
        'visibility',
        'reported_by',
        'created_at',
    )

    list_filter = (
        'report_type',
        'category',
        'status',
        'visibility',
        'campus',
    )

    search_fields = (
        'title',
        'description',
        'building',
        'specific_location',
        'reported_by__username',
    )

    list_select_related = ('reported_by',)

    readonly_fields = (
        'status',
        'closed_by',
        'closed_at',
        'closure_reason',
    )

    actions = (
        'close_selected_items',
    )

    action_form = ItemClosureActionForm

    @admin.action(description='Close selected open reports')
    def close_selected_items(self, request, queryset):

        reason = request.POST.get('closure_reason', '').strip()

        if not reason:
            self.message_user(
                request,
                'You must provide an administrative closure reason.',
                messages.ERROR,
            )
            return

        open_items = queryset.filter(
            status=Item.Status.OPEN
        )

        count = 0

        for item in open_items:
            item.status = Item.Status.CLOSED
            item.closed_by = request.user
            item.closed_at = timezone.now()
            item.closure_reason = reason

            item.save(update_fields=[
                'status',
                'closed_by',
                'closed_at',
                'closure_reason',
                'updated_at',
            ])

            count += 1

        self.message_user(
            request,
            f'{count} report(s) closed successfully.',
            messages.SUCCESS,
        )

class ClaimEvidenceInline(admin.TabularInline):
    model = ClaimEvidence
    extra = 0
    can_delete = False

    fields = (
        'image_name',
        'uploaded_at',
        'view_image',
    )

    readonly_fields = (
        'image_name',
        'uploaded_at',
        'view_image',
    )

    @admin.display(description='Evidence file')
    def image_name(self, obj):
        if not obj or not obj.pk:
            return '-'

        return obj.image.name

    @admin.display(description='Evidence')
    def view_image(self, obj):
        if not obj or not obj.pk:
            return '-'

        url = reverse(
            'view_claim_evidence',
            args=[obj.pk]
        )

        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">View evidence image</a>',
            url
        )


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'item',
        'claimant',
        'status',
        'created_at',
        'reviewed_by',
        'reviewed_at',
    )

    list_filter = (
        'status',
        'created_at',
        'reviewed_at',
    )

    search_fields = (
        'item__title',
        'claimant__username',
        'claimant__email',
        'explanation',
    )

    list_select_related = (
        'item',
        'claimant',
        'reviewed_by',
    )

    readonly_fields = (
        'created_at',
        'reviewed_by',
        'reviewed_at',
    )

    fields = (
        'item',
        'claimant',
        'explanation',
        'status',
        'admin_notes',
        'created_at',
        'reviewed_by',
        'reviewed_at',
    )

    inlines = (ClaimEvidenceInline,)

    actions = (
        'approve_claims',
        'reject_claims',
    )

    @admin.action(description='Approve selected pending claims')
    def approve_claims(self, request, queryset):
        pending_claims = queryset.filter(
            status=Claim.Status.PENDING
        )

        count = 0

        for claim in pending_claims:
            claim.status = Claim.Status.APPROVED
            claim.reviewed_by = request.user
            claim.reviewed_at = timezone.now()

            claim.save(update_fields=[
                'status',
                'reviewed_by',
                'reviewed_at',
            ])

            count += 1

        self.message_user(
            request,
            f'{count} claim(s) approved.',
            messages.SUCCESS,
        )

    @admin.action(description='Reject selected pending claims')
    def reject_claims(self, request, queryset):
        pending_claims = queryset.filter(
            status=Claim.Status.PENDING
        )

        count = 0

        for claim in pending_claims:
            claim.status = Claim.Status.REJECTED
            claim.reviewed_by = request.user
            claim.reviewed_at = timezone.now()

            claim.save(update_fields=[
                'status',
                'reviewed_by',
                'reviewed_at',
            ])

            count += 1

        self.message_user(
            request,
            f'{count} claim(s) rejected.',
            messages.SUCCESS,
        )


    def save_model(self, request, obj, form, change):
        if change:
            previous = Claim.objects.get(pk=obj.pk)

            if (
                previous.status == Claim.Status.PENDING
                and obj.status in [
                    Claim.Status.APPROVED,
                    Claim.Status.REJECTED,
                ]
            ):
                obj.reviewed_by = request.user
                obj.reviewed_at = timezone.now()

            elif obj.status == Claim.Status.PENDING:
                obj.reviewed_by = None
                obj.reviewed_at = None

        super().save_model(request, obj, form, change)


@admin.register(ItemImage)
class ItemImageAdmin(admin.ModelAdmin):
    list_display = (
        'item',
        'uploaded_at',
    )

    search_fields = ('item__title',)

@admin.register(Handover)
class HandoverAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'claim',
        'get_item',
        'get_claimant',
        'recorded_by',
        'handed_over_at',
    )

    list_filter = ('handed_over_at',)

    search_fields = (
        'claim__item__title',
        'claim__claimant__username',
    )

    list_select_related = (
        'claim',
        'claim__item',
        'claim__claimant',
        'recorded_by',
    )

    fields = (
        'claim',
        'identity_verified',
        'notes',
        'recorded_by',
        'handed_over_at',
    )

    readonly_fields = (
        'recorded_by',
        'handed_over_at',
    )

    @admin.display(description='Item')
    def get_item(self, obj):
        return obj.claim.item.title

    @admin.display(description='Claimant')
    def get_claimant(self, obj):
        return obj.claim.claimant.username

    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user

        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        if obj is not None:
            return False

        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(ClosureRequest)
class ClosureRequestAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'item',
        'requested_by',
        'status',
        'created_at',
        'reviewed_by',
        'reviewed_at',
    )

    list_filter = (
        'status',
        'created_at',
        'reviewed_at',
    )

    search_fields = (
        'item__title',
        'requested_by__username',
        'reason',
    )

    list_select_related = (
        'item',
        'requested_by',
        'reviewed_by',
    )

    readonly_fields = (
        'item',
        'requested_by',
        'reason',
        'status',
        'created_at',
        'reviewed_by',
        'reviewed_at',
    )

    fields = (
        'item',
        'requested_by',
        'reason',
        'status',
        'review_notes',
        'admin_closure_reason',
        'created_at',
        'reviewed_by',
        'reviewed_at',
    )

    actions = (
        'approve_closure_requests',
        'reject_closure_requests',
    )

    @admin.action(description='Approve selected pending closure requests')
    def approve_closure_requests(self, request, queryset):

        approved = 0
        skipped = 0

        for closure in queryset.filter(
            status=ClosureRequest.Status.PENDING
        ):
            try:
                closure.review(
                    reviewer=request.user,
                    decision=ClosureRequest.Status.APPROVED,
                )
                approved += 1

            except ValidationError:
                skipped += 1

        if approved:
            self.message_user(
                request,
                f'{approved} closure request(s) approved.',
                messages.SUCCESS,
            )

        if skipped:
            self.message_user(
                request,
                f'{skipped} request(s) could not be approved because their reports were no longer open or the requests had already been reviewed.',
                messages.WARNING,
            )

    @admin.action(description='Reject selected pending closure requests')
    def reject_closure_requests(self, request, queryset):

        rejected = 0

        for closure in queryset.filter(
            status=ClosureRequest.Status.PENDING
        ):
            try:
                closure.review(
                    reviewer=request.user,
                    decision=ClosureRequest.Status.REJECTED,
                )
                rejected += 1

            except ValidationError:
                continue

        if rejected:
            self.message_user(
                request,
                f'{rejected} closure request(s) rejected.',
                messages.SUCCESS,
            )

    def get_readonly_fields(self, request, obj=None):

        readonly = list(super().get_readonly_fields(request, obj))

        if obj and obj.status != ClosureRequest.Status.PENDING:
            readonly.extend([
                'review_notes',
                'admin_closure_reason',
            ])

        return readonly

    def save_model(self, request, obj, form, change):

        if change:
            previous = ClosureRequest.objects.get(pk=obj.pk)

            if previous.status != ClosureRequest.Status.PENDING:
                self.message_user(
                    request,
                    'Reviewed closure requests are read-only.',
                    messages.WARNING,
                )
                return

        super().save_model(request, obj, form, change)