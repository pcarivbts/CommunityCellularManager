"""Testing subscriber detail views in endagaweb.views.dashboard.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant 
of patent rights can be found in the PATENTS file in the same directory.
"""

from django import test
import mock
from django.http import HttpResponseBadRequest
from endagaweb import models


class SubscriberBaseTest(test.TestCase):
    """Base tests for all subscriber detail pages."""

    @classmethod
    def setUpClass(cls):
        cls.user = models.User(username="abe", email="a@b.com")
        cls.password = 'test123'
        cls.user.set_password(cls.password)
        cls.user.save()
        cls.subscriber_imsi = 'IMSI000123'
        cls.subscriber_num = '5551234'
        cls.user_profile = models.UserProfile.objects.get(user=cls.user)
        cls.bts = models.BTS(
            uuid="12345abcd", nickname="testbts",
            inbound_url="http://localhost/test",
            network=cls.user_profile.network)
        cls.bts.save()

        cls.adjust_credit_endpoint = (
            '/dashboard/subscribers/%s/adjust-credit' % cls.subscriber_imsi)
        # Drop all PCUs.
        for pcu in models.PendingCreditUpdate.objects.all():
            pcu.delete()

    @classmethod
    def tearDownClass(cls):
        """Deleting the objects created for the tests."""
        cls.user.delete()
        cls.user_profile.delete()
        cls.bts.delete()
        cls.subscriber.delete()

    @classmethod
    def createsubscriber(cls, currency, max_network_balance, subscriber_balance):

        """Helper method to create subscriber and add max_amount to max_account
        of network """

        cls.subscriber = models.Subscriber.objects.create(
            balance=subscriber_balance, name='test-name', imsi=cls.subscriber_imsi,
            network=cls.user_profile.network, bts=cls.bts)
        cls.subscriber.save()
        cls.user_profile.network.max_balance = max_network_balance
        cls.user_profile.network.subscriber_currency = currency
        cls.user_profile.network.save()

    @classmethod
    def getmessage(cls, response):
        """Helper method to return message from response """
        for c in response.context:
            message = [m for m in c.get('messages')][0]
            if message:
                return message

    def setUp(self):
        self.client = test.Client()
        self.client.login(username=self.user.username, password=self.password)


class SubscriberAdjustCreditTest(SubscriberBaseTest):
    """Testing endagaweb.views.dashboard.SubscriberAdjustCredit for currency"""

    def test_get_without_subscriber(self):
        """ validate get request without subscriber create return
         HttpResponseBadRequest """
        response = self.client.get(self.adjust_credit_endpoint)
        self.assertEqual(HttpResponseBadRequest.status_code, response.status_code)

    def test_get_with_subscriber(self):
        """ validate get request with  subscriber create return 200 status code """
        self.createsubscriber('USD', 7000, 700)
        response = self.client.get(self.adjust_credit_endpoint)
        self.assertEqual(200, response.status_code)

    def test_faliuer_post_for_currency_USD(self):
        """validate  failuer scenario for adjust credit(subscriber balance + amount )
         for currency USD goes more than max_amount_limit of newtwork throw error """
        self.createsubscriber('USD', 7000, 700)
        data = {
            'amount': 7000
        }
        response = self.client.post(self.adjust_credit_endpoint, data, follow=True)
        message = self.getmessage(response)
        self.assertEqual(message.tags, 'error')

    def test_success_post_for_currency_USD(self):
        """validate success scenario for adjust credit(subscriber balance + amount)
         for currency USD not goes more than max_amount_limit of newtwork  """
        self.createsubscriber('USD', 7000, 700)
        data = {
            'amount': 6000
        }
        with mock.patch('endagaweb.tasks.update_credit.delay') as mocked_task:
            self.client.post(self.adjust_credit_endpoint, data)
            # There should now be one PCU.
            self.assertEqual(1, models.PendingCreditUpdate.objects.count())
            self.assertTrue(mocked_task.called)
            args, _ = mocked_task.call_args
        task_imsi, task_msgid = args
        self.assertEqual(self.subscriber_imsi, task_imsi)
        pcu = models.PendingCreditUpdate.objects.all()[0]
        self.assertEqual(pcu.uuid, task_msgid)

    def test_faliuer_post_for_currency_PHP(self):
        """validate  failuer scenario for adjust credit(subscriber balance + amount )
         for currency PHP goes more than max_amount_limit of newtwork throw error """
        self.createsubscriber('PHP', 7000, 700)
        data = {
            'amount': 7000
        }
        response = self.client.post(self.adjust_credit_endpoint, data, follow=True)
        message = self.getmessage(response)
        self.assertEqual(message.tags, 'error')

    def test_success_post_for_currency_PHP(self):
        """validate success scenario for adjust credit(subscriber balance + amount )
         for currency PHP not goes more than max_amount_limit of newtwork  """
        self.createsubscriber('PHP', 7000, 700)
        data = {
            'amount': 6000
        }
        with mock.patch('endagaweb.tasks.update_credit.delay') as mocked_task:
            self.client.post(self.adjust_credit_endpoint, data)
            # There should now be one PCU.
            self.assertEqual(1, models.PendingCreditUpdate.objects.count())
            self.assertTrue(mocked_task.called)
            args, _ = mocked_task.call_args
        task_imsi, task_msgid = args
        self.assertEqual(self.subscriber_imsi, task_imsi)
        pcu = models.PendingCreditUpdate.objects.all()[0]
        self.assertEqual(pcu.uuid, task_msgid)

    def test_faliuer_post_for_currency_IDR(self):
        """validate  failuer scenario for adjust credit(subscriber balance + amount )
        for currency IDR goes more than max_amount_limit of newtwork throw error """
        self.createsubscriber('IDR', 7000, 700)
        data = {
            'amount': 7000
        }
        response = self.client.post(self.adjust_credit_endpoint, data,
                                    follow=True)
        message = self.getmessage(response)
        self.assertEqual(message.tags, 'error')

    def test_success_post_for_currency_IDR(self):
        """validate success scenario for adjust credit(subscriber balance + amount )
        for currency IDR not goes more than max_amount_limit of newtwork  """
        self.createsubscriber('IDR', 7000, 700)
        data = {
            'amount': 6000
        }
        with mock.patch('endagaweb.tasks.update_credit.delay') as mocked_task:
            self.client.post(self.adjust_credit_endpoint, data)
            # There should now be one PCU.
            self.assertEqual(1, models.PendingCreditUpdate.objects.count())
            self.assertTrue(mocked_task.called)
            args, _ = mocked_task.call_args
        task_imsi, task_msgid = args
        self.assertEqual(self.subscriber_imsi, task_imsi)
        pcu = models.PendingCreditUpdate.objects.all()[0]
        self.assertEqual(pcu.uuid, task_msgid)

