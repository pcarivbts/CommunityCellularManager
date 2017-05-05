"""Dashboard views.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import datetime
import logging
import time
import urllib
import uuid
import operator

from django.template.loader import get_template
from django.http import HttpResponse, HttpResponseBadRequest, QueryDict, JsonResponse

from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone as django_utils_timezone
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.conf import settings
from django.core import urlresolvers
from django.views.generic import View
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q

import django_tables2 as tables
import csv
import humanize
import pytz
from rest_framework.authtoken.models import Token
import stripe
from ccm.common.currency import parse_credits, humanize_credits, \
    CURRENCIES, Money
from endagaweb.models import (UserProfile, Ledger, Subscriber, UsageEvent,
                              Network, PendingCreditUpdate, Number)
from endagaweb.util.currency import cents2mc
from endagaweb.forms import dashboard_forms as dform
from endagaweb import tasks
from endagaweb.views import django_tables
from guardian.shortcuts import (assign_perm, get_objects_for_user,
                                get_users_with_perms)

from django.contrib.auth.models import User, Permission, ContentType, Group
from django.db.models.signals import post_save
from django.db import transaction


class ProtectedView(View):
    """ A class-based view that requires a login. """

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProtectedView, self).dispatch(*args, **kwargs)


"""
Views for logged in users.
"""

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_API_KEY


# views
@login_required
def addcard(request):
    if request.method == 'POST':
        token = request.POST['stripe_token[id]']
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        if network.update_card(token):
            messages.add_message(request, messages.INFO, "addcard_saved",
                                 extra_tags="billing_resp_code")
            return redirect("/dashboard/billing")
        else:
            # The card has been declined
            messages.add_message(request, messages.ERROR,
                                 "addcard_stripe_declined",
                                 extra_tags="billing_resp_code")
            return redirect("/dashboard/billing")
    else:
        return HttpResponseBadRequest()


@login_required
def addmoney(request):
    if request.method == 'POST':
        amt = cents2mc(int(float(request.POST['amount']) * 100))
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        try:
            charge = network.authorize_card(amt, "credit", "Add Credit")
            network.add_credit(amt)
            network.capture_charge(charge.id)
            messages.add_message(request, messages.SUCCESS,
                                 "addmoney_stripe_success",
                                 extra_tags="billing_resp_code")
            return redirect("/dashboard/billing")
        except stripe.StripeError:
            logger.error("Failed to add money, stripe.CardError: %s", request)
            messages.add_message(request, messages.WARNING,
                                 "addmoney_stripe_error",
                                 extra_tags="billing_resp_code")
            return redirect("/dashboard/billing")
    else:
        return HttpResponseBadRequest()


@login_required
def dashboard_view(request):
    """Main dashboard page with graph of network activity.

    The js on the template itself gets the data for the graph using the stats
    API.  We also load the server's notion of the current time so that we don't
    have to rely on the user's clock.
    """
    user_profile = UserProfile.objects.get(user=request.user)
    network = user_profile.network
    timezone_offset = pytz.timezone(user_profile.timezone).utcoffset(
        datetime.datetime.now()).total_seconds()
    # Determine if there has been any activity on the network (if not, we won't
    # show the graphs).
    network_has_activity = UsageEvent.objects.filter(
        network=network).exists()
    context = {
        'networks': get_objects_for_user(request.user,
                                         'view_network', klass=Network),
        'user_profile': user_profile,
        'network_id': network.id,
        'current_time_epoch': int(time.time()),
        'timezone_offset': timezone_offset,
        'network_has_activity': network_has_activity,
    }
    template = get_template("dashboard/index.html")
    html = template.render(context, request)
    return HttpResponse(html)


@login_required
def profile_view(request):
    """Shows the operator profile settings.

    Allows one to change email, name, password and timezone.
    """
    user_profile = UserProfile.objects.get(user=request.user)
    contact_form = dform.UpdateContactForm({
        'email': request.user.email,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'timezone': user_profile.timezone
    })
    context = {
        'networks': get_objects_for_user(request.user,
                                         'view_network', klass=Network),
        'user_profile': user_profile,
        'network': user_profile.network,
        'contact_form': contact_form,
        'change_pass_form': dform.ChangePasswordForm(request.user),
        'update_notify_emails_form': dform.NotifyEmailsForm(
            {'notify_emails': user_profile.network.notify_emails}),
        'update_notify_numbers_form': dform.NotifyNumbersForm(
            {'notify_numbers': user_profile.network.notify_numbers}),
    }
    template = get_template("dashboard/profile.html")
    html = template.render(context, request)
    return HttpResponse(html)


@login_required
def billing_view(request):
    """Shows CC info and transaction history."""
    user_profile = UserProfile.objects.get(user=request.user)
    network = user_profile.network
    transactions = (network.ledger.transaction_set.filter(
        kind__in=["credit", "adjustment"]).order_by('-created'))
    transaction_paginator = Paginator(transactions, 10)

    page = request.GET.get('page', 1)
    try:
        transactions = transaction_paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        transactions = transaction_paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        num_pages = transaction_paginator.num_pages
        transactions = transaction_paginator.page(num_pages)
    context = {
        'networks': get_objects_for_user(request.user,
                                         'view_network', klass=Network),
        'user_profile': user_profile,
        'transactions': transactions
    }

    # deal with messages; template needs to explicitly handle messages
    msgs = messages.get_messages(request)
    for m in msgs:
        if "billing_resp_code" in m.tags:
            context[m.message] = True  # pass the message on to the template as-is

    if network.stripe_card_type == "American Express":
        context['card_type'] = 'AmEx'
    else:
        context['card_type'] = network.stripe_card_type

    # Pass in card types that have icons.
    context['cards_with_icons'] = ['Visa', 'AmEx', 'MasterCard', 'Discover']

    t = get_template("dashboard/billing.html")
    html = t.render(context, request)
    return HttpResponse(html)


@login_required
def subscriber_list_view(request):
    """View the list of Subscribers at /dashboard/subscribers.

    You can pass 'query' as a GET request parameter -- it can contain a
    case-insensitive fragment of a subscriber name, IMSI or number.

    Args:
       request: (type?)

    Returns:
       an HttpResponse
    """

    user_profile = UserProfile.objects.get(user=request.user)
    network = user_profile.network
    all_subscribers = Subscriber.objects.filter(network=network)

    query = request.GET.get('query', None)
    if query:
        # Get actual subs with partial IMSI matches or partial name matches.
        query_subscribers = (
            network.subscriber_set.filter(imsi__icontains=query) |
            network.subscriber_set.filter(name__icontains=query))
        # Get ids of subs with partial number matches.
        sub_ids = network.number_set.filter(
            number__icontains=query
        ).values_list('subscriber_id', flat=True)
        # Or them together to get list of actual matching subscribers.
        query_subscribers |= network.subscriber_set.filter(
            id__in=sub_ids)
    else:
        # Display all subscribers.
        query_subscribers = all_subscribers

    # Setup the subscriber table.
    subscriber_table = django_tables.SubscriberTable(list(query_subscribers))
    tables.RequestConfig(request, paginate={'per_page': 15}).configure(
        subscriber_table)

    # Render the response with context.
    context = {
        'networks': get_objects_for_user(request.user,
                                         'view_network', klass=Network),
        'currency': CURRENCIES[network.subscriber_currency],
        'user_profile': user_profile,
        'total_number_of_subscribers': len(all_subscribers),
        'number_of_filtered_subscribers': len(query_subscribers),
        'subscriber_table': subscriber_table,
        'search': dform.SubscriberSearchForm({'query': query}),
    }
    template = get_template("dashboard/subscribers.html")
    html = template.render(context, request)
    return HttpResponse(html)


class SubscriberInfo(ProtectedView):
    """View info on a single subscriber."""

    def get(self, request, imsi=None):
        """Handles GET requests."""
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        try:
            subscriber = Subscriber.objects.get(imsi=imsi,
                                                network=network)
        except Subscriber.DoesNotExist:
            return HttpResponseBadRequest()
        # Set the context with various stats.
        context = {
            'networks': get_objects_for_user(request.user,
                                             'view_network', klass=Network),
            'currency': CURRENCIES[network.subscriber_currency],
            'user_profile': user_profile,
            'subscriber': subscriber,
        }
        try:
            context['created'] = subscriber.usageevent_set.order_by(
                'date')[0].date
        except IndexError:
            context['created'] = None
        # Set usage info (SMS sent, total call duration, data usage).
        sms_kinds = ['free_sms', 'outside_sms', 'incoming_sms', 'local_sms',
                     'local_recv_sms', 'error_sms']
        context['num_sms'] = subscriber.usageevent_set.filter(
            kind__in=sms_kinds).count()
        call_kinds = ['free_call', 'outside_call', 'incoming_call',
                      'local_call', 'local_recv_call', 'error_call']
        calls = subscriber.usageevent_set.filter(kind__in=call_kinds)
        context['number_of_calls'] = len(calls)
        context['voice_sec'] = sum([call.voice_sec() for call in calls])
        gprs_events = subscriber.usageevent_set.filter(kind='gprs')
        up_bytes = sum([g.uploaded_bytes for g in gprs_events])
        down_bytes = sum([g.downloaded_bytes for g in gprs_events])
        context['up_bytes'] = humanize.naturalsize(up_bytes)
        context['down_bytes'] = humanize.naturalsize(down_bytes)
        context['total_bytes'] = humanize.naturalsize(up_bytes + down_bytes)
        # Render template.
        template = get_template('dashboard/subscriber_detail/info.html')
        html = template.render(context, request)
        return HttpResponse(html)


class SubscriberActivity(ProtectedView):
    """View activity for a single subscriber.

    Filtering is achieved by posting data to this CBV.  The view will redirect
    to get with some filtering parameters set.  Date params are formatted in
    two ways: once for the datepicker, another for the URL.
    """
    datepicker_time_format = '%Y-%m-%d at %I:%M%p'
    url_time_format = '%Y-%m-%d-at-%I.%M%p'

    def post(self, request, imsi=None):
        """Handles POST requests for activity filtering.

        Reads the POSTed params, sets them as URL params and redirects to GET.
        """
        url_params = {}
        if request.POST.get('keyword', None):
            url_params['keyword'] = request.POST.get('keyword')
        if request.POST.get('start_date', None):
            start_date = datetime.datetime.strptime(
                request.POST.get('start_date'), self.datepicker_time_format)
            url_params['start_date'] = start_date.strftime(
                self.url_time_format)
        if request.POST.get('end_date', None):
            end_date = datetime.datetime.strptime(
                request.POST.get('end_date'), self.datepicker_time_format)
            url_params['end_date'] = end_date.strftime(self.url_time_format)
        if request.POST.get('services[]', None):
            # We do some custom encoding of the services list to make the
            # URL look nicer.
            services = request.POST.getlist('services[]')
            url_params['services'] = '-'.join(services)
        kwargs = {
            'imsi': imsi
        }
        base_url = urlresolvers.reverse('subscriber-activity', kwargs=kwargs)
        url = '%s?%s' % (base_url, urllib.urlencode(url_params))
        return redirect(url)

    def get(self, request, imsi=None):
        """Handles GET requests."""
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        try:
            subscriber = Subscriber.objects.get(imsi=imsi,
                                                network=network)
        except Subscriber.DoesNotExist:
            return HttpResponseBadRequest()

        # Queue up the recent events for the subscriber.
        events = subscriber.usageevent_set.all().order_by('-date')
        total_number_of_events = len(events)

        # Progressively filter events by start and end date, if they're
        # specified.  Cast them in the UserProfile's timezone.
        user_profile_timezone = pytz.timezone(user_profile.timezone)
        start_date = request.GET.get('start_date', None)
        if start_date:
            start_date = django_utils_timezone.make_aware(
                datetime.datetime.strptime(start_date, self.url_time_format),
                user_profile_timezone)
            now = datetime.datetime.now(pytz.UTC)
            events = events.filter(date__range=(start_date, now))
        end_date = request.GET.get('end_date', None)
        if end_date:
            end_date = django_utils_timezone.make_aware(
                datetime.datetime.strptime(end_date, self.url_time_format),
                user_profile_timezone)
            years_ago = django_utils_timezone.make_aware(
                datetime.datetime.strptime('Jan 1 2013', '%b %d %Y'),
                user_profile_timezone)
            events = events.filter(date__range=(years_ago, end_date))

        # Filter events by keyword.
        keyword = request.GET.get('keyword', '')
        if keyword:
            events = (events.filter(kind__icontains=keyword) |
                      events.filter(reason__icontains=keyword))

        # Filter the services.  If 'other' is selected, result is
        # !(any excluded options). If 'other' is not selected, result is
        # OR(selected options).
        all_services = set(['sms', 'call', 'gprs', 'transfer', 'other'])
        checked_services = request.GET.get('services', None)
        if checked_services:
            checked_services = set(checked_services.split('-'))
        else:
            # ..just assume that's a mistake and check em all.
            checked_services = all_services
        if "other" in checked_services:
            for excluded_service in all_services - checked_services:
                events = events.exclude(kind__icontains=excluded_service)
        else:
            queryset = [Q(kind__icontains=s) for s in checked_services]
            events = events.filter(reduce(operator.or_, queryset))

        # Setup the activity table with these events.
        subscriber_activity_table = django_tables.SubscriberActivityTable(
            list(events))
        tables.RequestConfig(request, paginate={'per_page': 15}).configure(
            subscriber_activity_table)

        # If start and end dates were specified, reformat them so we can inject
        # them into the datepickers.
        context_start_date, context_end_date = None, None
        if start_date:
            context_start_date = start_date.strftime(
                self.datepicker_time_format)
        if end_date:
            context_end_date = end_date.strftime(self.datepicker_time_format)

        context = {
            'networks': get_objects_for_user(request.user,
                                             'view_network', klass=Network),
            'currency': CURRENCIES[network.subscriber_currency],
            'user_profile': user_profile,
            'subscriber': subscriber,
            'subscriber_activity_table': subscriber_activity_table,
            'total_number_of_events': total_number_of_events,
            'number_of_filtered_events': len(events),
            'keyword': keyword,
            'start_date': context_start_date,
            'end_date': context_end_date,
            'all_services': all_services,
            'checked_services': checked_services,
        }

        template = get_template('dashboard/subscriber_detail/activity.html')
        html = template.render(context, request)
        return HttpResponse(html)


class SubscriberSendSMS(ProtectedView):
    """Send an SMS to a single subscriber."""

    def get(self, request, imsi=None):
        """Handles GET requests."""
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        try:
            subscriber = Subscriber.objects.get(imsi=imsi,
                                                network=network)
        except Subscriber.DoesNotExist:
            return HttpResponseBadRequest()

        initial_form_data = {
            'imsi': subscriber.imsi
        }
        # Set the response context.
        context = {
            'networks': get_objects_for_user(request.user,
                                             'view_network', klass=Network),
            'user_profile': user_profile,
            'subscriber': subscriber,
            'send_sms_form': dform.SubscriberSendSMSForm(
                initial=initial_form_data)
        }
        # Render template.
        template = get_template('dashboard/subscriber_detail/send_sms.html')
        html = template.render(context, request)
        return HttpResponse(html)

    def post(self, request, imsi=None):
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        if 'message' not in request.POST:
            return HttpResponseBadRequest()
        try:
            sub = Subscriber.objects.get(imsi=imsi,
                                         network=network)
        except Subscriber.DoesNotExist:
            return HttpResponseBadRequest()
        # Fire off an async task request to send the SMS.  We send to the
        # subscriber's first number and from some admin number.
        num = sub.number_set.all()[0]
        params = {
            'to': num.number,
            'sender': '0000',
            'text': request.POST['message'],
            'msgid': str(uuid.uuid4())
        }
        url = sub.bts.inbound_url + "/endaga_sms"
        tasks.async_post.delay(url, params)
        params = {
            'imsi': sub.imsi
        }
        url_params = {
            'sent': 'true'
        }
        base_url = urlresolvers.reverse('subscriber-send-sms', kwargs=params)
        url = '%s?%s' % (base_url, urllib.urlencode(url_params))
        return redirect(url)


class SubscriberAdjustCredit(ProtectedView):
    """Adjust credit for a single subscriber."""

    def get(self, request, imsi=None):
        """Handles GET requests."""
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        try:
            subscriber = Subscriber.objects.get(imsi=imsi,
                                                network=network)
        except Subscriber.DoesNotExist:
            return HttpResponseBadRequest()
        # Set the response context.
        pending_updates = subscriber.pendingcreditupdate_set.all().order_by(
            'date')
        initial_form_data = {
            'imsi': subscriber.imsi,
        }
        context = {
            'networks': get_objects_for_user(request.user,
                                             'view_network', klass=Network),
            'currency': CURRENCIES[network.subscriber_currency],
            'user_profile': user_profile,
            'subscriber': subscriber,
            'pending_updates': pending_updates,
            'credit_update_form': dform.SubscriberCreditUpdateForm(
                initial=initial_form_data),
        }
        # Render template.
        template = get_template(
            'dashboard/subscriber_detail/adjust_credit.html')
        html = template.render(context, request)
        return HttpResponse(html)

    def post(self, request, imsi=None):
        """Operators can use this API to add credit to a subscriber.

        These additions become PendingCreditUpdates and celery will try to
        "apply" then by sending the info to the corresponding BTS.  The
        operator may also delete PendingCreditUpdates, effectively canceling
        them.
        """
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        # In all cases we'll redirect back to the adjust-credit page.
        sub = Subscriber.objects.get(imsi=imsi, network=network)
        params = {
            'imsi': sub.imsi
        }
        adjust_credit_redirect = redirect(
            urlresolvers.reverse('subscriber-adjust-credit', kwargs=params))
        # Validate the input.
        if 'amount' not in request.POST:
            return HttpResponseBadRequest()
        error_text = 'Error: credit value must be between -10M and 10M.'
        try:
            currency = network.subscriber_currency
            amount = parse_credits(request.POST['amount'],
                                   CURRENCIES[currency]).amount_raw
            if abs(amount) > 2147483647:
                raise ValueError(error_text)
        except ValueError:
            messages.error(request, error_text)
            return adjust_credit_redirect
        # Validation suceeded, create a PCU and start the update credit task.
        msgid = str(uuid.uuid4())
        credit_update = PendingCreditUpdate(subscriber=sub, uuid=msgid,
                                            amount=amount)
        credit_update.save()
        tasks.update_credit.delay(sub.imsi, msgid)
        return adjust_credit_redirect

    def delete(self, request, imsi=None):
        """Handle the deletion of Pending Credit Updates."""
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        request_data = QueryDict(request.body)
        if "pending_id" not in request_data:
            return HttpResponseBadRequest()
        pending_id = request_data['pending_id']
        try:
            update = PendingCreditUpdate.objects.get(uuid=pending_id)
        except PendingCreditUpdate.DoesNotExist:
            return HttpResponseBadRequest()
        if update.subscriber.network != network:
            return HttpResponseBadRequest()
        update.delete()
        return HttpResponse()


class SubscriberEdit(ProtectedView):
    """Edit a single subscriber's info."""

    def get(self, request, imsi=None):
        """Handles GET requests."""
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        try:
            subscriber = Subscriber.objects.get(imsi=imsi,
                                                network=network)
        except Subscriber.DoesNotExist:
            return HttpResponseBadRequest()
        # Set the response context.
        initial_form_data = {
            'imsi': subscriber.imsi,
            'name': subscriber.name,
            'prevent_automatic_deactivation': (
                subscriber.prevent_automatic_deactivation),
        }
        context = {
            'networks': get_objects_for_user(request.user,
                                             'view_network', klass=Network),
            'user_profile': user_profile,
            'subscriber': subscriber,
            'subscriber_info_form': dform.SubscriberInfoForm(
                initial=initial_form_data),
            'network_version': (
                subscriber.network.get_lowest_tower_version()),
        }
        # Render template.
        template = get_template(
            'dashboard/subscriber_detail/edit.html')
        html = template.render(context, request)
        return HttpResponse(html)

    def post(self, request, imsi=None):
        """Handles POST requests to change subscriber info."""
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        try:
            subscriber = Subscriber.objects.get(imsi=imsi,
                                                network=network)
        except Subscriber.DoesNotExist:
            return HttpResponseBadRequest()
        if (request.POST.get('name') and
                    subscriber.name != request.POST.get('name')):
            subscriber.name = request.POST.get('name')
            subscriber.save()
        if request.POST.get('prevent_automatic_deactivation'):
            protected = (
                request.POST.get('prevent_automatic_deactivation') == 'True')
            subscriber.prevent_automatic_deactivation = protected
            subscriber.save()
        messages.success(request, "Subscriber information updated.",
                         extra_tags="alert alert-success")
        kwargs = {
            'imsi': imsi
        }
        return redirect(urlresolvers.reverse('subscriber-edit', kwargs=kwargs))


