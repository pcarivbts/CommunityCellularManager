"""Application logic for the SMS credit transfer service.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import os
import random
import re
import sqlite3
import time

from core import config_database
from core import events
from core import freeswitch_strings
from core.denomination_store import DenominationStore
from core.exceptions import SubscriberNotFound
from core.sms import sms
from core.subscriber import subscriber
from core.freeswitch_strings import BASE_MESSAGES
from core.subscriber.base import BaseBTSNotification

config_db = config_database.ConfigDB()
ERROR_TRX = " error_transfer"
notification = BaseBTSNotification()


def _init_pending_transfer_db():
    """Create the pending transfers table if it doesn't already exist."""
    db_create_str = (
        "CREATE TABLE pending_transfers (code VARCHAR(5) PRIMARY KEY,"
        " time FLOAT, from_acct INTEGER, to_acct INTEGER, amount INTEGER);")
    try:
        with open(config_db['pending_transfer_db_path']):
            pass
    except IOError:
        db = sqlite3.connect(config_db['pending_transfer_db_path'])
        db.execute(db_create_str)
        db.commit()
        db.close()
        # Make the DB world-writable.
        os.chmod(config_db['pending_transfer_db_path'], 0o777)


def get_validity_days(amount):
    denomination = DenominationStore()
    validity_days = denomination.get_validity_days(amount)
    if validity_days is None:
        return None
    else:
        return validity_days[0]


def process_transfer(from_imsi, to_imsi, amount):
    """Process a transfer request.

    Args:
      from_imsi: the sender's IMSI
      to_imsi: the recipient's IMSI
      amount: an amount of credit to add (type?)

    Returns:
      boolean indicating success
    """
    # Error when user tries to transfer to his own account
    if from_imsi == to_imsi:
        return False, get_event('transfer_self_fail')
    from_balance = int(subscriber.get_account_balance(from_imsi))
    # Error when blocked or expired user tries to transfer credit
    from_imsi_status = subscriber.status().get_account_status(
        from_imsi)
    to_imsi_status = subscriber.status().get_account_status(
        from_imsi)
    if from_imsi_status != 'active':
        if from_imsi_status == 'active*':
            status = get_event('account_blocked')
        else:
            status = get_event('no_validity')
        return False, status
    # rare scenario
    if to_imsi_status in ['recycle', 'recycle*']:
        return False, ("%s does not exists" % to_imsi)
    # Error when user tries to transfer more credit than they have.
    if not from_balance or from_balance < amount:
        return False, (get_event('low_credit'))
    # Error when user tries to transfer to a non-existent user.
    #       Could be 0!  Need to check if doesn't exist.
    if not to_imsi or (subscriber.get_account_balance(to_imsi) == None):
        return False, (get_event('sender_dont_exists'))
    # Error when user tries to transfer more credit than network max balance
    network_max_balance = int(config_db['network_max_balance'])
    credit_limit = freeswitch_strings.humanize_credits(network_max_balance)
    to_balance = int(subscriber.get_account_balance(to_imsi))
    max_transfer = network_max_balance - to_balance
    max_transfer_str = freeswitch_strings.humanize_credits(max_transfer)
    from_num = subscriber.get_numbers_from_imsi(from_imsi)[0]
    to_num = subscriber.get_numbers_from_imsi(to_imsi)[0]
    max_attempts = config_db['network_mput']
    if to_balance > network_max_balance:
        attempts = subscriber.status().get_invalid_count(from_imsi)
        block_info = " Attempts left %(left)s !" % {
            'left': int(max_attempts) - (int(attempts) + 1)
        }
        reason = (get_event('top_up_not_allowed')) % {
            'credit': credit_limit}

        # For cloud
        event_msg = (BASE_MESSAGES['top_up_not_allowed']) % {
            'credit': credit_limit}
        events.create_transfer_event(from_imsi, from_balance, from_balance,
                                     event_msg + ERROR_TRX, from_num, to_num)

        return False, reason + block_info + ERROR_TRX
    elif (amount + to_balance) > network_max_balance:
        # Mark this event for blocking
        attempts = subscriber.status().get_invalid_count(from_imsi)
        block_info = get_event(
            'transfer_attempts_left') % {
                         'attempts': int(max_attempts) - (int(attempts) + 1)
                     }
        reason = get_event('top_up_not_allowed_detail') % {
            'credit': credit_limit, 'transfer': max_transfer_str}

        # For cloud
        event_msg = (BASE_MESSAGES['top_up_not_allowed_detail']) % {
            'credit': credit_limit, 'transfer': max_transfer_str}
        events.create_transfer_event(from_imsi, from_balance, from_balance,
                                     event_msg + ERROR_TRX, from_num, to_num)

        return False, reason + block_info + ERROR_TRX
    # check top-up amount in denomination bracket
    validity_days = get_validity_days(amount)
    if validity_days is None:
        attempts = subscriber.status().get_invalid_count(from_imsi)
        block_info = get_event(
            'transfer_attempts_left') % {
            'attempts': int(max_attempts) - (int(attempts) + 1)}
        reason = get_event('transfer_denomination_error')

        # For cloud
        event_msg = (BASE_MESSAGES['transfer_denomination_error'])
        events.create_transfer_event(from_imsi, from_balance, from_balance,
                                     event_msg + ERROR_TRX, from_num, to_num)
        return False, reason + block_info + ERROR_TRX
    # Add the pending transfer.
    code = ''
    for _ in range(int(config_db['code_length'])):
        code += str(random.randint(0, 9))
    db = sqlite3.connect(config_db['pending_transfer_db_path'])
    db.execute("INSERT INTO pending_transfers VALUES (?, ?, ?, ?, ?)",
               (code, time.time(), from_imsi, to_imsi, amount))
    db.commit()
    db.close()
    to_num = subscriber.get_numbers_from_imsi(to_imsi)[0]
    amount_str = freeswitch_strings.humanize_credits(amount)
    response = (get_event('transfer_confirm')) % {
        'code': code, 'amount': amount_str, 'to_number': to_num
    }
    return True, response


