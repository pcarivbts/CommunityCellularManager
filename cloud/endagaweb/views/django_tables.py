"""Table definitions for the django-tables2 library.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import datetime
import json

from django.contrib.humanize.templatetags import humanize
from django.core import urlresolvers
from django.utils import html as html_utils
from django.utils import safestring
from django.utils.timesince import timesince
import django_tables2 as tables

from ccm.common.currency import humanize_credits, CURRENCIES
from endagaweb import models
from googletrans.constants import LANGUAGES


def render_user_profile(record):
    """Show the linked UserProfile's email."""
    if not record.network:
        return None
    user_profiles = models.UserProfile.objects.filter(network=record.network)
    network_names = [user_profile.network.name + ',' for user_profile in
                     user_profiles]
    limit_names = 2
    if len(network_names) > limit_names:
        network_names = network_names[:limit_names] + ['...']
    return ''.join(network_names)[:-1]


def render_uptime(record):
    """Show the humanized tower uptime."""
    if record.status != 'active' or not record.uptime:
        return safestring.mark_safe('<i>unknown</i>')
    boot = (datetime.datetime.now() -
            datetime.timedelta(seconds=record.uptime))
    return timesince(boot)


def render_last_active(value):
    """Show the tower's last active time."""
    if not value:
        element = '<i>n/a</i>'
        return safestring.mark_safe(element)
    return humanize.naturaltime(value)


def render_status(value):
    """Show the tower status as a label."""
    label_class_mapping = {
        'No Data': 'label-default',
        'Inactive': 'label-danger',
        'Active': 'label-success',
    }
    span_class = 'label'
    if value in label_class_mapping.keys():
        span_class += ' %s' % label_class_mapping[value]
    element = "<span class='%s'>%s</span>" % (span_class, value)
    return safestring.mark_safe(element)


def render_name_and_imsi_link(record):
    """Show the subscriber name and IMSI together as a link."""
    if not record.imsi:
        # sometimes empty IMSIs get uploaded to the cloud
        return "<empty IMSI>"
    kwargs = {
        'imsi': record.imsi
    }
    link = urlresolvers.reverse('subscriber-info', kwargs=kwargs)
    if record.name:
        value = "%s (%s)" % (record.name, record.imsi)
    else:
        value = record.imsi
    element = "<a href='%s'>%s</a>" % (link, html_utils.escape(value))
    return safestring.mark_safe(element)


def render_name_and_imsi(record):
    """Show the subscriber name and IMSI together without link."""
    if not record.imsi:
        # sometimes empty IMSIs get uploaded to the cloud
        return "<empty IMSI>"
    kwargs = {
        'imsi': record.imsi
    }
    if record.name:
        value = "%s / %s" % (record.name, record.imsi)
    else:
        value = record.imsi
    return safestring.mark_safe(value)


def render_balance(record):
    """Show the subscriber's balance in a humanized currency."""
    return humanize_credits(record.balance,
                            CURRENCIES[record.network.subscriber_currency])


def render_imsi(record):
    element = "<input type = 'checkbox' class ='imsi_id' name='imsi[]' " \
              "value='{0}'  id ='imsi_id_{0}' " \
              "onchange = 'imsiSelected(this)' / > ".format(record.imsi)
    return safestring.mark_safe(element)


def render_as_label(message, record, ltype='info'):
    element = "<label class='btn btn-xs btn-%s'  data-target='#all-translations' " \
              "data-toggle='modal' onclick='getNotification(%s);'>%s </label> " % (
                  ltype, record.id, message)
    return safestring.mark_safe(element)


# Changing Checkbox to Column Name
class CheckBoxColumnWithName(tables.CheckBoxColumn):
    @property
    def header(self):
        return self.verbose_name


class MinimalSubscriberTable(tables.Table):
    """Showing just a few sub attributes."""

    class Meta:
        model = models.Subscriber
        fields = ('name_and_imsi_link', 'numbers', 'balance')
        attrs = {'class': 'table'}

    name_and_imsi_link = tables.Column(
        empty_values=(), verbose_name='Name / IMSI', order_by=('name', 'imsi'))
    numbers = tables.Column(orderable=False, verbose_name='Number(s)')
    balance = tables.Column(verbose_name='Balance')

    def render_name_and_imsi_link(self, record):
        return render_name_and_imsi_link(record)

    def render_balance(self, record):
        return render_balance(record)