class ActivityView(ProtectedView):
    """View activity on the network."""

    datepicker_time_format = '%Y-%m-%d at %I:%M%p'

    def get(self, request, *args, **kwargs):
        return self._handle_request(request)

    def post(self, request, *args, **kwargs):
        return self._handle_request(request)

    def _handle_request(self, request):
        """Process request.

        We want filters to persist even when someone changes pages without
        re-submitting the form. Page changes will always come over a GET
        request, not a POST.
         - If it's a GET, we should try to pull settings from the session.
         - If it's a POST, we should replace whatever is in the session.
         - If it's a GET with no page, we should blank out the session.
        """
        profile = UserProfile.objects.get(user=request.user)
        network = profile.network
        # Process parameters.
        # We want filters to persist even when someone changes pages without
        # re-submitting the form. Page changes will always come over a GET
        # request, not a POST.
        # - If it's a GET, we should try to pull settings from the session.
        # - If it's a POST, we should replace whatever is in the session.
        # - If it's a GET with no page variable, we should blank out the
        #   session.
        if request.method == "POST":
            page = 1
            request.session['keyword'] = request.POST.get('keyword', None)
            request.session['start_date'] = request.POST.get('start_date',
                                                             None)
            request.session['end_date'] = request.POST.get('end_date', None)
            request.session['services'] = request.POST.getlist('services[]',
                                                               None)
            # We always just do a redirect to GET. We include page reference
            # to retain the search parameters in the session.
            return redirect(urlresolvers.reverse('network-activity') +
                            "?page=1")

        elif request.method == "GET":
            page = request.GET.get('page', 1)
            if 'page' not in request.GET:
                # Reset filtering params.
                request.session['keyword'] = None
                request.session['start_date'] = None
                request.session['end_date'] = None
                request.session['services'] = None
        else:
            return HttpResponseBadRequest()

        # Determine if there has been any activity on the network (if not, we
        # won't show the filter boxes).
        network_has_activity = UsageEvent.objects.filter(
            network=network).exists()
        # Read filtering params out of the session.
        keyword = request.session['keyword']
        start_date = request.session['start_date']
        end_date = request.session['end_date']
        services = request.session['services']
        events = self._get_events(profile, keyword, start_date, end_date,
                                  services)
        event_count = events.count()

        currency = CURRENCIES[network.subscriber_currency]

        # If a CSV has been requested, return that here.
        # TODO(shaddi): Kind of a hack, probably should be exposed as REST API
        if request.method == "GET" and request.GET.get('csv', False):
            headers = [
                'Transaction ID',
                'Day',
                'Time',
                'Time Zone',
                'Subscriber IMSI',
                'BTS Identifier',
                'BTS Name',
                'Type of Event',
                'Description',
                'From Number',
                'To Number',
                'Billable Call Duration (sec)',
                'Total Call Duration (sec)',
                'Tariff (%s)' % (currency,),
                'Cost (%s)' % (currency,),
                'Prior Balance (%s)' % (currency,),
                'Final Balance (%s)' % (currency,),
                'Bytes Uploaded',
                'Bytes Downloaded',
            ]
            response = HttpResponse(content_type='text/csv')
            # TODO(shaddi): use a filename that captures the search terms?
            response['Content-Disposition'] = ('attachment;filename='
                                               '"etage-%s.csv"') \
                                              % (datetime.datetime.now().date(),)
            writer = csv.writer(response)
            writer.writerow(headers)
            # Forcibly limit to 7000 items.
            timezone = pytz.timezone(profile.timezone)
            for e in events[:7000]:
                # first strip the IMSI off if present
                subscriber = e.subscriber_imsi
                if e.subscriber_imsi.startswith('IMSI'):
                    subscriber = e.subscriber_imsi[4:]

                tz_date = django_utils_timezone.localtime(e.date, timezone)

                writer.writerow([
                    e.transaction_id,
                    tz_date.date().strftime("%m-%d-%Y"),
                    tz_date.time().strftime("%I:%M:%S %p"),
                    timezone,
                    subscriber,
                    e.bts_uuid,
                    e.bts.nickname if e.bts else "<deleted BTS>",
                    e.kind,
                    e.reason,
                    e.from_number,
                    e.to_number,
                    e.billsec,
                    e.call_duration,
                    humanize_credits(e.tariff, currency=currency).amount_str()
                    if e.tariff else None,
                    humanize_credits(e.change, currency=currency).amount_str()
                    if e.change else None,
                    humanize_credits(e.oldamt, currency=currency).amount_str()
                    if e.oldamt else None,
                    humanize_credits(e.newamt, currency=currency).amount_str()
                    if e.newamt else None,
                    e.uploaded_bytes,
                    e.downloaded_bytes,
                ])
            return response
        # Otherwise, we paginate.
        event_paginator = Paginator(events, 25)
        try:
            events = event_paginator.page(page)
        except PageNotAnInteger:
            # If page is not an integer, deliver first page.
            events = event_paginator.page(1)
        except EmptyPage:
            # If page is out of range (e.g. 999), deliver last page of results.
            events = event_paginator.page(event_paginator.num_pages)
        # Setup the context for the template.
        context = {
            'networks': get_objects_for_user(request.user,
                                             'view_network', klass=Network),
            'currency': CURRENCIES[network.subscriber_currency],
            'user_profile': profile,
            'network_has_activity': network_has_activity,
            'events': events,
            'event_count': event_count,
        }

        # Setup various stuff for filter form generation.
        service_names = ["SMS", "Call", "GPRS", "Transfer", "Other"]
        if not services:
            context['service_types'] = [
                ("SMS", True),
                ("Call", True),
                ("GPRS", True),
                ("Transfer", True),
                ("Other", True)
            ]
        else:
            context['service_types'] = []
            for name in service_names:
                if name.lower() in services:
                    context['service_types'].append((name, True))
                else:
                    context['service_types'].append((name, False))
        context['eventfilter'] = {
            'keyword': keyword,
            'start_date': start_date,
            'end_date': end_date
        }
        template = get_template('dashboard/activity.html')
        html = template.render(context, request)
        return HttpResponse(html)

    def _get_events(self, user_profile, query=None, start_date=None,
                    end_date=None, services=None):
        network = user_profile.network
        events = UsageEvent.objects.filter(
            network=network).order_by('-date')
        # If only one of these is set, set the other one.  Otherwise, both are
        # set, or neither.
        if start_date and not end_date:
            end_date = "2300-01-01 at 01:01AM"
        elif end_date and not start_date:
            start_date = "2000-01-01 at 01:01AM"
        if query:
            events = self._search_events(user_profile, query, events)
        if start_date or end_date:
            # Convert date strings to datetimes and cast them into the
            # UserProfile's timezone.
            user_profile_timezone = pytz.timezone(user_profile.timezone)
            start_date = django_utils_timezone.make_aware(
                datetime.datetime.strptime(
                    start_date, self.datepicker_time_format),
                user_profile_timezone)
            end_date = django_utils_timezone.make_aware(
                datetime.datetime.strptime(
                    end_date, self.datepicker_time_format),
                user_profile_timezone)
            events = events.filter(date__range=(start_date, end_date))
        # filtering services. If 'other' is selected, result is !(any excluded
        # options). If 'other' is not selected, result is OR(selected options).
        if services:
            possible_services = set(['sms', 'call', 'gprs', 'transfer',
                                     'other'])
            selected_services = set(services)
            if "other" in services:
                excluded = possible_services - selected_services
                for e in excluded:
                    events = events.exclude(kind__icontains=e)
            else:
                qs = [Q(kind__icontains=s) for s in services]
                events = events.filter(reduce(operator.or_, qs))
        return events

    def _search_events(self, profile, query_string, orig_events):
        """ Searches for events matching space-separated keyword list

            Args:
                a UserProfile object
                a space-separated query string
                a QuerySet containing UsageEvents we want to search through

            Returns:
                a QuerySet that matches the query string
            """
        network = profile.network
        queries = query_string.split()

        res_events = UsageEvent.objects.none()
        for query in queries:
            events = orig_events
            events = (events.filter(kind__icontains=query)
                      | events.filter(reason__icontains=query)
                      | events.filter(subscriber__name__icontains=query)
                      | events.filter(subscriber__imsi__icontains=query)
                      | events.filter(subscriber_imsi__icontains=query))

            # Get any numbers that match, and add their associated
            # subscribers' events to the results
            potential_subs = (
                Number.objects.filter(number__icontains=query).values('subscriber')
                    .filter(subscriber__network=network).distinct())
            if potential_subs:
                events |= (UsageEvent.objects
                           .filter(subscriber__in=potential_subs))

            res_events |= events
        return res_events


