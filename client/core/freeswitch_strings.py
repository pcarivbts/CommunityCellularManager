"""
The way we handle this is via the endaga_notification script. It's used in a
dialplan/chatplan like so:

    <action application="python" data='endaga_notification 'any key in Base_MESSAGES' % {"number": ${vbts_callerid}}'/>
    ex:
    <action application="python" data='endaga_notification sms_error % {"number": ${vbts_callerid}}'/>

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import gettext

import core.config_database
from ccm.common import currency

configdb = core.config_database.ConfigDB()
number_check_number = configdb.get('number_check_number') or 104
credit_check_number = configdb.get('credit_check_number') or 103

BASE_MESSAGES = {
    # Mapped
    str(credit_check_number): "Your balance is %(account_bal)s.",
    str(number_check_number): "Your number is %(from_number)s.",

    'block_expired': "Your account is blocked or expired, Please contact "
                     "your service provider.",
    'receiver_expired': "Failed to deliver message, as the receiver number "
                        "has expired.",
    'provisioning': "Already registered with number %(from_number)s",
    'unprovisioned': "Your phone is not provisioned.",
    'sms_error': "Message not sent to %(to_number)s",
    'no_money': "Your account doesn't have sufficient funds.",
    'no_money_sms': "Your account doesn't have sufficient funds to send an "
                    "SMS.",
    'invalid_address': "Invalid Address",
    'reg_failed': "Failed to register your handset.",

    # SMS CREDIT TRANSFER (CT_MESSAGES)
    'transfer_self_fail': "Transaction Failed. Sharing load to your own "
                            "account is not allowed.",
    'transfer_attempts_left': "Your left attempts %(attempts)s",
    'transfer_denomination_error': "Top-up not under denomination range.",
    'transfer_confirm': "Reply to this message with %(code)s to confirm your "
                        "transfer of %(amount)s to %(to_number)s Code expires "
                        "in ten minutes.",
    'transfer_from_to': "SMS transfer from %(from_number)s to %(to_number)s",
    'transfer_details_recipient': "You've received %(amount)s. credits from "
                                  "%(from_number)s Now your balance "
                                  "%(new_balance)s and validity is "
                                  "%(validity)s.",
    'transfer_details_sender': "You've transferred %(amount)s to "
                               "%(to_number)s Your new balance is "
                               "%(account_bal)s.",
    'transfer_expired': "That transfer confirmation code doesn't exist or has "
                        "expired .",
    'transfer_help': "To transfer credit, reply with a message in the format "
                     "'NUMBER*AMOUNT'.",
    'invalid_number': "Invalid phone number: %(to_number)s",
    'low_credit': "Your account doesn't have sufficient funds for the "
                  "transfer.",
    'sender_dont_exists': "The number you're sending to doesn't exist. "
                          "Try again.",
    'account_blocked': "Your account is blocked",
    'no_validity': "Your account has no validity",
    'top_up_not_allowed': "Top-up not allowed. Maximum balance limit crossed "
                          "%(credit)s.",
    'top_up_not_allowed_detail': "Top-up not allowed. Maximum balance limit "
                                 "crossed %(credit)s You can transfer upto"
                                 " %(transfer)s.",
}
# TODO(sharma-sagar): After above below will be dead code below (remove later)
gt = gettext.translation("endaga", configdb['localedir'],
                         [configdb['locale'], "en"]).gettext

# NOTE: (chatplan/01_provisioning) This message is sent when a user tries to register an already registered SIM card.
gt("Already registered with number %(from_number)s.")

# NOTE: (chatplan/02_unprovisioned) This message is sent when an unprovisioned phone tries to use the network.
gt("Your phone is not provisioned.")

# NOTE: (chatplan/12_credit_check, dialplan/10_credit_check) This message is sent when the user checks their account balance.
gt("Your balance is %(account_bal)s.")

# NOTE: (chatplan/13_number_check, dialplan/11_number_check) This message is sent when the user checks their phone number.
gt("Your number is %(from_number)s.")

# NOTE: (chatplan/20_error) Sent when the SMS contains bad characters.
gt("Message not sent to %(to_number)s.")

# NOTE: (dialplan/25_no_money) This message is sent when the user has insufficient funds.
gt("Your account doesn't have sufficient funds.")

# NOTE: (chatplan/22_no_money) This message is sent when the user has insufficient funds for an SMS
gt("Your account doesn't have sufficient funds to send an SMS.")

# NOTE: (chatplan/99_invalid) This message is sent when the SMS is sent to an invalid address.
gt("Invalid Address")


def localize(string_key, params):
    return str(gt(string_key) % params)


def humanize_credits(amount_raw):
    """Given a raw amount from the subscriber registry, this will return a
    human readable Money instance in the local Currency.
    """
    currency_code = configdb['currency_code']
    money = currency.humanize_credits(amount_raw,
                                      currency.CURRENCIES[currency_code])
    return money


def parse_credits(string):
    """Given a numerical string, this will return a Money instance in the
    local currency.
    """
    currency_code = configdb['currency_code']
    money = currency.parse_credits(string,
                                   currency.CURRENCIES[currency_code])
    return money
