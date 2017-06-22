"""The stats clients -- aggregates data for the stats API views.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant 
of patent rights can be found in the PATENTS file in the same directory.
"""

import time
from datetime import datetime, timedelta
from operator import itemgetter

import pytz
import qsstats
from dateutil.rrule import rrule, MONTHLY
from django.db.models import Q
from django.db.models import aggregates
from endagaweb import models

CALL_KINDS = [
    'local_call', 'local_recv_call', 'outside_call', 'incoming_call',
    'free_call', 'error_call']
SMS_KINDS = [
    'local_sms', 'local_recv_sms', 'outside_sms', 'incoming_sms', 'free_sms',
    'error_sms']
SUBSCRIBER_KINDS = ['provisioned', 'deprovisioned']
ZERO_BALANCE_SUBSCRIBER = ['zero_balance_subscriber']
INACTIVE_SUBSCRIBER = ['expired', 'first_expired', 'blocked']
HEALTH_STATUS = ['bts down','bts up']
TRANSFER_KINDS = ['transfer', 'add-money']
WATERFALL_KINDS = ['loader', 'reload_rate', 'reload_amount',
                   'reload_transaction', 'average_frequency']
DENOMINATION_KINDS = ['start_amount', 'end_amount']
USAGE_EVENT_KINDS = CALL_KINDS + SMS_KINDS + ['gprs'] + SUBSCRIBER_KINDS + \
                    TRANSFER_KINDS + WATERFALL_KINDS
TIMESERIES_STAT_KEYS = [
    'ccch_sdcch4_load', 'tch_f_max', 'tch_f_load', 'sdcch8_max',
    'tch_f_pdch_load', 'tch_f_pdch_max', 'tch_h_load', 'tch_h_max',
    'sdcch8_load', 'ccch_sdcch4_max',
    'sdcch_load', 'sdcch_available', 'tchf_load', 'tchf_available',
    'pch_active', 'pch_total', 'agch_active', 'agch_pending',
    'gprs_current_pdchs', 'gprs_utilization_percentage', 'noise_rssi_db',
    'noise_ms_rssi_target_db', 'cpu_percent', 'memory_percent', 'disk_percent',
    'bytes_sent_delta', 'bytes_received_delta',
]


