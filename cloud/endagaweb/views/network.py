"""Network views.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import datetime
import json
import time

import django_tables2 as tables
from django import http
from django import template
from django.conf import settings
from django.contrib import messages
from django.core import exceptions
from django.core import urlresolvers
from django.db import transaction, IntegrityError
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.template.loader import get_template
from googletrans.constants import LANGUAGES
from guardian.shortcuts import get_objects_for_user

from ccm.common.currency import parse_credits, humanize_credits, \
    CURRENCIES, DEFAULT_CURRENCY
from endagaweb import models
from endagaweb.forms import dashboard_forms
from endagaweb.forms import dashboard_forms as dform
from endagaweb.util import api
from endagaweb.views import django_tables
from endagaweb.views.dashboard import ProtectedView

NUMBER_COUNTRIES = {
    'US': 'United States (+1)',
    'CA': 'Canada (+1)',
    'SE': 'Sweden (+46)',
    'ID': 'Indonesia (+62)',
    'PH': 'Philippines (+63)',
}


class NetworkInfo(ProtectedView):
    """View info on a single network."""
    permission_required = 'view_network'

    def get(self, request):
        """Handles GET requests."""
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network

        # Determine the current version and latest client releases.  We need to
        # use the printable_version function and for that we need a BTS
        # instance (which will just reside in memory and not be saved).
        bts = models.BTS()
        current_version = bts.printable_version(
            network.get_lowest_tower_version())

        latest_stable_version = None
        tmp_objs = models.ClientRelease.objects.filter(channel='stable').order_by('-date')
        if (tmp_objs):
            latest_stable_version = tmp_objs[0].version

        latest_beta_version = None
        tmp_objs = models.ClientRelease.objects.filter(channel='beta').order_by('-date')
        if (tmp_objs):
            latest_beta_version = tmp_objs[0].version

        # Count the associated numbers, towers and subscribers.
        towers_on_network = models.BTS.objects.filter(network=network).count()
        subscribers_on_network = models.Subscriber.objects.filter(
            network=network).count()
        numbers_on_network = models.Number.objects.filter(
            network=network).count()
        # Count the 30-, 7- and 1-day active subs.
        thirty_days = datetime.datetime.utcnow() - datetime.timedelta(days=30)
        seven_days = datetime.datetime.utcnow() - datetime.timedelta(days=7)
        one_day = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        thirty_day_actives = models.Subscriber.objects.filter(
            last_active__gt=thirty_days, network=network).count()
        seven_day_actives = models.Subscriber.objects.filter(
            last_active__gt=seven_days, network=network).count()
        one_day_actives = models.Subscriber.objects.filter(
            last_active__gt=one_day, network=network).count()
        # Count the camped subscribers.  Unfortunately the Django ORM cannot
        # filter on properties.
        all_subs = models.Subscriber.objects.filter(network=network)
        camped_right_now = len([s for s in all_subs if s.is_camped])
        # Set the context with various stats.
        context = {
            'networks': get_objects_for_user(request.user, 'view_network', klass=models.Network),
            'currency': CURRENCIES[user_profile.network.subscriber_currency],
            'user_profile': user_profile,
            'network': network,
            'number_country': NUMBER_COUNTRIES[network.number_country],
            'current_version': current_version,
            'latest_stable_version': latest_stable_version,
            'latest_beta_version': latest_beta_version,
            'towers_on_network': towers_on_network,
            'subscribers_on_network': subscribers_on_network,
            'numbers_on_network': numbers_on_network,
            'thirty_day_actives': thirty_day_actives,
            'seven_day_actives': seven_day_actives,
            'one_day_actives': one_day_actives,
            'camped_right_now': camped_right_now,
        }
        # Render template.
        info_template = template.loader.get_template(
            'dashboard/network_detail/info.html')
        html = info_template.render(context, request)
        return http.HttpResponse(html)


class NetworkInactiveSubscribers(ProtectedView):
    """Edit settings for expiring inactive subs."""
    permission_required = 'edit_network'

    def get(self, request):
        """Handles GET requests."""
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network
        # Find subscribers that, with the current settings, will soon be
        # deactivated.  Also divide that group up into "protected" and
        # "unprotected" subs.
        inactive_subs = network.get_outbound_inactive_subscribers(
            network.sub_vacuum_inactive_days)
        protected_subs = []
        unprotected_subs = []
        for sub in inactive_subs:
            if sub.prevent_automatic_deactivation:
                protected_subs.append(sub)
            else:
                unprotected_subs.append(sub)
        # Setup tables showing both groups of subs.
        protected_subs_table = django_tables.MinimalSubscriberTable(
            protected_subs)
        unprotected_subs_table = django_tables.MinimalSubscriberTable(
            unprotected_subs)
        tables.RequestConfig(request, paginate={'per_page': 25}).configure(
            protected_subs_table)
        tables.RequestConfig(request, paginate={'per_page': 25}).configure(
            unprotected_subs_table)
        # Set the context with various stats.
        context = {
            'networks': get_objects_for_user(request.user, 'view_network', klass=models.Network),
            'user_profile': user_profile,
            'network': network,
            'sub_vacuum_form': dashboard_forms.SubVacuumForm({
                'sub_vacuum_enabled': network.sub_vacuum_enabled,
                'inactive_days': network.sub_vacuum_inactive_days,
                'grace_days': network.sub_vacuum_grace_days,
            }),
            'protected_subs': protected_subs,
            'unprotected_subs': unprotected_subs,
            'protected_subs_table': protected_subs_table,
            'unprotected_subs_table': unprotected_subs_table,
        }
        # Render template.
        vacuum_template = template.loader.get_template(
            'dashboard/network_detail/inactive-subscribers.html')
        html = vacuum_template.render(context, request)
        return http.HttpResponse(html)

    def post(self, request):
        """Handles post requests."""
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network
        with transaction.atomic():
            if 'sub_vacuum_enabled' in request.POST:
                enabled = 'True' == request.POST['sub_vacuum_enabled']
                network.sub_vacuum_enabled = enabled
                network.save()
            if 'inactive_days' in request.POST:
                try:
                    inactive_days = int(request.POST['inactive_days'])
                    grace_days = int(request.POST['grace_days'])
                    if inactive_days > 10000:
                        inactive_days = 10000
                    if grace_days > 1000:
                        grace_days = 1000
                    network.sub_vacuum_inactive_days = inactive_days
                    network.sub_vacuum_grace_days = grace_days
                    network.save()
                    messages.success(
                        request, 'Subscriber auto-deletion settings saved.',
                        extra_tags='alert alert-success')
                except ValueError:
                    text = 'The "inactive days" parameter must be an integer.'
                    messages.error(request, text,
                                   extra_tags="alert alert-danger")
        return redirect(urlresolvers.reverse('network-inactive-subscribers'))


class NetworkPrices(ProtectedView):
    """View pricing for a single network."""
    permission_required = ['view_network', 'edit_network']

    def get(self, request):
        """Handles GET requests."""
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network
        # We will show a very different UI for networks that have old towers --
        # only one off-network send tier will be displayed and other text will
        # change.
        network_version = network.get_lowest_tower_version()
        # Start building context for the template.
        tiers = models.BillingTier.objects.filter(network=network)
        billing_tiers = []
        for tier in tiers:
            # Setup sensible labels for the traffic_enabled checkbox.
            if tier.directionality == 'off_network_send':
                label = ('Allow subscribers to make calls and send SMS to'
                         ' numbers not in this network.')
                note = ('The costs when a subscriber sends an SMS or makes a'
                        ' call to one of the countries below.')
            elif tier.directionality == 'off_network_receive':
                label = ('Allow subscribers to receive calls and SMS from'
                         ' numbers not in this network.')
                note = ('The costs when a subscriber receives an SMS or a call'
                        ' from a number outside of your network.')
            elif tier.directionality == 'on_network_send':
                label = ('Allow subscribers to make calls and send SMS to'
                         ' numbers that are in this network.')
                note = ('The costs when a subscriber on your network makes a'
                        ' call or sends an SMS to a number also on your'
                        ' network.')
            elif tier.directionality == 'on_network_receive':
                label = ('Allow subscribers to receive calls and SMS from'
                         ' numbers that are in this network.')
                note = ('The costs when a subscriber on your network receives'
                        ' a call or SMS from a subscriber who is also on your'
                        ' network.')
            # Get a list of countries for each off_network_send tier.
            destinations = models.Destination.objects.filter(
                destination_group=tier.destination_group)
            countries = [d.country_name for d in destinations]
            countries.sort()
            countries = ', '.join(countries)
            tier_data = {
                'name': tier.name,
                'directionality': tier.directionality,
                'id': tier.id,
                'cost_to_subscriber_per_min': tier.cost_to_subscriber_per_min,
                'cost_to_subscriber_per_sms': tier.cost_to_subscriber_per_sms,
                'cost_to_operator_per_min': tier.cost_to_operator_per_min,
                'cost_to_operator_per_sms': tier.cost_to_operator_per_sms,
                'countries_in_tier': countries,
                'traffic_enabled_label': label,
                'note': note,
            }
            billing_tiers.append(tier_data)
        # Sort the tiers so they show up in a sensible order on the dashboard.
        # Note that if the version is None, we dont' show the Off-Network
        # Sending Tiers B, C and D.
        if network_version == None:
            billing_tiers_sorted = 4 * [None]
        else:
            billing_tiers_sorted = 7 * [None]
        for tier in billing_tiers:
            if tier['name'] == 'On-Network Receiving Tier':
                billing_tiers_sorted[0] = tier
            elif tier['name'] == 'On-Network Sending Tier':
                billing_tiers_sorted[1] = tier
            elif tier['name'] == 'Off-Network Receiving Tier':
                billing_tiers_sorted[2] = tier
            elif tier['name'] == 'Off-Network Sending, Tier A':
                billing_tiers_sorted[3] = tier
            if network_version == None:
                continue
            if tier['name'] == 'Off-Network Sending, Tier B':
                billing_tiers_sorted[4] = tier
            elif tier['name'] == 'Off-Network Sending, Tier C':
                billing_tiers_sorted[5] = tier
            elif tier['name'] == 'Off-Network Sending, Tier D':
                billing_tiers_sorted[6] = tier
        # Build up some dynamic example data for use in the help text.
        country_name = 'Iceland'
        destination = models.Destination.objects.get(country_name=country_name)
        billing_tier = models.BillingTier.objects.get(
            destination_group=destination.destination_group, network=network)
        # Create the context for the template.
        context = {
            'networks': get_objects_for_user(request.user, 'view_network', klass=models.Network),
            'currency': CURRENCIES[user_profile.network.subscriber_currency],
            'user_profile': user_profile,
            'network': network,
            'billing_tiers': billing_tiers_sorted,
            'example': {
                'country_name': country_name,
                'billing_tier_name': billing_tier.name,
                'cost_to_subscriber_per_min': (
                    billing_tier.cost_to_subscriber_per_min),
                'cost_to_operator_per_min': (
                    billing_tier.cost_to_operator_per_min),
            },
            'network_version': network_version,
        }
        # Render template.
        prices_template = template.loader.get_template(
            'dashboard/network_detail/prices.html')
        html = prices_template.render(context, request)
        return http.HttpResponse(html)

    def post(self, request):
        """Handles POSTs -- changes to the billing tiers."""
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network
        if 'tier_id' not in request.POST:
            return http.HttpResponseBadRequest()
        # Make sure the Tier exists and the correct UserProfile is associated
        # with it.
        try:
            billing_tier = models.BillingTier.objects.get(
                id=request.POST['tier_id'], network=network)
        except models.BillingTier.DoesNotExist:
            return http.HttpResponseBadRequest()
        # Redirect to GET, appending the billing-tier-section-{id} anchor so
        # the page hops directly to the billing tier that was just edited.
        billing_redirect = redirect('%s#billing-tier-section-%s' % (
            urlresolvers.reverse('network-prices'), billing_tier.id))
        error_text = 'Error: cost is negative or too large'
        try:
            currency = CURRENCIES[user_profile.network.subscriber_currency]
            cost_to_subscriber_per_min = self.parse_subscriber_cost(
                request.POST['cost_to_subscriber_per_min'], currency)
            cost_to_subscriber_per_sms = self.parse_subscriber_cost(
                request.POST['cost_to_subscriber_per_sms'], currency)
        except ValueError:
            messages.error(request, error_text)
            return billing_redirect
        billing_tier.cost_to_subscriber_per_min = \
            cost_to_subscriber_per_min.amount_raw
        billing_tier.cost_to_subscriber_per_sms = \
            cost_to_subscriber_per_sms.amount_raw
        if request.POST.get('traffic_enabled'):
            billing_tier.traffic_enabled = True
        else:
            billing_tier.traffic_enabled = False
        billing_tier.save()
        return billing_redirect

    def parse_subscriber_cost(self, string, currency=DEFAULT_CURRENCY):
        """Parses input cost strings for the network prices page and performs
        value checks. Outputs a Money instance. The cost must be non-negative
        and the integer reperesentation must fit in a 32 bit signed integer.

        Arguments:
            string: numerical string with support for thousands commas and
            decimal places
            currency: the desired output currency. Default currency
            controlled by common/currency extension
        Returns:
            A Money instance
        Raises:
            ValueError: if the string doesn't parse or is out of bounds.
        """
        money = parse_credits(string, currency)
        if money.amount_raw < 0:
            raise ValueError("Cost must be non-negative")
        # This is the max value that is allowed by the DB
        if money.amount_raw > 2147483647:
            raise ValueError("Value is too large")
        return money


class NetworkEdit(ProtectedView):
    """Edit basic network info (but not prices)."""
    permission_required = 'edit_network'

    def get(self, request):
        """Handles GET requests."""
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network
        # Set the context with various stats.
        context = {
            'networks': get_objects_for_user(request.user, 'view_network', klass=models.Network),
            'user_profile': user_profile,
            'network': network,
            'network_settings_form': dashboard_forms.NetworkSettingsForm({
                'network_name': network.name,
                'subscriber_currency': network.subscriber_currency,
                'number_country': network.number_country,
                'autoupgrade_enabled': network.autoupgrade_enabled,
                'autoupgrade_channel': network.autoupgrade_channel,
                'autoupgrade_in_window': network.autoupgrade_in_window,
                'autoupgrade_window_start': network.autoupgrade_window_start,
            }),
        }
        # Render template.
        edit_template = template.loader.get_template(
            'dashboard/network_detail/edit.html')
        html = edit_template.render(context, request)
        return http.HttpResponse(html)

    def post(self, request):
        """Handles post requests."""
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network
        with transaction.atomic():
            if 'network_name' in request.POST:
                network.name = str(request.POST['network_name'])
                network.save()
            if 'subscriber_currency' in request.POST:
                network.subscriber_currency = str(
                    request.POST['subscriber_currency'])
                network.save()
            if 'number_country' in request.POST:
                if request.POST['number_country'] not in NUMBER_COUNTRIES:
                    return http.HttpResponseBadRequest()
                network.number_country = request.POST['number_country']
                network.save()
            if 'autoupgrade_enabled' in request.POST:
                # Convert to boolean.
                enabled = 'True' == request.POST['autoupgrade_enabled']
                network.autoupgrade_enabled = enabled
                network.save()
            if 'autoupgrade_channel' in request.POST:
                # Validate the POSTed channel, defaulting to stable.
                valid_channels = [
                    v[0] for v in models.ClientRelease.channel_choices]
                if request.POST['autoupgrade_channel'] not in valid_channels:
                    network.autoupgrade_channel = 'stable'
                else:
                    network.autoupgrade_channel = (
                        request.POST['autoupgrade_channel'])
                network.save()
            if 'autoupgrade_in_window' in request.POST:
                # Convert to boolean.
                in_window = 'True' == request.POST['autoupgrade_in_window']
                network.autoupgrade_in_window = in_window
                network.save()
        # Validate the autoupgrade window format outside of the transaction so,
        # if this fails, the rest of the options will still be saved.
        if 'autoupgrade_window_start' in request.POST:
            window_start = request.POST['autoupgrade_window_start']
            try:
                time.strptime(window_start, '%H:%M:%S')
                network.autoupgrade_window_start = window_start
                network.save()
            except ValueError:
                messages.error(request, "Invalid start time format.",
                               extra_tags="alert alert-danger")
                return redirect(urlresolvers.reverse('network-edit'))
        # All values were saved successfully, redirect back to editing.
        messages.success(request, "Network information updated.",
                         extra_tags="alert alert-success")
        return redirect(urlresolvers.reverse('network-edit'))

class NetworkSelectView(ProtectedView):
    """This is a view that allows users to switch their current
    network. They must have view_network permission on the instance
    for this to work.
    """
    permission_required = 'view_network'

    def get(self, request, network_id):
        user_profile = models.UserProfile.objects.get(user=request.user)
        try:
            network = models.Network.objects.get(pk=network_id)
            if 'sync_status' in request.session:
                del request.session['sync_status']
        except models.Network.DoesNotExist:
            return http.HttpResponse('Network doesn\'t exist.', status=401)
        if not request.user.has_perm('view_network', network):
            return http.HttpResponse('User not permitted to view this network', status=401)

        user_profile.network = network
        user_profile.save()
        return http.HttpResponseRedirect(request.META.get('HTTP_REFERER', urlresolvers.reverse('Call_Sms_Data_Usage')))


def sync_denomination(network_id, status):
    """ Rebase denomination table remove pending changes. """
    if status == 'apply':
        with transaction.atomic():
            models.NetworkDenomination.objects.filter(
                network=network_id,
                status__in=['pending']).update(status='done')
            deleted_denom = models.NetworkDenomination.objects.filter(
                status__in=['deleted'])
            for denomination in deleted_denom:
                denomination.delete()
    if status == 'discard':
        with transaction.atomic():
            new_denom = models.NetworkDenomination.objects.filter(
                status__in=['pending'])
            for denomination in new_denom:
                denomination.delete()
            deleted_denom = models.NetworkDenomination.objects.filter(
                status__in=['deleted'])
            for denomination in deleted_denom:
                denomination.status = 'done'
                denomination.save()


class NetworkDenomination(ProtectedView):
    """Assign denominations bracket for recharge/adjust-credit in network."""
    permission_required = 'view_denomination'

    def get(self, request):
        """Handles GET requests."""
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network
        currency = network.subscriber_currency

        sync_status = False
        if 'sync_status' in request.session:
            sync_status = request.session['sync_status']
        else:
            sync_denomination(network.id, 'discard')
            request.session['sync_status'] = sync_status

        # Count the associated denomination with selected network.
        denom = models.NetworkDenomination.objects.filter(
            network=network, status__in=['done', 'pending'])
        denom_count = denom.count()

        dnm_id = request.GET.get('id', None)
        if dnm_id:
            response = {
                'status': 'ok',
                'messages': [],
                'data': {}
            }
            denom = models.NetworkDenomination.objects.get(id=dnm_id)
            denom_data = {
                'id': denom.id,
                'start_amount': humanize_credits(denom.start_amount,
                                                 CURRENCIES[currency]).amount,
                'end_amount': humanize_credits(denom.end_amount,
                                               CURRENCIES[currency]).amount,
                'validity_days': denom.validity_days
            }
            response["data"] = denom_data
            return http.HttpResponse(json.dumps(response),
                                     content_type="application/json")

        invalid_ranges = []
        max_denominations = 100000
        for denomination in denom:
            if denomination.start_amount > (max_denominations):
                start_range = humanize_credits((max_denominations),
                                               CURRENCIES[currency]).money_str()
                end_range = humanize_credits((denomination.start_amount),
                                             CURRENCIES[currency]).money_str()
                invalid_ranges.append({"start": start_range,
                                       "end": end_range})
            max_denominations = denomination.end_amount
        next_start_amount = humanize_credits(max_denominations,
                                             CURRENCIES[currency]).amount
        denom_table = django_tables.DenominationTable(list(denom))
        towers_per_page = 8
        paginate = False
        if denom > towers_per_page:
            paginate = {'per_page': towers_per_page}
        tables.RequestConfig(request, paginate=paginate).configure(denom_table)
        # Set the context with various stats.
        context = {
            'networks': get_objects_for_user(request.user, 'view_network',
                                             klass=models.Network),
            'currency': CURRENCIES[user_profile.network.subscriber_currency],
            'user_profile': user_profile,
            'network': network,
            'number_country': NUMBER_COUNTRIES[network.number_country],
            'denomination': denom_count,
            'denominations_table': denom_table,
            'invalid_ranges': invalid_ranges,
            'next_start_amount': next_start_amount,
            'sync_status': sync_status
        }
        # Render template.
        info_template = template.loader.get_template(
            'dashboard/network_detail/denomination.html')
        html = info_template.render(context, request)
        return http.HttpResponse(html)


class NetworkDenominationEdit(ProtectedView):

    permission_required = ['view_denomination', 'edit_denomination']

    def post(self, request):
        """Operators can use this API to add denomination to a network.

        These denomination bracket will be used to recharge subscriber,
        set balance validity and status
        """
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network
        try:
            sync = request.GET.get('sync', False)
            if sync:
                sync_denomination(network.id, 'apply')
                request.session['sync_status'] = False
                messages.success(
                    request, 'New denomination changes applied successfully.',
                    extra_tags='alert alert-success')
                return http.HttpResponse(json.dumps({'status': 'ok'}),
                                         content_type="application/json")

            currency = network.subscriber_currency
            start_amount_raw = request.POST.get('start_amount')
            start_amount = parse_credits(start_amount_raw,
                                         CURRENCIES[currency]).amount_raw
            end_amount_raw = request.POST.get('end_amount')
            end_amount = parse_credits(end_amount_raw,
                                       CURRENCIES[currency]).amount_raw
            validity_days = int(request.POST.get('validity_days')) or 0

            dnm_id = int(request.POST.get('dnm_id')) or 0
            if validity_days > settings.ENDAGA['MAX_VALIDITY_DAYS']:
                message = ('Validity days value exceeds maximum permissible '
                           'limit (%s Days).' %
                           (settings.ENDAGA['MAX_VALIDITY_DAYS']))
                messages.error(
                    request, message,
                    extra_tags='alert alert-danger')
                return redirect(urlresolvers.reverse('network-denominations'))
            elif start_amount < 1 or end_amount <= 1:
                messages.error(request,
                               'Enter value >= 1 for start amount.',
                               extra_tags='alert alert-danger')
                return redirect(urlresolvers.reverse('network-denominations'))
            elif validity_days <= 0:
                messages.error(
                    request, 'Validity can not be 0 day.',
                    extra_tags='alert alert-danger')
                return redirect(urlresolvers.reverse('network-denominations'))
            elif end_amount <= start_amount:
                messages.error(
                    request, 'End amount should be greater than start amount.',
                    extra_tags='alert alert-danger')
                return redirect(urlresolvers.reverse('network-denominations'))

            user_profile = models.UserProfile.objects.get(user=request.user)
            with transaction.atomic():
                if dnm_id > 0:
                    try:
                        denom = models.NetworkDenomination.objects.get(
                            id=dnm_id, status__in=['done', 'pending'])
                        # Check for existing denomination range exist.
                        denom_exists = \
                          models.NetworkDenomination.objects.filter(
                              end_amount__gte=start_amount+1,
                              start_amount__lte=end_amount-1,
                              network=user_profile.network,
                              status__in=['done', 'pending']).exclude(
                                  id=dnm_id).count()
                        if denom_exists:
                            messages.error(
                                request, 'Denomination range already exists.',
                                extra_tags='alert alert-danger')
                            return redirect(
                                urlresolvers.reverse('network-denominations'))
                        denom.status = 'deleted'
                        denom.save()
                        # Create new denomination for updated record
                        new_denom = models.NetworkDenomination(
                            network=user_profile.network)
                        new_denom.network = user_profile.network
                        new_denom.start_amount = start_amount
                        new_denom.end_amount = end_amount
                        new_denom.validity_days = validity_days
                        new_denom.status = 'pending'
                        new_denom.save()
                        request.session['sync_status'] = True
                        messages.success(
                            request, 'Denomination is updated successfully.',
                            extra_tags='alert alert-success')
                    except models.NetworkDenomination.DoesNotExist:
                        messages.error(
                            request, 'Invalid denomination ID.',
                            extra_tags='alert alert-danger')
                        return redirect(
                            urlresolvers.reverse('network-denominations'))
                else:
                    # Check for existing denomination range exist.
                    denom_exists = models.NetworkDenomination.objects.filter(
                        end_amount__gte=start_amount+1,
                        start_amount__lte=end_amount-1,
                        network=user_profile.network,
                        status__in=['done', 'pending']).count()
                    if denom_exists:
                        messages.error(
                            request, 'Denomination range already exists.',
                            extra_tags='alert alert-danger')
                        return redirect(
                            urlresolvers.reverse('network-denominations'))
                    # Create new denomination for selected network
                    denom = models.NetworkDenomination(
                        network=user_profile.network)
                    denom.network = user_profile.network
                    denom.start_amount = start_amount
                    denom.end_amount = end_amount
                    denom.validity_days = validity_days
                    denom.status = 'pending'
                    denom.save()
                    request.session['sync_status'] = True
                    messages.success(
                        request, 'Denomination is created successfully.',
                        extra_tags='alert alert-success')
        except Exception:
            messages.error(request,
                           'Invalid validity value. Enter greater than '
                           '0 digit value',
                           extra_tags='alert alert-danger')
        return redirect(urlresolvers.reverse('network-denominations'))

    def delete(self, request):
        """soft delete denominations, this can be commit/rollback by
        sync_denomination() as per request."""
        response = {
            'status': 'ok',
            'messages': [],
        }
        dnm_ids = request.GET.getlist('ids[]') or False
        if dnm_ids:
            try:
                models.NetworkDenomination.objects.filter(
                    id__in=dnm_ids).update(status='deleted')
                request.session['sync_status'] = True
                response['status'] = 'success'
                messages.success(request, 'Denomination deleted successfully.',
                                 extra_tags='alert alert-success')
            except models.NetworkDenomination.DoesNotExist:
                response['status'] = 'failed'
                messages.error( request, 'Invalid denomination ID.',
                    extra_tags='alert alert-danger')
        else:
            response['status'] = 'failed'
            messages.error(request, 'Invalid request data.',
                extra_tags='alert alert-danger')
        return http.HttpResponse(json.dumps(response),
                                 content_type="application/json")


class NetworkBalanceLimit(ProtectedView):
    """Edit basic network info (to add credit to Network)."""
    permission_required = ['edit_network', 'view_network']

    def get(self, request):
        """Handles GET requests."""
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network
        # Set the context with various stats.
        currency = network.subscriber_currency
        context = {
            'networks': get_objects_for_user(request.user, 'view_network',
                                             klass=models.Network),
            'user_profile': user_profile,
            'network': network,
            'currency': CURRENCIES[network.subscriber_currency],
            'network-balance-limit_form': dashboard_forms.NetworkBalanceLimit({
                'max_balance': '',
                'max_unsuccessful_transaction': '',

            }),
        }
        # Render template.
        edit_template = template.loader.get_template(
            'dashboard/network_detail/network-balancelimit.html')
        html = edit_template.render(context, request)
        return http.HttpResponse(html)

    def post(self, request):
        """Handles POST requests."""
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network
        success = []
        if 'max_balance' not in request.POST:
            return http.HttpResponseBadRequest()
        if 'max_unsuccessful_transaction' not in request.POST:
            return http.HttpResponseBadRequest()
        try:
            form = dform.NetworkBalanceLimit(data=request.POST)
            if form.is_valid():
                cleaned_field_data = form.clean_network_balance()
                max_balance = cleaned_field_data.get("max_balance")
                max_failure_transaction = cleaned_field_data.get("max_unsuccessful_transaction")
                with transaction.atomic():
                    try:
                        currency = network.subscriber_currency
                        if max_balance:
                            balance = float(max_balance)
                            max_network_amount = parse_credits(balance,
                                                               CURRENCIES[
                                                                   currency]).amount_raw
                            network.max_balance = max_network_amount
                            success.append(
                                'Network maximum balance limit updated.')
                        if max_failure_transaction:
                            transaction_val = int(max_failure_transaction)
                            network.max_failure_transaction = transaction_val
                            success.append(
                                'Network maximun permissible unsuccessful' \
                                ' transactions limit updated.')
                        network.save()
                    except ValueError:
                        error_text = 'Error : please provide valid value.'
                        messages.error(request, error_text,
                                       extra_tags="alert alert-danger")
                        return redirect(
                            urlresolvers.reverse('network-balance-limit'))
                messages.success(request,
                                 ''.join(success),
                                 extra_tags="alert alert-success")
                return redirect(urlresolvers.reverse('network-balance-limit'))
        except exceptions.ValidationError as e:
            tags = 'password alert alert-danger'
            messages.error(request, ''.join(e.messages), extra_tags=tags)
            return redirect(urlresolvers.reverse('network-balance-limit'))


class NetworkNotifications(ProtectedView):
    """View event notifications for current network. """

    permission_required = 'view_notification'

    def get(self, request):
        """Handles GET requests.
        Show event-notification listing page"""
        user_profile = models.UserProfile.objects.get(user=request.user)
        network = user_profile.network
        notifications = models.Notification.objects.filter(network=network)
        notification_id = request.GET.get('id', None)
        number = event = None
        languages = {}
        if notification_id:
            response = {
                'status': 'ok',
                'messages': [],
                'data': {}
            }
            notification = models.Notification.objects.get(id=notification_id)
            try:
                number = int(notification.event)
            except ValueError:
                event = str(notification.event).replace('_', ' ').upper()
            notifications = models.Notification.objects.filter(
                event=notification.event)
            translations = {}
            for notif in notifications:
                translations[notif.language] = notif.translation
            notification_data = {
                'id': notification.id,
                'event': event,
                'number': number,
                'message': notification.message,
                'protected': notification.protected,
                'translations': translations,
                'type': notification.type,
            }
            response["data"] = notification_data
            return http.HttpResponse(json.dumps(response),
                                     content_type="application/json")
        # Set the response context.
        langs = notifications.values_list('language', flat=True).distinct()
        for lg in langs:
            languages[lg] = str(LANGUAGES[lg]).capitalize()
        query = request.GET.get('query', None)
        language = request.GET.get('language', None)
        notifications = notifications.distinct('event')
        l_notifications = q_notifications = None
        notification_table = django_tables.NotificationTable(
            list(notifications))
        if query and len(query) > 0:
            q_notifications = (notifications.filter(event__icontains=str(
                query).replace(' ', '_')) |
                             notifications.filter(type__icontains=query) |
                             notifications.filter(
                                 translation__icontains=query) |
                             notifications.filter(message__icontains=query))
            notification_table = django_tables.NotificationTable(
                list(q_notifications))
        if language and len(language) > 0:
            l_notifications = notifications.filter(
                language=language)
            notification_table = django_tables.NotificationTableTranslated(
                list(l_notifications))
        if q_notifications and l_notifications:
            notifications = q_notifications.filter(
                language=language)
            notification_table = django_tables.NotificationTableTranslated(
                list(notifications))
        tables.RequestConfig(request, paginate={'per_page': 10}).configure(
            notification_table)
        # default page language
        if not language:
            language = 'en'
        context = {
            'networks': get_objects_for_user(request.user, 'view_network',
                                             klass=models.Network),
            'user_profile': user_profile,
            'notification': dashboard_forms.NotificationForm(
                language=languages,
                initial={'type': 'automatic'},),
            'notification_table': notification_table,
            'records': len(list(notifications)),
            'languages': languages,
            'network': network,
            'search': dform.NotificationSearchForm({'query': query,
                                                    'language': language}),
        }
        # Render template.
        template = get_template('dashboard/network_detail/notifications.html')
        html = template.render(context, request)
        return http.HttpResponse(html)


class NetworkNotificationsEdit(ProtectedView):

    permission_required = ['edit_notification', 'view_notification']

    def post(self, request):
        """Handles POST requests.
        CRUD operations for notifications.
        """
        delete_notification = request.POST.getlist('id') or None
        if delete_notification is None:
            # Create/Edit the notifications
            user_profile = models.UserProfile.objects.get(user=request.user)
            network = user_profile.network
            type = request.POST.get('type')
            event = request.POST.get('event')
            message = request.POST.get('message')
            number = request.POST.get('number')
            pk = request.POST.get('pk')
            if event:
                try:
                    int(event)
                    alert_message = 'Mapped events cannot be numeric only!'
                    messages.error(request, alert_message,
                                   extra_tags="alert alert-danger")
                    return redirect(urlresolvers.reverse(
                        'network-notifications'))
                except ValueError:
                    # to use event as key on client
                    event = str(event).lower().strip().replace(' ', '_')
            if number:
                # Format number to 3 digits
                event = str(number)
                if int(number) < 10:
                    event = '00' + event
                elif int(number) < 100:
                    event = '0' + event
            if int(pk) != 0:
                # Check for existing notification and update
                notification = models.Notification.objects.get(id=pk)
                all_notifications = models.Notification.objects.filter(
                    event=notification.event)
                for msg in all_notifications:
                    msg.type = type
                    if message:
                        msg.message = message
                    msg.translation = request.POST.get('lang_' + msg.language)
                    if not msg.protected:
                        msg.event = event
                    msg.save()
                resp = 'Updated Successfully!'
                messages.success(request, resp)
            else:
                try:
                    if not models.Notification.objects.filter(
                            event=event,
                            language__in=settings.BTS_LANGUAGES,
                            network=network).exists():
                        # Create new notifications
                        languages = settings.BTS_LANGUAGES
                        with transaction.atomic():
                            for language in languages:
                                translation = request.POST.get(
                                    'lang_' + language)
                                notification =\
                                    models.Notification.objects.create(
                                    network=network, language=language)
                                notification.type = type
                                notification.message = message
                                notification.translation = translation
                                notification.event = event
                                notification.save()
                        resp = 'Added Successfully!'
                        messages.success(request, resp)
                        return redirect(
                            urlresolvers.reverse('network-notifications'))
                except IntegrityError:
                    resp = 'Notification Already Exists!'
                    messages.warning(request, resp)
                    return redirect(
                        urlresolvers.reverse('network-notifications'))
        else:
            # Delete notifications
            notifications = models.Notification.objects.filter(
                id__in=delete_notification)
            events = notifications.values_list('event', flat=True).distinct()
            models.Notification.objects.filter(event__in=events).delete()
            resp = 'Selected notification(s) deleted successfully.'
            messages.success(request, resp)
        return redirect(urlresolvers.reverse('network-notifications'))
