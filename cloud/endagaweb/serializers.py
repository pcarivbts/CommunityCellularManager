"""
Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant 
of patent rights can be found in the PATENTS file in the same directory.
"""

from models import UserProfile, BTS, Number, UsageEvent
from django.contrib.auth.models import User
from rest_framework import serializers

class BTSSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = BTS

class NumberSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Number

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'date_joined', 'last_login')

class UserProfileSerializer(serializers.HyperlinkedModelSerializer):
    id = serializers.Field()
    user = UserSerializer()
    class Meta:
        model = UserProfile


class UsageEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageEvent
        fields = (
                'transaction_id',
                'subscriber',
                'subscriber_imsi',
                'bts',
                'bts_uuid',
                'network',
                'date',
                'kind',
                'reason',
                'oldamt',
                'newamt',
                'change',
                'billsec',
                'call_duration',
                'from_imsi',
                'from_number',
                'to_imsi',
                'to_number',
                'destination',
                'tariff',
                'uploaded_bytes',
                'downloaded_bytes',
                'timespan',
                'date_synced',
        )