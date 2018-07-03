"""Our endpoints.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin, auth
from django.contrib.auth import views as auth_views
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse_lazy

import endagaweb.views

import endagaweb.stats_app

import rest_framework.authtoken.views


urlpatterns = [
    # API v1.
    url(r'^api-token-auth/',
        rest_framework.authtoken.views.obtain_auth_token,
        name='api-token-auth'),
    url(r'^api/v1/register/(.*)/(.*)/',
        endagaweb.views.api.Register.as_view(),
        name='api-v1-register-params'),
    url(r'^api/v1/register/', endagaweb.views.api.Register.as_view(),
        name='api-v1-register'),
    url(r'^api/v1/fetch/(.*)/', endagaweb.views.api.GetNumber.as_view(),
        name='api-v1-register-params'),
    url(r'^api/v1/fetch/', endagaweb.views.api.GetNumber.as_view(),
        name='api-v1-register'),
    url(r'^api/v1/send/', endagaweb.views.api.SendSMS.as_view(),
        name='api-v1-send'),
    url(r'^api/v1/inbound/', endagaweb.views.api.InboundSMS.as_view(),
        name='api-v1-inbound'),
    url(r'^api/v1/receipt/',
        endagaweb.views.api.InboundReceipt.as_view(),
        name='api-v1-receipt'),
    url(r'^api/v1/checkin', endagaweb.views.api.Checkin.as_view(),
        name='api-v1-checkin'),
    url(r'^api/v1/bts/sslconf', endagaweb.views.api.SSLConfig.as_view(),
        name='api-v1-bts-sslconf'),
    url(r'^api/v1/bts/register',
        endagaweb.views.api.BTSRegistration.as_view(),
        name='api-v1-bts-register'),
    url(r'^api/v1/bts/logfile',
        endagaweb.views.api.BTSLogfile.as_view(),
        name='api-v1-bts-logfile'),
    # API v2.
    # /numbers/<number> -- POST to start the number-deactivation process.
    url(r'^api/v2/numbers/(?P<msisdn>[0-9]+)$',
        endagaweb.views.api_v2.Number.as_view(), name='api-v2-numbers'),
    # /towers/<uuid> -- DELETE to start the bts deregistration process.
    url(r'^api/v2/towers/(?P<tower_uuid>[A-Za-z0-9-]+)$',
        endagaweb.views.api_v2.Tower.as_view(), name='api-v2-towers'),
    # /subscribers/<imsi> -- DELETE to start the sub-deactivation process.
    url(r'^api/v2/subscribers/(?P<imsi>[^/]+)$',
        endagaweb.views.api_v2.Subscriber.as_view(), name='api-v2-subscribers'),

    # Routes for the new stats API, not to be confused with /stats (below).
    # Passes the infrastructure level in the URL (global, network, etc) and the
    # level id as a query param.
    url(r'^api/v1/stats/(.*)',
        endagaweb.stats_app.views.StatsAPIView.as_view(),
        name='api-v1-stats-params'),

    # the internal API.
    url(r'^internal/api/v1/number/',
        endagaweb.views.internalapi.NumberLookup.as_view(),
        name='api-v1-number'),
    url(r'^internal/api/v1/uuid/',
        endagaweb.views.internalapi.UUIDLookup.as_view(),
        name='api-v1-uuid'),
    url(r'^internal/api/v1/auth/',
        endagaweb.views.internalapi.NumberAuth.as_view(),
        name='api-v1-auth'),
    url(r'^internal/api/v1/voice/',
        endagaweb.views.internalapi.BillVoice.as_view(),
        name='api-v1-voice'),

    # Our homepage.
    url(r'^$', endagaweb.views.static.LandingIndexView.as_view(),
        name='homepage'),

    # ELB testing endpoint
    url(r'^django-status', endagaweb.views.static.TestView.as_view()),

    # Notification emails and phone nnumbers
    url(r'^account/notify_emails/update', endagaweb.views.user.update_notify_emails,
        name='notify-emails'),
    url(r'^account/notify_numbers/update', endagaweb.views.user.update_notify_numbers,
        name='notify-numbers'),

    # Auth.
    url(r'^login/$', endagaweb.views.user.loginview, name='endagaweb-login'),
    url(r'^auth/', endagaweb.views.user.auth_and_login, name='auth-and-login'),
    url(r'^account/password/change', endagaweb.views.user.change_password, name="change-password"),
    url(r'^account/update', endagaweb.views.user.update_contact, name="update-account"),
    url(r'^account/', endagaweb.views.dashboard.DashboardView.as_view(),
        name='dashboard-view'),
    url(r'^logout/$', auth_views.logout, {'next_page': reverse_lazy("homepage")}, name="logout"),
    # Added for ExpiredPassword
    url(r'^password/change', endagaweb.views.user.change_expired_password, 
        name="change-expired-password"),

    # Dashboard.
    url(r'^dashboard/card/', endagaweb.views.dashboard.addcard, name="card"),
    url(r'^addmoney/', endagaweb.views.dashboard.addmoney, name="addmoney"),
    url(r'^dashboard/billing/', endagaweb.views.dashboard.billing_view, name="billing"),
    url(r'^dashboard/profile/', endagaweb.views.dashboard.profile_view, name="profile"),
    # Tower views in the dashboard.
    # /towers -- GET a list of towers or POST here to add one
    # /towers/<uuid> -- GET details on one tower
    # /towers/<uuid>/monitor -- GET related TimeseriesStats
    # /towers/<uuid>/edit -- GET details on one tower or POST to change them
    # /towers/<uuid>/deregister -- GET a UI for deregistering
    # /towers/<uuid>/tower_events -- GET related tower events
    url(r'^dashboard/towers$',
        endagaweb.views.towers.TowerList.as_view(),
        name='tower-list'),
    url(r'^dashboard/towers/(?P<uuid>[A-Za-z0-9-]+)$',
        endagaweb.views.towers.TowerInfo.as_view(),
        name='tower-info'),
    url(r'^dashboard/towers/(?P<uuid>[A-Za-z0-9-]+)/monitor$',
        endagaweb.views.towers.TowerMonitor.as_view(),
        name='tower-monitor'),
    url(r'^dashboard/towers/(?P<uuid>[A-Za-z0-9-]+)/edit$',
        endagaweb.views.towers.TowerEdit.as_view(),
        name='tower-edit'),
    url(r'^dashboard/towers/(?P<uuid>[A-Za-z0-9-]+)/deregister$',
        endagaweb.views.towers.TowerDeregister.as_view(),
        name='tower-deregister'),
    url(r'^dashboard/towers/(?P<uuid>[A-Za-z0-9-]+)/tower_events$',
        endagaweb.views.towers.TowerEvents.as_view(),
        name='tower-events'),
    # Subscriber views in the dashboard.
    url(r'^dashboard/subscribers$',
        endagaweb.views.dashboard.SubscriberListView.as_view(),
        name='subscribers-list'),
    url(r'^dashboard/subscribers/role$',
        endagaweb.views.dashboard.SubscriberUpdateRole.as_view(),
        name='subscribers-update-role'),

    url(r'^dashboard/subscribers/(?P<imsi>[^/]+)$',
        endagaweb.views.dashboard.SubscriberInfo.as_view(),
        name='subscriber-info'),
    url(r'^dashboard/subscribers/(?P<imsi>[^/]+)/activity$',
        endagaweb.views.dashboard.SubscriberActivity.as_view(),
        name='subscriber-activity'),
    url(r'^dashboard/subscribers/(?P<imsi>[^/]+)/send-sms$',
        endagaweb.views.dashboard.SubscriberSendSMS.as_view(),
        name='subscriber-send-sms'),
    url(r'^dashboard/subscribers/(?P<imsi>[^/]+)/adjust-credit$',
        endagaweb.views.dashboard.SubscriberAdjustCredit.as_view(),
        name='subscriber-adjust-credit'),
    url(r'^dashboard/subscribers/(?P<imsi>[^/]+)/edit$',
        endagaweb.views.dashboard.SubscriberEdit.as_view(),
        name='subscriber-edit'),
    url(r'^dashboard/user/management$',
        endagaweb.views.dashboard.UserManagement.as_view(),
        name='user-management'),

    url(r'^dashboard/user/management/update',
        endagaweb.views.dashboard.UserUpdate.as_view(),
        name='user-update'),

    url(r'^dashboard/user/management/checkuser',
        endagaweb.views.user.check_user,
        name='checkuser'),

    url(r'^dashboard/network/notification/translate',
        endagaweb.views.user.get_translation,
        name='notification-translate'),

    url(r'^dashboard/network/notification/event',
        endagaweb.views.user.get_event,
        name='network-event'),

    url(r'^dashboard/user/management/permissions',
        endagaweb.views.user.role_default_permissions,
        name='role-permission'),

    url(r'^dashboard/network/broadcast_sms$',
        endagaweb.views.dashboard.SubscriberSendSMS.as_view(),
        name='broadcast-sms'),

    url(r'^reset$', endagaweb.views.user.reset,
        name='reset'),

    url(r'^reset/(?P<token>[A-Za-z0-9-]+)/(?P<uidb64>[0-9A-Za-z_\-]+)/$',
        endagaweb.views.user.reset_confirm,
        name='password_reset_confirm'),

    url(r'^success/$', endagaweb.views.user.success, name='success'),

#     url(r'^password_reset/$', auth_views.password_reset, name='password_reset'),
#     url(r'^password_reset/done/$', auth_views.password_reset_done, name='password_reset_done'),
#     url(r'^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
#         auth_views.password_reset_confirm, name='password_reset_confirm'),
#     url(r'^reset/done/$', auth_views.password_reset_complete, name='password_reset_complete'),  

    url(r'^dashboard/subscriber_management/subscriber$',
        endagaweb.views.dashboard.SubscriberCategoryEdit.as_view(),
        name='subscriber-category'),
    # Network views in the dashboard.
    # /network -- GET basic network info
    # /network/prices -- GET pricing data for the network or POST to change it
    # /network/edit -- GET details on the network or POST to change them
    url(r'^dashboard/network$',
        endagaweb.views.network.NetworkInfo.as_view(),
        name='network-info'),
    url(r'^dashboard/network/prices$',
        endagaweb.views.network.NetworkPrices.as_view(),
        name='network-prices'),
    url(r'^dashboard/network/denominations$',
        endagaweb.views.network.NetworkDenomination.as_view(),
        name='network-denominations'),
    url(r'^dashboard/network/denominations/manage$',
        endagaweb.views.network.NetworkDenominationEdit.as_view(),
        name='network-denominations-manage'),
    url(r'^dashboard/network/inactive-subscribers$',
        endagaweb.views.network.NetworkInactiveSubscribers.as_view(),
        name='network-inactive-subscribers'),
    url(r'^dashboard/network/edit$',
        endagaweb.views.network.NetworkEdit.as_view(),
        name='network-edit'),
    url(r'^dashboard/network/select/(?P<network_id>[0-9]+)$',
        endagaweb.views.network.NetworkSelectView.as_view(),
        name='network-select'),
    # Added for network balance limit
    url(r'^dashboard/network/balance-limit',
        endagaweb.views.network.NetworkBalanceLimit.as_view(),
        name='network-balance-limit'),
    # Notifications
    url(r'^dashboard/network/notification/$',
        endagaweb.views.network.NetworkNotifications.as_view(),
        name='network-notifications'),
    url(r'^dashboard/network/notification/update',
        endagaweb.views.network.NetworkNotificationsEdit.as_view(),
        name='network-notifications-manage'),
    # The activity table.
    url(r'^dashboard/activity',
        endagaweb.views.dashboard.ActivityView.as_view(),
        name='network-activity'),
    url(r'^dashboard/reports/calls',
        endagaweb.views.reports.CallReportView.as_view(),
        name='call-report'),
    url(r'^dashboard/reports/subscriber',
        endagaweb.views.reports.SubscriberReportView.as_view(),
        name='subscriber-report'),
    url(r'^report/downloadcsv',
        endagaweb.views.reports.ReportGraphDownload.as_view(),
        name='download-csv'),
    url(r'^dashboard/reports/billing',
        endagaweb.views.reports.BillingReportView.as_view(),
        name='billing-report'),
    url(r'^dashboard/reports/health',
        endagaweb.views.reports.HealthReportView.as_view(),
        name='health-report'),
    url(r'^dashboard/broadcast',
        endagaweb.views.dashboard.BroadcastView.as_view(),
        name='sms-broadcast'),
    # Raise a server error on-demand to test the 500 template.
    url(r'^insta-five-hundred$',
        endagaweb.views.static.InstaFiveHundred.as_view(),
        name='insta-five-hundred'),

    # OAuth login TODO(omar): setup OAuth provider
    url(r'^staff-login/', endagaweb.views.user.staff_login_view,
        name='staff-login'),
    url(r'^accounts/', include('allauth.urls'), name='accounts'),
]


if 'django.contrib.admin' in settings.INSTALLED_APPS:
    # Only show the all-numbers table, the all-towers table and the margin
    # analysis page in staff-mode.
    urlpatterns += [
        url(r'^dashboard/staff/all-numbers$',
            endagaweb.views.staff.Numbers.as_view(),
            name='all-numbers'),
        url(r'^dashboard/staff/all-towers$',
            endagaweb.views.staff.Towers.as_view(),
            name='all-towers'),
        url(r'^dashboard/staff/margin-analysis$',
            endagaweb.views.staff.MarginAnalysis.as_view(),
            name='margin-analysis'),
        url(r'^dashboard/staff/tower-monitoring$',
            endagaweb.views.staff.TowerMonitoring.as_view(),
            name='tower-monitoring'),
        url(r'^dashboard/staff/tower-monitoring\?tower=(?P<tower>[0-9-]+)$',
            endagaweb.views.staff.TowerMonitoring.as_view(),
            name='tower-monitoring'),
        url(r'^dashboard/staff/network-earnings$',
            endagaweb.views.staff.NetworkEarnings.as_view(),
            name='network-earnings'),
    ]


urlpatterns += [
    # The dashboard 'home'.
    url(r'^dashboard', endagaweb.views.reports.DashboardView.as_view(),
        name='Call_Sms_Data_Usage'),

    # Old stats.
    url(r'^stats/numbers', endagaweb.views.stats.numbers,
        name='stats-numbers'),
    url(r'^stats/totals', endagaweb.views.stats.totals,
        name='stats-totals'),

    # Debug.
    url(r'^debug', endagaweb.views.debug.debug_view,
        name='debug'),
]


# Only use django admin outside of prod.
if 'django.contrib.admin' in settings.INSTALLED_APPS:
    # Register any apps that have admin functionality and add new URLs.
    admin.autodiscover()
    urlpatterns += [
        url(r'^django-admin/', include(admin.site.urls), name='admin'),
    ]


# We only install the loginas app in the staff version of the site and we hide
# the ghosting routes in other versions.
if 'loginas' in settings.INSTALLED_APPS:
    urlpatterns += url(r'^django-admin/', include('loginas.urls'),  name='admin'),

if 'DatabaseStorage' in settings.DEFAULT_FILE_STORAGE:
    urlpatterns += [
        url(r'^file/(?P<fname>.+)$',
            endagaweb.views.file_upload.file_view, name='file-upload')
    ]