def process_confirm(from_imsi, code):
    """Process a confirmation request.

    Args:
      from_imsi: sender's IMSI
      code: the input confirmation code string
    """
    # Step one: delete all the confirm codes older than some time.
    db = sqlite3.connect(config_db['pending_transfer_db_path'])
    db.execute("DELETE FROM pending_transfers"
               " WHERE time - ? > 600", (time.time(),))
    db.commit()

    # Step two: check if this (from_imsi, code) combo is valid.
    r = db.execute("SELECT from_acct, to_acct, amount FROM pending_transfers"
                   " WHERE code=? AND from_acct=?", (code, from_imsi))
    res = r.fetchone()
    if res and len(res) == 3:
        from_imsi, to_imsi, amount = res
        from_num = subscriber.get_numbers_from_imsi(from_imsi)[0]
        to_num = subscriber.get_numbers_from_imsi(to_imsi)[0]
        reason = (get_event('transfer_from_to')) % {
            'from_number': from_num, 'to_number': to_num}

        event_msg = (BASE_MESSAGES['transfer_from_to']) % {
            'from_number': from_num, 'to_number': to_num}
        # Deduct credit from the sender.
        from_imsi_old_credit = subscriber.get_account_balance(from_imsi)
        from_imsi_new_credit = int(from_imsi_old_credit) - int(amount)
        events.create_transfer_event(from_imsi, from_imsi_old_credit,
                                     from_imsi_new_credit, event_msg,
                                     from_number=from_num, to_number=to_num)
        subscriber.subtract_credit(from_imsi, str(int(amount)))

        # Add credit to the recipient.
        to_imsi_old_credit = subscriber.get_account_balance(to_imsi)
        to_imsi_new_credit = int(to_imsi_old_credit) + int(amount)
        events.create_transfer_event(to_imsi, to_imsi_old_credit,
                                     to_imsi_new_credit, event_msg,
                                     from_number=from_num, to_number=to_num)
        top_up_validity = subscriber.status().get_subscriber_validity(
            to_imsi, get_validity_days(amount))
        subscriber.add_credit(to_imsi, str(int(amount)))

        # Humanize credit strings
        amount_str = freeswitch_strings.humanize_credits(amount)
        to_balance_str = freeswitch_strings.humanize_credits(
            to_imsi_new_credit)
        from_balance_str = freeswitch_strings.humanize_credits(
            from_imsi_new_credit)
        # Let the recipient know they got credit.
        message = (get_event(
            'transfer_details_recipient')) % {
                      'amount': amount_str, 'from_number': from_num,
                      'new_balance': to_balance_str,
                      'validity': top_up_validity}
        sms.send(str(to_num), str(config_db['app_number']), str(message))
        # Remove this particular the transfer as it's no longer pending.
        db.execute("DELETE FROM pending_transfers WHERE code=?"
                   " AND from_acct=?", (code, from_imsi))
        db.commit()
        # Tell the sender that the operation succeeded.
        return True, get_event(
            'transfer_details_sender') % {
                   'amount': amount_str, 'to_number': to_num,
                   'account_bal': from_balance_str}

    return False, get_event('transfer_expired')


def handle_incoming(from_imsi, request):
    """Called externally by an FS script.

    Args:
      from_imsi: sender's IMSI
      request: a credit transfer or credit transfer confirmation request
    """
    request = request.strip()

    # This parses a to_number (length 1 or more) and an amount that can
    # be formatted using a comma for a thousands seperator and a period for
    # the decimal place
    transfer_command = re.compile(
        r'^(?P<to_number>[0-9]+)'
        r'\*'
        r'(?P<amount>[0-9]*(?:,[0-9]{3})*(?:\.[0-9]*)?)$')
    transfer = transfer_command.match(request)

    confirm_command = re.compile(r'^(?P<confirm_code>[0-9]{%d})$' %
                                 int(config_db['code_length']))
    confirm = confirm_command.match(request)
    _init_pending_transfer_db()
    max_attempts = config_db['network_mput']
    if transfer:
        to_number, amount = transfer.groups()
        amount = freeswitch_strings.parse_credits(amount).amount_raw
        # Translate everything into IMSIs.
        try:
            to_imsi = subscriber.get_imsi_from_number(to_number)
            _, resp, = process_transfer(from_imsi, to_imsi, amount)
            if not _ and ERROR_TRX in resp:
                subscriber.status().set_invalid_count(from_imsi, max_attempts)
                resp = resp.replace(ERROR_TRX, '')
            else:
                subscriber.status().reset_invalid_count(from_imsi)
        except SubscriberNotFound:
            resp = get_event('invalid_number') % {
                'to_number': to_number}
    elif confirm:
        # The code is the whole request, so no need for groups.
        code = request.strip()
        _, resp = process_confirm(from_imsi, code)
    else:
        # NOTE: Sent when the user tries to transfer credit with the wrong
        #       format message.
        resp = get_event('transfer_help')
    from_number = subscriber.get_numbers_from_imsi(from_imsi)[0]
    sms.send(str(from_number), str(config_db['app_number']), str(resp))


def get_event(event):
    if notification.get_notification(event):
        return notification.get_notification(event)
    return BASE_MESSAGES[event]