class StatsClientBase(object):
    """The base Stats client.

    Aggregates and analyzes data related to UsageEvents and TimeseriesStats.
    This client is primarily meant to be used by the stats_app's views and the
    js in those views, but it could also be used to populate templates in the
    views of other apps.

    To use, create a client with two args: 'infrastructure level' and id.  The
    level is global or network.  Stats will be aggregated at this level.  The
    id is the id of, say, the network-of-interest.

    Then query for a timeseries within some timeframe and over some interval.
    The querying is usually specified in one of the specific SMS, call or
    billing clients.  Data is counted within the interval along the timeframe.
    That is, it will return something like "the number of SMS sent on this
    network for each month in this timespan."  Or the "total cost of Nexmo SMS
    for this BTS per day."  Or "the average SDCCH load last week."

    Note that this base client supports queries over UsageEvent and
    TimeseriesStat objects.  The former objects can be queried at the global or
    network level, the latter only at the tower level.
    """

    def __init__(self, level, level_id=None):
        """A generic stats client.

        Args:
            level: the 'infrastructure level' on which to aggregate data, valid
                   values are global, network or tower
            level_id: the model id of the network or tower
        """
        self.level = level
        self.level_id = level_id

    def aggregate_timeseries(self, param, **kwargs):
        """Get timeseries data for SMS, calls, data or tower stats.

        Args:
            param: the "kind" of UsageEvent to filter for or the key of a
                   TimeseriesStat.  See the KINDS and KEYS constants for valid
                   values.

        Keyword Args:
            start_time_epoch: start of the timespan in seconds since epoch
                              (default is the start of epoch)
            end_time_epoch: end of the timespan in seonds since epoch (default
                            is -1 which gets translated into the current time)
            interval: the interval on which to count, valid values are years,
                      months, weeks, days, hours or minutes
            aggregation: controls the aggregation method.  May be one of
                         'count' or 'duration' (the default is 'count').

        Returns:
            a list of (epoch timestamp, value) tuples

        Raises:
            qsstats.InvalidInterval if the interval is unknown
        """
        start_time_epoch = kwargs.pop('start_time_epoch', 0)
        end_time_epoch = kwargs.pop('end_time_epoch', -1)
        interval = kwargs.pop('interval', 'months')
        aggregation = kwargs.pop('aggregation', 'count')
        report_view = kwargs.pop('report_view', 'list')
        # Turn the start and end epoch timestamps into datetimes.
        start = datetime.fromtimestamp(start_time_epoch, pytz.utc)
        if end_time_epoch != -1:
            end = datetime.fromtimestamp(end_time_epoch, pytz.utc)
        else:
            end = datetime.fromtimestamp(time.time(), pytz.utc)
        # Build the queryset -- first determine if we're dealing with
        # UsageEvents or TimeseriesStats.
        filters = None
        if param in USAGE_EVENT_KINDS:
            objects = models.UsageEvent.objects
            filters = Q(kind=param)
        elif param in ZERO_BALANCE_SUBSCRIBER:
            objects = models.UsageEvent.objects
            filters = Q(oldamt__gt=0,newamt__lte=0)
        elif param in INACTIVE_SUBSCRIBER:
            aggregation = 'valid_through'
            objects = models.Subscriber.objects
            filters = Q(state = param)
        elif param in TIMESERIES_STAT_KEYS:
            objects = models.TimeseriesStat.objects
            filters = Q(key=param)
        elif param in HEALTH_STATUS:
            objects = models.SystemEvent.objects
            filters = Q(type=param)
        else:
            # For Dynamic Kinds coming from Database currently for Top Up
            objects = models.UsageEvent.objects
            filters = Q(kind='transfer')
        # Filter by infrastructure level.
        if self.level == 'tower':
            filters = filters & Q(bts__id=self.level_id)
        elif self.level == 'network' and param not in HEALTH_STATUS:
            filters = filters & Q(network__id=self.level_id)
        elif self.level == 'global':
            pass
        if kwargs.has_key('query'):
            filters = filters & kwargs.pop('query')

        if report_view == 'value':
            filters = filters & Q(date__lte=end) & Q(date__gte=start)
            result = models.UsageEvent.objects.filter(filters).values_list(
                'subscriber_id', flat=True).distinct()
            return list(result)

        # Create the queryset itself.
        queryset = objects.filter(filters)
        # Use qsstats to aggregate the queryset data on an interval.
        if aggregation == 'duration':
            queryset_stats = qsstats.QuerySetStats(
                queryset, 'date', aggregate=aggregates.Sum('billsec'))
        elif aggregation == 'up_byte_count':
            queryset_stats = qsstats.QuerySetStats(
                queryset, 'date', aggregate=aggregates.Sum('uploaded_bytes'))
        elif aggregation == 'down_byte_count':
            queryset_stats = qsstats.QuerySetStats(
                queryset, 'date', aggregate=aggregates.Sum('downloaded_bytes'))
        elif aggregation == 'average_value':
            queryset_stats = qsstats.QuerySetStats(
                queryset, 'date', aggregate=aggregates.Avg('value'))
        elif aggregation == 'valid_through':
            queryset_stats = qsstats.QuerySetStats(queryset, 'valid_through')
        # Sum of change in amounts for SMS/CALL
        elif aggregation == 'transaction_sum':
            queryset_stats = qsstats.QuerySetStats(
                # Change is negative value, set positive for charts
                queryset, 'date', aggregate=(aggregates.Sum('change') * -1))
            # Do this if percentage if set for top top-up
            percentage = kwargs['topup_percent']
            if percentage is not None:
                subscribers = {}
                percentage = float(percentage) / 100
                # Create subscribers dict
                for query in queryset:
                    subscribers[query.subscriber_imsi] = 0
                for query in queryset_stats.qs:
                    subscribers[query.subscriber_imsi] += (query.change * -1)
                top_count_of_subscribers = (len(subscribers) * percentage)
                top_imsis = int(round(top_count_of_subscribers))
                # Get top percentage of subscribers for TOP UP
                top_subscribers = list(dict(
                    sorted(subscribers.iteritems(), key=itemgetter(1),
                           reverse=True)[:top_imsis]).keys())
                queryset = queryset_stats.qs.filter(
                    Q(subscriber_imsi__in=top_subscribers))
                queryset_stats = qsstats.QuerySetStats(
                    queryset, 'date', aggregate=(
                        aggregates.Sum('change') * -1))
        elif aggregation == 'loader':
            queryset_stats = qsstats.QuerySetStats(
                queryset, 'date', aggregate=aggregates.Count('subscriber_id'))
        else:
            queryset_stats = qsstats.QuerySetStats(queryset, 'date')
        timeseries = queryset_stats.time_series(start, end, interval=interval)
        # The timeseries results is a list of (datetime, value) pairs.  We need
        # to convert the datetimes to timestamps with millisecond precision and
        # then zip the pairs back together.
        datetimes, values = zip(*timeseries)
        if report_view == 'summary':
            # Return sum count for pie-chart and table view
            if aggregation == 'transaction_sum':
                # When kind is change
                return sum(values) * 0.000001
            return sum(values)

        timestamps = [
            int(time.mktime(dt.timetuple()) * 1e3 + dt.microsecond / 1e3)
            for dt in datetimes
        ]
        # Round the stats values when necessary.
        rounded_values = []
        for value in values:
            if round(value) != round(value, 2):
                rounded_values.append(round(value, 2))
            else:
                rounded_values.append(value)
        return zip(timestamps, rounded_values)


