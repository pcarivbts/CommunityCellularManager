"""Tests for NetworkBalanceLimit form

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from django import test
from django.test import TestCase
from endagaweb import models


class TestBase(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.username = 'testuser'
        cls.password = 'testpw'
        cls.user = models.User(username=cls.username, email='y@l.com',
                               is_superuser=True)
        cls.user.set_password(cls.password)
        cls.user.save()
        cls.user_profile = models.UserProfile.objects.get(user=cls.user)
        cls.uuid = "59216199-d664-4b7a-a2db-6f26e9a5d208"
        # Create a test client.
        cls.client = test.Client()

    @classmethod
    def tearDownClass(cls):
        cls.user.delete()
        cls.user_profile.delete()

    def tearDown(self):
        self.logout()

    def login(self):
        """Log the client in."""
        data = {
            'email': self.username,
            'password': self.password,
        }
        self.client.post('/auth/', data)

    def logout(self):
        """Log the client out."""
        self.client.get('/logout')


class NetworkLimitUITest(TestBase):
    """Testing Network Limit UI."""

    def test_network_balance_limit_unauth_get_request(self):
        self.logout()
        response = self.client.get('/dashboard/network/balance-limit')
        self.assertEqual(302, response.status_code)

    def test_network_balance_limit_auth_get_request(self):
        self.login()
        response = self.client.get('/dashboard/network/balance-limit')
        self.assertEqual(200, response.status_code)

    def test_post_bad_response_with_invalid_input_limits(self):
        self.login()
        data = {
            'max_balances': 1,
            'max_unsuccessful_transaction': 2,

        }
        response = self.client.post('/dashboard/network/balance-limit', data)
        self.assertEqual(400, response.status_code)

    def test_post_bad_response_with_invalid_input_transactions(self):
        self.login()
        data = {
            'max_balance': 1,
            'max_unsuccessful_transactions': 2,

        }
        response = self.client.post('/dashboard/network/balance-limit', data)
        self.assertEqual(400, response.status_code)

    def test_post_response_redirect_status_code(self):
        self.login()
        data = {
            'max_balance': 4,
            'max_unsuccessful_transaction': 6,

        }
        response = self.client.post('/dashboard/network/balance-limit', data)
        self.assertEqual(302, response.status_code)

    def test_post_response_redirect_url(self):
        self.login()
        data = {
            'max_balance': 4,
            'max_unsuccessful_transaction': 6,

        }
        response = self.client.post('/dashboard/network/balance-limit', data)
        self.assertEqual('/dashboard/network/balance-limit', response.url)
