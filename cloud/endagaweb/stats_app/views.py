"""API handlers for accessing stats.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant 
of patent rights can be found in the PATENTS file in the same directory.
"""

from rest_framework import authentication
from rest_framework import permissions
from rest_framework import renderers
from rest_framework import response
from rest_framework import status
from rest_framework import views
import pytz
from rest_framework.authtoken.models import Token
import stripe
from guardian.shortcuts import get_objects_for_user

from ccm.common.currency import parse_credits, humanize_credits, \
    CURRENCIES, Money
from endagaweb.stats_app import stats_client

from endagaweb.models import (UserProfile, Ledger, Subscriber, UsageEvent,
                              Network, PendingCreditUpdate, Number)
# Set the stat types that we can query for.  Note that some of these kinds are
# 'faux kinds' in that the stats client aggregates the true UsageEvent kinds
# for these other categories: sms, call, uploaded_data, downloaded_data,
# total_data.
SMS_KINDS = stats_client.SMS_KINDS + ['sms']
CALL_KINDS = stats_client.CALL_KINDS + ['call'] #, 'oustside_call']
GPRS_KINDS = ['total_data', 'uploaded_data', 'downloaded_data']
TIMESERIES_STAT_KEYS = stats_client.TIMESERIES_STAT_KEYS
SUBSCRIBER_KINDS = stats_client.SUBSCRIBER_KINDS
ZERO_BALANACE_SUBSCRIBER = stats_client.ZERO_BALANCE_SUBSCRIBER
INACTIVE_SUBSCRIBER = stats_client.INACTIVE_SUBSCRIBER
HEALTH_STATUS = stats_client.HEALTH_STATUS
WATERFALL_KINDS = ['loader', 'reload_rate', 'reload_amount',
                   'reload_transaction', 'average_frequency']
DENOMINATION_KINDS = stats_client.DENOMINATION_KINDS
# Set valid intervals.
INTERVALS = ['years', 'months', 'weeks', 'days', 'hours', 'minutes']

TRANSFER_KINDS = stats_client.TRANSFER_KINDS
VALID_STATS = SMS_KINDS + CALL_KINDS + GPRS_KINDS + TIMESERIES_STAT_KEYS + \
              TRANSFER_KINDS + SUBSCRIBER_KINDS + ZERO_BALANACE_SUBSCRIBER + \
              INACTIVE_SUBSCRIBER + WATERFALL_KINDS + HEALTH_STATUS + DENOMINATION_KINDS
# Set valid aggregation types.
AGGREGATIONS = ['count', 'duration', 'up_byte_count', 'down_byte_count',
                'average_value', 'transaction_sum']
REPORT_VIEWS = ['summary', 'list']

# Any requested start time earlier than this date will be set to this date.
# This comes from a bug where UEs were generated at an astounding rate in
# ~April 2014.
# TODO(matt): scrub our Papua UEs and then remove this limit.
JUL30_2014 = 1406680050


def parse_query_params(params):
    """Validate incoming query params."""
    # Set query defaults -- the default timespan end is 'now' (and we'll
    # represent now as -1).
    parsed_params = {
        'start-time-epoch': JUL30_2014,
        'end-time-epoch': -1,
        'interval': 'months',
        'stat-types': ['sms'],
        'level-id': -1,
        'aggregation': 'count',
        'report-view': 'list',
        'extras': [],
        'topup-percent': None,
    }
    # Override defaults with any query params that have been set, if the
    # query params are valid.
    if 'start-time-epoch' in params:
        parsed_params['start-time-epoch'] = int(params['start-time-epoch'])
        if parsed_params['start-time-epoch'] < JUL30_2014:
            parsed_params['start-time-epoch'] = JUL30_2014
    if 'end-time-epoch' in params:
        parsed_params['end-time-epoch'] = int(params['end-time-epoch'])
    # Check if, for some reason, the end time is before the start time.  If it
    # is, reset both params to their defaults.
    if parsed_params['end-time-epoch'] < parsed_params['start-time-epoch']:
        parsed_params['start-time-epoch'] = JUL30_2014
        parsed_params['end-time-epoch'] = -1
    if 'interval' in params and params['interval'] in INTERVALS:
        parsed_params['interval'] = params['interval']
    if 'stat-types' in params:
        stat_types = params['stat-types'].split(',')
        validated_types = [s for s in stat_types if s in VALID_STATS]
        # If nothing validated, we just leave the stat-types as the default.
        if validated_types:
            parsed_params['stat-types'] = validated_types
        # Check if stat-type is dynamic currently for denominations
        if params.has_key('dynamic-stat') and bool(params['dynamic-stat']):
            parsed_params['stat-types'] = stat_types
            # For filtering top topups as per percentage
            if params.has_key('topup-percent'):
                parsed_params['topup-percent'] = params['topup-percent']
    if 'level-id' in params:
        parsed_params['level-id'] = int(params['level-id'])
    if 'aggregation' in params and params['aggregation'] in AGGREGATIONS:
        parsed_params['aggregation'] = params['aggregation']
    if 'extras' in params:
        parsed_params['extras'] = params['extras'].split(',')
    if 'report-view' in params and params['report-view'] in REPORT_VIEWS:
        parsed_params['report-view'] = params['report-view']
    return parsed_params


