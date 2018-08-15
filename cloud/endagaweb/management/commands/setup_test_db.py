"""Sets up a a basic test DB for external (non-test suite) testing.

Adds Users, BTSs, Numbers, Subscribers, UsageEvents and SystemEvents.
-- all this should then be visible in a local dashboard.  Make sure you've first
run fabric's init_dev to properly setup the db and its migrations.  Then you can
login with the test username and pw as defined below.

Usage:
    python manage.py setup_test_db

To reset the local test db:
    python manage.py flush
    python manage.py migrate endagaweb
    python manage.py migrate authtoken

Or to really start afresh:
    vagrant ssh db
    sudo -u postgres psql
    drop database endagaweb_dev;
    create database endagaweb_dev;
    exit
    vagrant ssh web
    python manage.py migrate

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import datetime
import json
import random
import sys
import uuid

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.utils import DataError
from django.utils import timezone
import pytz

from endagaweb import stats_app
from endagaweb.models import BTS
from endagaweb.models import ClientRelease
from endagaweb.models import Destination

from endagaweb.models import Network
from endagaweb.models import Number
from endagaweb.models import Subscriber
from endagaweb.models import SystemEvent
from endagaweb.models import TimeseriesStat
from endagaweb.models import Transaction
from endagaweb.models import UsageEvent
from endagaweb.models import User
from rest_framework.authtoken.models import Token
from django.db.models.signals import post_save
from django.db import IntegrityError
from django.contrib.auth.models import User, Permission, ContentType
from guardian.shortcuts import assign_perm, get_perms, remove_perm, \
    get_users_with_perms

from endagaweb.models import UserProfile


class Command(BaseCommand):
    """A custom management command.

    As per the docs:
    docs.djangoproject.com/en/1.7/howto/custom-management-commands/
    """

    help = 'sets up a test db -- see management/commands for more'

    def handle(self, *args, **options):
        # first create some client releases
        for channel in ['beta', 'stable']:
            cr = ClientRelease(date=datetime.datetime(year=1984, month=6,
                                                      day=24, hour=21,
                                                      tzinfo=pytz.utc),
                               version='0.0.1', channel=channel)
            cr.save()

        # Add two users with a lot of activity, towers and subs.  Note that the
        # first sub, unlike the second one, has no 'endaga_version.'
        self.create_admin("myadmin", "myadmin", 2, "number.telecom.permanent",
                          "63917555", '0.3.26')

        # Add one user with no such activity.
        username = 'newuser'
        sys.stdout.write('creating user "%s"..\n' % username)
        user = User(username=username, email="%s@endaga.com" % username)
        user.set_password('newpw')
        user.save()

    def create_admin(self, username, password, usernum, kind, prefix,
                     endaga_version):

        # Create a user.
        sys.stdout.write('Creating admin user: %s %s %s..\n' % (
            username, password, usernum))
        user = User(username=username, email="%s@endaga.com" % username)
        user.set_password(password)
        user.is_superuser = True
        user.is_staff = True
        user.save()

        # Get user profile and add some credit.
        sys.stdout.write('setting user profile..\n')
        user_profile = UserProfile.objects.get(user=user)
        user_profile.save()
        network = user_profile.network
        network.name = "%s Network Test " % username.upper()
        network.save()

        # Create role users
        self.create_role_users(network)
        self.create_towers(network, usernum, kind, prefix, endaga_version)

    def create_role_users(self, network):

        sys.stdout.write('Creating role users for : %s ..\n' % (
            network.name))

        role_usernames = {
            'netadmin': 'Network Admin',
            'analyst': 'Business Analyst',
            'loader': 'Loader',
            'partner': 'Partner'
        }

        business_analyst = (
            'view_activity', 'view_bts', 'view_denomination',
            'view_graph', 'view_network', 'view_notification',
            'view_report', 'view_subscriber',
        )

        loader = (
            'view_activity', 'view_bts', 'view_denomination',
            'view_graph', 'view_network', 'view_notification',
            'view_report', 'view_subscriber', 'adjust_credit',
            'send_sms', 'edit_subscriber',
        )

        partner = (
            'view_activity', 'view_bts', 'view_denomination',
            'view_graph', 'view_network', 'view_notification',
            'view_report', 'view_subscriber', 'send_sms',
            'edit_subscriber',
        )
        roles_and_permissions = {
            'Business Analyst': business_analyst,
            'Loader': loader,
            'Partner': partner
        }

        # Create a role users.
        for key, value in role_usernames.iteritems():
            username = key
            password = key
            user_role = value
            email = "%s@%s.com" % (
                username, network.name.replace(" ", "").lower())
            sys.stdout.write('Creating role : %s..\n' % (email))

            post_save.disconnect(UserProfile.new_user_hook, sender=User)
            try:
                with transaction.atomic():
                    user = User(username=username)
                    if user_role == 'Network Admin':
                        user.is_staff = True
                    else:
                        user.is_staff = user.is_superuser = False
                    user.email = email
                    user.set_password(password)
                    user.save()
                    # creates Token that BTSs on the network use to
                    # authenticate
                    Token.objects.create(user=user)
                    sys.stdout.write('Setting user profile..\n')

                    user_profile = UserProfile.objects.create(user=user)
                    user_network = Network.objects.get(id=network.id)

                    # assign permissions to a give role
                    content_type = ContentType.objects.filter(
                        app_label='endagaweb', model='network').values_list(
                        'id', flat=True)[0]
                    permission = Permission.objects.filter(
                        content_type=content_type)
                    role_permission = []
                    if user_role in roles_and_permissions.keys():
                        role_permission = permission.filter(
                            codename__in=roles_and_permissions[user_role])
                    else:
                        for i in permission:
                            role_permission.append(i)

                    for i in role_permission:
                        assign_perm(i.codename, user, user_network)

                    # Set last network as default network for User
                    user_profile.network = user_network
                    user_profile.role = user_role
                    user_profile.save()
            except IntegrityError:
                post_save.connect(UserProfile.new_user_hook, sender=User)
                sys.stdout.write('Unable to create a user role!')
            post_save.connect(UserProfile.new_user_hook, sender=User)

    def create_towers(self, network, usernum, kind, prefix, endaga_version):
        # Add some towers.
        towers_to_add = random.randint(4, 7)
        added_towers = []
        print 'Adding %s towers..' % towers_to_add

        for index in range(towers_to_add):
            nickname = None
            if random.random() < 0.5:
                nickname = 'Test Tower %s' % index
            bts = BTS(uuid=str(uuid.uuid4()), nickname=nickname, secret='mhm',
                      inbound_url='http://localhost:8090',
                      network=network)
            added_towers.append(bts)
            # Set the last_active time and uptime randomly.
            random_seconds = random.randint(0, 24 * 60 * 60)
            random_date = (timezone.now() -
                           datetime.timedelta(seconds=random_seconds))
            bts.last_active = random_date
            bts.uptime = random.randint(24 * 60 * 60, 100 * 24 * 60 * 60)
            bts.status = random.choice(['no-data', 'active', 'inactive'])
            bts.save()
            # Set the metapackage version.  This has to be done after initially
            # creating the BTS or the post-create hook will override.
            if endaga_version is not None:
                endaga_version = bts.sortable_version(endaga_version)
                versions = {
                    'endaga_version': endaga_version,
                    'freeswitch_version': None,
                    'gsm_version': None,
                    'python_endaga_core_version': None,
                    'python_gsm_version': None,
                }
            bts.package_versions = json.dumps(versions)
            bts.save()
            # Add some TimeseriesStats for each tower.
            stats_to_add = random.randint(100, 1000)
            print 'Adding %s TimeseriesStats..' % stats_to_add
            for _ in range(stats_to_add):
                date = (
                    timezone.now() -
                    datetime.timedelta(
                        seconds=random.randint(
                            0,
                            7 *
                            24 *
                            60 *
                            60)))
                key = random.choice(stats_app.views.TIMESERIES_STAT_KEYS)
                if key in ('noise_rssi_db', 'noise_ms_rssi_target_db'):
                    value = random.randint(-75, -20)
                elif 'percent' in key:
                    value = random.randint(0, 100)
                elif 'bytes' in key:
                    value = random.randint(0, 10000)
                else:
                    value = random.randint(0, 10)
                stat = TimeseriesStat(key=key, value=value, date=date, bts=bts,
                                      network=network)
                stat.save()
            # Add some SystemEvents for each tower (either small or large
            # number)
            number_of_events = [0, 1, 2, 5, 18, 135, 264]
            events_to_add = random.choice(number_of_events)
            print 'adding %s SystemEvents..' % events_to_add
            for _ in range(events_to_add):
                # Actual events should be in order. But we should support
                # out-of-order events just in case
                date = (
                    timezone.now() -
                    datetime.timedelta(
                        seconds=random.randint(
                            0,
                            7 *
                            24 *
                            60 *
                            60)))
                event = SystemEvent(date=date, bts=bts,
                                    type=random.choice(['bts up', 'bts down']))
                event.save()

        # Make at least one BTS active recently.
        bts.last_active = timezone.now()
        bts.status = 'active'
        bts.save()
        # Make one BTS in the no-data state.
        bts = BTS(uuid=str(uuid.uuid4()), nickname='No-data tower', secret='z',
                  inbound_url='http://localhost:5555',
                  network=network,
                  package_versions=json.dumps(versions))
        bts.save()

        # Add some subscribers.
        sys.stdout.write("adding subscribers and numbers..\n")
        added_subscribers = []
        for index in range(random.randint(3, 20)):
            imsi = "IMSI%d999900000000%s" % (usernum, index)
            if random.random() < 0.5:
                name = "test name %s" % index
            else:
                name = ''
            balance = random.randint(40000000, 60000000)
            state = "active"
            bts = BTS.objects.filter(
                network=network).order_by('?').first()
            subscriber = Subscriber(
                network=network,
                imsi=imsi,
                name=name,
                balance=balance,
                state=state,
                bts=bts,
                last_camped=bts.last_active)  # , role=role)
            subscriber.save()
            added_subscribers.append(subscriber)
            # And attach some numbers.
            for _ in range(random.randint(1, 5)):
                msisdn = int(prefix + str(random.randint(1000, 9999)))
                number = Number(
                    number=msisdn, state="inuse", network=network,
                    kind=kind, subscriber=subscriber)
                number.save()

        # Add one last subscriber so we have at least one sub with no activity.
        imsi = "IMSI%d8888000000000" % usernum
        name = 'test name (no activity)'
        subscriber = Subscriber(network=network, imsi=imsi,
                                bts=bts, name=name, balance=1000,
                                state='active')
        subscriber.save()

        imsi = "IMSI%d1888000000000" % usernum
        name = 'test name (no activity)'
        subscriber2 = Subscriber(network=network, imsi=imsi,
                                 bts=bts, name=name, balance=1000,
                                 state='first_expired')
        subscriber2.save()

        imsi = "IMSI%d8848000000000" % usernum
        name = 'test name (no activity)'
        subscriber3 = Subscriber(network=network, imsi=imsi,
                                 bts=bts, name=name, balance=1000,
                                 state='expired')
        subscriber3.save()
        imsi = "IMSI%d8828000000000" % usernum
        name = 'test name (no activity)'
        subscriber4 = Subscriber(network=network, imsi=imsi,
                                 bts=bts, name=name, balance=1000,
                                 state='blocked')
        subscriber4.save()

        # Add some UsageEvents attached to random subscribers.
        events_to_add = random.randint(100, 2000)
        sys.stdout.write("adding %s usage events..\n" % events_to_add)
        all_destinations = list(Destination.objects.all())
        with transaction.atomic():
            for _ in range(events_to_add):
                random_sub = random.choice(added_subscribers)
                time_delta = datetime.timedelta(
                    minutes=random.randint(0, 60000))
                date = (timezone.now() - time_delta)
                kinds = [
                    ('outside_sms', 10000), ('incoming_sms', 2000),
                    ('local_sms', 4000),
                    ('local_recv_sms', 1000), ('free_sms', 0),
                    ('error_sms', 0),
                    ('outside_call', 8000), ('incoming_call', 3000),
                    ('local_call', 2000),
                    ('local_recv_call', 1000),
                    ('free_call', 0), ('error_call', 0), ('gprs', 5000),
                    ('transfer', 2000), ('add-money', 43333),
                    ('Provisioned', 1000), ('deactivate_number', 4000),
                ]
                (kind, tariff) = random.choice(kinds)
                to_number, billsec, up_bytes, call_duration = 4 * [None]
                from_number, down_bytes, timespan, change = 4 * [None]
                if 'call' in kind:
                    billsec = random.randint(0, 120)
                    change = tariff * billsec
                    call_duration = billsec + random.randint(0, 10)
                    to_number = str(random.randint(1234567890, 9876543210))
                    from_number = str(random.randint(1234567890, 9876543210))
                    reason = '%s sec call to %s (%s)' % (billsec, to_number,
                                                         kind)
                elif 'sms' in kind:
                    change = tariff
                    to_number = str(random.randint(1234567890, 9876543210))
                    from_number = str(random.randint(1234567890, 9876543210))
                    reason = '%s to %s' % (kind, to_number)
                elif kind == 'gprs':
                    up_bytes = random.randint(20000, 400000)
                    down_bytes = random.randint(20000, 400000)
                    change = (down_bytes / 1024) * tariff
                    timespan = 60
                    reason = 'gprs_usage, %sB uploaded, %sB downloaded' % (
                        up_bytes, down_bytes)
                elif kind == 'transfer':
                    change = tariff - random.randint(500, tariff)
                    to_number = str(random.randint(1234567890, 9876543210))
                    from_number = str(random.randint(1234567890, 9876543210))
                    reason = '%s to %s' % (kind, to_number)
                elif kind == 'add-money':
                    change = tariff
                    to_number = str(random.randint(1234567890, 9876543210))
                    from_number = str(random.randint(1234567890, 9876543210))
                    reason = '%s to %s' % (kind, to_number)
                elif kind == 'Provisioned':
                    change = tariff
                    to_number = str(random.randint(1234567890, 9876543210))
                    from_number = str(random.randint(1234567890, 9876543210))
                    reason = '%s to %s' % (kind, to_number)
                elif kind == 'deactivate_number':
                    change = tariff
                    to_number = str(random.randint(1234567890, 9876543210))
                    from_number = str(random.randint(1234567890, 9876543210))
                    reason = '%s to %s' % (kind, to_number)

                old_amount = random_sub.balance
                random_sub.change_balance(change)
                usage_event = UsageEvent(
                    subscriber=random_sub, bts=random.choice(added_towers),
                    date=date, kind=kind,
                    reason=reason, oldamt=old_amount,
                    newamt=random_sub.balance, change=-change, billsec=billsec,
                    call_duration=call_duration, uploaded_bytes=up_bytes,
                    downloaded_bytes=down_bytes,
                    timespan=timespan, to_number=to_number,
                    from_number=from_number,
                    destination=random.choice(all_destinations), tariff=tariff)

                try:
                    usage_event.save()
                except DataError:
                    from django.db import connection
                    print connection.queries[-1]
                random_sub.save()
            # Create one more UE with a negative "oldamt" to test display
            # handling of such events.
            usage_event = UsageEvent(
                subscriber=random_sub, bts=random.choice(added_towers),
                date=date, kind='local_sms',
                reason='negative oldamt', oldamt=-200000,
                newamt=0, change=200000,
                billsec=0, to_number='19195551234',
                destination=random.choice(all_destinations))
            usage_event.save()

        # Add some transaction history.
        sys.stdout.write("adding transactions..\n")
        for _ in range(random.randint(10, 50)):
            time_delta = datetime.timedelta(
                minutes=random.randint(0, 60000))
            date = (timezone.now() - time_delta)
            new_transaction = Transaction(
                ledger=network.ledger, kind='credit',
                reason='Automatic Recharge',
                amount=1e3 * random.randint(1000, 100000),
                created=date,
            )
            new_transaction.save()

        # And some floating numbers for release testing.
        sys.stdout.write("adding floating phone numbers..\n")
        for num in random.sample(range(10000, 99999), 300):
            # need to be e164, that's what we use
            msisdn = int('155555%s' % str(num))
            state = random.choice(('available', 'pending'))
            kind = random.choice(('number.nexmo.monthly',
                                  'number.telecom.permanent'))
            number = Number(
                number=msisdn, state=state, kind=kind, country_id='US')
            number.save()
