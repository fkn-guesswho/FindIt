
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404

from .forms import ItemReportForm, ClaimForm
from .models import Item, Claim, ItemImage

@login_required
def create_item_report(request):
    if request.method == 'POST':
        form = ItemReportForm(request.POST, request.FILES)

        if form.is_valid():
            uploaded_images = form.cleaned_data['images']

            item = form.save(commit=False)
            item.reported_by = request.user

            if uploaded_images:
                item.image = uploaded_images[0]

            item.save()

            for uploaded_image in uploaded_images[1:]:
                ItemImage.objects.create(
                    item=item,
                    image=uploaded_image
                )

            return redirect('my_item_reports')
    else:
        form = ItemReportForm()

    return render(request, 'items/item_form.html', {
        'form': form
    })

@login_required
def my_item_reports(request):
    items = Item.objects.filter(reported_by=request.user)
    return render(request, 'items/my_reports.html', {'items': items})


def browse_items(request):
    items = Item.objects.filter(
        status=Item.Status.OPEN,
        visibility=Item.Visibility.PUBLIC
    )

    search_query = request.GET.get('q', '').strip()
    report_type = request.GET.get('type', '')
    category = request.GET.get('category', '')

    if search_query:
        items = items.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    if report_type in Item.ReportType.values:
        items = items.filter(report_type=report_type)

    if category in Item.Category.values:
        items = items.filter(category=category)

    context = {
        'items': items,
        'search_query': search_query,
        'selected_type': report_type,
        'selected_category': category,
        'categories': Item.Category.choices,
    }

    return render(request, 'items/browse_items.html', context)


def item_detail(request, item_id):
    item = get_object_or_404(
        Item,
        id=item_id,
        status=Item.Status.OPEN
    )

    if item.visibility == Item.Visibility.PRIVATE:
        is_owner = (
            request.user.is_authenticated
            and request.user == item.reported_by
        )
        is_admin = (
            request.user.is_authenticated
            and request.user.is_staff
        )

        if not is_owner and not is_admin:
            raise Http404

    can_claim = (
        request.user.is_authenticated
        and item.report_type == Item.ReportType.FOUND
        and item.visibility == Item.Visibility.PUBLIC
        and request.user != item.reported_by
    )

    return render(request, 'items/item_detail.html', {
        'item': item,
        'can_claim': can_claim,
    })


@login_required
def submit_claim(request, item_id):
    item = get_object_or_404(
        Item,
        id=item_id,
        report_type=Item.ReportType.FOUND,
        status=Item.Status.OPEN,
        visibility=Item.Visibility.PUBLIC
    )

    if item.reported_by == request.user:
        return redirect('item_detail', item_id=item.id)

    existing_claim = Claim.objects.filter(
        item=item,
        claimant=request.user,
        status=Claim.Status.PENDING
    ).exists()

    if existing_claim:
        return redirect('item_detail', item_id=item.id)

    if request.method == 'POST':
        form = ClaimForm(request.POST)

        if form.is_valid():
            claim = form.save(commit=False)
            claim.item = item
            claim.claimant = request.user
            claim.save()

            return redirect('item_detail', item_id=item.id)
    else:
        form = ClaimForm()

    return render(request, 'items/claim_form.html', {
        'form': form,
        'item': item,
    })