class SMSStatsClient(StatsClientBase):
    """The SMS stats client.

    Gets number of SMS, with the ability to filter by SMS kind.

    sms_stats_client = stats_client.SMSStatsClient('network', 2)
    print sms_stats_client.timeseries(kind='outside_sms', interval='minutes',
                                      start_time_epoch=12000,
                                      end_time_epoch=13000)
    # [(12345, 1), (12305, 4), (12365, 6) ... ]
    """

    def __init__(self, *args, **kwargs):
        super(SMSStatsClient, self).__init__(*args, **kwargs)

    def timeseries(self, kind=None, **kwargs):
        """Get SMS timeseries.

        Wraps StatsClientBase.aggregate_timeseries with some filtering
          capabilities.
        TODO(matt): implement filtering to support outgoing_sms

        Args:
            kind: the kind of SMS UsageEvent to query for, valid values are
                  outside_sms, incoming_sms, local_sms, local_recv_sms,
                  free_sms, error_sms, sms.  If nothing is specified this will
                  default to 'sms' and return the sum of outside, local, free,
                  error and incoming.

        Keyword Args:
            start_time_epoch, end_time_epoch, interval: are all passed on to
            StatsClientBase.aggregate_timeseries
        """
        results = []
        if kind == None or kind == 'sms':
            # Make calls to aggregate_timeseries and aggregate the results.
            all_sms_kinds = ['outside_sms', 'incoming_sms', 'local_sms',
                             'local_recv_sms', 'free_sms', 'error_sms']
            for sms_kind in all_sms_kinds:
                usage = self.aggregate_timeseries(sms_kind, **kwargs)
                values = [u[1] for u in usage]
                results.append(values)
            # The dates are all the same in each of the loops above, so we'll
            # just grab the last one.
            dates = [u[0] for u in usage]
            # The results var is now a list of lists where each sub-list is a
            # category of SMS and each element is the number of SMS sent for
            # each date matching that category.  So we want to sum each
            # 'column' into one value.
            totals = [sum(v) for v in zip(*results)]
            return zip(dates, totals)
        else:
            return self.aggregate_timeseries(kind, **kwargs)


