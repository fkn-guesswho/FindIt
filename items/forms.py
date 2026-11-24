
from django import forms
from .models import Item, Claim, ClosureRequest


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    widget = MultipleImageInput

    def clean(self, data, initial=None):
        if not data:
            return []

        files = data if isinstance(data, (list, tuple)) else [data]

        if len(files) > 5:
            raise forms.ValidationError(
                "You can upload a maximum of 5 images."
            )

        cleaned_files = []

        for uploaded_file in files:
            image = forms.ImageField().clean(uploaded_file)

            if image.size > 5 * 1024 * 1024:
                raise forms.ValidationError(
                    "Each image must be 5 MB or smaller."
                )

            cleaned_files.append(image)

        return cleaned_files


class ItemReportForm(forms.ModelForm):

    images = MultipleImageField(
        required=False,
        label="Item photos (maximum 5)",
        help_text=(
            "You can select up to 5 images. "
            "The first image will be the main thumbnail."
        )
    )

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



class ClaimForm(forms.ModelForm):
    evidence_images = MultipleImageField(
        required=True,
        label="Ownership evidence (maximum 5 images)",
        help_text="Upload up to 5 images that help verify ownership. Each image must be 5 MB or smaller."
    )

    class Meta:
        model = Claim
        fields = ['explanation']

        widgets = {
            'explanation': forms.Textarea(attrs={
                'rows': 5,
                'placeholder': (
                    'Explain how you can identify or '
                    'prove ownership of this item.'
                ),
            }),
        }


class ClosureRequestForm(forms.ModelForm):
    class Meta:
        model = ClosureRequest
        fields = ['reason']

        widgets = {
            'reason': forms.Textarea(attrs={
                'rows': 5,
                'placeholder': (
                    'Explain why this item report should be closed.'
                ),
            }),
        }