# 47600
class UserManagement(ProtectedView):
    def get(self, request, *args, **kwargs):
        # Handles request from Network Admin or Cloud Admin
        user_profile = UserProfile.objects.get(user=request.user)
        user = User.objects.get(id=user_profile.user_id)
        role = ('Network Admin', 'Business Analyst', 'Loader', 'Partner', 'Cloud Admin')

        if user.is_staff:
            networks = Network.objects.all()
        else:
            networks = user_profile.network

        # Set the context with various stats.
        content_type = ContentType.objects.filter(app_label='endagaweb').values_list('id', flat=True)
        permission = []
        for content in content_type:
            # Excluding view_network permission else a user
            # will have access to all networks

            permissions = Permission.objects.filter(content_type=content).exclude(codename='view_network')
            permission.append(permissions)
        context = {
            'user_profile': user_profile,
            'networks': networks,
            'network': user_profile.network,
            'permissions': permission,
            'staff': user.is_staff,
            'roles': role
        }
        # Render template.
        info_template = get_template(
            'dashboard/user_management/add.html')
        html = info_template.render(context, request)
        return HttpResponse(html)

    def post(self, request, *args, **kwargs):
        """Cloud Admin --> superuser + staff + active
       
        No user allowed to access Django Admin Site
        Network Admin --> staff + active 
        Loader --> active
        BA --> active
        Partner --> active
        Creating a user with (can be Admin, Loader, Partner or Business Analyst)
        """
        # Get form details
        username = request.POST['username']
        password = request.POST['password']
        user_role = str(request.POST['role']).lower().replace(' ', '_')
        networks = request.POST.getlist('network')
        permissions = request.POST.getlist('permissions')

        # Disconnect the signal only to create user,set network,role and group
        post_save.disconnect(UserProfile.new_user_hook, sender=User)
        try:
            with transaction.atomic():
                # Add User
                # is_staff --> If a user can log into Django administration
                # is_superuser --> has all permissions
                # is_active --> Can login or not

                user = User(username=username)
                if user_role == 'cloud_admin':
                    user.is_staff = user.is_superuser = True
                elif user_role == 'network_admin':
                    user.is_staff = False
                else:
                    user.is_staff = user.is_superuser = False
                user.set_password(password)
                user.save()
                # creates Token that BTSs on the network use to authenticate
                Token.objects.create(user=user)

                # Setup UserProfile database
                user_profile = UserProfile.objects.create(user=user)

                for network in networks:
                    user_network = Network.objects.get(id=network)
                    auth_group = Group.objects.get(id=user_network.auth_group_id)
                    auth_group.user_set.add(user)

                # Set last network as default network for User
                user_profile.network = user_network
                user_profile.role = user_role
                user_profile.save()

                # Add the permissions
                for permission_id in permissions:
                    permission = Permission.objects.get(id=permission_id)
                    user.user_permissions.add(permission)

        except Exception as err:
            # ReConnect the signal before return if it reaches exception
            post_save.connect(UserProfile.new_user_hook, sender=User)
            messages.warning(request, err)
            return redirect(urlresolvers.reverse('user-management'))

        post_save.connect(UserProfile.new_user_hook, sender=User)
        messages.success(request, 'User added successfully!')

        return redirect(urlresolvers.reverse('user-management'))