class CallStatsClient(StatsClientBase):
    """The call stats client.

    Gets number of calls, with the ability to filter by call kind.
    Supports aggregation by counts (number of calls) or by the duration of
    calls with the ability to filter by call kind.

    call_stats_client = stats_client.CallStatsClient('network', 2)
    print call_stats_client.timeseries(kind='outside_call', interval='minutes',
                                       start_time_epoch=12000,
                                       end_time_epoch=13000,
                                       aggregation='duration')
    # [(12345, 1), (12305, 4), (12365, 6) ... ]
    """

    def __init__(self, *args, **kwargs):
        super(CallStatsClient, self).__init__(*args, **kwargs)

    def timeseries(self, kind=None, **kwargs):
        """Get call timeseries.

        Wraps StatsClientBase.aggregate_timeseries with some filtering
          capabilities.

        Args:
            kind: the kind of call UsageEvent to query for, valid values are
                  outside_call, incoming_call, local_call, local_recv_call,
                  free_call, error_call and call.  If nothing is specified this
                  will default to 'call' and return the sum of outside,
                  incoming, local, free and error.

        Keyword Args:
            start_time_epoch, end_time_epoch, interval: are all passed on to
                StatsClientBase.aggregate_timeseries
            aggregation: controls the qsstats aggregation, one of 'count' or
                         'duration' (default is 'count').  The former just
                         counts the UsageEvents by id while the latter takes
                         the sum of the 'call_duration' field (and thus should
                         really only be used for calls).
        """
        results = []
        if kind == None or kind == 'call':
            # Make calls to aggregate_timeseries and aggregate the results.
            all_call_kinds = ['outside_call', 'incoming_call', 'local_call',
                              'local_recv_call', 'free_call', 'error_call']
            for call_kind in all_call_kinds:
                usage = self.aggregate_timeseries(call_kind, **kwargs)
                values = [u[1] for u in usage]
                results.append(values)
            # The dates are all the same in each of the loops above, so we'll
            # just grab the last one.
            dates = [u[0] for u in usage]
            # The results var is now a list of lists where each sub-list is a
            # category of call and each element is the number of calls sent for
            # each date matching that category.  So we want to sum each
            # 'column' into one value.
            totals = [sum(v) for v in zip(*results)]
            return zip(dates, totals)
        else:
            return self.aggregate_timeseries(kind, **kwargs)


