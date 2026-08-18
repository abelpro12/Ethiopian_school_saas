"""
accounts/views.py — First-login forced password change view.
"""
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import render, redirect


from apps.accounts.models import User


@login_required
def force_change_password(request):
    """
    Handles the first-login password change requirement.
    Users with `must_change_password=True` are redirected here by the
    ForcePasswordChangeMiddleware until they set a new password.
    """
    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            user.must_change_password = False
            user.save(update_fields=['must_change_password'])
            # Keep the session alive so the user is not logged out
            update_session_auth_hash(request, user)
            messages.success(
                request,
                'Your password has been updated successfully. Welcome!'
            )
            return redirect('/')
    else:
        form = PasswordChangeForm(user=request.user)

    return render(request, 'accounts/force_change_password.html', {'form': form})


@login_required
def update_my_credentials(request):
    """
    Allows any logged-in user (Super Admin, School Admin, Principal, etc.)
    to update their own username and/or password.
    """
    if request.method == 'POST':
        new_username = request.POST.get('new_username', '').strip().lower()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        user = request.user
        updated = False

        # Username update
        if new_username and new_username != user.username:
            if len(new_username) < 3:
                messages.error(request, "Username must be at least 3 characters long.")
                referer = request.META.get('HTTP_REFERER') or '/'
                return redirect(referer)
            if User.objects.filter(username=new_username).exclude(id=user.id).exists():
                messages.error(request, f"Username '{new_username}' is already taken. Please choose another username.")
                referer = request.META.get('HTTP_REFERER') or '/'
                return redirect(referer)
            
            old_un = user.username
            user.username = new_username
            user.save(update_fields=['username'])
            updated = True
            messages.success(request, f"Your username was changed from '{old_un}' to '{new_username}'.")

        # Password update
        if new_password:
            if len(new_password) < 6:
                messages.error(request, "New password must be at least 6 characters long.")
                referer = request.META.get('HTTP_REFERER') or '/'
                return redirect(referer)
            if confirm_password and new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
                referer = request.META.get('HTTP_REFERER') or '/'
                return redirect(referer)

            user.set_password(new_password)
            user.save()
            update_session_auth_hash(request, user)
            updated = True
            messages.success(request, "Your password was updated successfully.")

        if not updated:
            messages.info(request, "No changes were made to your account.")

    referer = request.META.get('HTTP_REFERER') or '/'
    return redirect(referer)
