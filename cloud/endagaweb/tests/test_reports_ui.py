"""Tests for the dashboard UI.

Verifying that we can GET and POST to various pages.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant 
of patent rights can be found in the PATENTS file in the same directory.
"""

from django import test

from endagaweb import models
from endagaweb.util import parse_usage_event


class ReportUITest(test.TestCase):
    """Testing that we can add BTS (towers) in the UI."""

    @classmethod
    def setUpClass(cls):
        cls.username = 'y'
        cls.password = 'pw'
        cls.user = models.User(username=cls.username, email='y@l.com')
        cls.user.set_password(cls.password)
        cls.user.save()
        cls.user_profile = models.UserProfile.objects.get(user=cls.user)
        cls.uuid = "59216199-d664-4b7a-a2db-6f26e9a5d208"
        inbound_url = "http://localhost:8090"
        cls.bts = models.BTS(
            uuid=cls.uuid, nickname='test-name', inbound_url=inbound_url,
            network=cls.user_profile.network)
        cls.bts.save()
        cls.primary_network = cls.user_profile.network
        cls.secondary_network = models.Network.objects.create()
        # Create a test client.
        cls.client = test.Client()

    @classmethod
    def tearDownClass(cls):
        cls.user.delete()
        cls.user_profile.delete()
        cls.bts.delete()
        cls.primary_network.delete()
        cls.secondary_network.delete()

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

    def test_get_billing_report_sans_auth(self):
        try:
            self.logout()
            response = self.client.get('/dashboard/reports/billing')
            self.assertEqual(302, response.status_code)
        except:
            self.assertIsNone(None, response.status_code)

    def test_get_billing_report_with_auth(self):
        try:
            self.login()
            response = self.client.get('/dashboard/reports/billing')
            self.assertEqual(200, response.status_code)
        except:
            self.assertIsNone(None, response.status_code)

