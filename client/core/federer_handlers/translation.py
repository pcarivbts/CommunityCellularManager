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
            #import subprocess
            #cmd = ['mount', '-o' ,'remount', 'rw' ,'/tmp/.opkg_rootfs/']
            #proc=subprocess.Popen(cmd, stdout=subprocess.PIPE,
            #                      stderr=subprocess.STDOUT)
            #proc.wait()
            # Source path need to make writable by mount tmp directory manually
            filedir = config_db['tmp_localedir']
            languages = ['en', 'es', 'fil', 'id']
            for dt in data:
                if dt in languages:
                    filepath = filedir + dt + "/LC_MESSAGES/endaga.mo"
                    fout = open(filepath, 'wb')
                    fout.write(data[dt])
                    fout.close()
                    logger.error("Translation updated for %s " % dt)
            return web.ok(None, headers)
        except Exception as e:
            logger.error("Endaga translation " + traceback.format_exc(e))
