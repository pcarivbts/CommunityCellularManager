# Copyright (c) 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import json

from freeswitch import consoleLog

from core.freeswitch_strings import BASE_MESSAGES
from core.subscriber.base import BaseBTSNotification

notification = BaseBTSNotification()


def parse(args):
    """
    The format of the arguments must be:

        This is some %(word)s string.|{'word': 1234}
        This is some string.

    The first argument is required; the second argument is not
    required. This will return the first argument and either the
    second as a dictionary or an empty dictionary if the second
    isn't present.
    """

    res = args.split('|', 1)
    if len(res) == 1:
        return args, {}
    else:
        return res[0], json.loads(res[1])


def localize(args):

    event, params = parse(args)
    # For notifications by cloud
    if 'EVENT' == event.split('_')[0]:
        event = event.split('_')[1]
        if notification.get_notification(event) and len(event) == 3:
            # not handling params for events created by CLOUD
            message = str(True)
        else:
            message = str(False)
        consoleLog('info', 'message to check for event %s' % event)
    else:
        try:
            message = str(notification.get_notification(event) % params)
            consoleLog('info', "Localizing %s: %s" % (args, message))
        except:
            # Let's send english as default
            message = str(BASE_MESSAGES[event] % params)
            consoleLog('info', "translation missing for '%s'" % event)
        consoleLog('info', 'message %s' % message)
    return message


def chat(message, args):
    res = localize(args)
    message.chat_execute('set', '_localstr=%s' % res)


def fsapi(session, stream, env, args):
    message = localize(args)
    if isinstance(session, str):
        # we're in the FS CLI, so no session object
        consoleLog('info',
                   "No session; otherwise would set _localstr=%s" % message)
    else:
        session.execute("set", "_localstr=%s" % message)


def handler(session, args):
    res = localize(args)
    session.execute("set", "_localstr=%s" % res)
