"""utlity methods running on the underlying database.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""
import uuid

import django


def get_db_time(connection):
    cursor = connection.cursor()
    cursor.execute("SELECT statement_timestamp();")
    return cursor.fetchone()[0]


def format_transaction(tansaction_date=None, transaction_type=False):
    # Generating new transaction id using old transaction and date
    if tansaction_date is None:
        dt = django.utils.timezone.now()
    else:
        dt = tansaction_date
    uuid_transaction = str(uuid.uuid4().hex[:6])
    transaction = '{0}id{1}'.format(str(dt.date()).replace('-', ''),
                                    uuid_transaction)
    if transaction_type:
        return '-%s' % (transaction,)
    else:
        return transaction