# class ProfileManagement(ProtectedView):
#     def get(self, request):
#         """Handles GET requests."""
#         user_profile = UserProfile.objects.get(user=request.user)
#         network = Network.objects.values()
#         # network = Network.objects.values_list('name','id')
#         # Set the context with various stats.
#         context = {
#             'networks': get_objects_for_user(request.user, 'view_network', klass=Network),
#             'user_profile': user_profile,
#             'network': network,
#             'network_settings_form': dform.NetworkSettingsForm({
#                 # 'network_name': network.name,
#                 'subscriber_currency': network.subscriber_currency,
#                 'number_country': network.number_country,
#                 'autoupgrade_enabled': network.autoupgrade_enabled,
#                 'autoupgrade_channel': network.autoupgrade_channel,
#                 'autoupgrade_in_window': network.autoupgrade_in_window,
#                 'autoupgrade_window_start': network.autoupgrade_window_start,
#             }),
#         }
#         # Render template.
#         info_template = get_template(
#             'dashboard/subscriber_detail/profile_mgmt.html')
#         html = info_template.render(context, request)
#         return HttpResponse(html)
#

class UserDelete(ProtectedView):
    def get(self, request, *args, **kwargs):

        user_profile = UserProfile.objects.get(user=request.user)
        all_users = User.objects.all().exclude(is_superuser=True)
        query = request.GET.get('query', None)

        if query:
            # Not showing Super/Django Admin
            query_users = (
                User.objects.filter(username__icontains=query)).exclude(is_superuser=True)
            # Remove render_table to show all users
            render_table = True
        else:
            # Display all users currently and using render_table variable to hide.
            query_users = all_users
            render_table = False

        # Setup the subscriber table.
        user_table = django_tables.UserTable(list(query_users))
        tables.RequestConfig(request, paginate={'per_page': 10}).configure(
            user_table)

        context = {
            # Except Super User
            'search': dform.UserSearchForm({'query': query}),
            'users_found': len(query_users),
            'user_table': user_table,
            'show_all_users': render_table,
            'user_profile': user_profile,
            'networks': get_objects_for_user(request.user, 'view_network', klass=Network),
        }
        # Render template.
        info_template = get_template(
            'dashboard/user_management/delete.html')
        html = info_template.render(context, request)
        return HttpResponse(html)

    def post(self, request, *args, **kwargs):
        """Handles POST requests to delete User."""
        user_profile = UserProfile.objects.get(user=request.user)
        try:
            user = User.objects.get(id=request.GET['user'])
        except User.DoesNotExist:
            return HttpResponseBadRequest()

        if user.is_staff:
            message = 'Cannot Delete admin %s' % user.username
        else:
            user.delete()
            message = '%s successfully deleted' % user.username

        messages.success(request, message)
        return HttpResponse(message)


