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
from commands.translating import compile_lang
from ccm.common import logger

class translate(common.incoming):
    """
    Class for handling incoming translation files from Endaga cloud.
    """
    def __init__(self):
        common.incoming.__init__(self)

    def GET(self):
        return web.ok()

    def POST(self):
        try:
            headers = {
                'Content-type': 'text/plain'
            }
            data = web.input()
            filedir = '/usr/share/locale/'
            uploaded_files = ['en', 'es', 'fil', 'id']
            for dt in data:
                if dt in uploaded_files:
                    filepath = filedir + dt + "/LC_MESSAGES/endaga.po"
                    fout = open(filepath, 'wb')
                    fout.write(data[dt])
                    fout.close()
            compile_lang()
            return web.ok(None, headers)
        except Exception as e:
            logger.error("Endaga translation " + traceback.format_exc(e))
