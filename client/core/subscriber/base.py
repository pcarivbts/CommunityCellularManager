"""Core subscriber utility methods.

Subscriber balances are stored in the local database instances.

This module also serves as a thin wrapper to the HLR implemented by
Osmocom and OpenBTS. The appropriate module is loaded at runtime based
on the system configuration.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import json
from datetime import datetime
from datetime import timedelta

import dateutil.parser as dateparser

from ccm.common import crdt, logger
from core.db.kvstore import KVStore
from core.exceptions import SubscriberNotFound, EventNotFound
from core.freeswitch_strings import BASE_MESSAGES
from itertools import count


class BaseSubscriber(KVStore):
    def __init__(self, connector=None):

        super(BaseSubscriber, self).__init__('subscribers', connector,
                                             key_name='imsi',
                                             val_name='balance')

    def get_subscriber_states(self, imsis=None):
        """
        Return a dictionary containing all the subscriber info.  Format is:

        { 'IMSIxxx...' : {'balance': <PNCounter>, 'numbers': [1,...]},
            ...
        }

        Args:
            imsis: A list of IMSIs to get state for. If None, returns
                   everything.
        Returns: if imsis is None => return ALL subscribers
                 imsis is an empty list [] => return an empty dictionary
                 otherwise => return information about the subscribers listed
                 in imsis
        """
        if imsis:  # non-empty list, return requested subscribers
            subs = self.get_multiple(imsis)
        elif imsis is None:  # empty list, return all subscribers
            subs = list(self.items())
        else:
            return {}  # empty list - return an empty dict

        res = {}
        for (imsi, balance) in subs:
            res[imsi] = {}
            # ship this as json string straight from db
            res[imsi]['balance'] = balance
            res[imsi]['numbers'] = []  # TODO(shasan): nothing for now
        return res

    def create_subscriber(self, imsi, number, ip=None, port=None):
        """Subscribers are stored  between a postgres table and the HLR.
        The postgres table stores balance information while the HLR
        stores extensions and subscriber preferences.

        Arguments:
            imsi: The subscriber IMSI.
            number: The phone number used by the subscriber. Should be in
                international e.164 format, but without the leading +.

         Raises:
            BSSError if the HLR operation failed
            ValueError if the subscriber already exists in the HLR
        """

        def _add_if_absent(cur):
            if self._get_option(cur, imsi):
                raise ValueError(imsi)
            bal = crdt.PNCounter()
            self._insert(cur, imsi, bal.serialize())

        self.add_subscriber_to_hlr(imsi, number, ip, port)
        self._connector.with_cursor(_add_if_absent)

    def delete_subscriber(self, imsi):
        """
        Deletes a subscriber from the HLR and the local postgres instance

        Raises:
            BSSError if the HLR operation failed
            SubscriberNotFound if the subscriber doesn't exist
        """
        self.delete_subscriber_from_hlr(imsi)
        del self[imsi]

    def get_account_balance(self, imsi):
        """
        Gets a subscriber's balance as an integer.

        Raises:
            SubscriberNotFound if the subscriber doesn't exist
        """
        try:
            return int(crdt.PNCounter.from_json(self[imsi]).value())
        except KeyError:
            raise SubscriberNotFound(imsi)

    def _set_credit(self, imsi, new_balance):
        """
        Set a subscriber's balance.

        Note: behavior of this is somewhat counter-intuitive. Internally, we'll
        either increment or decrement the counter such that

            balance.value() + X = new_balance.

        This kinda breaks the underlying model of the PNCounter representation,
        which only supports increment() and decrement() operations. So, if you
        run set_credit(imsi, 5) in two places such that those two set_credit's
        don't have a causal dependency, the subscriber balance will converge to
        a value that is something other than 5 probably, depending on what
        operations were necessary to get that value on each device.

        Raises:
            SubscriberNotFound if the subscriber doesn't exist
        """
        try:
            self[imsi] = new_balance
        except TypeError:
            raise IOError('corrupt billing table: multiple records for %s' %
                          (imsi,))
        except IndexError:
            raise SubscriberNotFound(imsi)

    def _get_balance(self, cur, imsi):
        """
        Get a PN counter representing the subscribers' balance.

        Important: This doesn't do anything about transactions, you need to
        make sure the caller appropriately implements that logic.

        Arguments:
            imsi: Subscriber IMSI
            cursor: DB cursor

        Returns: PNCounter representing subscriber's balance.

        Raises:
            IOError: Invalid DB state (more than one record for an IMSI)
            SubscriberNotFound: No subscriber exists in the DB
        """
        try:
            res = self._get_option(cur, imsi)
        except TypeError:
            raise IOError()
        else:
            if res is None or res == []:
                raise SubscriberNotFound(imsi)
            return crdt.PNCounter.from_json(res)

    def _set_balance(self, cur, imsi, pncounter):
        """
        Sets a subscriber balance to the given PN counter. Subscriber must
        exist in the database.

        Important: This doesn't do anything about transactions, you need to
        make sure the caller appropriately implements that logic.

        Arguments:
            imsi: Subscriber IMSI
            cursor: DB cursor
            pncounter: A PNCounter representing the subscriber's balance

        Returns: None

        Raises:
            ValueError: Invalid PNCounter
            SubscriberNotFound: No subscriber exists in the DB
        """
        bal = pncounter.serialize()

        # validate state; raises ValueError if there's a problem
        crdt.PNCounter.from_state(pncounter.state)

        try:
            self._update(cur, imsi, bal)
        except KeyError:
            # No subscriber affected
            raise SubscriberNotFound(imsi)

    def update_balance(self, imsi, pncounter):
        """
        Updates a subscriber's balance given another PN counter.

        Internally, this merges the current balance with the new PN counter,
        then saves the result as the subscribers balance.
        """

        # TODO(shasan): this needs SERIALIZABLE isolation level for correctness
        def _update(cur):
            bal = self._get_balance(cur, imsi)
            new_bal = crdt.PNCounter.merge(bal, pncounter)
            self._set_balance(cur, imsi, new_bal)

        self._connector.with_cursor(_update)

    def adjust_credit(self, imsi, credit_delta):
        """
        Adjusts a subscriber's balance by an integer delta

        Sub balances are clamped at a min of zero. If they go lower,
        we have made a mistake in the billing system as the
        procedure is to first check if a sub has the funds to complete
        an operation and then, if so, to complete the operation and
        bill for it.  When we previously allowed negative sub balances
        it created some confusing displays in the dashboard.

        Raises:
            SubscriberNotFound if the subscriber doesn't exist
            TypeError if the delta is not castable as an integer
        """
        try:
            int(credit_delta)
        except ValueError:
            raise TypeError('value %s passed to _adjust_credit is not'
                            ' int()-friendly' % credit_delta)

        # short circuit the null operation
        if credit_delta == 0:
            return

        # TODO(shasan): this needs SERIALIZABLE isolation level for correctness
        def _inc_or_dec(cur):
            bal = self._get_balance(cur, imsi)
            if credit_delta > 0:
                bal.increment(amount=credit_delta)
            else:
                # don't decrement by more than balance (see above)
                bal.decrement(amount=min(-credit_delta, bal.value()))
            self._update(cur, imsi, bal.serialize())

        self._connector.with_cursor(_inc_or_dec)

    @staticmethod
    def _get_credit_delta(amount):
        """ Convert to int, should always be positive. """
        delta = int(amount)
        # check for negative values and warn
        if delta < 0:
            logger.warning("negative credit delta")
            delta = -delta
        return delta

    def subtract_credit(self, imsi, amount):
        """
        Deducts a subscriber's balance by a scalar delta

        Raises:
            SubscriberNotFound if the subscriber doesn't exist
            ValueError if the delta is not castable as an integer
        """
        self.adjust_credit(imsi, -self._get_credit_delta(amount))

    def add_credit(self, imsi, amount):
        """
        Increments a subscriber's balance by a scalar delta

        Raises:
            SubscriberNotFound if the subscriber doesn't exist
            ValueError if the delta is not castable as an integer
        """
        self.adjust_credit(imsi, self._get_credit_delta(amount))

    def add_subscriber_to_hlr(self, imsi, number, ip, port):
        """Adds a subscriber to the radio stack HLR.

        Arguments:
            imsi: The IMSI
            number: Number in e164 format, minus the leading +
            ip: The ipaddr of this subscriber, if relevant and known.
                Typically 127.0.0.1, but OpenBTS
                will set this automatically when it gets a LUR from the phone.
            port: The port of this subscriber, if relevant and known.
                Default is 5062, but can change in
                multibts or fakephone scenarios. OpenBTS automatically updates this.

           Raises:
              BSSError if the operation failed
        """
        pass

    def delete_subscriber_from_hlr(self, imsi):
        """Removes a subscriber from the radio stack HLR.

           Raises:
              SubscriberNotFound if imsi is not found
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def get_subscribers(self, imsi=None):
        """Gets the list of subscribers that are provisioned in the GSM
           stacks HLR, filtering by the prefix, imsi, if specified.

           Note: This is different than get_subscriber_states which only
           queries postgres.

           Raises:
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def get_subscriber_imsis(self):
        return {s['name'] for s in self.get_subscribers()}

    def add_number(self, imsi, number):
        """Associate another number with an IMSI.

           Raises:
              SubscriberNotFound if imsi is not found
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def delete_number(self, imsi, number):
        """Disassociate a number with an IMSI.

           Raises:
              SubscriberNotFound if imsi is not found
              ValueError if number doesn't belong to IMSI
                  or this is the sub's last number
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def get_caller_id(self, imsi):
        """Get a subscriber's caller_id.

           Raises:
              SubscriberNotFound if imsi is not found
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def get_ip(self, imsi):
        """Get a subscriber's IP address.

           Raises:
              SubscriberNotFound if imsi is not found
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def get_port(self, imsi):
        """Get a subscriber's port.

           Raises:
              SubscriberNotFound if imsi is not found
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def get_numbers_from_imsi(self, imsi):
        """Gets numbers associated with a subscriber.

           Raises:
              SubscriberNotFound if imsi is not found
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def get_imsi_from_number(self, number, canonicalize=True):
        """Gets the IMSI associated with a number.

           Raises:
              SubscriberNotFound if imsi is not found
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def get_username_from_imsi(self, imsi):
        """Gets the SIP name of the subscriber

           Raises:
              SubscriberNotFound if imsi is not found
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def get_imsi_from_username(self, username):
        """Get the IMSI from the SIP name.
           This doesn't validate the subscriber

            Raises
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def is_authed(self, imsi):
        """Returns True if the subscriber is provisioned and authorized
        to use GSM services.

           Raises:
              BSSError if the operation failed
        """
        raise NotImplementedError()

    def get_gprs_usage(self, target_imsi=None):
        """Get all available GPRS data, or that of a specific IMSI (experimental).

        Will return a dict of the form: {
          'ipaddr': '192.168.99.1',
          'downloaded_bytes': 200,
          'uploaded_bytes': 100,
        }

        Or, if no IMSI is specified, multiple dicts like the one above will be
        returned as part of a larger dict, keyed by IMSI.

        Args:
          target_imsi: the subsciber-of-interest

        Raises:
          BSSError if the operation failed
        """
        raise NotImplementedError()

    def process_update(self, net_subs):
        """
        Processes the subscriber list. Format is:

        {
            IMSI1: {'number': [<numbers>,...], 'balance': {<PN counter>}},
            IMSI2: ...
        }

        This updates the BTS with all subscribers instructed by the cloud; any
        subscribers that are not reported by the cloud will be removed from
        this BTS.
        """
        # dict where keys are imsis and values are sub info
        bts_imsis = self.get_subscriber_imsis()
        net_imsis = set(net_subs.keys())

        subs_to_add = net_imsis.difference(bts_imsis)
        subs_to_delete = bts_imsis.difference(net_imsis)
        subs_to_update = bts_imsis.intersection(net_imsis)

        for imsi in subs_to_delete:
            self.delete_subscriber(imsi)

        # TODO(shasan) does not add new numbers
        for imsi in subs_to_update:
            sub = net_subs[imsi]
            try:
                bal = crdt.PNCounter.from_state(sub['balance'])
                self.update_balance(imsi, bal)
            except SubscriberNotFound as e:
                logger.warning(
                    "Balance sync fail! IMSI: %s is not found Error: %s" %
                    (imsi, e))
            except ValueError as e:
                logger.error("Balance sync fail! IMSI: %s, %s Error: %s" %
                             (imsi, sub['balance'], e))
                subs_to_add.add(imsi)  # try to add it (again)

        for imsi in subs_to_add:
            sub = net_subs[imsi]
            numbers = sub['numbers']
            if not numbers:
                logger.notice("IMSI with no numbers? %s" % imsi)
                continue
            self.create_subscriber(imsi, numbers[0])
            for n in numbers[1:]:
                self.add_number(imsi, n)
            try:
                bal = crdt.PNCounter.from_state(sub['balance'])
                self.update_balance(imsi, bal)
            except (SubscriberNotFound, ValueError) as e:
                logger.error("Balance sync fail! IMSI: %s, %s Error: %s" %
                             (imsi, sub['balance'], e))

    def status(self, update=None):
        status = BaseSubscriberStatus()
        if update is not None:
            status.process_update(update)
            return
        return status

    def notif_status(self, update=None):
        status = BaseBTSNotification()
        if update is not None:
            status.process_notifcaiton(update)
            return
        return status


