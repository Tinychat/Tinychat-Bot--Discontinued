import logging
import threading
import time
import traceback
from colorama import init, Fore, Style
import auth
import user
import config
from rtmplib import rtmp
from util import core, string_util, file_handler

__version__ = '6.1.2'

#  Console colors.
COLOR = {
    'white': Fore.WHITE,
    'green': Fore.GREEN,
    'bright_green': Style.BRIGHT + Fore.GREEN,
    'yellow': Fore.YELLOW,
    'bright_yellow': Style.BRIGHT + Fore.YELLOW,
    'cyan': Fore.CYAN,
    'bright_cyan': Style.BRIGHT + Fore.CYAN,
    'red': Fore.RED,
    'bright_red': Style.BRIGHT + Fore.RED,
    'magenta': Fore.MAGENTA,
    'bright_magenta': Style.BRIGHT + Fore.MAGENTA
}

init(autoreset=True)
log = logging.getLogger(__name__)

# Reference to config for submodules.
CONFIG = config


def write_to_log(msg, room_name):
    """
    Writes chat events to log.
    :param msg: str the message to write to the log.
    :param room_name: str the room name.
    """
    d = time.strftime('%Y-%m-%d')
    file_name = d + '.log'
    path = config.CONFIG_PATH + room_name + '/logs/'
    file_handler.file_writer(path, file_name, msg.encode(encoding='UTF-8', errors='ignore'))


