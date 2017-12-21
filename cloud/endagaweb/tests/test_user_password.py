"""Tests for models.Users password

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
        cls.password = 'testuser_abad'
        cls.user = models.User(username=cls.username, email='y@l.com')
        cls.user.set_password(cls.password)
        cls.user.save()
        cls.error_tag = 'password alert alert-danger error'
        cls.success_tag = 'password alert alert-success success'
        # Create a test client.
        cls.client = test.Client()

    @classmethod
    def tearDownClass(cls):
        cls.user.delete()

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

    @classmethod
    def getmessage(cls, response):
        """Helper method to return message from response """
        for c in response.context:
            message = [m for m in c.get('messages')][0]
            if message:
                return message


class UserPasswordStrengthTests(TestBase):
    """Testing strength of new password."""

    def test_old_password(self):
        """validate invalid old password."""
        self.login()
        data = {
            'old_password': 'testuser_abads',
            'new_password1': 'Admin_123',
            'new_password2': 'Admin_123'
        }
        response = self.client.post('/account/password/change/',  data ,
                                    follow=True, HTTP_REFERER='/password/change')
        message = self.getmessage(response)
        self.assertEqual(message.tags, self.error_tag)

    def test_new_password_case1(self):
        """validate new password  must contain 8 length."""
        self.login()
        data = {
            'old_password': 'testuser_abad',
            'new_password1': 'test_12',
            'new_password2': 'test_12'
        }
        response = self.client.post('/account/password/change/', data,
                                    follow=True,HTTP_REFERER='/password/change')
        message = self.getmessage(response)
        self.assertEqual(message.tags, self.error_tag)

    def test_new_password_case2(self):
        """validate new password  must contain alphanumeric."""
        self.login()
        data = {
            'old_password': 'testuser_abad',
            'new_password1': 'user_abcde',
            'new_password2': 'user_abcde'
        }
        response = self.client.post('/account/password/change/', data,
                                    follow=True, HTTP_REFERER='/password/change')
        message = self.getmessage(response)
        self.assertEqual(message.tags, self.error_tag)

    def test_new_password_case3(self):
        """validate new password must contain alphanumeric."""
        self.login()
        data = {
            'old_password': 'testuser_abad',
            'new_password1': '1988@1999',
            'new_password2': '1988@1999'
        }
        response = self.client.post('/account/password/change/', data,
                                    follow=True, HTTP_REFERER='/password/change')
        message = self.getmessage(response)
        self.assertEqual(message.tags,self.error_tag)


    def test_new_password_case4(self):
        """validate new password must contain special character."""
        self.login()
        data = {
            'old_password': 'testuser_abad',
            'new_password1': '1988abcd',
            'new_password2': '1988abcd'
        }
        response = self.client.post('/account/password/change/', data,
                                    follow=True, HTTP_REFERER='/password/change')
        message = self.getmessage(response)
        self.assertEqual(message.tags, self.error_tag)

    def test_new_password_case5(self):
        """validate new password must be minimum length of 8 character."""
        self.login()
        data = {
            'old_password': 'testuser_abad',
            'new_password1': 'sinha_1',
            'new_password2': 'sinha_1'
        }
        response = self.client.post('/account/password/change', data,
                                    follow=True, HTTP_REFERER='/password/change')
        message = self.getmessage(response)
        self.assertEqual(message.tags, self.error_tag)

    def test_new_password_case6(self):
        """validate new password must have alhanumeric and special character."""
        self.login()
        data = {
            'old_password': 'testuser_abad',
            'new_password1': 'userA_183',
            'new_password2': 'userA_183'
        }
        response = self.client.post('/account/password/change', data,
                                    follow=True, HTTP_REFERER='/password/change')
        message = self.getmessage(response)
        self.assertEqual(message.tags, self.success_tag)

    def test_redirect_url_for_dashbboard_profile(self):
        """validate if change password page come from /dashboard/profile ,
        redirect to /dashboard/profile."""
        self.login()
        data = {
            'old_password': 'testuser_abad',
            'new_password1': 'userA_184',
            'new_password2': 'userA_184'
        }
        response = self.client.post('/account/password/change/', data,
                                    HTTP_REFERER='/dashboard/profile')
        self.assertEqual(response.url, '/dashboard/profile')
        self.assertEqual(response.status_code,302)

    def test_redirect_url_for_password_change(self):
        """validate if change password page come from /password/change ,
        redirect to /password/change."""
        self.login()
        data = {
            'old_password': 'testuser_abad',
            'new_password1': 'userA%185',
            'new_password2': 'userA%184'
        }
        response = self.client.post('/account/password/change', data,

                                    HTTP_REFERER='/password/change')
        self.assertEqual(response.url, '/password/change')
        self.assertEqual(response.status_code, 302)

    def test_new_password_case7(self):
        """validate new password with special character."""
        self.login()
        data = {
            'old_password': 'testuser_abad',
            'new_password1': '185@auser1',
            'new_password2': '185@auser1'
        }
        response = self.client.post('/account/password/change', data,follow=True,
                                    HTTP_REFERER='/password/change' )
        message = self.getmessage(response)
        self.assertEqual(message.tags, self.success_tag)

    def test_new_password_case8(self):
        """validate new password with special character."""
        self.login()
        data = {
            'old_password': 'testuser_abad',
            'new_password1': 'User*#4As',
            'new_password2': 'User*#4As'
        }
        response = self.client.post('/account/password/change', data,follow=True,
                                    HTTP_REFERER='/password/change' )
        message = self.getmessage(response)
        self.assertEqual(message.tags, self.success_tag)

    def test_new_password_case9(self):
        """validate new password with special character."""
        self.login()
        data = {
            'old_password': 'testuser_abad',
            'new_password1': '4as8trtaabb^',
            'new_password2': '4as8trtaabb^'
        }
        response = self.client.post('/account/password/change', data,follow=True,
                                    HTTP_REFERER='/password/change' )
        message = self.getmessage(response)
        self.assertEqual(message.tags, self.success_tag)
