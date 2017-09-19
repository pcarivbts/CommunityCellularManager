"""Get a subscriber's account balance via their IMSI.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

from freeswitch import consoleLog

from core.subscriber import subscriber
from core.subscriber.base import SubscriberNotFound


def chat(message, args):
    """Handle chat requests.

    Args:
    string of the form <imsi>|<True if for dest_imsi (default is False)>

    Subscriber State can be:
      active (unblocked), -active (blocked),first_expired (validity expired)
    """
    args = args.split('|')
    imsi = args[0]
    dest_imsi = False

    if len(args) > 1:
        dest_imsi = True
    subscriber_state = str(
        subscriber.subscriber_status.get_account_status(imsi)).lower()
    try:
        account_status = False
        if not dest_imsi:
            if 'active' == subscriber_state:
                account_status = True
        else:
            # incoming number status
            if subscriber_state == 'active' or subscriber_state == 'active*':
                account_status = True

    except SubscriberNotFound:
        account_status = False
    consoleLog('info', "Returned Chat:" + str(account_status) + "\n")
    message.chat_execute('set', '_openbts_ret=%s' % account_status)


def fsapi(session, stream, env, args):
    """Handle FS API requests.

    Args:
    string of the form <imsi>|<True if for dest_imsi (default is False)>

    Subscriber State can be:
      active (unblocked), -active (blocked),first_expired (validity expired)
    """
    args = args.split('|')
    imsi = args[0]
    dest_imsi = False

    if len(args) > 1:
        dest_imsi = True
    subscriber_state = str(
        subscriber.subscriber_status.get_account_status(imsi)).lower()
    try:
        account_status = False
        if not dest_imsi:
            if 'active' == subscriber_state:
                account_status = True
        else:
            # incoming number status
            if subscriber_state == 'active' or subscriber_state == 'active*':
                account_status = True

    except SubscriberNotFound:
        account_status = False
    consoleLog('info', "Returned FSAPI: " + str(account_status) + "\n")
    stream.write(str(account_status))