class GPRSStatsClient(StatsClientBase):
    """The GPRS stats client.

    Gets number of MB uploaded and downloaded, as well as the sum.

    gprs_stats_client = stats_client.GPRSStatsClient('network', 2)
    print sms_stats_client.timeseries(kind='downloaded_data', interval='days',
                                      start_time_epoch=12000,
                                      end_time_epoch=33000)
    # [(12345, 1.3), (12305, 4.2), (12365, 6.3) ... ]
    """

    def __init__(self, *args, **kwargs):
        super(GPRSStatsClient, self).__init__(*args, **kwargs)

    def timeseries(self, kind=None, **kwargs):
        """Get GPRS timeseries.

        Wraps StatsClientBase.aggregate_timeseries with some filtering
          capabilities.

        Note that GPRS UEs are all of the type "gprs," but each event of this
        type contains a count for uploaded and downloaded bytes.

        Args:
            kind: the kind of GPRS UsageEvent to query for, valid values are
                  downloaded_data, uploaded_data and the default, total_data.
                  The default will return the sum of downloaded and uploaded.

        Keyword Args:
            start_time_epoch, end_time_epoch, interval: are all passed on to
            StatsClientBase.aggregate_timeseries
        """
        start_time_epoch = kwargs.pop('start_time_epoch', 0)
        end_time_epoch = kwargs.pop('end_time_epoch', -1)
        interval = kwargs.pop('interval', 'months')
        if kind in (None, 'total_data', 'uploaded_data'):
            uploaded_usage = self.aggregate_timeseries(
                'gprs', aggregation='up_byte_count', interval=interval,
                start_time_epoch=start_time_epoch,
                end_time_epoch=end_time_epoch)
            uploaded_usage = self.convert_to_megabytes(uploaded_usage)
        if kind in (None, 'total_data', 'downloaded_data'):
            downloaded_usage = self.aggregate_timeseries(
                'gprs', aggregation='down_byte_count', interval=interval,
                start_time_epoch=start_time_epoch,
                end_time_epoch=end_time_epoch)
            downloaded_usage = self.convert_to_megabytes(downloaded_usage)
        if kind == 'uploaded_data':
            return uploaded_usage
        elif kind == 'downloaded_data':
            return downloaded_usage
        elif kind in (None, 'total_data'):
            # Sum uploaded and downloaded.
            up_values = [v[1] for v in uploaded_usage]
            down_values = [v[1] for v in downloaded_usage]
            totals = [sum(i) for i in zip(up_values, down_values)]
            # The dates are all the same for uploaded and downloaded, so we'll
            # just use the uploaded usage dates.
            dates = [v[0] for v in uploaded_usage]
            return zip(dates, totals)

    def convert_to_megabytes(self, timeseries):
        """Converts values in a [(time, value) .. ] timeseries to MB."""
        times, values = zip(*timeseries)
        values = [v / 2. ** 20 for v in values]
        return zip(times, values)


class BillingStatsClient(StatsClientBase):
    """The billing stats client.

    Supports aggregation by total cost or "counts" (transaction number) with
    the ability to filter by transaction kind.
    """
    pass


class TimeseriesStatsClient(StatsClientBase):
    """Gathers data on TimeseriesStat instances at a tower level only.

    client = stats_client.TimeseriesStatsClient('tower', tower_id)
    print client.timeseries(
        key='gprs_utilization_percentage', interval='minutes',
        start_time_epoch=12000, end_time_epoch=13000)
    # [(12345, 1), (12305, 4), (12365, 6) ... ]
    """

    def __init__(self, *args, **kwargs):
        super(TimeseriesStatsClient, self).__init__(*args, **kwargs)

    def timeseries(self, key=None, **kwargs):
        if 'aggregation' not in kwargs:
            kwargs['aggregation'] = 'average_value'
        return self.aggregate_timeseries(key, **kwargs)


class SubscriberStatsClient(StatsClientBase):
    """Gathers data on SubscriberStats instance at tower and network level"""

    def __init__(self, *args, **kwargs):
        super(SubscriberStatsClient, self).__init__(*args, **kwargs)

    def timeseries(self, key=None, **kwargs):
        if 'aggregation' not in kwargs:
            kwargs['aggregation'] = 'average_value'
        return self.aggregate_timeseries(key, **kwargs)


class TransferStatsClient(StatsClientBase):
    """ Gather retailer transfer and recharge report """

    def __init__(self, *args, **kwargs):
        super(TransferStatsClient, self).__init__(*args, **kwargs)

    def timeseries(self, kind=None, **kwargs):
        # Set queryset from subscriber role as retailer
        kwargs['query'] = Q(subscriber__role='retailer')
        return self.aggregate_timeseries(kind, **kwargs)


