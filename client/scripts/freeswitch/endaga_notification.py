# Copyright (c) 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import json

from freeswitch import consoleLog

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

    # do the localization lookup
    # res = freeswitch_strings.localize(event, params)
    message = notification.get_notification(event)
    try:
        res = str((message) % params)
    except TypeError:
        # If dynamic var not in table
        res = str(message)
    consoleLog('info', "Localizing %s: %s" % (args, res))
    return res


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

# DB Entries Req for :
# block_or_expired
# receiver_block_or_expired
# unprovisioned
# invalid_address
# no_money
# no money sms
# bal_check : your balance is <BALANCE>
# number_info : your number is <NUM>
# number_already_registered: Already registered with number <NUM>
# msg_sent : Message is sent to <Num>
# number_exists : Already reg. with number <Num>