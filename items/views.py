from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import ItemReportForm
from .models import Item
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404


@login_required
def create_item_report(request):

    if request.method == 'POST':
        form = ItemReportForm(request.POST)

        if form.is_valid():
            item = form.save(commit=False)
            item.reported_by = request.user
            item.save()

            return redirect('my_item_reports')

    else:
        form = ItemReportForm()

    return render(
        request,
        'items/item_form.html',
        {'form': form}
    )


@login_required
def my_item_reports(request):
    items = Item.objects.filter(
        reported_by=request.user
    )

    return render(
        request,
        'items/my_reports.html',
        {'items': items}
    )

def browse_items(request):

    items = Item.objects.filter(
        status=Item.Status.OPEN
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

    return render(
        request,
        'items/browse_items.html',
        context
    )

def item_detail(request, item_id):

    item = get_object_or_404(
        Item,
        id=item_id,
        status=Item.Status.OPEN
    )

    return render(
        request,
        'items/item_detail.html',
        {'item': item}
    )