class TopUpStatsClient(StatsClientBase):
    def __init__(self, *args, **kwargs):
        super(TopUpStatsClient, self).__init__(*args, **kwargs)

    def timeseries(self, kind=None, **kwargs):
        # Change is negative convert to compare
        try:
            raw_amount = [(float(denom) * -1 / 10000) for denom in
                          kwargs['extras'].split('-')]
            kwargs['query'] = Q(change__gte=raw_amount[1]) & Q(
                change__lte=raw_amount[0]) & Q(subscriber__role='retailer')
            return self.aggregate_timeseries(kind, **kwargs)
        except ValueError:
            # If no denominations available in this network
            raise ValueError('no denominations available in current network')



class BTSStatsClient(StatsClientBase):
    """Gathers data on BTSStats instances at a tower and network level"""

    def __init__(self, *args, **kwargs):
        super(BTSStatsClient, self).__init__(*args, **kwargs)

    def timeseries(self, key=None, **kwargs):
        if 'aggregation' not in kwargs:
            kwargs['aggregation'] = 'average_value'
        return self.aggregate_timeseries(key, **kwargs)


class WaterfallStatsClient(StatsClientBase):
    """ waterfall reports data """

    def __init__(self, *args, **kwargs):
        super(WaterfallStatsClient, self).__init__(*args, **kwargs)

    def timeseries(self, kind=None, **kwargs):
        # Get report data in timeseries format
        start_time_epoch = kwargs.pop('start_time_epoch', 0)
        end_time_epoch = kwargs.pop('end_time_epoch', -1)

        start = datetime.fromtimestamp(start_time_epoch, pytz.utc)
        if end_time_epoch != -1:
            end = datetime.fromtimestamp(end_time_epoch, pytz.utc)
        else:
            end = datetime.fromtimestamp(time.time(), pytz.utc)

        response = {'header': [{'title': "Months"}, {'title': "Activation"}],
                    'data': []};

        months = rrule(MONTHLY, dtstart=start, until=end)
        for mnth in months:
            key = mnth.strftime("%b") + "-" + mnth.strftime("%Y")
            response['header'].append({'title':key})

            # Get last/first date of month from selected month
            next_month = mnth.replace(day=28) + timedelta(days=4)
            stats_end_dt = next_month - timedelta(days=next_month.day)
            stats_start_dt = mnth

            kwargs['start_time_epoch'] = int(stats_start_dt.strftime("%s"))
            kwargs['end_time_epoch'] = int(stats_end_dt.strftime("%s"))
            kwargs['query'] = Q(subscriber__role='retailer')
            kind_key = 'provisioned'
            kwargs['report_view'] = 'value'
            subscribers = self.aggregate_timeseries(kind_key, **kwargs)

            month_row = [key, len(subscribers)]
            for col_mnth in months:
                month_start_dt = col_mnth
                # Get last date of month from selected month
                next_month = col_mnth.replace(day=28) + timedelta(days=4)
                month_end_dt = next_month - timedelta(days=next_month.day)

                kwargs['start_time_epoch'] = int(month_start_dt.strftime("%s"))
                kwargs['end_time_epoch'] = int(month_end_dt.strftime("%s"))
                if kind == 'loader':
                    kwargs['aggregation'] = 'loader'
                    kwargs['report_view'] = 'value'
                elif kind == 'reload_transaction':
                    kwargs['aggregation'] = 'count'
                    kwargs['report_view'] = 'summary'
                elif kind == 'reload_amount':
                    kwargs['aggregation'] = 'transaction_sum'
                    kwargs['report_view'] = 'summary'
                elif kind == 'reload_rate':
                    kwargs['aggregation'] = 'transaction_sum'
                    kwargs['report_view'] = 'summary'
                elif kind == 'average_frequency':
                    kwargs['aggregation'] = 'transaction_sum'
                    kwargs['report_view'] = 'summary'
                kwargs['query'] = Q(subscriber_id__in=subscribers)
                kind_row = 'transfer'
                result = self.aggregate_timeseries(kind_row, **kwargs)

                if isinstance(result, (list, tuple)):
                    month_row.append(len(result))
                else:
                    month_row.append(result)
            response['data'].append(month_row)
        return response

