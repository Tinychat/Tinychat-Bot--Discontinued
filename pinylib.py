# -*- coding: utf-8 -*-
import logging
import threading
import time
import traceback
from colorama import init, Fore, Style
import config
import user
import apis.tinychat
from rtmplib import rtmp
from page import acc, params
from util import string_util, file_handler

__version__ = '7.0.0'

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

CONFIG = config
init(autoreset=True)
log = logging.getLogger(__name__)


def write_to_log(msg, room_name):
    """ Writes chat events to log.

    :param msg: the message to write to the log.
    :type msg: str
    :param room_name: the room name.
    :type room_name: str
    """
    d = time.strftime('%Y-%m-%d')
    file_name = d + '.log'
    path = config.CONFIG_PATH + room_name + '/logs/'
    file_handler.file_writer(path, file_name, msg.encode(encoding='UTF-8', errors='ignore'))


class TinychatRTMPClient(object):
    """
    Tinychat client responsible for managing the connection and the different
    events that may occur in the chat room.
    """
    def __init__(self, roomname, nick='', account='', password='', room_pass=None, proxy=None):
        """ Create a instance of the TinychatRTMPClient class.

        :param roomname: The room name to connect to.(required)
        :type roomname: str
        :param nick: The nick name to use in the chat room.(optional)
        :type nick: str
        :param account: Tinychat account name.(optional)
        :type account: str
        :param password: The password for the tinychat account.(optional)
        :type password: str
        :param room_pass: The password for the room.(optional)
        :type room_pass: str | None
        :param proxy: A proxy in the format IP:PORT for the connection to the remote server,
        but also for doing the various web requests related to establishing a connection.(optional)
        :type proxy: str | None
        """
        self.roomname = roomname
        self.nickname = nick
        self.account = account
        self.password = password
        self.room_pass = room_pass
        self.is_client_mod = False
        self.is_client_owner = False
        self.connection = None
        self.green_connection = None
        self.is_connected = False
        self.is_green_connected = False
        self.users = user.Users()
        self.active_user = None
        self.param = None
        self._proxy = proxy
        self._client_id = None
        self._bauth_key = None
        self._is_reconnected = False
        self._reconnect_delay = config.RECONNECT_DELAY
        self._init_time = time.time()

    def console_write(self, color, message):
        """ Writes message to console.

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

    def set_rtmp_parameters(self):
        """ Set the RTMP parameters before making a connect. """
        self.param = params.Params(room_name=self.roomname, room_pass=self.room_pass,
                                   swf_version=config.SWF_VERSION, proxy=self._proxy)
        self.param.get_config()
        if self.param.config_status == 3:
            if config.DEBUG_MODE:
                for k in self.param.config_dict:
                    self.console_write(COLOR['white'], '%s: %s' % (k, self.param.config_dict[k]))
                if self.account:
                    self.console_write(COLOR['white'], 'Account: %s' % self.account)
        return self.param.config_status

    def login(self):
        """ Login to tinychat.

        :return: True if logged in, else False.
        :rtype: bool
        """
        account = acc.Account(account=self.account, password=self.password, proxy=self._proxy)
        if self.account and self.password:
            if account.is_logged_in():
                return True
            account.login()
        return account.is_logged_in()

    def connect(self):
        """ Make a connection with the remote RTMP server. """
        if not self.is_connected:
            log.info('connecting to: %s' % self.roomname)
            try:
                self.param.recaptcha()
                self.connection = rtmp.RtmpClient(
                    ip=self.param.ip,
                    port=self.param.port,
                    tc_url=self.param.tc_url,
                    app=self.param.app,
                    page_url=self.param.embed_url,
                    swf_url=self.param.swf_url,
                    proxy=self._proxy,
                    is_win=True
                )
                self.connection.connect(
                    {
                        'account': self.account,
                        'type': self.param.roomtype,
                        'prefix': u'tinychat',
                        'room': self.roomname,
                        'version': self.param.desktop_version,
                        'cookie': self.param.cauth_cookie()
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
                if self.param.is_greenroom and not self.is_green_connected:
                    threading.Thread(target=self.__connect_green).start()
                self.__callback()

    def __connect_green(self):
        """ Make a connection to the greenroom application. """
        if not self.is_green_connected:
            try:
                self.green_connection = rtmp.RtmpClient(
                    ip=self.param.ip,
                    port=self.param.port,
                    tc_url=self.param.tc_url,
                    app=self.param.app,
                    page_url=self.param.embed_url,
                    swf_url=self.param.swf_url,
                    proxy=self._proxy,
                    is_win=True
                )
                self.green_connection.connect(
                    {
                        'account': '',
                        'type': self.param.roomtype,
                        'prefix': u'greenroom',
                        'room': self.roomname,
                        'version': self.param.desktop_version,
                        'cookie': ''
                    }
                )
                self.is_green_connected = True
            except Exception as e:
                log.critical('greenroom connect error: %s' % e, exc_info=True)
                self.is_green_connected = False
                self.reconnect(greenroom=True)
                if config.DEBUG_MODE:
                    traceback.print_exc()
            finally:
                self.__green_callback()

    def disconnect(self, greenroom=False):
        """ Close the connection with the remote RTMP server.

        :param greenroom: True closes the greenroom connection,
        else close the normal connection.
        :type greenroom: bool
        """
        log.info('disconnecting from server.')
        try:
            if greenroom:
                log.info('disconnection from greenroom application')
                self.is_green_connected = False
                self.green_connection.shutdown()
            else:
                self.is_connected = False
                self._bauth_key = None
                self.users.clear()
                self.connection.shutdown()
        except Exception as e:
            log.error('disconnect error, greenroom: %s, error: %s' % (greenroom, e), exc_info=True)
            if config.DEBUG_MODE:
                traceback.print_exc()

    def reconnect(self, greenroom=False):
        """ Reconnect to the application.

        :param greenroom: True reconnect to the greenroom application else
        reconnect to the normal application(room)
        :type greenroom: bool
        """
        if greenroom:
            log.info('reconnecting to the greenroom application.')
            self.disconnect(greenroom=True)
            time.sleep(config.RECONNECT_DELAY)
            self.__connect_green()
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
            self.set_rtmp_parameters()
            if self.param.config_status == 3:
                self.connect()
            else:
                msg = 'failed to set rtmp parameters, %s' % self.param.config_status
                log.error(msg)
                if config.DEBUG_MODE:
                    self.console_write(COLOR['bright_red'], msg)

    def __green_callback(self):
        """ Read packets from the greenroom RTMP application. """
        log.info('starting greenroom callback loop. is_green_connected: %s' % self.is_green_connected)
        fails = 0
        amf0_data_type = - 1
        amf0_data = None
        while self.is_green_connected:
            try:
                amf0_data = self.green_connection.amf()
                amf0_data_type = amf0_data['msg']
            except rtmp.AmfDataReadError as e:
                fails += 1
                log.error('greenroom amf read error: %s %s' % (fails, e), exc_info=True)
                if fails == 2:
                    if config.DEBUG_MODE:
                        traceback.print_exc()
                    self.reconnect(greenroom=True)
                    break
            else:
                fails = 0
            try:
                if amf0_data_type == rtmp.rtmp_type.DT_COMMAND:

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

            except Exception as gge:
                log.error('general greenroom callback error: %s' % gge, exc_info=True)
                if config.DEBUG_MODE:
                    traceback.print_exc()
                self.reconnect(greenroom=True)

    def __callback(self):
        """ Read packets from the RTMP application. """
        log.info('starting callback loop. is_connected: %s' % self.is_connected)
        fails = 0
        amf0_data_type = -1
        amf0_data = None
        while self.is_connected:
            try:
                amf0_data = self.connection.amf()
                amf0_data_type = amf0_data['msg']
            except rtmp.AmfDataReadError as e:
                fails += 1
                log.error('amf data read error count: %s %s' % (fails, e), exc_info=True)
                if fails == 2:
                    if config.DEBUG_MODE:
                        traceback.print_exc()
                    self.reconnect()
                    break
            else:
                fails = 0
            try:
                if amf0_data_type == rtmp.rtmp_type.DT_COMMAND:

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
                        join_info = amf0_cmd[3]
                        threading.Thread(target=self.on_join, args=(join_info,)).start()

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

                    # elif cmd == 'owner':
                    #     self.on_owner()

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
        """ Default NetConnection message containing info about the connection.

        :param result_info: Info containing various information.
        :type result_info: dict
        :param greenroom: True if the info is from the greenroom connection.
        :type greenroom: bool
        """
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
        """ Default NetConnection message containing error info about the connection.

        :param error_info: Info containing various error information.
        :type error_info: dict
        :param greenroom: True if the error info is from the greenroom connection.
        :type greenroom: bool
        """
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
        """ Default NetStream status updates message.

        :param status_info: Info containing various information related to a NetStream
        :type status_info: dict
        """
        if config.DEBUG_MODE:
            for list_item in status_info:
                if type(list_item) is rtmp.pyamf.ASObject:
                    for k in list_item:
                        self.console_write(COLOR['white'], k + ': ' + str(list_item[k]))
                else:
                    self.console_write(COLOR['white'], str(list_item))

    def on_bwdone(self):
        """ Application specific message. """
        if not self._is_reconnected:
            if config.ENABLE_AUTO_JOB:
                self.start_auto_job_timer()

    def on_registered(self, client_info):
        """ Application message containing client info.

        :param client_info: Info containing client information.
        :type client_info: dict
        """
        self._client_id = client_info['id']
        self.is_client_mod = client_info['mod']
        self.is_client_owner = client_info['own']
        client = self.users.add(client_info)
        client.user_level = 0

        self.console_write(COLOR['bright_green'], 'registered with ID: %d' % self._client_id)

        key = self.param.get_captcha_key(self._client_id)
        if key is None:
            self.console_write(COLOR['bright_red'],
                               'There was a problem obtaining the captcha key. Key=%s' % str(key))
        else:
            self.console_write(COLOR['bright_green'], 'Captcha key: %s' % key)
            self.send_cauth_msg(key)
            self.set_nick()

    def on_join(self, join_info):
        """ Application message received when a user joins the room.

        :param join_info: Information about the user joining.
        :type join_info: dict
        """
        _user = self.users.add(join_info)
        if _user is not None:
            if _user.account:
                tc_info = apis.tinychat.user_info(_user.account)
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
                    self.console_write(COLOR['bright_yellow'], '%s:%d has account: %s' %
                                       (_user.nick, _user.id, _user.account))
            else:
                if _user.id is not self._client_id:
                    self.console_write(COLOR['cyan'], '%s:%d joined the room.' % (_user.nick, _user.id))
        else:
            log.warning('user join: %s' % _user)

    def on_joins(self, joins_info):
        """ Application message received for every user in the room when the client joins the room.

        :param joins_info: Information about a user.
        :type joins_info: dict
        """
        _user = self.users.add(joins_info)
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
                    self.console_write(COLOR['bright_yellow'], 'Joins %s:%d:%s' %
                                       (_user.nick, _user.id, _user.account))
            else:
                if joins_info['id'] is not self._client_id:
                    self.console_write(COLOR['bright_cyan'], 'Joins %s:%d' % (_user.nick, _user.id))
        else:
            log.warning('user joins: %s' % _user)

    def on_joinsdone(self):
        """ Application message received when all room users information have been received. """
        if self.is_client_mod:
            self.send_banlist_msg()

    def on_oper(self, uid, nick):
        """ Application message received when a user is oper(moderator)

        NOTE: This message is most likely deprecated.
        :param uid: str the Id of the oper.
        :param nick: str the nick of the user
        """
        _user = self.users.search(nick)
        _user.is_mod = True
        if uid != self._client_id:
            self.console_write(COLOR['bright_red'], '%s:%s is moderator.' % (nick, uid))

    def on_deop(self, uid, nick):
        """ Application message received when a moderator is de-moderated(deop)

        NOTE: This message is most likely deprecated.
        :param uid: str the Id of the moderator.
        :param nick: str the nick of the moderator.
        """
        _user = self.users.search(nick)
        _user.is_mod = False
        self.console_write(COLOR['red'], '%s:%s was deoped.' % (nick, uid))

    def on_avon(self, uid, name, greenroom=False):
        """ Application message received when a user starts broadcasting.

        :param uid: The Id of the user.
        :type uid: str
        :param name: The nick name of the user.
        :type name: str
        :param greenroom: True the user is waiting in the greenroom.
        :type greenroom: bool
        """
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
        """ Application message received when a user is using a PRO account.

        :param uid: The Id of the pro user.
        :type uid: str
        """
        _user = self.users.search_by_id(uid)
        if _user is not None:
            self.console_write(COLOR['bright_magenta'], '%s:%s is pro.' % (_user.nick, uid))
        else:
            self.console_write(COLOR['bright_magenta'], '%s is pro.' % uid)

    def on_nick(self, old, new, uid):
        """ Application message received when a user changes nick name.

        :param old: The old nick name of the user.
        :type old: str
        :param new: The new nick name of the user
        :type new: str
        :param uid: The Id of the user.
        :type uid: int
        """
        if uid == self._client_id:
            self.nickname = new
        old_info = self.users.search(old)
        old_info.nick = new
        if not self.users.change(old, new, old_info):
            log.error('failed to change nick for user: %s' % new)
        self.console_write(COLOR['bright_cyan'], '%s:%s changed nick to: %s' % (old, uid, new))

    def on_nickinuse(self):
        """ Application message received when the client nick name chosen is already in use."""
        self.nickname += string_util.create_random_string(1, 5)
        self.console_write(COLOR['white'], 'Nick already taken. Changing nick to: %s' % self.nickname)
        self.set_nick()

    def on_quit(self, uid, name):
        """ Application message received when a user leaves the room.

        :param uid: The Id of the user leaving.
        :type uid: str
        :param name: The nick name of the user leaving.
        :type name: str
        """
        log.debug('%s:%s left the room' % (name, uid))
        if self.users.delete(name):
            self.console_write(COLOR['cyan'], '%s:%s left the room.' % (name, uid))
        else:
            msg = 'failed to delete user: %s' % name
            if config.DEBUG_MODE:
                self.console_write(COLOR['bright_red'], msg)
            log.debug(msg)

    def on_kick(self, uid, name):
        """ Application message received when a user gets banned.

        :param uid: The Id of the user getting banned.
        :type uid: str
        :param name: The nick name of the user getting banned.
        :type name: str
        """
        self.console_write(COLOR['bright_red'], '%s:%s was banned.' % (name, uid))
        self.send_banlist_msg()

    def on_banned(self):
        """ Application message received when the client is banned from a room. """
        self.console_write(COLOR['red'], 'You are banned from this room.')

    def on_banlist(self, uid, nick):
        """ Application message containing a user currently on the banlist.

        :param uid: Id of the banned user.
        :type uid: str
        :param nick: nick name of the banned user.
        :type nick: str
        """
        self.console_write(COLOR['bright_red'], 'Banned user: %s:%s' % (nick, uid))

    def on_topic(self, topic):
        """ Application message containing the rooms topic(if any)

        :param topic: The topic of the room.
        :type topic: str
        """
        topic_msg = topic.encode('utf-8', 'replace')
        self.console_write(COLOR['cyan'], 'room topic: ' + topic_msg)

    def on_from_owner(self, owner_msg):
        """ Application message received when a user's broadcast gets closed by a moderator.

        NOTE: There are other types of this message kind..
        :param owner_msg: url encoded string.
        :type owner_msg: str
        """
        msg = str(owner_msg).replace('notice', '')
        msg = string_util.unquote(msg.encode('utf-8'))
        self.console_write(COLOR['bright_red'], msg)

    def on_doublesignon(self):
        """ Application message received when the client account is already in the room. """
        self.console_write(COLOR['bright_red'], 'Double account sign on. Aborting!')
        self.is_connected = False

    def on_reported(self, nick, uid):
        """ Application message received when the client gets reported by another user in the room.

        :param nick: The nick name of the user reporting the client.
        :type nick: str
        :param uid: The Id of the user reporting the client.
        :type uid: str
        """
        self.console_write(COLOR['bright_red'], 'You were reported by: %s:%s' % (nick, uid))

    def on_gift(self, gift_sender, gift_receiver, gift_info):
        """ Application message received when a user sends another user a gift.

        NOTE: This is not fully tested/discovered
        :param gift_sender: The gift senders information.
        :type gift_sender: dict
        :param gift_receiver: The gift receiver information.
        :type gift_receiver: dict
        :param gift_info: The gift information.
        :type gift_info: dict
        """
        sender_nick = gift_sender['name']
        receiver_nick = gift_receiver['name']
        receiver_gp = int(gift_receiver['points'])
        gift_name = gift_info['name']
        gift_comment = gift_info['comment']

        self.console_write(COLOR['bright_magenta'], '%s sent gift %s to %s points: %s, comment: %s' %
                           (sender_nick, gift_name, receiver_nick, receiver_gp, gift_comment))

    def on_privmsg(self, msg_sender, raw_msg, msg_color):
        """ Application message received when a user sends a chat message among other.

        Several commands are sent through this type of message, this method
        sorts the different commands out, and sends them of to the correct event handlers(methods).

        :param msg_sender: The nick name of the message sender.
        :type msg_sender: str
        :param raw_msg: The message as comma seperated decimals.
        :type raw_msg: str
        :param msg_color: The chat message color.
        :type msg_color: str
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
                    if len(msg_cmd) == 4:
                        media_type = msg_cmd[1]
                        media_id = msg_cmd[2]
                        threading.Thread(target=self.on_media_broadcast_start,
                                         args=(media_type, media_id, msg_sender,)).start()

            elif msg_cmd[0] == '/mbc':
                if self.active_user.is_mod:
                    if len(msg_cmd) == 2:
                        media_type = msg_cmd[1]
                        self.on_media_broadcast_close(media_type, msg_sender)

            elif msg_cmd[0] == '/mbpa':
                if self.active_user.is_mod:
                    if len(msg_cmd) == 2:
                        media_type = msg_cmd[1]
                        self.on_media_broadcast_paused(media_type, msg_sender)

            elif msg_cmd[0] == '/mbpl':
                if self.active_user.is_mod:
                    if len(msg_cmd) == 3:
                        media_type = msg_cmd[1]
                        time_point = int(msg_cmd[2])
                        self.on_media_broadcast_play(media_type, time_point, msg_sender)

            elif msg_cmd[0] == '/mbsk':
                if self.active_user.is_mod:
                    if len(msg_cmd) == 3:
                        media_type = msg_cmd[1]
                        time_point = int(msg_cmd[2])
                        self.on_media_broadcast_skip(media_type, time_point, msg_sender)
        else:
            if len(msg_color) == 10:
                self.message_handler(decoded_msg.strip())
            else:
                log.warning('rejecting chat msg from: %s:%s with unusual msg color: %s' %
                            (self.active_user.nick, self.active_user.id, msg_color))

    # Message Handler.
    def message_handler(self, decoded_msg):
        """ Message handler.

        :param decoded_msg: The decoded msg(text).
        :type decoded_msg: str
        """
        self.console_write(COLOR['green'], '%s: %s ' % (self.active_user.nick, decoded_msg))

    # Private Message Handler.
    def private_message_handler(self, private_msg):
        """ A user private message the client.

        :param private_msg: The private message.
        :type private_msg: str
        """
        self.console_write(COLOR['white'], 'Private message from %s: %s' % (self.active_user.nick, private_msg))

    # Media Events Handlers.
    def on_media_broadcast_start(self, media_type, video_id, usr_nick):
        """ A user started a media broadcast.

        :param media_type: The type of media. youTube or soundCloud.
        :type media_type: str
        :param video_id: The youtube ID or souncloud trackID.
        :type video_id: str
        :param usr_nick: The user name of the user playing media.
        :type usr_nick: str
        """
        self.console_write(COLOR['bright_magenta'], '%s is playing %s %s' % (usr_nick, media_type, video_id))

    def on_media_broadcast_close(self, media_type, usr_nick):
        """ A user closed a media broadcast.

        :param media_type: The type of media. youTube or soundCloud.
        :type media_type: str
        :param usr_nick: The user name of the user closing the media.
        :type usr_nick: str
        """
        self.console_write(COLOR['bright_magenta'], '%s closed the %s' % (usr_nick, media_type))

    def on_media_broadcast_paused(self, media_type, usr_nick):
        """ A user paused the media broadcast.

        :param media_type: The type of media being paused. youTube or soundCloud.
        :type media_type: str
        :param usr_nick: The user name of the user pausing the media.
        :type usr_nick: str
        """
        self.console_write(COLOR['bright_magenta'], '%s paused the %s' % (usr_nick, media_type))

    def on_media_broadcast_play(self, media_type, time_point, usr_nick):
        """ A user resumed playing a media broadcast.

        :param media_type: The media type. youTube or soundCloud.
        :type media_type: str
        :param time_point: The time point in the tune in milliseconds.
        :type time_point: int
        :param usr_nick: The user resuming the tune.
        :type usr_nick: str
        """
        self.console_write(COLOR['bright_magenta'], '%s resumed the %s at: %s' %
                           (usr_nick, media_type, time_point))

    def on_media_broadcast_skip(self, media_type, time_point, usr_nick):
        """ A user time searched a tune.

        :param media_type: The media type. youTube or soundCloud.
        :type media_type: str
        :param time_point: The time point in the tune in milliseconds.
        :type time_point: int
        :param usr_nick: The user time searching the tune.
        :type usr_nick: str
        """
        self.console_write(COLOR['bright_magenta'], '%s time searched the %s at: %s ' %
                           (usr_nick, media_type, time_point))

    # Message Methods.
    def send_bauth_msg(self):
        """ Get and send the bauth key needed before we can start a broadcast. """
        if self._bauth_key is not None:
            self.connection.call('bauth', [u'' + self._bauth_key])
        else:
            _token = self.param.get_broadcast_token(self.nickname, self._client_id)
            if _token != 'PW':
                self._bauth_key = _token
                self.connection.call('bauth', [u'' + _token])

    def send_cauth_msg(self, cauthkey):
        """ Send the cauth message, we need to send this before we can chat.

        :param cauthkey: The cauth key.
        :type cauthkey: str
        """
        self.connection.call('cauth', [u'' + cauthkey])

    def send_owner_run_msg(self, msg):
        """ Send owner run message.

        :param msg: The message to send.
        :type msg: str
        """
        if self.is_client_mod:
            msg = string_util.quote_str(msg)
            self.connection.call('owner_run', [u'notice' + msg])

    def send_cam_approve_msg(self, nick, uid=None):
        """ Send cam approval message.

        NOTE: if no uid is provided, we try and look up the user by nick.
        :param nick: The nick to be approved.
        :type nick: str
        :param uid: (optional) The user id.
        :type uid: int | str
        """
        if self.is_client_mod and self.param.bpassword is not None:
            msg = '/allowbroadcast %s' % self.param.bpassword
            if uid is None:
                _user = self.users.search(nick)
                if _user is not None:
                    self.connection.call('privmsg', [u'' + self._encode_msg(msg), u'#0,en',
                                                     u'n' + str(_user.id) + '-' + nick])
            else:
                self.connection.call('privmsg',
                                     [u'' + self._encode_msg(msg), u'#0,en', u'n' + str(uid) + '-' + nick])

    def send_chat_msg(self, msg):
        """  Send a chat room message.

        :param msg: The message to send.
        :type msg: str
        """
        self.connection.call('privmsg', [u'' + self._encode_msg(msg), u'#262626,en'])

    def send_private_msg(self, msg, nick):
        """ Send a private message.

        :param msg: The private message to send.
        :type msg: str
        :param nick: The user name to receive the message.
        :type nick: str
        """
        _user = self.users.search(nick)
        if _user is not None:
            self.connection.call('privmsg', [u'' + self._encode_msg('/msg ' + nick + ' ' + msg),
                                             u'#262626,en', u'n' + str(_user.id) + '-' + nick])
            self.connection.call('privmsg', [u'' + self._encode_msg('/msg ' + nick + ' ' + msg),
                                             u'#262626,en', u'b' + str(_user.id) + '-' + nick])

    def send_userinfo_request_msg(self, user_id):
        """ Send user info request to a user.

        :param user_id: User id of the user we want info from.
        :type user_id: str
        """
        self.connection.call('account', [u'' + str(user_id)])

    def send_undercover_msg(self, nick, msg, use_b=True, use_n=True):
        """ Send a 'undercover' message.

        This is a special message that appears in the main chat, but is only visible to the user it is sent to.
        It can also be used to play 'private' youtubes/soundclouds with.

        :param nick: The user name to send the message to.
        :type nick: str
        :param msg: The message to send.
        :type msg: str
        :param use_b:
        :param use_n:
        """
        _user = self.users.search(nick)
        if _user is not None:
            if use_b:
                self.connection.call('privmsg', [u'' + self._encode_msg(msg),
                                                 '#0,en', u'b' + str(_user.id) + '-' + nick])
            if use_n:
                self.connection.call('privmsg', [u'' + self._encode_msg(msg),
                                                 '#0,en', u'n' + str(_user.id) + '-' + nick])

    def set_nick(self):
        """ Send the nick message. """
        if not self.nickname:
            self.nickname = string_util.create_random_string(5, 25)
        self.console_write(COLOR['bright_magenta'], 'Setting nick: %s' % self.nickname)
        self.connection.call('nick', [u'' + self.nickname])

    def send_ban_msg(self, nick, uid=None):
        """ Send ban message.

        :param nick: The nick name of the user to ban.
        :type nick: str
        :param uid: The Id of the user to ban (optional)
        :type uid: int | str
        """
        if self.is_client_mod:
            if uid is None:
                _user = self.users.search(nick)
                if _user is not None:
                    self.connection.call('kick', [u'' + nick, str(_user.id)])
            else:
                self.connection.call('kick', [u'' + nick, str(uid)])

    def send_forgive_msg(self, uid):
        """ Send forgive message.

        :param uid: The ID of the user we want to forgive.
        :type uid: int | str
        """
        if self.is_client_mod:
            self.connection.call('forgive', [u'' + str(uid)])
            # get the updated ban list.
            self.send_banlist_msg()

    def send_banlist_msg(self):
        """ Send ban list message. """
        if self.is_client_mod:
            self.connection.call('banlist')

    def send_topic_msg(self, topic):
        """ Send a room topic message.

        :param topic: The room topic.
        :type topic: str
        """
        if self.is_client_mod:
            self.connection.call('topic', [u'' + topic])

    def send_close_user_msg(self, nick):
        """ Send close user broadcast message.

        :param nick: The user name of the user we want to close.
        :type nick: str
        """
        if self.is_client_mod:
            self.connection.call('owner_run', [u'_close' + nick])

    # Media Message Functions
    def send_media_broadcast_start(self, media_type, video_id, time_point=0, private_nick=None):
        """ Starts a media broadcast.

        :param media_type: 'youTube' or 'soundCloud'
        :type media_type: str
        :param video_id: The media video ID.
        :type video_id: str
        :param time_point: Where to start the media from in milliseconds.
        :type time_point: int
        :param private_nick: If not None, start the media broadcast for this username only.
        :type private_nick: str
        """
        mbs_msg = '/mbs %s %s %s' % (media_type, video_id, time_point)
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbs_msg)
        else:
            self.send_chat_msg(mbs_msg)

    def send_media_broadcast_close(self, media_type, private_nick=None):
        """ Close a media broadcast.

        :param media_type: 'youTube' or 'soundCloud'
        :type media_type: str
        :param private_nick If not None, send this message to this username only.
        :type private_nick: str
        """
        mbc_msg = '/mbc %s' % media_type
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbc_msg)
        else:
            self.send_chat_msg(mbc_msg)

    def send_media_broadcast_play(self, media_type, time_point, private_nick=None):
        """ Play a currently paused media broadcast.

        :param media_type: 'youTube' or 'soundCloud'
        :type media_type: str
        :param time_point: Where to play the media from in milliseconds.
        :type time_point: int
        :param private_nick: If not None, send this message to this username only.
        :type private_nick: str
        """
        mbpl_msg = '/mbpl %s %s' % (media_type, time_point)
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbpl_msg)
        else:
            self.send_chat_msg(mbpl_msg)

    def send_media_broadcast_pause(self, media_type, private_nick=None):
        """ Pause a currently playing media broadcast.

        :param media_type: 'youTube' or 'soundCloud'
        :type media_type: str
        :param private_nick: If not None, send this message to this username only.
        :type private_nick: str
        """
        mbpa_msg = '/mbpa %s' % media_type
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbpa_msg)
        else:
            self.send_chat_msg(mbpa_msg)

    def send_media_broadcast_skip(self, media_type, time_point, private_nick=None):
        """ Time search a currently playing/paused media broadcast.

        :param media_type: 'youTube' or 'soundCloud'
        :type media_type: str
        :param time_point: The time point to skip to.
        :type time_point: int
        :param private_nick: if not None, send this message to this username only.
        :type private_nick: str
        """
        mbsk_msg = '/mbsk %s %s' % (media_type, time_point)
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbsk_msg)
        else:
            self.send_chat_msg(mbsk_msg)

    # Helper Methods
    def get_runtime(self, milliseconds=True):
        """ Get the time the connection has been alive.

        :param milliseconds: True return the time as milliseconds, False return seconds.
        :type milliseconds: bool
        :return: Milliseconds or seconds.
        :rtype: int
        """
        up = int(time.time() - self._init_time)
        if milliseconds:
            return up * 1000
        return up

    @staticmethod
    def _decode_msg(msg):
        """ Decode str from comma separated decimal to normal text str.

        :param msg: The encoded message.
        :return: A normal text.
        :rtype: str
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
        """ Encode normal text str to comma separated decimal.

        :param msg: The normal text to encode
        :type msg: str
        :return: Comma separated decimal string.
        :rtype: str
        """
        return ','.join(str(ord(char)) for char in msg)

    # Timed Auto Method.
    def auto_job_handler(self):
        """ The event handler for auto_job_timer. """
        if self.is_connected:
            self.param.get_config()
            if self.param.config_status is 3:
                if self.is_client_mod:
                    if self.param.is_greenroom and not self.is_green_connected:
                        # if the greenroom has been enabled after we joined the room.
                        threading.Thread(target=self.__connect_green).start()
                    elif not self.param.is_greenroom and self.is_green_connected:
                        # no need to keep the greenroom connection open
                        # if it is not enabled anymore.
                        self.disconnect(greenroom=True)
            log.debug('recv configuration: %s' % self.param.config_dict)
        self.start_auto_job_timer()

    def start_auto_job_timer(self):
        """
        Just like using tinychat with a browser, this method will
        fetch the room config from tinychat API every 5 minute(300 seconds)(default).
        See line 228 at http://tinychat.com/embed/chat.js
        """
        threading.Timer(config.AUTO_JOB_INTERVAL, self.auto_job_handler).start()
