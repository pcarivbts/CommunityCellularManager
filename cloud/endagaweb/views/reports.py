"""Report views"""

import datetime
import time

import pytz
from django.core import urlresolvers
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.template.loader import get_template
from guardian.shortcuts import get_objects_for_user

from endagaweb import models
from endagaweb.models import (UserProfile, UsageEvent, Network)
from endagaweb.views.dashboard import ProtectedView


class CallReportView(ProtectedView):
    """View Call and SMS reports on basis of Network or tower level."""

    reports = {'Call': [
        'Number of Calls',
        'Number of Minutes', ],
        'SMS': [
            'Total Usage',
        ], }

    def get(self, request, *args, **kwargs):
        return self._handle_request(request)

    def post(self, request, *args, **kwargs):
        return self._handle_request(request)

    def _handle_request(self, request):
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        if request.method == "POST":
            request.session['level'] = request.POST.get('level', "")
            if request.session['level'] == 'tower':
                request.session['level_id'] = request.POST.get('level_id') or 0
            else:
                request.session['level'] = "network"
                request.session['level_id'] = network.id
            request.session['reports'] = request.POST.getlist('reports', None)
            return redirect(urlresolvers.reverse('call-report') + "?filter=1")

        elif request.method == "GET":
            if 'filter' not in request.GET:
                # Reset filtering params.
                request.session['level'] = "network"
                request.session['level_id'] = network.id
                request.session['reports'] = self.reports
        else:
            return HttpResponseBadRequest()

        timezone_offset = pytz.timezone(user_profile.timezone).utcoffset(
            datetime.datetime.now()).total_seconds()
        level = request.session['level']
        level_id = int(request.session['level_id'])

        towers = models.BTS.objects.filter(
            network=user_profile.network).values('nickname', 'uuid', 'id')
        network_has_activity = UsageEvent.objects.filter(
            network=network).exists()

        context = {
            'networks': get_objects_for_user(request.user, 'view_network',
                                             klass=Network),
            'towers': towers,
            'level': level,
            'level_id': level_id,
            'reports': request.session['reports'],
            'user_profile': user_profile,
            'current_time_epoch': int(time.time()),
            'timezone_offset': timezone_offset,
            'network_has_activity': network_has_activity,
        }
        template = get_template("dashboard/report/call-sms.html")
        html = template.render(context, request)
        return HttpResponse(html)


class SubscriberReportView(ProtectedView):
    """View Subscriber reports on basis of Network or tower level."""
    reports = {}

    def get(self, request):
        user_profile = UserProfile.objects.get(user=request.user)
        try:
            towers = models.BTS.objects.filter(network=user_profile.network)
        except models.BTS.DoesNotExist:
            tower = None
        network = user_profile.network
        timezone_offset = pytz.timezone(user_profile.timezone).utcoffset(
            datetime.datetime.now()).total_seconds()
        # Determine if there has been any activity on the network (if not,
        # we won't show the graphs).
        network_has_activity = UsageEvent.objects.filter(
            network=network).exists()
        context = {
            'networks': get_objects_for_user(request.user, 'view_network',
                                             klass=Network),
            'user_profile': user_profile,
            'network_id': network.id,
            'towers': towers,
            'current_time_epoch': int(time.time()),
            'timezone_offset': timezone_offset,
            'network_has_activity': network_has_activity,
            'reports': self.reports
        }
        template = get_template("dashboard/report/subscriber.html")
        html = template.render(context, request)
        return HttpResponse(html)


class BillingReportView(ProtectedView):
    """View Billing reports on basis of Network or tower level."""
    reports = {'Call & SMS': [
        'SMS Billing',
        'Call and SMS Billing',
        'Call Billing'],

        'Retailer': [
            'Retailer Recharge',
            'Retailer Load Transfer',
            # 'Waterfall Activation'
        ], }

    def get(self, request, *args, **kwargs):
        return self._handle_request(request)

    def post(self, request, *args, **kwargs):
        return self._handle_request(request)

    def _handle_request(self, request):
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        if request.method == "POST":
            request.session['level'] = request.POST.get('level', "")
            if request.session['level'] == 'tower':
                request.session['level_id'] = request.POST.get('level_id') or 0
            else:
                request.session['level'] = "network"
                request.session['level_id'] = network.id
            request.session['reports'] = request.POST.getlist('reports', None)
            # We always just do a redirect to GET. We include page reference
            # to retain the search parameters in the session.
            return redirect(
                urlresolvers.reverse('billing-report') + "?filter=1")

        elif request.method == "GET":
            if 'filter' not in request.GET:
                # Reset filtering params.
                request.session['level'] = "network"
                request.session['level_id'] = network.id
                request.session['reports'] = self.reports
        else:
            return HttpResponseBadRequest()

        timezone_offset = pytz.timezone(user_profile.timezone).utcoffset(
            datetime.datetime.now()).total_seconds()
        level = request.session['level']
        level_id = int(request.session['level_id'])

        towers = models.BTS.objects.filter(
            network=user_profile.network).values('nickname', 'uuid', 'id')

        network_has_activity = UsageEvent.objects.filter(
            network=network).exists()
        context = {
            'networks': get_objects_for_user(request.user, 'view_network',
                                             klass=Network),
            'towers': towers,
            'level': level,
            'level_id': level_id,
            'user_profile': user_profile,
            'network_id': network.id,
            'current_time_epoch': int(time.time()),
            'timezone_offset': timezone_offset,
            'network_has_activity': network_has_activity,
            'reports': self.reports
        }
        template = get_template("dashboard/report/billing.html")
        html = template.render(context, request)
        return HttpResponse(html)


class HealthReportView(ProtectedView):
    """View System health reports."""
    reports = {}

    def get(self, request):
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        timezone_offset = pytz.timezone(user_profile.timezone).utcoffset(
            datetime.datetime.now()).total_seconds()
        # Determine if there has been any activity on the network (if not,
        # we won't show the graphs).
        network_has_activity = UsageEvent.objects.filter(
            network=network).exists()
        context = {
            'networks': get_objects_for_user(request.user, 'view_network',
                                             klass=Network),
            'user_profile': user_profile,
            'network_id': network.id,
            'current_time_epoch': int(time.time()),
            'timezone_offset': timezone_offset,
            'network_has_activity': network_has_activity,
            'reports': self.reports
        }
        template = get_template("dashboard/report/call-sms.html")
        html = template.render(context, request)
        return HttpResponse(html)
