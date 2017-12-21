# coding=utf-8
"""Testing the NetworkBilling view.

Usage:
  $ python manage.py test endagaweb.NetworkNotification

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

from django import test

from endagaweb import models
from endagaweb.util import api
from endagaweb.views import network
from settings import BTS_LANGUAGES

class NetworkNotification(test.TestCase):
    """Testing the view's ability to convert credits.

    Some day this may be more complex as we take into account the network
    setting for subscriber currency.
    """

    # user = notification = user_profile = bts = subscriber = None

    @classmethod
    def setUpClass(cls):
        cls.username = 'y'
        cls.password = 'pw'
        cls.user = models.User(username=cls.username, email='y@l.com')
        cls.user.set_password(cls.password)
        cls.user.is_superuser = True
        cls.user.save()
        cls.user_profile = models.UserProfile.objects.get(user=cls.user)

        cls.bts = models.BTS(uuid="12345abcd", nickname="testbts",
                             inbound_url="http://localhost/test",
                             network=cls.user_profile.network,
                             locale='en')
        cls.bts.save()

        cls.subscriber_imsi = 'IMSI000123'
        cls.subscriber_num = '5551234'
        cls.subscriber_role = 'Subscriber'
        cls.subscriber = models.Subscriber.objects.create(
            name='test-name', imsi=cls.subscriber_imsi,
            role=cls.subscriber_role, network=cls.bts.network, bts=cls.bts)
        cls.subscriber.save()

        message = 'the quick brown fox jumped over the lazy dog'
        translated = api.translate(message, to_lang='tl', from_lang='auto')
        cls.notification = models.Notification(
            network=cls.user_profile.network, event='Test Event',
            message=message, type='automatic', language='tl',
            translation=translated)
        cls.notification.save()

    @classmethod
    def tearDownClass(cls):
        """Deleting the objects created for the tests."""
        cls.user.delete()
        cls.user_profile.delete()
        cls.bts.delete()
        cls.subscriber.delete()
        cls.notification.delete()

    def login(self):
        """Log the client in."""
        data = {
            'email': self.user,
            'password': self.password,
        }
        self.client.post('/auth/', data)

    def logout(self):
        """Log the client out."""
        self.client.get('/logout')

    def setUp(self):
        self.view = network.NetworkNotifications()
        self.manage = network.NetworkNotificationsEdit()

    def test_translation(self):
        languages = ['es', 'id', 'tl']
        message = 'the quick brown fox jumped over the lazy dog'

        translation = {
            # filipino
            'tl':
                'ang mabilis na brown na lobo ay tumalon sa tamad na aso',
            # Spanish
            'es': 'el rápido zorro marrón saltó sobre el perro perezoso',
            # Indonesian
            'id':
                'Rubah coklat cepat melompati anjing malas itu'
        }
        for language in languages:
            translated = api.translate(message, to_lang=language)
            self.assertEqual(translated, translation[language].decode('utf-8'))

    def test_notification_exists(self):
        translation = {
            # filipino
            'tl':
                'ang mabilis na brown na lobo ay tumalon sa tamad na aso'
        }
        event = models.Notification.objects.get(
            network=self.user_profile.network, language='tl',
            translation=translation['tl']
        )
        self.assertEqual(event, self.notification)

    def test_dashboard_notification_request_unauth(self):
        self.logout()
        response = self.client.get('/dashboard/network/notification')
        self.assertEqual(302, response.status_code)

    def test_dashboard_notification_request_auth(self):
        self.login()
        response = self.client.get('/dashboard/network/notification')
        self.assertEqual(200, response.status_code)

    def test_notification_created(self):
        self.login()
        message = 'the quick brown fox jumped over the lazy dog test'
        translate = api.multiple_translations(message, *BTS_LANGUAGES)
        params = {
            'type': 'mapped',
            'number': '123',
            'message': message,
            'pk': 0,
        }
        for language in translate:
            params['lang_'+language] = translate[language]

        self.client.post('/dashboard/network/notification/update', params)
        self.assertEqual(len(BTS_LANGUAGES), models.Notification.objects.filter(
            network=self.user_profile.network, event='123').count())

    def test_notification_deleted(self):
        self.login()
        event_id = models.Notification.objects.filter(
            network=self.user_profile.network).values_list('id', flat=True)
        delete_event = {'id': event_id}
        self.client.post('/dashboard/network/notification/update',
                         delete_event)
        # delete all events for that network
        self.assertEqual(0, models.Notification.objects.filter(
            network=self.user_profile.network).count())
