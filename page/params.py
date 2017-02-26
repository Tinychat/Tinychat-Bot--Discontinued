import logging
import random
import time
import webbrowser
from xml.dom.minidom import parseString
from xml.parsers.expat import ExpatError

import util.web

log = logging.getLogger(__name__)


class Params(object):
    """
    Class containing methods needed to establish a connection.
    It also contains the method to retrieve the token to start a broadcast.
    """
    _config_url = 'https://apl.tinychat.com/api/find.room/{0}?site=tinychat&url=tinychat.com'
    _config_url_pw = 'https://apl.tinychat.com/api/find.room/{0}?site=tinychat&password={1}&url=tinychat.com'
    _captcha_key_url = 'https://tinychat.com/api/captcha/check.php?room=tinychat^{0}&guest_id={1}'
    _broadcast_token_url = 'https://tinychat.com/api/broadcast.pw?site=tinychat&name={0}&nick={1}&id={2}'

    def __init__(self, room_name, room_pass, swf_version, proxy=None):
        """ Create a instance of the Params class.

        :param room_name: The name of the tinychat room.
        :type room_name: str
        :param room_pass: The room password (if any)
        :type room_pass: str
        :param swf_version: The current tinychat SWF version.
        :type swf_version: str
        :param proxy: Proxy and port in the format IP:PORT
        :type proxy: str
        """
        self.room_name = room_name
        self.room_pass = room_pass
        self.proxy = proxy
        self.swf_version = swf_version

        self._config_status = None
        self._tc_url = None
        self._roomtype = None
        self._greenroom = False
        self._bpassword = None

    def get_config(self):
        """ Sets the different RTMP properties. """
        if self.room_pass:
            _url = self._config_url_pw.format(self.room_name, self.room_pass)
        else:
            _url = self._config_url.format(self.room_name)

        _response = util.web.http_get(url=_url, proxy=self.proxy)
        log.debug('room config response: %s' % _response)
        if _response['content'] is not None:
            try:
                _xml = parseString(_response['content'])
            except ExpatError as e:
                log.error('ExpatError: %s' % e)
                _xml = None
            if _xml is not None:
                root = _xml.getElementsByTagName('response')[0]
                # set the config_status property.
                self._config_status = root.getAttribute('result')
                if self._config_status != 'PW' or self._config_status != 'CLOSED':
                    # set the roomtype property.
                    self._roomtype = root.getAttribute('roomtype')
                    # set the tc_url property.
                    self._tc_url = root.getAttribute('rtmp')

                    if root.getAttribute('greenroom'):
                        # set the is_greenroom property.
                        self._greenroom = True

                    if 'bpassword' in _response['content']:
                        # set the bpassword property.
                        self._bpassword = root.getAttribute('bpassword')

    @property
    def config_status(self):
        """ This method can be called to check if the RTMP properties were set successfully.

        :return: The current configurations status as int
        1 = the room is password protected.
        2 = the room is closed.
        3 = the configuration was retrieved successfully.
        4 = failure.
        :rtype: int
        """
        if self._config_status == 'PW':
            return 1
        elif self._config_status == 'CLOSED':
            return 2
        elif self._config_status == 'OK' or self._config_status == 'RES':
            return 3
        return 4

    @property
    def tc_url(self):
        """
        :return: RTMP tc_utl or None on failure.
        :rtype: str | None
        """
        if self._tc_url is None:
            return None
        return str(self._tc_url)

    @property
    def ip(self):
        """
        :return: RTMP ip or None on failure.
        :rtype: str | None
        """
        if self.tc_url is None:
            return None
        return u'' + self.tc_url.split('/')[2].split(':')[0]

    @property
    def port(self):
        """
        :return: RTMP port or None on failure.
        :rtype: int | None
        """
        if self.tc_url is None:
            return None
        return int(self.tc_url.split('/')[2].split(':')[1])

    @property
    def app(self):
        """
        :return: RTMP app or None on failure.
        :rtype: str | None
        """
        if self.tc_url is None:
            return None
        return u'' + self.tc_url.split('/')[3]

    @property
    def roomtype(self):
        """
        :return: Specific application RTMP parameter.
        :rtype: str
        """
        return u'' + self._roomtype

    @property
    def is_greenroom(self):
        """
        :return: True if greenroom, else False
        :rtype: bool
        """
        return self._greenroom

    @property
    def bpassword(self):
        """
        :return: Md5 hash if available.
        :rtype: str | None
        """
        return self._bpassword

    @property
    def embed_url(self):
        """ The html page the SWF file is embedded on.

        :return: RTMP embed_url.
        :rtype: str
        """
        return u'http://tinychat.com/{0}'.format(self.room_name)

    @property
    def desktop_version(self):
        """ Specific application RTMP parameter.

        :return: tinychat (desktop) version.
        :rtype: str
        """
        return u'Desktop 1.0.0.{0}'.format(self.swf_version)

    @property
    def swf_url(self):
        """ The url to the SWF file.

        :return: RTMP swf_url
        :rtype: str
        """
        _swf_url = u'http://tinychat.com/embed/Tinychat-11.1-1.0.0.{0}.swf?version=1.0.0.{0}/[[DYNAMIC]]/8'
        return _swf_url.format(self.swf_version)

    @property
    def config_dict(self):
        """
        :return: All the properties as dictionary.
        :rtype: dict
        """
        conf = {
            'result': self._config_status,
            'tcurl': self.tc_url,
            'ip': self.ip,
            'port': self.port,
            'app': self.app,
            'roomtype': self.roomtype,
            'greenroom': self.is_greenroom,
            'bpassword': self.bpassword,
            'embed_url': self.embed_url,
            'desktop_version': self.desktop_version,
            'swf_url': self.swf_url
        }
        return conf

    def cauth_cookie(self):
        """ This is needed to make a successful connection, it is not really a 'cookie',
         but named so after it's name in the json response.

        :return: The cauth cookie needed to make a connection.
        :rtype: str | None
        """
        ts = int(round(time.time() * 1000))
        _url = 'https://tinychat.com/cauth?room={0}&t={1}'.format(self.room_name, ts)

        _response = util.web.http_get(url=_url, json=True, proxy=self.proxy)
        log.debug('cauth cookie response: %s' % _response)
        if _response['json'] is not None:
            if 'cookie' in _response['json']:
                return _response['json']['cookie']
            return None

    def recaptcha(self):
        """ Check if we need to solve a captcha.

        This will open in the default browser.

        If we choose to not solve the captcha should it be required,
        we will then be considered a 'lurker' and we will not be able to chat
        and our name will be shown as a guest name in the room.
        """
        t = str(random.uniform(0.9, 0.10))
        _url = 'https://tinychat.com/cauth/captcha?{0}'.format(t)

        _response = util.web.http_get(url=_url, json=True, proxy=self.proxy)
        log.debug('recaptcha response: %s' % _response)
        if _response['json'] is not None:
            if _response['json']['need_to_solve_captcha'] == 1:
                link = 'https://tinychat.com/cauth/recaptcha?token={0}'.format(_response['json']['token'])
                webbrowser.open(link, new=True)
                print (link)
                raw_input('Solve the captcha and click enter to continue.')

    def get_captcha_key(self, uid):
        """ This key is required before starting to chat.

        :param uid: Client user identification.
        :type uid: int | str
        :return: The captcha key required before we can start chatting or None on failure.
        :rtype: str | None
        """
        _url = self._captcha_key_url.format(self.room_name, uid)
        _response = util.web.http_get(url=_url, json=True, proxy=self.proxy)

        log.debug('captcha key response: %s' % _response)
        if _response['json'] is not None:
            if 'key' in _response['json']:
                return _response['json']['key']
            return None

    def get_broadcast_token(self, nick, uid):
        """ Token required to start a broadcast.

        :param nick: Client nick name
        :type nick: str
        :param uid: Client user identification
        :type uid: str | int
        :return: The broadcast token required to start a broadcast or None on failure.
        :rtype: str | None
        """
        _url = self._broadcast_token_url.format(self.room_name, nick, uid)
        if self.is_greenroom:
            _url.replace('site=tinychat', 'site=greenroom')

        _response = util.web.http_get(url=_url, proxy=self.proxy)
        log.debug('broadcast token response: %s' % _response)
        if _response['content'] is not None:
            _xml = parseString(_response['content'])
            root = _xml.getElementsByTagName('response')[0]
            result = root.getAttribute('result')
            if result == 'PW':
                return result
            return root.getAttribute('token')
        return None