class SubscriberTable(tables.Table):
    """A django-tables2 Table definition for the subscriber list."""

    class Meta:
        model = models.Subscriber
        fields = ('imsi', 'name_and_imsi_link', 'numbers', 'balance', 'status',
                  'last_active', 'role')
        attrs = {'class': 'table'}

    imsi = tables.CheckBoxColumn(accessor="imsi", attrs={"th__input"
                                                         : {"id"
                                                            : "subscriber-select-all",
                                                            "onclick": "toggle(this)",
                                                            }},
                                 orderable=False)
    name_and_imsi_link = tables.Column(
        empty_values=(), verbose_name='Name / IMSI', order_by=('name', 'imsi'))
    status = tables.Column(empty_values=(), order_by=('last_camped'))
    numbers = tables.Column(orderable=False, verbose_name='Number(s)')
    balance = tables.Column(verbose_name='Balance')
    last_active = tables.Column(verbose_name='Last Active')
    role = tables.Column(empty_values=(), order_by='role')

    def render_imsi(self, record):
        return render_imsi(record)

    def render_role(self, record):
        return str(record.role).capitalize()

    def render_name_and_imsi_link(self, record):
        return render_name_and_imsi_link(record)

    def render_balance(self, record):
        return render_balance(record)

    def render_last_active(self, value):
        return render_last_active(value)

    def render_status(self, record):
        label_class_mapping = {
            'unknown': 'label-default',
            'not camped': 'label-default',
            'camped': 'label-success',
        }
        if record.is_camped:
            status ='camped'
        elif record.network.get_lowest_tower_version() < "00000.00003.00021":
            status = 'unknown'
        else:
            status = 'not camped'
        span_class = 'label %s' % label_class_mapping[status]
        element = "<span class='%s'>%s</span>" % (span_class, status)
        return safestring.mark_safe(element)


class SubscriberActivityTable(tables.Table):
    """A django-tables2 Table definition for subscriber activity."""

    class Meta:
        model = models.UsageEvent
        fields = ('date', 'reason', 'change', 'newamt')
        attrs = {'class': 'table'}
        orderable = False

    date = tables.Column(verbose_name='Date')
    reason = tables.Column(verbose_name='Activity')
    change = tables.Column(verbose_name='Cost')
    newamt = tables.Column(verbose_name='Balance')

    def render_change(self, record):
        """Fixes cost col when balance < 0.

        We have an issue where sub balances can go negative due to problems
        with the billing system.  Negative balances cause events that cost X
        *appear* to cost X - the subscriber's balance.
        """
        if record.oldamt < 0 and record.kind != 'add_money':
            return humanize_credits(0,
                                    CURRENCIES[
                                        record.network.subscriber_currency])
        else:
            return humanize_credits(record.change,
                                    CURRENCIES[
                                        record.network.subscriber_currency])

    def render_newamt(self, record):
        return humanize_credits(record.newamt,
                                CURRENCIES[record.network.subscriber_currency])


class TowerTable(tables.Table):
    """A django-tables2 Table definition for the table list."""

    class Meta:
        model = models.BTS
        fields = ('name_and_uuid_link', 'status', 'last_active', 'uptime')
        attrs = {'class': 'table'}

    name_and_uuid_link = tables.Column(
        empty_values=(), verbose_name='Name / ID',
        order_by=('nickname', 'uuid'))
    status = tables.Column(empty_values=())
    last_active = tables.Column(empty_values=(), verbose_name='Last Sync')
    uptime = tables.Column(empty_values=(), verbose_name='Uptime')

    def render_name_and_uuid_link(self, record):
        kwargs = {
            'uuid': record.uuid
        }
        link = urlresolvers.reverse('tower-info', kwargs=kwargs)
        abbreviated_uuid = record.uuid[0:5]
        if record.nickname:
            value = "%s (%s..)" % (record.nickname, abbreviated_uuid)
        else:
            value = '%s..' % abbreviated_uuid
        element = "<a href='%s'>%s</a>" % (link, html_utils.escape(value))
        return safestring.mark_safe(element)

    def render_status(self, value):
        return render_status(value)

    def render_last_active(self, value):
        return render_last_active(value)

    def render_uptime(self, record):
        return render_uptime(record)


