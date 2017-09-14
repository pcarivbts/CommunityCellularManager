"""Handles outgoing SMS and delivery receipts for the federer server.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

import web
from core.federer_handlers import common
from commands.translating import compile_lang

class translate(common.incoming):
    """
    Class for handling incoming message from Endaga.
    """
    def __init__(self):
        common.incoming.__init__(self)

    def GET(self):
        data = web.input()
        f = open("/var/log/lighttpd/translation.txt", "w+")
        f.write("---- GET ----- %s " % data)
        return web.ok()

    def POST(self):
        headers = {
            'Content-type': 'text/plain'
        }
        data = web.input()
        f = open("/var/log/lighttpd/translation.txt", "w+")
        f.write("\n---------POST Method called------------------------\n")
        # f.write("\n POST ---  %s " % data)

        filedir = '/usr/share/locale/'
        uploaded_files = ['en', 'es', 'fil', 'id']
        for dt in data:
            f.write("\n****************** %s ************************** " % dt)
            if dt in uploaded_files:
                filepath = filedir + dt + "/LC_MESSAGES/endaga.po"
                fout = open(filepath, 'wb')
                fout.write(data[dt])
                fout.close()
            else:
                f.write("\n---- %s ------ %s" % (dt, data[dt]))
        compile_lang()
        return web.ok(None, headers)
