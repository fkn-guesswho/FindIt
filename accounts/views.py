from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm, ProfileUpdateForm


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect('login')

    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


@login_required
def dashboard(request):
    return render(request, 'accounts/dashboard.html')


@login_required
def profile(request):
    if request.method == 'POST':
        form = ProfileUpdateForm(
            request.POST,
            instance=request.user
        )

        if form.is_valid():
            form.save()
            return redirect('profile')

    else:
        form = ProfileUpdateForm(instance=request.user)

    return render(request, 'accounts/profile.html', {'form': form})