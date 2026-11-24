from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User


ALLOWED_EMAIL_DOMAINS = {
    "students.kcau.ac.ke",
    "kcau.ac.ke",
}


class SchoolEmailMixin:
    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        domain = email.rsplit("@", 1)[-1]

        if domain not in ALLOWED_EMAIL_DOMAINS:
            raise forms.ValidationError(
                "Use your official KCA University email address."
            )

        return email


class RegisterForm(SchoolEmailMixin, UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]


class ProfileUpdateForm(SchoolEmailMixin, forms.ModelForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email"]