class BaseSubscriberStatus(KVStore):
    """
    Sets and Updates Subscriber Status similar to balance updates
    Current Status can be (i.e States of subscriber):
        Blocked : Subscriber blocked for some reason (no call/sms) for some period.
        Active: Subscriber is active
        First Expire : Subscriber has no validity (no call/sms)
        Expired: Grace period also expired after First Expire (no call/sms)
    """

    def __init__(self, connector=None):
        super(BaseSubscriberStatus, self).__init__('subscribers_status',
                                                   connector, key_name='imsi',
                                                   val_name='status')

    def get_subscriber_status(self, imsis=None):
        """
        Return a dictionary containing all the subscriber status.  Format is:

        { 'IMSIxxx...' : {'state' : 'active' , 'valid_through': '01-09-2100'}
            ...
        }

        Args:
            imsis: A list of IMSIs to get state for. If None, returns
                   everything.
        Returns: if imsis is None => return ALL subscribers
                 imsis is an empty list [] => return an empty dictionary
                 otherwise => return information about the subscribers listed
                 in imsis
        """
        if imsis:  # non-empty list, return requested subscribers
            subs = self.get_multiple(imsis)
        elif imsis is None:  # empty list, return all subscribers
            subs = list(self.items())
        else:
            return {}  # empty list - return an empty dict

        res = {}
        for (imsi, state) in subs:
            res[imsi] = {}
            # state = {'state': 'active', 'valid_through': '01-09-2100'}
            res[imsi]['state'] = state
        return res

    def create_subscriber_status(self, imsi, status):
        def _add_if_absent(cur):
            if self._get_option(cur, imsi):
                raise ValueError(imsi)
            self._insert(cur, imsi, status)

        self._connector.with_cursor(_add_if_absent)

    def delete_subscriber(self, imsi):
        del self[imsi]

    def _set_status(self, cur, imsi, status):
        try:
            self._update(cur, imsi, status)
        except KeyError:
            raise SubscriberNotFound(imsi)

    def update_status(self, imsi, status):
        def _update(cur):
            self._set_status(cur, imsi, status)

        self._connector.with_cursor(_update)

    def get_subscriber_imsis(self):
        return {key for key in self.get_subscriber_status().keys()}

    def process_update(self, net_subs):
        from core import events
        bts_imsis = self.get_subscriber_imsis()
        net_imsis = set(net_subs.keys())
        subs_to_add = net_imsis.difference(bts_imsis)
        subs_to_delete = bts_imsis.difference(net_imsis)
        subs_to_update = bts_imsis.intersection(net_imsis)
        subscriber = BaseSubscriber()

        for imsi in subs_to_delete:
            self.delete_subscriber(imsi)

        for imsi in subs_to_update:
            sub = net_subs[imsi]
            sub_state = sub['state']
            sub_validity = sub['validity']
            sub_info = {"state": sub_state, "validity": sub_validity}
            # Error Transfer Count this won't sync to cloud
            if 'ie_count' not in sub:
                sub['ie_count'] = 0

            sub_info = {"state": sub_state, "validity": sub_validity,
                        "ie_count": sub['ie_count']}
            try:
                if str(sub_state).lower() not in ['active', 'active*']:
                    old_balance = subscriber.get_account_balance(imsi)
                    if old_balance > 0:
                        subscriber.subtract_credit(imsi, str(old_balance))
                        reason = 'Subscriber expired: Setting balance zero' \
                                 ' (deduct_money)'
                        events.create_add_money_event(imsi, old_balance, 0,
                                                      reason)
                self.update_status(imsi, json.dumps(sub_info))
            except SubscriberNotFound as e:
                logger.warning(
                    "State sync fail! IMSI: %s is not found Error: %s" %
                    (imsi, e))
            except ValueError as e:
                logger.error("State sync fail! IMSI: %s, %s Error: %s" %
                             (imsi, sub_info, e))
                subs_to_add.add(imsi)  # try to add it (again)

        for imsi in subs_to_add:
            sub = net_subs[imsi]
            sub_state = sub['state']
            sub_validity = sub['validity']
            sub_info = {"state": sub_state, "validity": sub_validity}
            try:
                if str(sub_state).lower() not in ['active', 'active*']:
                    old_balance = subscriber.get_account_balance(imsi)
                    if old_balance > 0:
                        subscriber.subtract_credit(imsi, str(old_balance))
                        reason = 'Subscriber expired:setting balance zero' \
                                 ' (deduct_money)'
                        events.create_add_money_event(imsi, old_balance, 0,
                                                      reason)
                self.create_subscriber_status(imsi, json.dumps(sub_info))
            except (SubscriberNotFound, ValueError) as e:
                logger.error("State sync fail! IMSI: %s, %s Error: %s" %
                             (imsi, sub_info, e))

    def get_account_status(self, imsi):
        status = json.loads(self.get(imsi))
        return str(status['state'])

    def get_subscriber_validity(self, imsi, days):
        sub_info = json.loads(self.get(imsi))
        validity = str(sub_info['validity'])
        delta_validity = datetime.utcnow() + timedelta(days=days)
        if validity is None:
            sub_info["validity"] = str(delta_validity.date())
            date = delta_validity
        else:
            validity_date = dateparser.parse(validity).date()
            if validity_date < delta_validity.date():
                sub_info["validity"] = str(delta_validity.date())
                date = delta_validity
            else:
                sub_info["validity"] = str(validity_date)
                date = validity_date
        sub_info['state'] = 'active'
        # '*' represents block, keep it blocked if already blocked.
        if '*' in self.get_account_status(imsi):
            sub_info['state'] += '*'
        self.update_status(imsi, json.dumps(sub_info))
        return str(datetime.combine(date, datetime.min.time()))

    def get_invalid_count(self, imsi):
        subscriber = json.loads(self.get(imsi))
        try:
            return int(subscriber['ie_count'])
        except:
            return 0  # doesn't exist

    def reset_invalid_count(self, imsi):
        subscriber = json.loads(self.get(imsi))
        subscriber['ie_count'] = 0
        self.update_status(imsi, json.dumps(subscriber))

    def set_invalid_count(self, imsi, max_transactions):
        subscriber = json.loads(self.get(imsi))
        if 'ie_count' in subscriber:
            subscriber['ie_count'] = int(subscriber['ie_count']) + 1
        else:
            subscriber['ie_count'] = 1

        if subscriber['ie_count'] >= max_transactions:
            # If transaction has happened means it's in active state
            subscriber['state'] = 'active*'
            subscriber['ie_count'] = 0
        self.update_status(imsi, json.dumps(subscriber))