class StaffTowerTable(tables.Table):
    """The staff-only version of the table of towers."""

    class Meta:
        model = models.BTS
        fields = ('name_and_uuid', 'user_profile', 'inbound_url',
                  'endaga_version', 'status', 'camped_subs', 'last_active',
                  'uptime')
        attrs = {'class': 'table'}

    name_and_uuid = tables.Column(
        empty_values=(), verbose_name='Name / ID',
        order_by=('nickname', 'uuid'))
    user_profile = tables.Column(empty_values=(), orderable=False)
    inbound_url = tables.Column(empty_values=(), verbose_name='Inbound URL')
    endaga_version = tables.Column(
        empty_values=(), order_by='package_versions',
        verbose_name='Endaga Version')
    status = tables.Column(empty_values=())
    camped_subs = tables.Column(empty_values=(), verbose_name='Camped Subs')
    last_active = tables.Column(empty_values=(), verbose_name='Last Sync')
    uptime = tables.Column(empty_values=(), verbose_name='Uptime')

    def render_name_and_uuid(self, record):
        kwargs = {
            'tower': record.id
        }
        link = urlresolvers.reverse('tower-monitoring', kwargs=kwargs)
        abbreviated_uuid = record.uuid[0:5]
        if record.nickname:
            value = "%s (%s..)" % (record.nickname, abbreviated_uuid)
        else:
            value = '%s..' % abbreviated_uuid
        element = "<a href='%s'>%s</a>" % (link, html_utils.escape(value))
        return safestring.mark_safe(element)

    def render_user_profile(self, record):
        return render_user_profile(record)

    def render_inbound_url(self, record):
        return record.inbound_url

    def render_endaga_version(self, record):
        package_versions = json.loads(record.package_versions)
        return package_versions['endaga_version']

    def render_status(self, value):
        return render_status(value)

    def render_camped_subs(self, record):
        """Count number of subs currently camped on this tower."""
        subs = models.Subscriber.objects.filter(
            network=record.network, bts__uuid=record.uuid)
        return len([s for s in subs if s.is_camped])

    def render_last_active(self, value):
        return render_last_active(value)

    def render_uptime(self, record):
        return render_uptime(record)


class NumberTable(tables.Table):
    """Viewing Numbers and their status."""

    class Meta:
        model = models.Number
        fields = ('created', 'number', 'subscriber_imsi', 'user_profile',
                  'state', 'country_id', 'actions')
        attrs = {'class': 'table'}

    subscriber_imsi = tables.Column(empty_values=(), verbose_name='IMSI',
                                    orderable=False)
    user_profile = tables.Column(empty_values=(), verbose_name='UserProfile',
                                 orderable=False)
    actions = tables.Column(empty_values=(), orderable=False)

    def render_subscriber_imsi(self, record):
        if not record.subscriber:
            return None
        return record.subscriber.imsi

    def render_user_profile(self, record):
        return render_user_profile(record)

    def render_actions(self, record):
        """Only show the release button in certain cases."""
        if record.subscriber:
            return None
        if record.state == 'inuse':
            return None
        template = ("<a href='#' class='release-number-link'"
                    " id='%s'>release</a>")
        element = template % record.number
        return safestring.mark_safe(element)


class DenominationTable(tables.Table):
    """A django-tables2 Table definition for the table list."""

    class Meta:
        model = models.NetworkDenomination
        fields = ('id', 'start_amount', 'end_amount', 'validity_days')
        attrs = {'class': 'table table-hover'}

    id = tables.CheckBoxColumn(accessor="pk", attrs={"th__input": {
        "onclick": "toggle(this)"}}
                               )
    start_amount = tables.Column(empty_values=(), verbose_name='Start Amount')
    end_amount = tables.Column(empty_values=(), verbose_name='End Amount')
    validity_days = tables.Column(empty_values=(),
                                  verbose_name='Validity(Days)')

    def render_start_amount(self, record):
        return humanize_credits(record.start_amount,
                                CURRENCIES[record.network.subscriber_currency])

    def render_end_amount(self, record):
        return humanize_credits(record.end_amount,
                                CURRENCIES[record.network.subscriber_currency])

    def render_action(self, record):
        """Shows the edit and delete button."""
        element = "<a href='javascript:void(0)' id='denom_%s' " \
                  "onclick='doAction(\"edit\", \"%s\");' " \
                  "class='btn btn-xs btn-info'>Edit</a> &nbsp; " % (
                      record.id, record.id)
        element += "<a href='javascript:void(0)' " \
                   "onclick='doAction(\"delete\",\"%s\");' " \
                   "class='btn btn-xs btn-danger'" \
                   "data-target='#delete-denom-modal' " \
                   "data-toggle='modal'>Delete</a>" % (
                       record.id)
        return safestring.mark_safe(element)