class StatsAPIView(views.APIView):
    """The stats API view (handles multiple client types)."""

    # DRF sets up permissions, auth and rendering with these class-level vars.
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (authentication.SessionAuthentication,
                              authentication.TokenAuthentication)
    renderer_classes = (renderers.JSONRenderer,)

    def get(self, request, infrastructure_level):
        """GET request handler.

        TODO(matt): there is an interesting issue here in that this client lets
                    one make a single request with many stat_types, but the
                    aggregation type may be invalid for some of those types.
                    The way we use this API now, things works fine, but maybe
                    we want to handle this better in the future.  For instance,
                    you could imagine passing in an array of more explicit
                    aggregations.

        Args:
            request: a DRF Request instance
            infrastructure_level: global, network or tower

        Query Params (none are required):
            start-time-epoch: start of timespan in seconds since epoch
            end-time-epoch: end of timespan in seconds since epoch
            interval: data will be aggregated for the timespan at points
                      according to this parameter
            stat-types: the types of stat we're requesting.  May be a
                        comma-separated set of multiple stat types.
            level-id: the infrastructure_level id, e.g. the network django
                      model id or None if global
            aggregation: how to process the stats

        Returns:
            a DRF response.Response instance
        """
        # Parse params.
        params = parse_query_params(request.query_params)
        # Build up the return data.
        data = {
            'results': [],
        }
        for index, stat_type in enumerate(params['stat-types']):
            # Setup the appropriate stats client, SMS, call or GPRS.
            if stat_type in SMS_KINDS:
                client_type = stats_client.SMSStatsClient
            elif stat_type in CALL_KINDS:
                client_type = stats_client.CallStatsClient
            elif stat_type in GPRS_KINDS:
                client_type = stats_client.GPRSStatsClient
            elif stat_type in TIMESERIES_STAT_KEYS:
                client_type = stats_client.TimeseriesStatsClient
            elif stat_type in SUBSCRIBER_KINDS:
                client_type = stats_client.SubscriberStatsClient
            elif stat_type in TRANSFER_KINDS:
                client_type = stats_client.TransferStatsClient
            elif stat_type in ZERO_BALANACE_SUBSCRIBER:
                client_type = stats_client.SubscriberStatsClient
            elif stat_type in INACTIVE_SUBSCRIBER:
                client_type = stats_client.SubscriberStatsClient
            elif stat_type in HEALTH_STATUS:
                client_type = stats_client.BTSStatsClient
            elif stat_type in WATERFALL_KINDS:
                client_type = stats_client.WaterfallStatsClient
            elif stat_type in TIMESERIES_STAT_KEYS:
                client_type = stats_client.TimeseriesStatsClient
            elif stat_type in TIMESERIES_STAT_KEYS:
                client_type = stats_client.TimeseriesStatsClient
            else:
                client_type = stats_client.TopUpStatsClient
            # Instantiate the client at an infrastructure level.
            if infrastructure_level == 'global':
                client = client_type('global')
            elif infrastructure_level == 'network':
                client = client_type('network', params['level-id'])
            elif infrastructure_level == 'tower':
                client = client_type('tower', params['level-id'])
            try:
                extra_param = params['extras'][index]
            except IndexError:
                extra_param = None


            # Get timeseries results and append it to data.
            results = client.timeseries(
                stat_type,
                interval=params['interval'],
                start_time_epoch=params['start-time-epoch'],
                end_time_epoch=params['end-time-epoch'],
                aggregation=params['aggregation'],
                report_view=params['report-view'],
                extras=extra_param,
                topup_percent=params['topup-percent']
            )
            data['results'].append({
                "key": stat_type,
                "values": results
            })
        # Convert params.stat_types back to CSV and echo back the request.
        params['stat-types'] = ','.join(params['stat-types'])
        data['request'] = params
        # Send results and echo back the request params.
        response_status = status.HTTP_200_OK
        return response.Response(data, response_status)
