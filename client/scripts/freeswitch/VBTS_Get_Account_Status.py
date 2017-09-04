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


def chat(message, imsi):
    """Handle chat requests.

    Args:
      imsi: a subscriber's IMSI
    """
    try:
        # account_status = str(subscriber.get_account_status(imsi))
        account_status = str(
            subscriber.subscriber_status.get_subscriber_states(imsi))
    except SubscriberNotFound:
        account_status = ''
    consoleLog('info', "Returned Chat:" + account_status + "\n")
    message.chat_execute('set', '_openbts_ret=%s' % account_status)


def fsapi(session, stream, env, imsi):
    """Handle FS API requests.

    Args:
      imsi: a subscriber's IMSI
    """
    try:
        account_status = str(subscriber.get_account_status(imsi))
    except SubscriberNotFound:
        account_status = ''
    consoleLog('info', "Returned FSAPI: " + account_status + "\n")
    stream.write(account_status)