class TinychatRTMPClient:
    """ Manages a single room connection to a given room. """
    desktop_version = u'Desktop 1.0.0.{0}'
    swf_url = u'http://tinychat.com/embed/Tinychat-11.1-1.0.0.{0}.swf?version=1.0.0.{0}/[[DYNAMIC]]/8'
    embed_url = u'http://tinychat.com/{0}'
    rtmp_parameter = dict()

    def __init__(self, roomname, nick=None, account='', password=None, room_pass=None, proxy=None):
        self.roomname = roomname
        self.nickname = nick
        self.account = account
        self.password = password
        self.room_pass = room_pass
        self.connection = None
        self.green_connection = None
        self.is_connected = False
        self.is_green_connected = False
        self.users = user.Users()
        self.active_user = None
        self._proxy = proxy
        self._client_id = None
        self._bauth_key = None
        self._is_reconnected = False
        self._is_client_mod = False
        self._is_client_owner = False
        self._b_password = None
        self._reconnect_delay = config.RECONNECT_DELAY
        self._init_time = time.time()

    def console_write(self, color, message):
        """
        Writes message to console.
        :param color: the colorama color representation.
        :param message: str the message to write.
        """
        msg_encoded = message.encode('ascii', 'ignore')
        if config.USE_24HOUR:
            ts = time.strftime('%H:%M:%S')
        else:
            ts = time.strftime('%I:%M:%S:%p')
        if config.CONSOLE_COLORS:
            msg = COLOR['white'] + '[' + ts + '] ' + Style.RESET_ALL + color + msg_encoded
        else:
            msg = '[' + ts + '] ' + msg_encoded
        try:
            print(msg)
        except UnicodeEncodeError as ue:
            log.error(ue, exc_info=True)
            if config.DEBUG_MODE:
                traceback.print_exc()

        if config.CHAT_LOGGING:
            write_to_log('[' + ts + '] ' + message, self.roomname)

    def get_rtmp_parameters(self):
        """ Get the RTMP parameters needed before trying to connect. """
        conf = core.get_roomconfig_xml(self.roomname, self.room_pass, proxy=self._proxy)
        log.debug('room config: %s' % conf)
        if conf is not None:
            if conf == 'PW':
                return 1
            elif conf == 'CLOSED':
                return 2
            else:
                self.rtmp_parameter['tcurl'] = conf['tcurl']
                self.rtmp_parameter['app'] = conf['app']
                self.rtmp_parameter['roomtype'] = conf['roomtype']
                self.rtmp_parameter['ip'] = conf['ip']
                self.rtmp_parameter['port'] = conf['port']
                self.rtmp_parameter['greenroom'] = conf['greenroom']
                self._b_password = conf['bpassword']
                if config.DEBUG_MODE:
                    for k in self.rtmp_parameter:
                        self.console_write(COLOR['white'], '%s: %s' % (k, self.rtmp_parameter[k]))
                    if self.account:
                        self.console_write(COLOR['white'], 'account: %s' % self.account)
                return 3  # is the magic number
        return 4

    def login(self):
        """
        Login to tinychat.
        :return: True if logged in else False
        """
        _account = auth.Account(account=self.account, password=self.password, proxy=self._proxy)
        if self.account and self.password:
            if _account.is_logged_in():
                return True
            _account.login()
        return _account.is_logged_in()

    def connect(self):
        """ Attempts to make a RTMP connection with the given connection parameters. """
        if not self.is_connected:
            log.info('connecting to: %s' % self.roomname)
            try:
                core.recaptcha(proxy=self._proxy)
                cauth_cookie = core.get_cauth_cookie(self.roomname, self._proxy)

                self.connection = rtmp.RtmpClient(
                    ip=self.rtmp_parameter['ip'],
                    port=self.rtmp_parameter['port'],
                    tc_url=self.rtmp_parameter['tcurl'],
                    app=self.rtmp_parameter['app'],
                    page_url=self.embed_url.format(self.roomname),
                    swf_url=self.swf_url.format(config.SWF_VERSION),
                    proxy=self._proxy,
                    is_win=True)
                self.connection.connect(
                    {
                        'account':  self.account,
                        'type': self.rtmp_parameter['roomtype'],
                        'prefix': u'tinychat',
                        'room': self.roomname,
                        'version': self.desktop_version.format(config.SWF_VERSION),
                        'cookie': cauth_cookie
                    }
                )
                self.is_connected = True
            except Exception as e:
                log.critical('connect error: %s' % e, exc_info=True)
                self.is_connected = False
                self.reconnect()
                if config.DEBUG_MODE:
                    traceback.print_exc()
            finally:
                if config.RESET_INIT_TIME:
                    self._init_time = time.time()
                if self.rtmp_parameter['greenroom'] and not self.is_green_connected:
                    threading.Thread(target=self.__connect_green).start()  #
                self.__callback()

    def __connect_green(self):
        """ Connect to the greenroom. """
        if not self.is_green_connected:
            log.debug('connecting to greenroom: %s' % self.roomname)
            try:
                self.green_connection = rtmp.RtmpClient(
                    ip=self.rtmp_parameter['ip'],
                    port=self.rtmp_parameter['port'],
                    tc_url=self.rtmp_parameter['tcurl'],
                    app=self.rtmp_parameter['app'],
                    page_url=self.embed_url.format(self.roomname),
                    swf_url=self.swf_url.format(config.SWF_VERSION),
                    proxy=self._proxy,
                    is_win=True)
                self.green_connection.connect(
                    {
                        'account': '',
                        'type': self.rtmp_parameter['roomtype'],
                        'prefix': u'greenroom',
                        'room': self.roomname,
                        'version': self.desktop_version.format(config.SWF_VERSION),
                        'cookie': ''
                    }
                )
                self.is_green_connected = True
            except Exception as gce:
                log.critical('greenroom connect error: %s' % gce, exc_info=True)
                self.is_green_connected = False
                self.reconnect(greenroom=True)  #
                if config.DEBUG_MODE:
                    traceback.print_exc()
            finally:
                self.__green_callback()  #

    def disconnect(self, greenroom=False):
        """ Closes the RTMP connection with the remote server. """
        log.debug('disconnecting from server.')
        try:
            if greenroom:
                log.debug('disconnecting from greenroom')
                self.is_green_connected = False
                self.green_connection.shutdown()
            else:
                self.is_connected = False
                self._bauth_key = None
                self.users.clear()
                self.connection.shutdown()
        except Exception as e:
            log.error('disconnect error: %s' % e, exc_info=True)
            if config.DEBUG_MODE:
                traceback.print_exc()

    def reconnect(self, greenroom=False):
        """ Reconnect to the room. """
        if greenroom:
            self.disconnect(greenroom=True)
            time.sleep(config.RECONNECT_DELAY)
            self.__connect_green()  #
        else:
            reconnect_msg = '============ RECONNECTING IN %s SECONDS ============' % self._reconnect_delay
            log.info('reconnecting: %s' % reconnect_msg)
            self.console_write(COLOR['bright_cyan'], reconnect_msg)
            self._is_reconnected = True
            self.disconnect()
            time.sleep(self._reconnect_delay)

            # increase reconnect_delay after each reconnect.
            self._reconnect_delay *= 2
            if self._reconnect_delay > 900:
                self._reconnect_delay = config.RECONNECT_DELAY

            if self.account and self.password:
                if not self.login():
                    self.console_write(COLOR['bright_red'], 'Failed to login.')
                else:
                    self.console_write(COLOR['bright_green'], 'Login okay.')
            status = self.get_rtmp_parameters()
            if status is 3:
                self.connect()
            else:
                msg = 'failed to fetch rtmp parameters, status: %s' % status
                log.error(msg)
                if config.DEBUG_MODE:
                    self.console_write(COLOR['bright_red'], msg)

    def __green_callback(self):
        log.info('starting greenroom callback. is_green_connected: %s' % self.is_green_connected)
        fails = 0
        amf0_data = None
        while self.is_green_connected:
            try:
                amf0_data = self.green_connection.reader.next()
            except Exception as e:
                fails += 1
                log.error('greenroom amf data read error: %s %s' % (fails, e), exc_info=True)
                if fails == 2:
                    if config.DEBUG_MODE:
                        traceback.print_exc()
                    self.reconnect(greenroom=True)  #
                    break
            else:
                fails = 0
            try:
                handled = self.green_connection.handle_packet(amf0_data)
                if handled:
                    msg = 'handled greenroom packet: %s' % amf0_data
                    log.debug(msg)
                    if config.DEBUG_MODE:
                        self.console_write(COLOR['white'], msg)
                    continue

                amf0_cmd = amf0_data['command']
                cmd = amf0_cmd[0]

                if cmd == '_result':
                    self.on_result(amf0_cmd, greenroom=True)

                elif cmd == '_error':
                    self.on_error(amf0_cmd, greenroom=True)

                elif cmd == 'notice':
                    notice_msg = amf0_cmd[3]
                    notice_msg_id = amf0_cmd[4]
                    if notice_msg == 'avon':
                        avon_name = amf0_cmd[5]
                        self.on_avon(notice_msg_id, avon_name, greenroom=True)
                else:
                    if config.DEBUG_MODE:
                        self.console_write(COLOR['white'], 'ignoring greenroom command: %s' % cmd)

            except Exception as gce:
                log.error('general greenroom callback error: %s' % gce, exc_info=True)
                if config.DEBUG_MODE:
                    traceback.print_exc()
                self.reconnect(greenroom=True)  #

    def __callback(self):
        """ Callback loop reading RTMP messages from the RTMP stream. """
        log.info('starting callback loop. is_connected: %s' % self.is_connected)
        failures = 0
        amf0_data_type = -1
        amf0_data = None
        while self.is_connected:
            try:
                amf0_data = self.connection.reader.next()
                if amf0_data is not None:
                    amf0_data_type = amf0_data['msg']
            except Exception as e:
                failures += 1
                log.error('amf data read error count: %s %s' % (failures, e), exc_info=True)
                if failures == 2:
                    if config.DEBUG_MODE:
                        traceback.print_exc()
                    self.reconnect()
                    break
            else:
                failures = 0
            try:
                handled = self.connection.handle_packet(amf0_data)
                if handled:
                    msg = 'Handled packet of type: %s Packet data: %s' % (amf0_data_type, amf0_data)
                    log.info(msg)
                    if config.DEBUG_MODE:
                        self.console_write(COLOR['white'], msg)
                    continue

                create_stream_res = self.connection.is_create_stream_response(amf0_data)
                if create_stream_res:
                    msg = 'create stream response, stream_id: %s' % self.connection.stream_id
                    log.info(msg)
                    self.connection.publish(self._client_id)
                    if config.DEBUG_MODE:
                        self.console_write(COLOR['white'], msg)
                    continue

                amf0_cmd = amf0_data['command']
                cmd = amf0_cmd[0]
                iparam0 = 0

                if cmd == '_result':
                    self.on_result(amf0_cmd)

                elif cmd == '_error':
                    self.on_error(amf0_cmd)

                elif cmd == 'onBWDone':
                    self.on_bwdone()

                elif cmd == 'onStatus':
                    self.on_status(amf0_cmd)

                elif cmd == 'registered':
                    client_info_dict = amf0_cmd[3]
                    self.on_registered(client_info_dict)

                elif cmd == 'join':
                    usr_join_info_dict = amf0_cmd[3]
                    threading.Thread(target=self.on_join, args=(usr_join_info_dict,)).start()

                elif cmd == 'joins':
                    current_room_users_info_list = amf0_cmd[3:]
                    if len(current_room_users_info_list) is not 0:
                        while iparam0 < len(current_room_users_info_list):
                            self.on_joins(current_room_users_info_list[iparam0])
                            iparam0 += 1

                elif cmd == 'joinsdone':
                    self.on_joinsdone()

                elif cmd == 'oper':
                    oper_id_name = amf0_cmd[3:]
                    while iparam0 < len(oper_id_name):
                        oper_id = str(int(oper_id_name[iparam0]))
                        oper_name = oper_id_name[iparam0 + 1]
                        if len(oper_id) == 1:
                            self.on_oper(oper_id[0], oper_name)
                        iparam0 += 2

                elif cmd == 'deop':
                    deop_id = amf0_cmd[3]
                    deop_nick = amf0_cmd[4]
                    self.on_deop(deop_id, deop_nick)

                elif cmd == 'owner':
                    self.on_owner()

                elif cmd == 'avons':
                    avons_id_name = amf0_cmd[4:]
                    if len(avons_id_name) is not 0:
                        while iparam0 < len(avons_id_name):
                            avons_id = avons_id_name[iparam0]
                            avons_name = avons_id_name[iparam0 + 1]
                            self.on_avon(avons_id, avons_name)
                            iparam0 += 2

                elif cmd == 'pros':
                    pro_ids = amf0_cmd[4:]
                    if len(pro_ids) is not 0:
                        for pro_id in pro_ids:
                            pro_id = str(int(pro_id))
                            self.on_pro(pro_id)

                elif cmd == 'nick':
                    old_nick = amf0_cmd[3]
                    new_nick = amf0_cmd[4]
                    nick_id = int(amf0_cmd[5])
                    self.on_nick(old_nick, new_nick, nick_id)

                elif cmd == 'nickinuse':
                    self.on_nickinuse()

                elif cmd == 'quit':
                    quit_name = amf0_cmd[3]
                    quit_id = amf0_cmd[4]
                    self.on_quit(quit_id, quit_name)

                elif cmd == 'kick':
                    kick_id = amf0_cmd[3]
                    kick_name = amf0_cmd[4]
                    self.on_kick(kick_id, kick_name)

                elif cmd == 'banned':
                    self.on_banned()

                elif cmd == 'banlist':
                    banlist_id_nick = amf0_cmd[3:]
                    if len(banlist_id_nick) is not 0:
                        while iparam0 < len(banlist_id_nick):
                            banned_id = banlist_id_nick[iparam0]
                            banned_nick = banlist_id_nick[iparam0 + 1]
                            self.on_banlist(banned_id, banned_nick)
                            iparam0 += 2

                elif cmd == 'startbanlist':
                    # print(amf0_data)
                    pass

                elif cmd == 'topic':
                    topic = amf0_cmd[3]
                    self.on_topic(topic)

                elif cmd == 'from_owner':
                    owner_msg = amf0_cmd[3]
                    self.on_from_owner(owner_msg)

                elif cmd == 'doublesignon':
                    self.on_doublesignon()

                elif cmd == 'privmsg':
                    raw_msg = amf0_cmd[4]
                    msg_color = amf0_cmd[5]
                    msg_sender = amf0_cmd[6]
                    self.on_privmsg(msg_sender, raw_msg, msg_color)

                elif cmd == 'notice':
                    notice_msg = amf0_cmd[3]
                    notice_msg_id = amf0_cmd[4]
                    if notice_msg == 'avon':
                        avon_name = amf0_cmd[5]
                        self.on_avon(notice_msg_id, avon_name)
                    elif notice_msg == 'pro':
                        self.on_pro(notice_msg_id)

                elif cmd == 'gift':
                    gift_to = amf0_cmd[3]
                    gift_sender = amf0_data[4]
                    gift_info = amf0_data[5]
                    self.on_gift(gift_sender, gift_to, gift_info)

                else:
                    self.console_write(COLOR['bright_red'], 'Unknown command: %s' % cmd)

            except Exception as ex:
                log.error('general callback error: %s' % ex, exc_info=True)
                if config.DEBUG_MODE:
                    traceback.print_exc()

    # Callback Event Methods.
    def on_result(self, result_info, greenroom=False):
        if config.DEBUG_MODE:
            if greenroom:
                self.console_write(COLOR['white'], '## Greenroom result..')
            for list_item in result_info:
                if type(list_item) is rtmp.pyamf.ASObject:
                    for k in list_item:
                        self.console_write(COLOR['white'], k + ': ' + str(list_item[k]))
                else:
                    self.console_write(COLOR['white'], str(list_item))

    def on_error(self, error_info, greenroom=False):
        if config.DEBUG_MODE:
            if greenroom:
                self.console_write(COLOR['bright_red'], '## Greenroom error..')
            for list_item in error_info:
                if type(list_item) is rtmp.pyamf.ASObject:
                    for k in list_item:
                        self.console_write(COLOR['bright_red'], k + ': ' + str(list_item[k]))
                else:
                    self.console_write(COLOR['bright_red'], str(list_item))

    def on_status(self, status_info):
        if config.DEBUG_MODE:
            for list_item in status_info:
                if type(list_item) is rtmp.pyamf.ASObject:
                    for k in list_item:
                        self.console_write(COLOR['white'], k + ': ' + str(list_item[k]))
                else:
                    self.console_write(COLOR['white'], str(list_item))

    def on_bwdone(self):
        if not self._is_reconnected:
            if config.ENABLE_AUTO_JOB:
                self.start_auto_job_timer()

    def on_registered(self, client_info):
        self._client_id = client_info['id']
        self._is_client_mod = client_info['mod']
        self._is_client_owner = client_info['own']
        self.users.add(client_info)

        self.console_write(COLOR['bright_green'], 'registered with ID: %d' % self._client_id)

        key = core.get_captcha_key(self.roomname, str(self._client_id), proxy=self._proxy)
        if key is None:
            self.console_write(COLOR['bright_red'],
                               'There was a problem obtaining the captcha key. Key=%s' % str(key))
        else:
            self.console_write(COLOR['bright_green'], 'Captcha key: %s' % key)
            self.send_cauth_msg(key)
            self.set_nick()

    def on_join(self, join_info_dict):
        _user = self.users.add(join_info_dict)
        if _user is not None:
            if _user.account:
                tc_info = core.tinychat_user_info(_user.account)
                if tc_info is not None:
                    _user.tinychat_id = tc_info['tinychat_id']
                    _user.last_login = tc_info['last_active']
                if _user.is_owner:
                    _user.user_level = 1
                    self.console_write(COLOR['red'], 'Room Owner %s:%d:%s' %
                                       (_user.nick, _user.id, _user.account))
                elif _user.is_mod:
                    _user.user_level = 3
                    self.console_write(COLOR['bright_red'], 'Moderator %s:%d:%s' %
                                       (_user.nick, _user.id, _user.account))
                else:
                    _user.user_level = 5
                    self.console_write(COLOR['bright_yellow'], '%s:%d has account: %s' %
                                       (_user.nick, _user.id, _user.account))
            else:
                _user.user_level = 5
                if _user.id is not self._client_id:
                    self.console_write(COLOR['cyan'], '%s:%d joined the room.' % (_user.nick, _user.id))
        else:
            log.warning('user join: %s' % _user)

    def on_joins(self, joins_info_dict):
        _user = self.users.add(joins_info_dict)
        if _user is not None:
            if _user.account:
                if _user.is_owner:
                    _user.user_level = 1
                    self.console_write(COLOR['red'], 'Joins Room Owner %s:%d:%s' %
                                       (_user.nick, _user.id, _user.account))
                elif _user.is_mod:
                    _user.user_level = 3
                    self.console_write(COLOR['bright_red'], 'Joins Moderator %s:%d:%s' %
                                       (_user.nick, _user.id, _user.account))
                else:
                    _user.user_level = 5
                    self.console_write(COLOR['bright_yellow'], 'Joins %s:%d:%s' %
                                       (_user.nick, _user.id, _user.account))
            else:
                if joins_info_dict['id'] is not self._client_id:
                    _user.user_level = 5
                    self.console_write(COLOR['bright_cyan'], 'Joins %s:%d' % (_user.nick, _user.id))
        else:
            log.warning('user joins: %s' % _user)

    def on_joinsdone(self):
        if self._is_client_mod:
            self.send_banlist_msg()

    def on_oper(self, uid, nick):
        _user = self.users.search(nick)
        _user.is_mod = True
        if uid != self._client_id:
            self.console_write(COLOR['bright_red'], '%s:%s is moderator.' % (nick, uid))

    def on_deop(self, uid, nick):
        _user = self.users.search(nick)
        _user.is_mod = False
        self.console_write(COLOR['red'], '%s:%s was deoped.' % (nick, uid))

    def on_owner(self):
        pass

    def on_avon(self, uid, name, greenroom=False):
        if greenroom:
            _user = self.users.search_by_id(name)
            if _user is not None:
                _user.is_waiting = True
                self.console_write(COLOR['bright_yellow'], '%s:%s is waiting in the greenroom' %
                                   (_user.nick, _user.id))
        else:
            _user = self.users.search(name)
            if _user is not None and _user.is_waiting:
                _user.is_waiting = False
            self.console_write(COLOR['cyan'], '%s:%s is broadcasting.' % (name, uid))

    def on_pro(self, uid):
        _user = self.users.search_by_id(uid)
        if _user is not None:
            self.console_write(COLOR['bright_magenta'], '%s:%s is pro.' % (_user.nick, uid))
        else:
            self.console_write(COLOR['bright_magenta'], '%s is pro.' % uid)

    def on_nick(self, old, new, uid):
        if uid == self._client_id:
            self.nickname = new
        old_info = self.users.search(old)
        old_info.nick = new
        if not self.users.change(old, new, old_info):
            log.error('failed to change nick for user: %s' % new)
        self.console_write(COLOR['bright_cyan'], '%s:%s changed nick to: %s' % (old, uid, new))

    def on_nickinuse(self):
        self.nickname += string_util.create_random_string(1, 5)
        self.console_write(COLOR['white'], 'Nick already taken. Changing nick to: %s' % self.nickname)
        self.set_nick()

    def on_quit(self, uid, name):
        if self.users.delete(name):
            self.console_write(COLOR['cyan'], '%s:%s left the room.' % (name, uid))
        else:
            msg = 'failed to delete user: %s' % name
            if config.DEBUG_MODE:
                self.console_write(COLOR['bright_red'], msg)
            log.debug(msg)

    def on_kick(self, uid, name):
        self.console_write(COLOR['bright_red'], '%s:%s was banned.' % (name, uid))
        self.send_banlist_msg()

    def on_banned(self):
        self.console_write(COLOR['red'], 'You are banned from this room.')

    def on_banlist(self, uid, nick):
        self.console_write(COLOR['bright_red'], 'Banned user: %s:%s' % (nick, uid))

    def on_topic(self, topic):
        topic_msg = topic.encode('utf-8', 'replace')
        self.console_write(COLOR['cyan'], 'room topic: ' + topic_msg)

    def on_from_owner(self, owner_msg):
        msg = str(owner_msg).replace('notice', '')
        msg = core.web.unquote(msg.encode('utf-8'))
        self.console_write(COLOR['bright_red'], msg)

    def on_doublesignon(self):
        self.console_write(COLOR['bright_red'], 'Double account sign on. Aborting!')
        self.is_connected = False

    def on_reported(self, nick, uid):
        self.console_write(COLOR['bright_red'], 'You were reported by: %s:%s' % (nick, uid))

    def on_privmsg(self, msg_sender, raw_msg, msg_color):
        """
        Message command controller
        :param msg_sender: str the sender of the message.
        :param raw_msg: str the unencoded message.
        :param msg_color: str the chat message color.
        """

        # Get user info object of the user sending the message..
        self.active_user = self.users.search(msg_sender)

        # decode the message from comma separated decimal to normal text
        decoded_msg = self._decode_msg(u'' + raw_msg)

        if decoded_msg.startswith('/'):
            msg_cmd = decoded_msg.split(' ')
            if msg_cmd[0] == '/msg':
                private_msg = ' '.join(msg_cmd[2:])
                self.private_message_handler(private_msg.strip())

            elif msg_cmd[0] == '/reported':
                self.on_reported(self.active_user.nick, self.active_user.id)

            elif msg_cmd[0] == '/mbs':
                if self.active_user.is_mod:
                    if len(msg_cmd) is 4:
                        media_type = msg_cmd[1]
                        media_id = msg_cmd[2]
                        threading.Thread(target=self.on_media_broadcast_start,
                                         args=(media_type, media_id, msg_sender,)).start()

            elif msg_cmd[0] == '/mbc':
                if self.active_user.is_mod:
                    if len(msg_cmd) is 2:
                        media_type = msg_cmd[1]
                        self.on_media_broadcast_close(media_type, msg_sender)

            elif msg_cmd[0] == '/mbpa':
                if self.active_user.is_mod:
                    if len(msg_cmd) is 2:
                        media_type = msg_cmd[1]
                        self.on_media_broadcast_paused(media_type, msg_sender)

            elif msg_cmd[0] == '/mbpl':
                if self.active_user.is_mod:
                    if len(msg_cmd) is 3:
                        media_type = msg_cmd[1]
                        time_point = int(msg_cmd[2])
                        self.on_media_broadcast_play(media_type, time_point, msg_sender)

            elif msg_cmd[0] == '/mbsk':
                if self.active_user.is_mod:
                    if len(msg_cmd) is 3:
                        media_type = msg_cmd[1]
                        time_point = int(msg_cmd[2])
                        self.on_media_broadcast_skip(media_type, time_point, msg_sender)
        else:
            if len(msg_color) is 10:
                self.message_handler(decoded_msg.strip())
            else:
                log.warning('rejecting chat msg from: %s:%s with unusual msg color: %s' %
                            (self.active_user.nick, self.active_user.id, msg_color))

    def on_gift(self, gift_sender, gift_reciever, gift_info):  # DEV
        sender_nick = gift_sender['name']
        reciever_nick = gift_reciever['name']
        reciever_gp = int(gift_reciever['points'])
        gift_name = gift_info['name']
        gift_comment = gift_info['comment']

        self.console_write(COLOR['bright_magenta'], '%s sent gift %s to %s points: %s, comment: %s' %
                           (sender_nick, gift_name, reciever_nick, reciever_gp, gift_comment))

    # Message Handler.
    def message_handler(self, decoded_msg):
        """
        Message handler.
        :param decoded_msg: str the decoded msg(text).
        """
        self.console_write(COLOR['green'], '%s: %s ' % (self.active_user.nick, decoded_msg))

    # Private message Handler.
    def private_message_handler(self, private_msg):
        """
        A user private message us.
        :param private_msg: str the private message.
        """
        self.console_write(COLOR['white'], 'Private message from %s: %s' % (self.active_user.nick, private_msg))

    # Media Events.
    def on_media_broadcast_start(self, media_type, video_id, usr_nick):
        """
        A user started a media broadcast.
        :param media_type: str the type of media. youTube or soundCloud.
        :param video_id: str the youtube ID or soundcloud trackID.
        :param usr_nick: str the user name of the user playing media.
        """
        self.console_write(COLOR['bright_magenta'], '%s is playing %s %s' % (usr_nick, media_type, video_id))

    def on_media_broadcast_close(self, media_type, usr_nick):
        """
        A user closed a media broadcast.
        :param media_type: str the type of media. youTube or soundCloud.
        :param usr_nick: str the user name of the user closing the media.
        """
        self.console_write(COLOR['bright_magenta'], '%s closed the %s' % (usr_nick, media_type))

    def on_media_broadcast_paused(self, media_type, usr_nick):
        """
        A user paused the media broadcast.
        :param media_type: str the type of media being paused. youTube or soundCloud.
        :param usr_nick: str the user name of the user pausing the media.
        """
        self.console_write(COLOR['bright_magenta'], '%s paused the %s' % (usr_nick, media_type))

    def on_media_broadcast_play(self, media_type, time_point, usr_nick):
        """
        A user resumed playing a media broadcast.
        :param media_type: str the media type. youTube or soundCloud.
        :param time_point: int the time point in the tune in milliseconds.
        :param usr_nick: str the user resuming the tune.
        """
        self.console_write(COLOR['bright_magenta'], '%s resumed the %s at: %s' %
                           (usr_nick, media_type, time_point))

    def on_media_broadcast_skip(self, media_type, time_point, usr_nick):
        """
        A user time searched a tune.
        :param media_type: str the media type. youTube or soundCloud.
        :param time_point: int the time point in the tune in milliseconds.
        :param usr_nick: str the user time searching the tune.
        """
        self.console_write(COLOR['bright_magenta'], '%s time searched the %s at: %s ' %
                           (usr_nick, media_type, time_point))

    # Message Methods.
    def send_bauth_msg(self):
        """ Get and send the bauth key needed before we can start a broadcast. """
        if self._bauth_key is not None:
            self._send_command('bauth', [u'' + self._bauth_key])
        else:
            _token = core.get_bauth_token(self.roomname, self.nickname, self._client_id,
                                          self.rtmp_parameter['greenroom'], proxy=self._proxy)
            if _token != 'PW':
                self._bauth_key = _token
                self._send_command('bauth', [u'' + _token])

    def send_cauth_msg(self, cauthkey):
        """
        Send the cauth message with a working cauth key, we need to send this before we can chat.
        :param cauthkey: str a working cauth key.
        """
        self._send_command('cauth', [u'' + cauthkey])

    def send_owner_run_msg(self, msg):
        """
        Send owner run message.
        :param msg: the message str to send.
        """
        if self._is_client_mod:
            msg = core.web.quote(msg, safe=':,/&+?#=@')
            self._send_command('owner_run', [u'notice' + msg])

    def send_cam_approve_msg(self, nick, uid=None):
        """
        Send cam approval message.
        NOTE: if no uid is provided, we try and look up the user by nick.
        :param nick: str the nick to be approved.
        :param uid: (optional) the user id.
        """
        if self._is_client_mod and self._b_password is not None:
            msg = '/allowbroadcast %s' % self._b_password
            if uid is None:
                _user = self.users.search(nick)
                if _user is not None:
                    self._send_command('privmsg', [u'' + self._encode_msg(msg), u'#0,en',
                                                   u'n' + str(_user.uid) + '-' + nick])
            else:
                self._send_command('privmsg',
                                   [u'' + self._encode_msg(msg), u'#0,en', u'n' + str(uid) + '-' + nick])

    def send_chat_msg(self, msg):
        """
        Send a chat room message.
        :param msg: str the message to send.
        """
        self._send_command('privmsg', [u'' + self._encode_msg(msg), u'#262626,en'])

    def send_private_msg(self, msg, nick):
        """
        Send a private message.
        :param msg: str the private message to send.
        :param nick: str the user name to receive the message.
        """
        _user = self.users.search(nick)
        if _user is not None:
            self._send_command('privmsg', [u'' + self._encode_msg('/msg ' + nick + ' ' + msg),
                                           u'#262626,en', u'n' + str(_user.id) + '-' + nick])
            self._send_command('privmsg', [u'' + self._encode_msg('/msg ' + nick + ' ' + msg),
                                           u'#262626,en', u'b' + str(_user.id) + '-' + nick])

    def send_userinfo_request_msg(self, user_id):
        """
        Send user info request to a user.
        :param user_id: str user id of the user we want info from.
        """
        self._send_command('account', [u'' + str(user_id)])

    def send_undercover_msg(self, nick, msg, use_b=True, use_n=True):
        """
        Send a 'undercover' message.
        This is a special message that appears in the main chat, but is only visible to the user it is sent to.
        It can also be used to play 'private' youtube/soundcloud with.

        :param nick: str the user name to send the message to.
        :param msg: str the message to send.
        :param use_b:
        :param use_n:
        """
        _user = self.users.search(nick)
        if _user is not None:
            if use_b:
                self._send_command('privmsg', [u'' + self._encode_msg(msg),
                                               '#0,en', u'b' + str(_user.id) + '-' + nick])
            if use_n:
                self._send_command('privmsg', [u'' + self._encode_msg(msg),
                                               '#0,en', u'n' + str(_user.id) + '-' + nick])

    def set_nick(self):
        """ Send the nick message. """
        if not self.nickname:
            self.nickname = string_util.create_random_string(5, 25)
        self.console_write(COLOR['bright_magenta'], 'Setting nick: %s' % self.nickname)
        self._send_command('nick', [u'' + self.nickname])

    def send_ban_msg(self, nick, uid=None):
        if self._is_client_mod:
            if uid is None:
                _user = self.users.search(nick)
                if _user is not None:
                    self._send_command('kick', [u'' + nick, str(_user.id)])
            else:
                self._send_command('kick', [u'' + nick, str(uid)])

    def send_forgive_msg(self, uid):
        """
        Send forgive message.
        :param uid: The ID of the user we want to forgive.
        """
        if self._is_client_mod:
            self._send_command('forgive', [u'' + str(uid)])
            # get the updated ban list.
            self.send_banlist_msg()

    def send_banlist_msg(self):
        """ Send ban list message. """
        if self._is_client_mod:
            self._send_command('banlist')

    def send_topic_msg(self, topic):
        """
        Send a room topic message.
        :param topic: str the room topic.
        """
        if self._is_client_mod:
            self._send_command('topic', [u'' + topic])

    def send_close_user_msg(self, nick):
        """
        Send close user broadcast message.
        :param nick: str the user name of the user we want to close.
        """
        if self._is_client_mod:
            self._send_command('owner_run', [u'_close' + nick])

    # Media Message Functions
    def send_media_broadcast_start(self, media_type, video_id, time_point=0, private_nick=None):
        """
        Starts a media broadcast.
        :param media_type: str 'youTube' or 'soundCloud'
        :param video_id: str the media video ID.
        :param time_point: int where to start the media from in milliseconds.
        :param private_nick: str if not None, start the media broadcast for this username only.
        """
        mbs_msg = '/mbs %s %s %s' % (media_type, video_id, time_point)
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbs_msg)
        else:
            self.send_chat_msg(mbs_msg)

    def send_media_broadcast_close(self, media_type, private_nick=None):
        """
        Close a media broadcast.
        :param media_type: str 'youTube' or 'soundCloud'
        :param private_nick str if not None, send this message to this username only.
        """
        mbc_msg = '/mbc %s' % media_type
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbc_msg)
        else:
            self.send_chat_msg(mbc_msg)

    def send_media_broadcast_play(self, media_type, time_point, private_nick=None):
        """
        Play a currently paused media broadcast.
        :param media_type: str 'youTube' or 'soundCloud'
        :param time_point: int where to play the media from in milliseconds.
        :param private_nick: str if not None, send this message to this username only.
        """
        mbpl_msg = '/mbpl %s %s' % (media_type, time_point)
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbpl_msg)
        else:
            self.send_chat_msg(mbpl_msg)

    def send_media_broadcast_pause(self, media_type, private_nick=None):
        """
        Pause a currently playing media broadcast.
        :param media_type: str 'youTube' or 'soundCloud'
        :param private_nick: str if not None, send this message to this username only.
        """
        mbpa_msg = '/mbpa %s' % media_type
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbpa_msg)
        else:
            self.send_chat_msg(mbpa_msg)

    def send_media_broadcast_skip(self, media_type, time_point, private_nick=None):
        """
        Time search a currently playing/paused media broadcast.
        :param media_type: str 'youTube' or 'soundCloud'
        :param time_point: int the time point to skip to.
        :param private_nick: str if not None, send this message to this username only.
        :return:
        """
        mbsk_msg = '/mbsk %s %s' % (media_type, time_point)
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbsk_msg)
        else:
            self.send_chat_msg(mbsk_msg)

    # Message Construction.
    def _send_command(self, cmd, params=None, trans_id=0):
        """
        Sends command messages to the server.

        NOTE: Im not sure what kind of effect the trans ID has,
        or if it indeed is the transaction ID.

        :param cmd: str command name.
        :param params: list command parameters.
        :param trans_id: int the trans action ID.
        """
        msg_format = [u'' + cmd, trans_id, None]
        if params and type(params) is list:
            msg_format.extend(params)
        msg = {
            'msg': rtmp.rtmp_type.DT_COMMAND,
            'command': msg_format
        }
        try:
            self.connection.writer.write(msg)
            self.connection.writer.flush()
        except Exception as ex:
            log.error('send command error: %s' % ex, exc_info=True)
            if config.DEBUG_MODE:
                traceback.print_exc()
            self.reconnect()

    # Helper Methods
    def get_runtime(self, milliseconds=True):
        """
        Get the time the connection has been alive.
        :param milliseconds: bool True return the time as milliseconds, False return seconds.
        :return: int milliseconds or seconds.
        """
        up = int(time.time() - self._init_time)
        if milliseconds:
            return up * 1000
        return up

    @staticmethod
    def _decode_msg(msg):
        """
        Decode str from comma separated decimal to normal text str.
        :param msg: str the encoded message.
        :return: str normal text.
        """
        chars = msg.split(',')
        msg = ''
        for i in chars:
            try:
                msg += unichr(int(i))
            except ValueError as ve:
                log.error('%s' % ve, exc_info=True)
        return msg

    @staticmethod
    def _encode_msg(msg):
        """
        Encode normal text str to comma separated decimal.
        :param msg: str the normal text to encode
        :return: comma separated decimal str.
        """
        return ','.join(str(ord(char)) for char in msg)

    # Timed Auto Method.
    def auto_job_handler(self):
        """ The event handler for auto_job_timer. """
        if self.is_connected:
            conf = core.get_roomconfig_xml(self.roomname, self.room_pass, proxy=self._proxy)
            if conf is not None:
                if self._is_client_mod:
                    self.rtmp_parameter['greenroom'] = conf['greenroom']
                    self._b_password = conf['bpassword']
                    if conf['greenroom'] and not self.is_green_connected:
                        # if the greenroom has been enabled after we joined the room.
                        threading.Thread(target=self.__connect_green).start()
                    elif not conf['greenroom'] and self.is_green_connected:
                        # no need to keep the greenroom connection open
                        # if it is not enabled anymore.
                        self.disconnect(greenroom=True)
            log.debug('recv configuration: %s' % conf)
        self.start_auto_job_timer()

    def start_auto_job_timer(self):
        """
        Just like using tinychat with a browser, this method will
        fetch the room config from tinychat API every 5 minute(300 seconds)(default).
        See line 228 at http://tinychat.com/embed/chat.js
        """
        threading.Timer(config.AUTO_JOB_INTERVAL, self.auto_job_handler).start()
