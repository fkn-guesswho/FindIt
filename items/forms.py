from django import forms
from .models import Item


class ItemReportForm(forms.ModelForm):

    class Meta:
        model = Item

        fields = [
            'title',
            'description',
            'category',
            'report_type',
            'campus',
            'building',
            'specific_location',
            'date_occurred',
        ]

        widgets = {
            'date_occurred': forms.DateInput(
                attrs={'type': 'date'}
            ),
        }