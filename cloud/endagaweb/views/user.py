"""User login and auth.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import logging

from allauth.account.utils import user_email
from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import ContentType, Permission
from django.contrib.auth.models import User
from django.contrib.auth.views import password_reset, password_reset_confirm
from django.core import urlresolvers
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.core.validators import validate_email
from django.http import HttpResponse, HttpResponseBadRequest
from django.http import JsonResponse
from django.shortcuts import render
from django.shortcuts import render_to_response, redirect
from django.template.context_processors import csrf
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _

from endagaweb.models import UserProfile

logger = logging.getLogger('endagaweb')


def validate_phone(value):
    if (value.startswith('+')):
        value = value[1:]

    if (len(value) < 6 or (not value.isdigit())):
        raise ValidationError(
            _('%(value)s is not a phone number'),
            params={'value': value}, )


def loginview(request):
    """Show the login page.

    If 'next' is a URL parameter, add its value to the context.  (We're
    mimicking the standard behavior of the django login auth view.)
    """
    context = {
        'next': request.GET.get('next', ''),
        'enable_social_login': settings.ENABLE_SOCIAL_LOGIN
    }
    context.update(csrf(request))
    template = get_template("home/login.html")
    html = template.render(context, request)
    return HttpResponse(html)


class WhitelistedSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom social account login handler."""

    def raiseException(self):
        login_url = urlresolvers.reverse('endagaweb-login')
        raise ImmediateHttpResponse(redirect(login_url))

    def pre_social_login(self, request, sociallogin):
        """Invoked after a user successfully auths with a provider, but before
        the login is actually processed on our side and before the
        pre_social_login signal is emitted.

        We use this hook to abort the login if the user is not coming from a
        whitelisted domain.  Otherwise this hook has no effect and the login
        proceeds as normal.

        Args:
          request: (unused)
          sociallogin: an allauth sociallogin instance with user data attached

        Raises:
          ImmediateHttpResponse if user's email domain is not in the whitelist
        """
        social_login_email = user_email(sociallogin.user)
        try:
            domain = social_login_email.split('@')[1]
        except:
            logger.warning("User %s, social login failed", social_login_email)
            self.raiseException()

        if domain not in settings.STAFF_EMAIL_DOMAIN_WHITELIST:
            logger.warning("User %s not in approved domain",
                           social_login_email)
            self.raiseException()


def staff_login_view(request):
    """Show the staff login page."""
    context = {}
    context.update(csrf(request))
    return render_to_response("home/staff-login.html", context)


def auth_and_login(request):
    """Handles POSTed credentials for login."""
    user = authenticate(username=request.POST['email'],
                        password=request.POST['password'])
    if user:
        login(request, user)
        next_url = '/dashboard'
        if 'next' in request.POST and request.POST['next']:
            next_url = request.POST['next']

        # Notification, if blocked user is trying to log in
        if not user.is_active:
            text = "This user is blocked. Please contact admin."
            messages.error(request, text)
        return redirect(next_url)
    else:
        text = "Sorry, that email / password combination is not valid."
        messages.error(request, text)
        return redirect('/login/')


@login_required(login_url='/login/')
def change_password(request):
    """Handles password change request data."""
    if request.method != 'POST':
        return HttpResponseBadRequest()
    # Make sure we have all parameters
    required_params = ('old_password', 'new_password1', 'new_password2')
    if not all([param in request.POST for param in required_params]):
        return HttpResponseBadRequest()
    # Validate
    redirect_url = '/dashboard/profile'
    if not request.user.check_password(request.POST['old_password']):
        text = 'Error: old password is incorrect.'
        tags = 'password alert alert-danger'
        messages.error(request, text, extra_tags=tags)
        return redirect(redirect_url)
    if request.POST['new_password1'] != request.POST['new_password2']:
        text = 'Error: new passwords do not match.'
        tags = 'password alert alert-danger'
        messages.error(request, text, extra_tags=tags)
        return redirect(redirect_url)
    if request.POST['new_password1'] == '':
        text = 'Error: new password is not valid.'
        tags = 'password alert alert-danger'
        messages.error(request, text, extra_tags=tags)
        return redirect(redirect_url)
    # Everything checks out, change the password.
    request.user.set_password(request.POST['new_password1'])
    request.user.save()
    text = 'Password changed successfully.'
    tags = 'password alert alert-success'
    messages.success(request, text, extra_tags=tags)
    return redirect(redirect_url)


@login_required(login_url='/login/')
def update_contact(request):
    """Handles a user changing their background contact info."""
    if request.method == 'POST':
        if 'email' in request.POST:
            try:
                validate_email(request.POST['email'])
                request.user.email = request.POST['email']
            except ValidationError:
                messages.error(request, "Invalid email address.",
                               extra_tags="contact alert alert-danger")
                return redirect("/dashboard/profile")
        if 'first_name' in request.POST:
            request.user.first_name = request.POST['first_name']
        if 'last_name' in request.POST:
            request.user.last_name = request.POST['last_name']
        user_profile = UserProfile.objects.get(user=request.user)
        if 'timezone' in request.POST:
            user_profile.timezone = request.POST['timezone']
        user_profile.save()
        request.user.save()
        messages.success(request, "Profile information updated.",
                         extra_tags="contact alert alert-success")
        return redirect("/dashboard/profile")
    return HttpResponseBadRequest()


