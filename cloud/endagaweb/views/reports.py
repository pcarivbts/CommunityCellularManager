"""Report views"""

import datetime
import time

import pytz
from django.core import urlresolvers
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.template.loader import get_template
from guardian.shortcuts import get_objects_for_user

from ccm.common.currency import humanize_credits
from endagaweb import models
from endagaweb.models import NetworkDenomination
from endagaweb.models import (UserProfile, UsageEvent, Network)
from endagaweb.views.dashboard import ProtectedView
from guardian.shortcuts import get_objects_for_user


class BaseReport(ProtectedView):
    """The base Report class.

        Process request and response for report view pages.This class used for
        handling filter by network, tower and report list.
        """
    def __init__(self, reports, template, url_namespace='call-report',
                 **kwargs):
        super(BaseReport, self).__init__(**kwargs)
        self.reports = reports
        self.template = template
        self.url_namespace = url_namespace

    def handle_request(self, request):
        """Process request.

        We want filters to persist even when someone changes pages without
        re-submitting the form. Page changes will always come over a GET
        request, not a POST.
         - If it's a GET, we should try to pull settings from the session.
         - If it's a POST, we should replace whatever is in the session.
         - If it's a GET with no page, we should blank out the session.
         """
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        report_list = list({x for v in self.reports.itervalues() for x in v})
        # Process parameters.
        # We want filters to persist even when someone changes pages without
        # re-submitting the form. Page changes will always come over a GET
        # request, not a POST.
        # - If it's a GET, we should try to pull settings from the session.
        # - If it's a POST, we should replace whatever is in the session.
        # - If it's a GET with no page variable, we should blank out the
        #   session.
        if request.method == "POST":
            request.session['level_id'] = request.POST.get('level_id') or 0
            if request.session['level_id']:
                request.session['level'] = 'tower'
            else:
                request.session['level'] = "network"
                request.session['level_id'] = network.id
            request.session['reports'] = request.POST.getlist('reports', None)
            # We always just do a redirect to GET. We include page reference
            # to retain the search parameters in the session.
            return redirect(
                urlresolvers.reverse(self.url_namespace) + '?filter=1')

        elif request.method == "GET":
            if 'filter' not in request.GET:
                # Reset filtering params.
                request.session['level'] = 'network'
                if self.url_namespace == 'subscriber-report':
                    request.session['level'] = 'network'
                request.session['level_id'] = network.id
                request.session['reports'] = report_list
        else:
            return HttpResponseBadRequest()
        timezone_offset = pytz.timezone(user_profile.timezone).utcoffset(
            datetime.datetime.now()).total_seconds()
        level = request.session['level']
        level_id = int(request.session['level_id'])
        reports = request.session['reports']

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
            'reports': reports,
            'report_list': self.reports,
            'user_profile': user_profile,
            'current_time_epoch': int(time.time()),
            'timezone_offset': timezone_offset,
            'network_has_activity': network_has_activity,
        }
        template = get_template(self.template)
        html = template.render(context, request)
        return HttpResponse(html)


class CallReportView(BaseReport):
    """View Call and SMS reports on basis of Network or tower level."""

    def __init__(self, **kwargs):
        template = "dashboard/report/call-sms.html"
        url_namespace = "call-report"
        reports = {'Call': ['Number of Calls', 'Minutes of Call'],
                   'SMS': ['Number of SMS']}
        super(CallReportView, self).__init__(reports, template,
                                             url_namespace, **kwargs)

    def get(self, request):
        return self.handle_request(request)

    def post(self, request):
        return self.handle_request(request)


class SubscriberReportView(BaseReport):
    """View Subscriber reports on basis of Network or tower level."""

    def __init__(self, **kwargs):
        template = "dashboard/report/subscriber.html"
        url_namespace = "subscriber-report"
        reports = {'Subscriber': ['Subscriber Activity',
                                  'Subscriber Status']}
        super(SubscriberReportView, self).__init__(reports ,template,
                                                   url_namespace, **kwargs)

    def get(self, request):
        return self.handle_request(request)

    def post(self, request):
        return self.handle_request(request)