def render_is_active(record):
    user = record.id
    is_superuser = ''
    if record.is_active:
        status = 'checked'
    else:
        status = ''

    # Disable toggle for Cloud Admin
    if record.is_superuser:
        is_superuser = 'disabled'
    element = "<input id='%d' type='checkbox' %s " \
              "data-toggle='toggle' data-size='mini' data-off='Blocked' " \
              "data-on='Active' %s><span id='toggle-%d' hidden>&nbsp;&nbsp;" \
              "<span class='glyphicon glyphicon-ok'></span>"" \
              ""</span>" % (
                  user, status, is_superuser, user)

    return safestring.mark_safe(element)


class UserTable(tables.Table):
    """A django-tables2 Table definition for User."""

    class Meta:
        model = models.User
        fields = ('id', 'email', 'role', 'is_active', 'last_login')
        attrs = {'class': 'table'}
        orderable = False

    id = tables.CheckBoxColumn(accessor="pk",
                               attrs={
                                   "th__input": {"onclick": "toggle(this)"}})
    # Get user role from userprofile
    role = tables.Column(accessor='userprofile.role', verbose_name='Role',
                         orderable=True)
    # username = tables.Column(verbose_name='Username', orderable=True)
    email = tables.Column(verbose_name='Email', orderable=True)
    is_active = tables.BooleanColumn(verbose_name='Status', orderable=True)
    last_login = tables.DateTimeColumn(verbose_name='Last Login', short=True,
                                       orderable=True)

    def render_is_active(self, record):
        return render_is_active(record)

    def render_role(self, record):
        role = record.userprofile.role
        if role in ['Cloud Admin', 'Network Admin']:
            element = '<span class = "label label-danger">%s</span>' % role
        else:
            element = '<span class = "label label-info">%s</span>' % role

        return safestring.mark_safe(element)


class SubscriberManagementTable(tables.Table):
    """A django-tables2 Table definition for managing the subscriber role."""

    class Meta:
        model = models.Subscriber
        fields = ('imsi', 'name_and_imsi', 'last_active', 'numbers', 'role')
        attrs = {'class': 'table'}

    imsi = CheckBoxColumnWithName(verbose_name='', empty_values=(), )
    name_and_imsi = tables.Column(
        empty_values=(), verbose_name='Name / IMSI', order_by=('name',
                                                               'imsi'))
    role = tables.Column(empty_values=(), order_by='role')
    numbers = tables.Column(orderable=False, verbose_name='Number(s)')
    last_active = tables.Column(verbose_name='Last Active')

    def render_name_and_imsi(self, record):
        return render_name_and_imsi(record)

    def render_last_active(self, value):
        return render_last_active(value)

    def render_imsi(self, record):
        return render_imsi(record)


class NotificationTable(tables.Table):
    """
    Notification table for managing notification messages
    """

    class Meta:
        model = models.Notification
        fields = ('id', 'event', 'message', 'type')
        attrs = {'class': 'table'}

    id = tables.CheckBoxColumn(accessor="pk",
                               attrs={"th__input":
                                          {"onclick": "toggle(this)"}
                                      }
                               )
    type = tables.Column()
    event = tables.Column(orderable=False)
    message = tables.Column(orderable=False)

    def render_event(self, record):
        event = str(record.event).replace('_', ' ').upper()
        element = "<a href='#'" \
                  "data-target='#all-translations' data-toggle='modal' " \
                  "onclick='getNotification(%s);'>%s </a> " % (record.id,
                                                               event)
        return safestring.mark_safe(element)


class NotificationTableTranslated(tables.Table):
    """
    Notification table specific language message
    """

    class Meta:
        model = models.Notification
        fields = ('id', 'event', 'translation', 'type')
        attrs = {'class': 'table'}

    id = tables.CheckBoxColumn(accessor="pk",
                               attrs={"th__input":
                                          {"onclick": "toggle(this)"}
                                      }
                               )
    type = tables.Column()
    event = tables.Column(orderable=False)
    translation = tables.Column(orderable=False, verbose_name='Message')

    def render_event(self, record):
        event = str(record.event).replace('_', ' ').upper()
        element = "<a href='#'" \
                  "data-target='#all-translations' data-toggle='modal' " \
                  "onclick='getNotification(%s);'>%s </a> " % (record.id,
                                                               event)
        return safestring.mark_safe(element)