class UserBlockUnblock(ProtectedView):
    def get(self, request, *args, **kwargs):

        user_profile = UserProfile.objects.get(user=request.user)
        all_blocked_users = User.objects.all().exclude(is_active=True)
        query = request.GET.get('query', None)

        if query:
            # Exclude Super/Django Admin
            all_users = (
                User.objects.filter(username__icontains=query))
        else:
            # Display all blocked users.
            all_users = all_blocked_users.exclude(is_active=True)

        # Setup the subscriber table.
        user_table = django_tables.BlockedUserTable(list(all_users))
        tables.RequestConfig(request, paginate={'per_page': 10}).configure(
            user_table)

        context = {
            'search': dform.UserSearchForm({'query': query}),
            'users_found': len(all_users),
            'user_table': user_table,
            'user_profile': user_profile,
            'networks': get_objects_for_user(request.user, 'view_network', klass=Network),
        }
        # Render template.
        info_template = get_template(
            'dashboard/user_management/block-unblock.html')
        html = info_template.render(context, request)
        return HttpResponse(html)

    def post(self, request, *args, **kwargs):
        """Handles POST requests to block/unblock User.
        """
        try:
            user = User.objects.get(id=request.GET['user'])
        except User.DoesNotExist:
            return HttpResponseBadRequest()

        if user.is_superuser:
            message = 'Cannot Block/Unblock Admin %s' % user.username
            messages.warning(request, message)
            return HttpResponse(message)

        elif user.is_active:
            user.is_active = False
            message = '%s is Blocked!' % user.username

        else:
            user.is_active = True
            message = '%s is Unblocked!' % user.username

        user.save()
        messages.success(request, message)
        return HttpResponse(message)