class BaseBTSNotification(KVStore):
    _ids = count(0)

    def __init__(self, connector=None):
        self.id = next(self._ids)
        super(BaseBTSNotification, self).__init__('notification', connector,
                                                  key_name='event',
                                                  val_name='message')
        # add only once.
        if 2 > self.id:
            for message in BASE_MESSAGES:
                self.get_or_create(message, BASE_MESSAGES[message])

    def get_notification(self, event=None):
        if event:  # non-empty list, return requested notifications
            return self.get(event)
        elif event is None:  # empty list, return all
            events = list(self.items())
        else:
            return {}  # empty list - return an empty dict
        res = {}
        for (event, message) in events:
            res[event] = message
        return res

    def _set_notification(self, cur, event, message):
        try:
            self._update(cur, event, message)
        except KeyError:
            raise EventNotFound(event)

    def get_events(self):
        return {key for key in self.get_notification().keys()}

    def delete_notification(self, event):
        del self[event]

    def create_notification(self, event, message):
        def _add_if_absent(cur):
            if self._get_option(cur, event):
                raise ValueError(event)

            self._insert(cur, event, message)

        self._connector.with_cursor(_add_if_absent)

    def update_notification(self, event, message):
        def _update(cur):
            self._set_notification(cur, event, message)

        self._connector.with_cursor(_update)

    def process_notifcaiton(self, notifications):
        """
        notifications: {event: some_event , message: some_translated_message}
        Update notification messages w.r.t current bts language
        :param event: Number(int type) or Event(string type)
        """
        bts_events = self.get_events()
        cloud_events = set(notifications.keys())

        events_to_add = cloud_events.difference(bts_events)
        events_to_delete = bts_events.difference(cloud_events)
        events_to_update = bts_events.intersection(cloud_events)

        for event in events_to_delete:
            self.delete_notification(event)

        for event in events_to_update:
            message = notifications[event]
            try:
                self.update_notification(event, message)
            except EventNotFound as e:
                logger.warning(
                    "Notification sync fail! Event: %s is not found Error: %s"
                    % (event, e))
            except ValueError as e:
                logger.error("Notification sync fail! Event: %s, Error: %s"
                             % (event, e))
                events_to_add.add(notifications)  # try to add it (again)

        for event in events_to_add:
            message = notifications[event]
            self.create_notification(event, message)
            try:
                self.update_notification(event, message)
            except (EventNotFound, ValueError) as e:
                logger.error(
                    "Notification sync fail! Event: %s Error: %s" %
                    (event, e))

    def get_or_create(self, key, message=None):
        if message is not None:
            # flag the message for translation,
            # cloud to translate and revert back notification for next time
            if self.get(key) is None:
                message = str(message) + '*'
                self.create_notification(event=key, message=message)
                return
        return self.get(key)
