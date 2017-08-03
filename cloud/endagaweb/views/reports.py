"""Report views"""

import datetime
import time
import csv
import pytz
import operator
from django.core import urlresolvers
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.template.loader import get_template
from guardian.shortcuts import get_objects_for_user

from ccm.common.currency import humanize_credits
from endagaweb import models
from endagaweb.models import NetworkDenomination
from endagaweb.models import (UserProfile, Subscriber, UsageEvent, Network)
from endagaweb.views.dashboard import ProtectedView
from guardian.shortcuts import get_objects_for_user
from ccm.common.currency import CURRENCIES
from django.utils import timezone as django_utils_timezone
from django.db.models import Q

report_keys= ('Top Up', 'Call & SMS', 'Retailer', 'Waterfall')
reports_dict= {
    'Top Up': ['Amount Based', 'Count Based'],
    'Call and SMS': ['SMS Billing', 'Call and SMS Billing', 'Call Billing'],
    'Retailer': ['Retailer Recharge', 'Retailer Load Transfer'],
    #'Non Loader': ['Total Base', 'Cumulative'],
    'Waterfall': ['Activation', 'Loader', 'Reload Rate', 'Reload Amount',
                  'Reload Transaction', 'Average Load', 'Average Frequency']
}


class BaseReport(ProtectedView):
    """The base Report class.

        Process request and response for report view pages.This class used for
        handling filter by network, tower and report list.
        """
    permission_required = 'view_graph'

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
            filter = request.session['filter']
            request.session['filter'] = filter

            # We always just do a redirect to GET. We include page reference
            # to retain the search parameters in the session.
            return redirect(
                urlresolvers.reverse(self.url_namespace) + '?filter='+filter)

        elif request.method == "GET":
            if 'filter' in request.GET and 'filter' in request.session:
                filter = request.GET.get('filter', 1)
                if filter != request.session['filter']:
                    request.session['reports'] = self.reports[filter]
                    request.session['level_id'] = None
                    request.session['level'] = None
                request.session['filter'] = filter
            else:
                request.session['level_id'] = request.GET.get('level_id')
                request.session['reports'] = report_list
                request.session['filter'] = request.GET['filter']
                request.session['level'] =request.GET.get('level','network')
            # Reset filtering params.
            #request.session['level'] = 'network'
            request.session['level_id'] =  request.session['level_id']
        else:
            return HttpResponseBadRequest()
        timezone_offset = pytz.timezone(user_profile.timezone).utcoffset(
            datetime.datetime.now()).total_seconds()
        level = request.session['level']
        if request.session['level_id'] !=None:
            level_id = int(request.session['level_id'])
        else:
            level_id = network.id
            level ='network'
        if request.session['level']!=None:
            request.session['level'] = request.session['level']
        else:
            request.session['level'] = request.GET.get('level','network')
        reports = request.session['reports']
        filter = request.session['filter']
        towers = models.BTS.objects.filter(network=user_profile.network).\
            order_by('id').values('nickname', 'uuid', 'id')
        network_has_activity = UsageEvent.objects.filter(
            network=network).exists()
        #print("check level ",level)
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
            'value_type': '',
            'filter': filter
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
        super(SubscriberReportView, self).__init__(reports, template,
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
        super(HealthReportView, self).__init__(reports, template,
                                               url_namespace, **kwargs)

    def get(self, request):
        return self.handle_request(request)

    def post(self, request):
        return self.handle_request(request)


class BillingReportView(ProtectedView):
    permission_required = 'view_report'

    def __init__(self, **kwargs):
        super(BillingReportView, self).__init__(**kwargs)
        self.template = "dashboard/report/billing.html"
        self.url_namespace = 'billing-report'
        self.reports = reports_dict

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
            filter = request.session['filter']
            request.session['filter'] = filter
            return redirect(
                urlresolvers.reverse(self.url_namespace) + '?filter='+filter)
        elif request.method == "GET":
            if 'filter' in request.GET and 'filter' in request.session:
                filter = request.GET.get('filter', 1)
                if filter != request.session['filter']:
                    request.session['reports'] = self.reports[filter]
                request.session['filter'] = filter
                if(request.session['topup_percent'])!=None:
                    request.session['topup_percent'] = request.session['topup_percent']
                else:
                    request.session['topup_percent'] =request.GET.get('topup_percent',100)
            else:
                request.session['level_id'] = request.GET.get('level_id')
                request.session['reports'] = report_list
                request.session['filter'] = None
                request.session['level'] = request.GET.get('level', 'network')
                request.session['topup_percent'] = request.GET.get('topup_percent',
                                                               100)
            # Reset filtering params.
            level = request.session['level']
            if request.session['level_id'] != None:
                level_id = int(request.session['level_id'])
            else:
                level_id = network.id
            #request.session['topup_percent'] = 100


        else:
            return HttpResponseBadRequest()

        # For top top-up percentage
        denom_list = []
        denom_list2 = []
        # Get denominatations available for that network
        denomination = NetworkDenomination.objects.filter(
            network_id=network.id)

        for denom in denomination:
            start_amount = humanize_credits(denom.start_amount, currency=CURRENCIES[network.currency])
            end_amount = humanize_credits(denom.end_amount, currency=CURRENCIES[network.currency])
            denom_list.append(
                (start_amount.amount_raw, end_amount.amount_raw))
        formatted_denomnation = []
        for denom in denom_list:
            # Now format to set them as stat-types
            formatted_denomnation.append(
                str(humanize_credits(
                    denom[0], CURRENCIES[network.subscriber_currency])).replace(',', '')
                + ' - ' +
                str(humanize_credits(
                    denom[1], CURRENCIES[network.subscriber_currency])).replace(',', ''))
            denom_list2.append(
                str(denom[0])
                + '-' +
                str(denom[1]))
        currency = CURRENCIES[network.subscriber_currency].symbol
        timezone_offset = pytz.timezone(user_profile.timezone).utcoffset(
            datetime.datetime.now()).total_seconds()
        level = request.session['level']
        if request.session['level_id'] != None:
            level_id = int(request.session['level_id'])
        else:
            level_id = network.id
        filter = request.session['filter']
        reports = request.session['reports']
        topup_percent = float(request.session['topup_percent'])

        towers = models.BTS.objects.filter(
            network=user_profile.network).values('nickname', 'uuid', 'id')
        network_has_activity = UsageEvent.objects.filter(
            network=network).exists()
        context = {
            'network': network,
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
            'value_type': currency,
            'filter': filter
        }
        template = get_template(self.template)
        html = template.render(context, request)
        return HttpResponse(html)


class ReportGraphDownload(ProtectedView):
    """downoad csv on basis of reports"""

    permission_required = ['downloads_graph']

    def get(self, request):
        user_profile = UserProfile.objects.get(user=request.user)
        network = user_profile.network
        currency = CURRENCIES[network.subscriber_currency]
        request.session['start_date'] = request.GET.get(
            'start-time-epoch',
            0)
        request.session['end_date'] = request.GET.get('end-time-epoch',
                                                      0)
        request.session['stats_type'] = request.GET.get('stat-types',
                                                        None)
        request.session['level'] = request.GET.get('level',None)
        request.session['level_id'] =  request.GET.get('level_id',0 )
        request.session['report-type'] = request.GET.get('report-type')
        start_date = request.session['start_date']
        end_date = request.session['end_date']
        stats_type = request.session['stats_type']
        stat_types = stats_type.split(',')
        level = request.session['level']
        level_id = request.session['level_id']
        start_time = datetime.datetime.fromtimestamp(float(start_date)).\
            strftime('%Y-%m-%d %H:%M:%S.%f')
        end_time = datetime.datetime.fromtimestamp(float(end_date)).\
            strftime('%Y-%m-%d %H:%M:%S.%f')
        report_type = request.session['report-type']
        if(report_type == 'Subscriber Status'):
            subscriber_events = self._get_subscriber_report(level, level_id,
                                      start_time, end_time, stat_types)
            headers = [
                'Subscriber IMSI',
                'Subscriber Name',
                'Credit Balance(%s' % (currency,),
                'Type of State',
                'Last Active',
                'Last Outbound Activity',
                'Last Camped',
                'Automatic Deactivation',
                'Valid Duration',
                'Subscriber Role',

            ]
            response = HttpResponse(content_type='text/csv')
            writer = csv.writer(response)
            writer.writerow(headers)
            timezone = pytz.timezone(user_profile.timezone)
            for e in subscriber_events[:7000]:
                subscriber = e.imsi
                if e.imsi.startswith('IMSI'):
                    subscriber = e.imsi[4:]
                writer.writerow([
                    subscriber,
                    e.name,
                    humanize_credits(e.balance, currency=currency).amount_str(),
                    e.state,
                    django_utils_timezone.localtime(e.last_active, timezone)
                        .strftime("%Y-%m-%d at %I:%M%p")
                    if e.last_active else '' ,
                    django_utils_timezone.localtime(e.last_outbound_activity,
                                                    timezone)
                        .strftime("%Y-%m-%d at %I:%M%p")
                    if e.last_outbound_activity else '',
                    django_utils_timezone.localtime(e.last_camped, timezone)
                        .strftime("%Y-%m-%d at %I:%M%p")
                    if e.last_camped else '',
                    e.prevent_automatic_deactivation,
                    e.valid_through,
                    e.role,
                ])
            return response
        if(report_type == 'BTS Status'):
            bts_events = self._get_bts_health_report(level,level_id,
                                                     start_time, end_time,
                                                     stat_types)
            headers = [
                'BTS Identifier',
                'BTS Name',
                'Day',
                'Time',
                'Time Zone',
                'Status',
             ]
            response = HttpResponse(content_type='text/csv')
            writer = csv.writer(response)
            writer.writerow(headers)
            timezone = pytz.timezone(user_profile.timezone)
            for e in bts_events[:7000]:
                tz_date = django_utils_timezone.localtime(e.date, timezone)
                writer.writerow([
                    e.bts.uuid,
                    e.bts.nickname if e.bts else "<deleted BTS>",
                    tz_date.date().strftime("%m-%d-%Y"),
                    tz_date.time().strftime("%I:%M:%S %p"),
                    timezone,
                    e.type,

                ])
            return response
        else:
            events = self._get_usage_event_values(report_type, level, level_id,
                                                  user_profile, start_time,
                                                  end_time, stat_types)

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
            writer = csv.writer(response)
            writer.writerow(headers)
            timezone = pytz.timezone(user_profile.timezone)
            for e in events[:7000]:
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
                    humanize_credits(e.tariff,
                                 currency=currency).amount_str()
                    if e.tariff else None,
                    humanize_credits(e.change,
                                 currency=currency).amount_str()
                    if e.change else None,
                    humanize_credits(e.oldamt,
                                 currency=currency).amount_str()
                    if e.oldamt else None,
                    humanize_credits(e.newamt,
                                 currency=currency).amount_str()
                    if e.newamt else None,
                    e.uploaded_bytes,
                    e.downloaded_bytes,
                ])
            return response

    def _get_usage_event_values(self, report_type, level, level_id, user_profile,
                                start_date=None, end_date=None,
                                stats_type=None):
        network = user_profile.network
        events = UsageEvent.objects.filter(
            network=network).order_by('-date')
        retailer_role_reports =['Top Up Report (Count Based)','Top Up Report (Amount Based)',
                                'Retailer Load Transfer Report']
        if start_date or end_date:
            events = events.filter(
                date__range=(str(start_date), str(end_date)))
        if level == 'tower':
            events = events.filter(bts__id=level_id)
        if level == 'network':
            events = events.filter(network__id=level_id)
        if report_type in retailer_role_reports:
            qs = Q(kind='transfer')
            qs1 = Q(subscriber__role='retailer')
            events = events.filter(qs & qs1)
            return events
        if stats_type:
            if report_type == 'Retailer Recharge Report':
                qs1 = Q(kind__icontains='add_money')
                qs = Q(subscriber__role='retailer')
                events = events.filter(qs1 & qs)
                return events
            qs = ([Q(kind__icontains=s)for s in stats_type] )
            if report_type == 'Subscriber Activity':
                qs.append((Q(oldamt__gt=0,newamt__lte=0)))
            events = events.filter(reduce(operator.or_, qs))
        return events

    def _get_subscriber_report(self, level, level_id, start_date=None,
                               end_date=None, stats_type=None):
        subscriber_events = Subscriber.objects.filter(
            valid_through__range=(str(start_date), str(end_date)))
        if stats_type:
            qs =([Q(state=s)for s in stats_type])
            subscriber_events = subscriber_events.filter(reduce(operator.or_, qs))
        if level == 'tower':
            subscriber_events = subscriber_events.filter(bts__id=level_id)
        elif level == 'network':
            subscriber_events = subscriber_events.filter(network__id=level_id)

        return subscriber_events

    def _get_bts_health_report(self, level, level_id, start_date=None,
                               end_date=None, stats_type=None):
        bts_events = models.SystemEvent.objects.order_by('-date')
        if start_date or end_date:
            bts_events = bts_events.filter(date__range=(str(start_date),
                                                        str(end_date)))
        if level == 'tower':
            bts_events = bts_events.filter(bts__id=level_id)
        return bts_events

