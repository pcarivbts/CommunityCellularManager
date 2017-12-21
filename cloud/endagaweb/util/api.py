"""
Api utility functions.

Copyright (c) 2016-present, Facebook, Inc.
All rights reserved.

This source code is licensed under the BSD-style license found in the
LICENSE file in the root directory of this source tree. An additional grant
of patent rights can be found in the PATENTS file in the same directory.
"""

from endagaweb import models
from googletrans import Translator, constants
import re
from requests.exceptions import ConnectionError
import settings
import logging
log = logging.getLogger(__name__)

def get_network_from_user(user):
    """The API can be called from the dashboard using a Django
    user session or from a BTS. Dashboard requests come from a user
    with a UserProfile while BTS requests come from a Network's auth_user.
    We return the correct network based on the user being used.
    """
    try:
        return models.Network.objects.get(auth_user=user)
    except models.Network.DoesNotExist:
        up = models.UserProfile.objects.get(user=user)
        return up.network


def translate(message, to_lang='en', from_lang='auto'):
    """
    translates messages to desired language default is English(en)
    :param message: message that needs to be translated
    :param to_lang: language message to be translated to.
    :param from_lang: current language of the message.
    :return:
    """
    translator = Translator()
    try:
        return translator.translate(message, dest=to_lang, src=from_lang).text
    except ConnectionError:
        log.error('Translation failing due to connection error, '
                  'please check network connectivity')
        raise

def multiple_translations(message, *to_lang):
    """
    :param message: message to be translated
    :param to_lang: list of languages to be converted in
    :return resp: a dictionary with lang as key translation as value
    ex: {'tl': translated message in filipino}
    """
    resp = {}
    for lang in to_lang:
        if lang in constants.LANGUAGES.keys():
            resp[lang] = translate(message, lang)
    return resp


def format_and_translate(message, language=None):
    if language is None:
        language = settings.BTS_LANGUAGES
    message = str(message).replace(')s.', ')s ')
    regx = "\%\(\w+\)s"  # regex for '%(params)s'
    matches = re.findall(regx, message)
    tampered_message = message.split()
    if matches:  # if any variables
        wildcards = {}
        cnt = 1
        for match in matches:
            cnt += 1
            # translation becomes better if replaced some number
            replacement = str(cnt * cnt)
            wildcards.update({str(match): replacement})
        for index, string in enumerate(tampered_message):
            if string in wildcards.keys():
                tampered_message[index] = wildcards[string]
        tampered_message = ' '.join(tampered_message)
        translation = multiple_translations(tampered_message, *language)
        for match in wildcards:
            for lang in language:
                translation[lang] = translation[lang].replace(
                    wildcards[match], match)
        return translation
    return multiple_translations(message, *language)
