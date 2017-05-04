"""Tests for models.BTS.

Usage:
    $ python manage.py test endagaweb.BTSHandleEventTestCase
    $ python manage.py test endagaweb.BTSCheckinResponseTest
    $ python manage.py test endagaweb.ChargeOperatorOnEventCreationTest

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import time

from datetime import datetime, timedelta
import json
from unittest import TestCase

from django.test import TestCase as DjangoTestCase
from django.conf import settings
import django.utils.timezone
import itsdangerous
import mock
import pytz
from rest_framework.test import APIClient

from endagaweb import checkin
from endagaweb import models
from endagaweb import notifications
from endagaweb import tasks

import syslog
from endagaweb.ic_providers.nexmo import NexmoProvider


class MockTest(TestCase):
	@classmethod
	def setUpClass(cls):
		cls.name='Shiv'
		cls.email='shiv.sah@aricent.com'

	@classmethod
	def tearDownClass(cls):
		cls.name=''
		cls.email=''

	def testName(self):
		self.assertEqual(self.name, 'Shiv')

	def testEmail(self):
		self.assertEqual(self.email, 'shiv.sah@aricent.com')