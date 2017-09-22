"""Handles outgoing SMS and delivery receipts for the federer server.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import web
import traceback
from core.federer_handlers import common
from core import config_database
from ccm.common import logger

config_db = config_database.ConfigDB()


class translate(common.incoming):
    """
    Class for handling incoming translation files from Endaga cloud.
    """
    def __init__(self):
        common.incoming.__init__(self)

    def GET(self):
        try:
            headers = {'Content-type': 'text/plain'}
            # This is DEBUG code, this need to remove before PR and core review
            f = open("/var/log/lighttpd/translation.txt", "w+")
            f.write("\nSKS---- GET ----- ")
            f.close()
            return web.ok(None, headers)
        except Exception as e:
            logger.error("Endaga translation " + traceback.format_exc(e))
            web.ok()

    def POST(self):
        try:
            headers = {
                'Content-type': 'text/plain'
            }
            data = web.input()
            filedir = config_db['localedir']

            # import subprocess
            # cmd = ['mount', '-o' ,'remount', 'rw' ,'/tmp/.opkg_rootfs/']
            # proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            # proc.wait()
            # This is DEBUG code, this need to remove before PR and core review
            f = open("/var/log/lighttpd/translation.txt", "w+")
            f.write("\n---------POST Method called------------------------\n")
            f.write("\n POST ---  %s " % data)
            filedir = '/tmp/.opkg_rootfs/usr/share/locale/'
            uploaded_files = ['en', 'es', 'fil', 'id']
            for dt in data:
                f.write("\n****************** %s ********************* " % dt)
                if dt in uploaded_files:
                    filepath = filedir + dt + "/LC_MESSAGES/endaga.mo"
                    fout = open(filepath, 'wb')
                    fout.write(data[dt])
                    fout.close()
            f.close()
            return web.ok(None, headers)
        except Exception as e:
            logger.error("Endaga translation " + traceback.format_exc(e))
