"""
store denomination bracket in the backend database.

Copyright (c) 2017-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""






import os

import psycopg2


# In our CI system, Postgres credentials are stored in env vars.
PG_USER = os.environ.get('PG_USER', 'endaga')
PG_PASSWORD = os.environ.get('PG_PASSWORD', 'endaga')


class DenominationStore(object):
    """Keeps track of all system events that need to be sent to the server."""

    def __init__(self):
        self.connection = psycopg2.connect(host='localhost', database='endaga',
                                     user=PG_USER, password=PG_PASSWORD)
        self.table_name = 'denomination_store'
        # Create the table if it doesn't yet exist.
        with self.connection.cursor() as cursor:
            command = ("CREATE TABLE IF NOT EXISTS %s("
                       " id integer NOT NULL,"
                       " start_amount bigint NOT NULL,"
                       " end_amount bigint NOT NULL,"
                       " validity_days integer NOT NULL"
                       ");")
            cursor.execute(command % self.table_name)
            self.connection.commit()

    def empty(self):
        """Drops all records from the table."""
        with self.connection.cursor() as cursor:
            command = 'truncate %s' % self.table_name
            cursor.execute(command)
            self.connection.commit()

    def get_records(self):
        res = []
        template = ('select * from %s ')
        command = template % (self.table_name)
        with self.connection.cursor() as cursor:

            cursor.execute(command)
            self.connection.commit()
            r = cursor.fetchall()
            for item in r:
                data = {'start_amount': item[1],
                        'end_amount': item[2], 'validity': item[3]}

            return res

    def get_all_id(self):
        res =[]

        template = 'select * from %s '
        command = template % (self.table_name)
        with self.connection.cursor() as cursor:
            cursor.execute(command)
            self.connection.commit()
            r = cursor.fetchall()
            for item in r:
               res.append(item[0])
            return res

    def get_record(self, id):
        """Gets the most recent record for an Id.

        Returns None if no record was found.
        """
        command = "select * from %s where id='%s'"
        with self.connection.cursor() as cursor:
            cursor.execute(command % (self.table_name, id))
            self.connection.commit()
            if not cursor.rowcount:
                return None
            else:
                return cursor.fetchall()[0]

    def delete_record(self, id):
        template = 'delete from %s where id = %s'
        command = template % (self.table_name, id)
        with self.connection.cursor() as cursor:
            cursor.execute(command)
            self.connection.commit()

    def get_validity_days(self,top_up):

        template = "select validity_days from %s where  start_amount <=%s and end_amount >=%s order by -end_amount"
        command = template %(self.table_name, top_up, top_up)
        with self.connection.cursor() as cursor:
            cursor.execute(command)
            self.connection.commit()
            r = cursor.fetchall()
            if len(r):
                return r[0]
            else:
                return None

    def add_record(self,id, start_amount, end_amount, validity):
        schema = ('id, start_amount, end_amount, validity_days')
        values = "'%s','%s', '%s', %s" % (
            id, start_amount, end_amount, validity)
        command = 'insert into %s (%s) values(%s)' % (
            self.table_name, schema, values)
        with self.connection.cursor() as cursor:
            cursor.execute(command)
            self.connection.commit()

