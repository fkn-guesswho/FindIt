
from django import forms
from .models import Item, Claim, ClosureRequest, CustodyRecord, Handover


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
            'colour',
            'brand',
            'distinguishing_marks',
            'private_identifying_details',
            'current_holding_location',
            'campus',
            'building',
            'specific_location',
            'date_occurred',
        ]

        widgets = {
            'date_occurred': forms.DateInput(
                attrs={'type': 'date'}
            ),
            'colour': forms.TextInput(attrs={
                'placeholder': 'e.g. Black, navy blue'
            }),
            'brand': forms.TextInput(attrs={
                'placeholder': 'e.g. HP, Samsung, Nike'
            }),
            'distinguishing_marks': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Describe scratches, stickers, patterns, etc.'
            }),
            'private_identifying_details': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': (
                    'Enter identifying details known only to the owner '
                    'or someone who can verify ownership.'
                )
            }),
            'current_holding_location': forms.TextInput(attrs={
                'placeholder': (
                    'e.g. Currently with finder, Security Office'
                )
            }),
        }

    def clean(self):
        cleaned_data = super().clean()

        report_type = cleaned_data.get('report_type')

        if report_type == Item.ReportType.FOUND:
            if not cleaned_data.get('private_identifying_details', '').strip():
                self.add_error(
                    'private_identifying_details',
                    'Private identifying details are required for found items.'
                )

            if not cleaned_data.get('current_holding_location', '').strip():
                self.add_error(
                    'current_holding_location',
                    'Please indicate where the found item is currently held.'
                )

        elif report_type == Item.ReportType.LOST:
            cleaned_data['private_identifying_details'] = ''
            cleaned_data['current_holding_location'] = ''

        return cleaned_data




class ClaimForm(forms.ModelForm):
    evidence_images = MultipleImageField(
        required=False,
        label="Ownership evidence (maximum 5 images)",
        help_text="Upload up to 5 images that help verify ownership. Each image must be 5 MB or smaller."
    )

    hidden_detail_answer = forms.CharField(
        label="Hidden identifying detail",
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text="Describe the private identifying detail of the item."
    )

    other_identifying_features = forms.CharField(
        required=False,
        label="Other identifying features",
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text="Describe at least one other feature that helps identify the item."
    )

    class Meta:
        model = Claim
        fields = [
            'explanation',
            'hidden_detail_answer',
            'other_identifying_features',
        ]

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


class CustodyConfirmationForm(forms.ModelForm):
    class Meta:
        model = CustodyRecord
        fields = ['storage_location', 'notes']

        widgets = {
            'storage_location': forms.TextInput(attrs={
                'placeholder': 'e.g. Security Office, Cabinet A'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Optional notes about the item received'
            }),
        }



class HandoverForm(forms.Form):

    submitted_code = forms.CharField(
        max_length=12,
        min_length=12,
        label='Pickup code',
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter the claimant’s 12-character code',
            'autocomplete': 'off',
        })
    )

    identity_verified = forms.BooleanField(
        required=True,
        label='I have physically verified the claimant’s identity.'
    )

    verification_method = forms.ChoiceField(
        choices=Handover.VerificationMethod.choices,
        label='Verification method'
    )

    collector_identifier = forms.CharField(
        max_length=100,
        required=False,
        label='Collector admission number / staff number',
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter identifier where applicable'
        })
    )

    notes = forms.CharField(
        required=False,
        label='Handover notes',
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Additional handover details...'
        })
    )