@login_required(login_url='/login/')
def update_notify_emails(request):
    if request.method == 'POST':
        if 'notify_emails' in request.POST:
            notify_emails = request.POST['notify_emails'].strip();
            if not notify_emails == "":
                for current_email in notify_emails.split(','):
                    try:
                        validate_email(current_email.strip())
                    except ValidationError:
                        messages.error(request,
                                       "Invalid email address: '" + current_email +
                                       "'. Example of a valid input is 'shaddi@example.com, damian@example.com'",
                                       extra_tags="alert alert-danger notify-emails")
                        return redirect("/dashboard/profile")
            network = UserProfile.objects.get(user=request.user).network
            network.notify_emails = notify_emails
            network.save()
            messages.success(request, "Notify emails updated.",
                             extra_tags="alert alert-success notify-emails")
            return redirect("/dashboard/profile")
    return HttpResponseBadRequest()


@login_required(login_url='/login/')
def update_notify_numbers(request):
    if request.method == 'POST':
        if 'notify_numbers' in request.POST:
            notify_numbers = request.POST['notify_numbers'].strip()
            if not notify_numbers == "":
                for current_number in notify_numbers.split(','):
                    try:
                        validate_phone(current_number.strip())
                    except ValidationError:
                        messages.error(request,
                                       "Invalid phone number: '" + current_number +
                                       "'. Example of valid input is '+62000000, +52000000, +63000000'",
                                       extra_tags="alert alert-danger notify-numbers")
                        return redirect("/dashboard/profile")
            network = UserProfile.objects.get(user=request.user).network
            network.notify_numbers = notify_numbers
            network.save()
            messages.success(request, "Notify numbers updated.",
                             extra_tags="alert alert-success notify-numbers")
            return redirect("/dashboard/profile")
    return HttpResponseBadRequest()


@login_required(login_url='/login/')
def check_user(request):
    if request.method == 'GET':
        context = {}
        if 'email' in request.GET:
            if User.objects.filter(email=request.GET['email']).exists():
                context['email_available'] = False
            else:
                context['email_available'] = True
        elif 'username' in request.GET:
            if User.objects.filter(username=request.GET['username']).exists():
                context['username_available'] = False
            else:
                context['username_available'] = True

        return JsonResponse(context)
    return HttpResponseBadRequest()


# This view handles the password reset.
def reset(request):
    return password_reset(request,
                          email_template_name=
                          'dashboard/user_management/reset_email.html',
                          subject_template_name=
                          'dashboard/user_management/reset_subject.txt',
                          post_reset_redirect=reverse('user-management'))


# This view handles the changing password to reset.
def reset_confirm(request, uidb64=None, token=None):
    return password_reset_confirm(request, uidb64=uidb64,
                                  template_name=
                                  'dashboard/user_management/reset_confirm.html',
                                  token=token, post_reset_redirect=
                                  reverse('success'))


def success(request):
    return render(request, "dashboard/user_management/success.html")


@login_required(login_url='/login/')
def role_default_permissions(request):
    if request.method == 'GET':
        role = request.GET['role']
        permission_set = ['credit', 'graph', 'report', "smsbroadcast", "tower",
                          "bts", "subscriber", "network",
                          "notification", "usageevent"]

        business_analyst = ['view_graph', 'view_report', 'view_bts',
                            'view_subscriber', 'view_network']

        loader = ['view_graph', 'view_report', 'view_bts', 'view_subscriber',
                  'view_network', 'change_subscriber', 'change_network',
                  'add_subscriber', 'add_sms', 'add_credit', 'download_graph']

        partner = ['view_graph', 'view_report', 'view_bts', 'view_subscriber',
                   'view_network', 'edit_subscriber', 'edit_network',
                   'add_subscriber', 'add_sms', 'download_graph']

        content_type = ContentType.objects.filter(app_label='endagaweb',
                                                  model__in=
                                                  permission_set).values_list('id', flat=True)
        permission = Permission.objects.filter(
            content_type__in=content_type).values_list('id', flat=True)
        role_permission = []
        if role == 'Business Analyst':
            role_permission = Permission.objects.filter(
                codename__in=business_analyst).values_list('id', flat=True)
        elif role == 'Loader':
            role_permission = Permission.objects.filter(
                codename__in=loader).values_list('id', flat=True)
        elif role == 'Partner':
            role_permission = Permission.objects.filter(
                codename__in=partner).values_list('id', flat=True)
        else:
            for i in permission:
                role_permission.append(i)

        return JsonResponse({'permissions': list(role_permission)})
    return HttpResponseBadRequest()