class HealthReportView(BaseReport):
    """View System health reports."""


    def __init__(self, **kwargs):
        template = "dashboard/report/health.html"
        url_namespace = "health-report"
        reports = {'Health': ['BTS Health']}
        super(HealthReportView, self).__init__(reports ,template,
                                                   url_namespace, **kwargs)
    def get(self, request):
        return self.handle_request(request)

    def post(self, request):
        return self.handle_request(request)



class BillingReportView(ProtectedView):
    def __init__(self, **kwargs):
        super(BillingReportView, self).__init__(**kwargs)
        self.template = "dashboard/report/billing.html"
        self.url_namespace = 'billing-report'
        self.reports = {'Call & SMS': ['SMS Billing', 'Call and SMS Billing',
                                       'Call Billing'],
                        'Retailer': ['Retailer Recharge',
                                     'Retailer Load Transfer',],
                        'Top Up': ['Top Up Report for Subscriber',
                                   'Top Up Report',],
                        'Waterfall': ['Activation', 'Loader',
                                      'Reload Amount', 'Reload Transaction']
                        }

    def get(self, request):
        return self.handle_request(request)

    def post(self, request):
        return self.handle_request(request)

    def handle_request(self, request):
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        report_list = list({x for v in self.reports.itervalues() for x in v})
        if request.method == "POST":
            request.session['topup_percent'] = request.POST.get(
                'top_percent') or 100
            request.session['level_id'] = request.POST.get('level_id') or 0
            if request.session['level_id']:
                request.session['level'] = 'tower'
            else:
                request.session['level'] = "network"
                request.session['level_id'] = network.id
            request.session['reports'] = request.POST.getlist('reports', None)
            return redirect(
                urlresolvers.reverse(self.url_namespace) + '?filter=1')

        elif request.method == "GET":
            if 'filter' not in request.GET:
                # Reset filtering params.
                request.session['level'] = 'network'
                # TODO(Piyush/Shiv): Need to fix this subscriber report
                if self.url_namespace == 'subscriber-report':
                    request.session['level'] = ''
                request.session['level_id'] = network.id
                request.session['reports'] = report_list
                request.session['topup_percent'] = 100
        else:
            return HttpResponseBadRequest()

        # For top top-up percentage
        denom_list = []
        denom_list2 = []
        denomination = NetworkDenomination.objects.filter(
            network_id=network.id)

        for denom in denomination:
            start_amount = humanize_credits(denom.start_amount)
            end_amount = humanize_credits(denom.end_amount)
            denom_list.append(
                (start_amount.amount_raw, end_amount.amount_raw))
        formatted_denomnation = []
        for denom in denom_list:
            # Now format to mark them as kinds
            formatted_denomnation.append(
                str(humanize_credits(denom[0])).replace(',', '')
                + ' - ' +
                str(humanize_credits(denom[1])).replace(',', ''))
            denom_list2.append(
                str(denom[0])
                + '-' +
                str(denom[1]))


        timezone_offset = pytz.timezone(user_profile.timezone).utcoffset(
            datetime.datetime.now()).total_seconds()
        level = request.session['level']
        level_id = int(request.session['level_id'])
        reports = request.session['reports']
        topup_percent = float(request.session['topup_percent'])

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
            'reports': reports,
            'report_list': self.reports,
            'user_profile': user_profile,
            'current_time_epoch': int(time.time()),
            'timezone_offset': timezone_offset,
            'network_has_activity': network_has_activity,
            'kinds': ','.join(formatted_denomnation),
            'extra_param': ','.join(denom_list2),
            'topup_percent': topup_percent,
        }
        template = get_template(self.template)
        html = template.render(context, request)
        return HttpResponse(html)