class SubscriberCategoryEdit(ProtectedView):
    """Search the Subscriber"""

    def get(self, request, *args, **kwargs):
        return self._handle_request(request)

    def post(self, request, *args, **kwargs):
        return self._handle_request(request)

    def _handle_request(self, request):
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        all_subscribers = Subscriber.objects.filter(network=network)
        if request.method == "POST":
            query = request.POST.get('keyword', None)
        elif request.method == "GET":
            query = None
        else:
            return HttpResponseBadRequest()
        show_table = "false"

        if query:
            # Get actual subs with partial IMSI matches or partial name matches.
            query_subscribers = (
                network.subscriber_set.filter(imsi__icontains=query) |
                network.subscriber_set.filter(name__icontains=query))
            # Get ids of subs with partial number matches.
            sub_ids = network.number_set.filter(
                number__icontains=query
            ).values_list('subscriber_id', flat=True)
            # Or them together to get list of actual matching subscribers.
            query_subscribers |= network.subscriber_set.filter(
                id__in=sub_ids)
            show_table = "true"
        else:
            # Display all subscribers.
            query_subscribers = all_subscribers
            show_table = "false"
        subscriber_table = django_tables.SubscriberTable(list(query_subscribers))
        tables.RequestConfig(request, paginate={'per_page': 15}).configure(
            subscriber_table)

        # Render the response with context.
        context = {
            'networks': get_objects_for_user(request.user, 'view_network', klass=Network),
            'currency': CURRENCIES[network.subscriber_currency],
            'user_profile': user_profile,
            'total_number_of_subscribers': len(all_subscribers),
            'number_of_filtered_subscribers': len(query_subscribers),
            'query_subscribers': query_subscribers,
            'subscriber_table': subscriber_table,
            'show_table': show_table
        }
        template = get_template('dashboard/subscriber_management/subscribers.html')
        html = template.render(context, request)
        return HttpResponse(html)


class SubscriberCategoryUpdate(ProtectedView):
    """Updating Subscriber category"""

    def post(self, request, *args, **kwargs):
        print("in subscriber update", request.POST)
        imsi = request.POST.getlist('imsi_val[]')
        category = request.POST.get('category')
        search_imsi = Subscriber.objects.filter(imsi__in=imsi)
        update_imsi = Subscriber.objects.filter(imsi__in=imsi).update(role=category)
        if (update_imsi > 0):
            return JsonResponse({'message': 'IMSI category updated successfully'})
        else:
            return JsonResponse({'message': 'IMSI category update cannot happen'})
