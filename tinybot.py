# -*- coding: utf-8 -*-
import logging
import re
import threading
import pinylib
import apis
from util import media_manager, privacy_settings

__all__ = ['pinylib']

log = logging.getLogger(__name__)
__version__ = '6.1.2'


class TinychatBot(pinylib.TinychatRTMPClient):
    privacy_settings = None
    media_manager = media_manager.MediaManager()
    media_timer_thread = None
    search_list = []
    is_search_list_youtube_playlist = False

    def on_join(self, join_info_dict):
        log.info('user join info: %s' % join_info_dict)
        _user = self.users.add(join_info_dict)
        if _user is not None:
            if _user.account:
                tc_info = pinylib.core.tinychat_user_info(_user.account)
                if tc_info is not None:
                    _user.tinychat_id = tc_info
                    _user.last_login = tc_info['last_active']
                if _user.is_owner:
                    _user.user_level = 1
                    self.console_write(pinylib.COLOR['red'], 'Room Owner %s:%d:%s' %
                                       (_user.nick, _user.id, _user.account))
                elif _user.is_mod:
                    _user.user_level = 3
                    self.console_write(pinylib.COLOR['bright_red'], 'Moderator %s:%d:%s' %
                                       (_user.nick, _user.id, _user.account))
                else:
                    _user.user_level = 5
                    self.console_write(pinylib.COLOR['bright_yellow'], '%s:%d has account: %s' %
                                       (_user.nick, _user.id, _user.account))

                    if _user.account in pinylib.CONFIG.B_ACCOUNT_BANS:
                        if self._is_client_mod:
                            self.send_ban_msg(_user.nick, _user.id)
                            if pinylib.CONFIG.B_FORGIVE_AUTO_BANS:
                                self.send_forgive_msg(_user.id)
                            self.send_bot_msg('*Auto-Banned:* (bad account)')

            else:
                _user.user_level = 5
                if _user.id is not self._client_id:
                    if _user.lf and not pinylib.CONFIG.B_ALLOW_LURKERS and self._is_client_mod:
                        self.send_ban_msg(_user.nick, _user.id)
                        if pinylib.CONFIG.B_FORGIVE_AUTO_BANS:
                            self.send_forgive_msg(_user.id)
                        self.send_bot_msg('*Auto-Banned:* (lurkers not allowed)')
                    elif not pinylib.CONFIG.B_ALLOW_GUESTS and self._is_client_mod:
                        self.send_ban_msg(_user.nick, _user.id)
                        if pinylib.CONFIG.B_FORGIVE_AUTO_BANS:
                            self.send_forgive_msg(_user.id)
                        self.send_bot_msg('*Auto-Banned:* (guests not allowed)')
                    else:
                        self.console_write(pinylib.COLOR['cyan'], '%s:%d joined the room.' % (_user.nick, _user.id))

    def on_joinsdone(self):
        if self._is_client_mod:
            self.send_banlist_msg()
            self.load_list(nicks=True, accounts=True, strings=True)
        if self._is_client_owner and self.rtmp_parameter['roomtype'] != 'default':
            threading.Thread(target=self.get_privacy_settings).start()

    def on_avon(self, uid, name, greenroom=False):
        if greenroom:
            _user = self.users.search_by_id(name)
            if _user is not None:
                _user.is_waiting = True
                self.send_bot_msg('%s:%s *is waiting in the greenroom.*' % (_user.nick, _user.id))
        else:
            _user = self.users.search(name)
            if _user is not None and _user.is_waiting:
                _user.is_waiting = False
            if not pinylib.CONFIG.B_ALLOW_BROADCASTS and self._is_client_mod:
                self.send_close_user_msg(name)
                self.console_write(pinylib.COLOR['cyan'], 'Auto closed broadcast %s:%s' % (name, uid))
            else:
                self.console_write(pinylib.COLOR['cyan'], '%s:%s is broadcasting.' % (name, uid))

    def on_nick(self, old, new, uid):
        if uid == self._client_id:
            self.nickname = new
        old_info = self.users.search(old)
        old_info.nick = new
        if not self.users.change(old, new, old_info):
            log.error('failed to change nick for user: %s' % new)
        if self.check_nick(old, old_info):
            if pinylib.CONFIG.B_FORGIVE_AUTO_BANS:
                self.send_forgive_msg(uid)
        elif uid != self._client_id:
            if self._is_client_mod and pinylib.CONFIG.B_GREET:
                if old_info.account:
                    self.send_bot_msg('*Welcome* %s:%s:%s' % (new, uid, old_info.account))
                else:
                    self.send_bot_msg('*Welcome* %s:%s' % (new, uid))
            if self.media_manager.has_active_track():
                if not self.media_manager.is_mod_playing:
                    self.send_media_broadcast_start(self.media_manager.track().type,
                                                    self.media_manager.track().id,
                                                    time_point=self.media_manager.elapsed_track_time(),
                                                    private_nick=new)

        self.console_write(pinylib.COLOR['bright_cyan'], '%s:%s changed nick to: %s' % (old, uid, new))

    # Media Events.
    def on_media_broadcast_start(self, media_type, video_id, usr_nick):
        """
        A user started a media broadcast.
        :param media_type: str the type of media. youTube or soundCloud.
        :param video_id: str the youtube ID or soundcloud track ID.
        :param usr_nick: str the user name of the user playing media.
        """
        self.cancel_media_event_timer()

        if media_type == 'youTube':
            _youtube = apis.youtube.video_details(video_id, check=False)
            if _youtube is not None:
                self.media_manager.mb_start(self.active_user.nick, _youtube)

        elif media_type == 'soundCloud':
            _soundcloud = apis.soundcloud.track_info(video_id)
            if _soundcloud is not None:
                self.media_manager.mb_start(self.active_user.nick, _soundcloud)

        self.media_event_timer(self.media_manager.track().time)
        self.console_write(pinylib.COLOR['bright_magenta'], '%s is playing %s %s' %
                           (usr_nick, media_type, video_id))

    def on_media_broadcast_close(self, media_type, usr_nick):
        """
        A user closed a media broadcast.
        :param media_type: str the type of media. youTube or soundCloud.
        :param usr_nick: str the user name of the user closing the media.
        """
        self.cancel_media_event_timer()
        self.media_manager.mb_close()
        self.console_write(pinylib.COLOR['bright_magenta'], '%s closed the %s' % (usr_nick, media_type))

    def on_media_broadcast_paused(self, media_type, usr_nick):
        """
        A user paused the media broadcast.
        :param media_type: str the type of media being paused. youTube or soundCloud.
        :param usr_nick: str the user name of the user pausing the media.
        """
        self.cancel_media_event_timer()
        self.media_manager.mb_pause()
        self.console_write(pinylib.COLOR['bright_magenta'], '%s paused the %s' % (usr_nick, media_type))

    def on_media_broadcast_play(self, media_type, time_point, usr_nick):
        """
        A user resumed playing a media broadcast.
        :param media_type: str the media type. youTube or soundCloud.
        :param time_point: int the time point in the tune in milliseconds.
        :param usr_nick: str the user resuming the tune.
        """
        self.cancel_media_event_timer()
        new_media_time = self.media_manager.mb_play(time_point)
        self.media_event_timer(new_media_time)

        self.console_write(pinylib.COLOR['bright_magenta'], '%s resumed the %s at: %s' %
                           (usr_nick, media_type, self.format_time(time_point)))

    def on_media_broadcast_skip(self, media_type, time_point, usr_nick):
        """
        A user time searched a tune.
        :param media_type: str the media type. youTube or soundCloud.
        :param time_point: int the time point in the tune in milliseconds.
        :param usr_nick: str the user time searching the tune.
        """
        self.cancel_media_event_timer()
        new_media_time = self.media_manager.mb_skip(time_point)
        if not self.media_manager.is_paused:
            self.media_event_timer(new_media_time)

        self.console_write(pinylib.COLOR['bright_magenta'], '%s time searched the %s at: %s' %
                           (usr_nick, media_type, self.format_time(time_point)))

    # Media Message Method.
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

    # Message Method.
    def send_bot_msg(self, msg, use_chat_msg=False):
        """
        Send a chat message to the room.

        NOTE: If the client is moderator, send_owner_run_msg will be used.
        If the client is not a moderator, send_chat_msg will be used.
        Setting use_chat_msg to True, forces send_chat_msg to be used.
        :param msg: str the message to send.
        :param use_chat_msg: boolean True, use normal chat messages.
        False, send messages depending on weather or not the client is mod.
        """
        if use_chat_msg:
            self.send_chat_msg(msg)
        else:
            if self._is_client_mod:
                self.send_owner_run_msg(msg)
            else:
                self.send_chat_msg(msg)

    # Command Handler.
    def message_handler(self, decoded_msg):
        """
        Custom command handler.
        NOTE: Any method using a online API will be started in a new thread.
        :param decoded_msg: str the message
        """
        prefix = pinylib.CONFIG.B_PREFIX
        if decoded_msg.startswith(prefix):
            parts = decoded_msg.split(' ')
            cmd = parts[0].lower().strip()
            cmd_arg = ' '.join(parts[1:]).strip()
            # Always enabled to allow contact with the bot even when public commands are disabled.
            if self.has_level(5):
                if cmd == prefix + 'pmme':
                    self.do_pmme()
            # Public commands. (if enabled)
            if (pinylib.CONFIG.B_PUBLIC_CMD and self.has_level(5)) or self.active_user.user_level < 5:
                # Misc
                if cmd == prefix + 'fullscreen':
                    self.do_full_screen(cmd_arg)

                elif cmd == prefix + 'help':
                    self.do_help()

                elif cmd == prefix + 'uptime':
                    self.do_uptime()
                # Media
                elif cmd == prefix + 'who?':
                    self.do_who_plays()

                elif cmd == prefix + 'status':
                    self.do_playlist_status()

                elif cmd == prefix + 'next?':
                    self.do_next_tune_in_playlist()

                elif cmd == prefix + 'now?':
                    self.do_now_playing()

                elif cmd == prefix + 'play':
                    threading.Thread(target=self.do_play_youtube, args=(cmd_arg,)).start()

                elif cmd == prefix + 'playsc':
                    threading.Thread(target=self.do_play_soundcloud, args=(cmd_arg,)).start()

                # Tinychat API commands.
                elif cmd == prefix + 'spy':
                    threading.Thread(target=self.do_spy, args=(cmd_arg,)).start()

                elif cmd == prefix + 'spyuser':
                    threading.Thread(target=self.do_account_spy, args=(cmd_arg,)).start()

                # Other API commands.
                elif cmd == prefix + 'urban':
                    threading.Thread(target=self.do_search_urban_dictionary, args=(cmd_arg,)).start()

                elif cmd == prefix + 'weather':
                    threading.Thread(target=self.do_weather_search, args=(cmd_arg,)).start()

                elif cmd == prefix + 'ip':
                    threading.Thread(target=self.do_whois_ip, args=(cmd_arg,)).start()

                elif cmd == prefix + 'time':
                    threading.Thread(target=self.do_time, args=(cmd_arg,)).start()

                elif cmd == prefix + 'translate':
                    threading.Thread(target=self.do_translate, args=(cmd_arg,)).start()

                # Just for fun.
                elif cmd == prefix + 'chuck':
                    threading.Thread(target=self.do_chuck_norris).start()

                elif cmd == prefix + '8ball':
                    self.do_8ball(cmd_arg)

            # Print command to console.
            self.console_write(pinylib.COLOR['yellow'], self.active_user.nick + ': ' + cmd + ' ' + cmd_arg)
        else:
            #  Print chat message to console.
            self.console_write(pinylib.COLOR['green'], self.active_user.nick + ': ' + decoded_msg)
            # Only check chat msg for ban string if we are mod.
            if self._is_client_mod and self.active_user.user_level > 4:
                threading.Thread(target=self.check_msg, args=(decoded_msg,)).start()

        self.active_user.last_msg = decoded_msg

    def do_make_mod(self, account):
        """
        Make a tinychat account a room moderator.
        :param account str the account to make a moderator.
        """
        if self._is_client_owner:
            if len(account) is 0:
                self.send_private_msg('Missing account name.', self.active_user.nick)
            else:
                tc_user = self.privacy_settings.make_moderator(account)
                if tc_user is None:
                    self.send_private_msg('*The account is invalid.*', self.active_user.nick)
                elif not tc_user:
                    self.send_private_msg('*%s* is already a moderator.' % account, self.active_user.nick)
                elif tc_user:
                    self.send_private_msg('*%s* was made a room moderator.' % account, self.active_user.nick)

    def do_remove_mod(self, account):
        """
        Removes a tinychat account from the moderator list.
        :param account str the account to remove from the moderator list.
        """
        if self._is_client_owner:
            if len(account) is 0:
                self.send_private_msg('Missing account name.', self.active_user.nick)
            else:
                tc_user = self.privacy_settings.remove_moderator(account)
                if tc_user:
                    self.send_private_msg('*%s* is no longer a room moderator.' % account, self.active_user.nick)
                elif not tc_user:
                    self.send_private_msg('*%s* is not a room moderator.' % account, self.active_user.nick)

    def do_directory(self):
        """ Toggles if the room should be shown on the directory. """
        if self._is_client_owner:
            if self.privacy_settings.show_on_directory():
                self.send_private_msg('*Room IS shown on the directory.*', self.active_user.nick)
            else:
                self.send_private_msg('*Room is NOT shown on the directory.*', self.active_user.nick)

    def do_push2talk(self):
        """ Toggles if the room should be in push2talk mode. """
        if self._is_client_owner:
            if self.privacy_settings.set_push2talk():
                self.send_private_msg('*Push2Talk is enabled.*', self.active_user.nick)
            else:
                self.send_private_msg('*Push2Talk is disabled.*', self.active_user.nick)

    def do_green_room(self):
        """ Toggles if the room should be in greenroom mode. """
        if self._is_client_owner:
            if self.privacy_settings.set_greenroom():
                self.send_private_msg('*Green room is enabled.*', self.active_user.nick)
                self.rtmp_parameter['greenroom'] = True
            else:
                self.send_private_msg('*Green room is disabled.*', self.active_user.nick)
                self.rtmp_parameter['greenroom'] = False

    def do_clear_room_bans(self):
        """ Clear all room bans. """
        if self._is_client_owner:
            if self.privacy_settings.clear_bans():
                self.send_private_msg('*All room bans was cleared.*', self.active_user.nick)

    def do_kill(self):
        """ Kills the bot. """
        self.disconnect()

    def do_reboot(self):
        """ Reboots the bot. """
        self.reconnect()

    def do_media_info(self):
        """ Shows basic media info. """
        if self._is_client_mod:
            self.send_private_msg('*Playlist Length:* ' + str(len(self.media_manager.track_list)),
                                  self.active_user.nick)
            self.send_private_msg('*Track List Index:* ' + str(self.media_manager.track_list_index),
                                  self.active_user.nick)
            self.send_private_msg('*Elapsed Track Time:* ' + self.format_time(self.media_manager.elapsed_track_time()),
                                  self.active_user.nick)
            self.send_private_msg('*Active Track:* ' + str(self.media_manager.has_active_track()),
                                  self.active_user.nick)
            self.send_private_msg('*Active Threads:* ' + str(threading.active_count()), self.active_user.nick)

    def do_op_user(self, user_name):
        """
        Lets the room owner, a mod or a bot controller make another user a bot controller.
        :param user_name: str the user to op.
        """
        if self._is_client_mod:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.active_user.nick)
            else:
                _user = self.users.search(user_name)
                if _user is not None:
                    _user.user_level = 4
                    self.send_private_msg('*%s* is now a bot controller' % user_name, self.active_user.nick)
                    self.send_private_msg('You are now a bot controller (Level 4).', user_name)
                    self.send_private_msg('Commands https://github.com/Tinychat/Tinychat-Bot/wiki#level-4', user_name)
                else:
                    self.send_private_msg('No user named: %s' % user_name, self.active_user.nick)

    def do_deop_user(self, user_name):
        """
        Lets the room owner, a mod or a bot controller remove a user from being a bot controller.
        :param user_name: str the user to deop.
        """
        if self._is_client_mod:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.active_user.nick)
            else:
                _user = self.users.search(user_name)
                if _user is not None:
                    _user.user_level = 5
                    self.send_private_msg('*%s* was removed' % user_name,
                                          self.active_user.nick)
                    self.send_private_msg('You are no longer a bot controller.', user_name)
                else:
                    self.send_private_msg('No user named: %s' % user_name, self.active_user.nick)

    def do_cam_up(self):
        """ Makes the bot cam up. """
        self.send_bauth_msg()
        self.connection.createstream()

    def do_cam_down(self):
        """ Makes the bot cam down. """
        self.connection.close_stream()

    def do_nocam(self):
        """ Toggles if broadcasting is allowed or not. """
        pinylib.CONFIG.B_ALLOW_BROADCASTS = not pinylib.CONFIG.B_ALLOW_BROADCASTS
        self.send_private_msg('*Allow Broadcasts:* %s' % pinylib.CONFIG.B_ALLOW_BROADCASTS, self.active_user.nick)

    def do_guests(self):
        """ Toggles if guests are allowed to join the room or not. """
        pinylib.CONFIG.B_ALLOW_GUESTS = not pinylib.CONFIG.B_ALLOW_GUESTS
        self.send_private_msg('*Allow Guests:* %s' % pinylib.CONFIG.B_ALLOW_GUESTS, self.active_user.nick)

    def do_lurkers(self):
        """ Toggles if lurkers are allowed or not. """
        pinylib.CONFIG.B_ALLOW_LURKERS = not pinylib.CONFIG.B_ALLOW_LURKERS
        self.send_private_msg('*Allow Lurkers:* %s' % pinylib.CONFIG.B_ALLOW_LURKERS, self.active_user.nick)

    def do_guest_nicks(self):
        """ Toggles if guest nicks are allowed or not. """
        pinylib.CONFIG.B_ALLOW_GUESTS_NICKS = not pinylib.CONFIG.B_ALLOW_GUESTS_NICKS
        self.send_private_msg('*Allow Guest Nicks:* %s' % pinylib.CONFIG.B_ALLOW_GUESTS_NICKS, self.active_user.nick)

    def do_newusers(self):
        """ Toggles if newusers are allowed to join the room or not. """
        pinylib.CONFIG.B_ALLOW_NEWUSERS = not pinylib.CONFIG.B_ALLOW_NEWUSERS
        self.send_private_msg('*Allow Newusers:* %s' % pinylib.CONFIG.B_ALLOW_NEWUSERS, self.active_user.nick)

    def do_greet(self):
        """ Toggles if users should be greeted on entry. """
        pinylib.CONFIG.B_GREET = not pinylib.CONFIG.B_GREET
        self.send_private_msg('*Greet Users:* %s' % pinylib.CONFIG.B_GREET, self.active_user.nick)

    def do_public_cmds(self):
        """ Toggles if public commands are public or not. """
        pinylib.CONFIG.B_PUBLIC_CMD = not pinylib.CONFIG.B_PUBLIC_CMD
        self.send_private_msg('*Public Commands Enabled:* %s' % pinylib.CONFIG.B_PUBLIC_CMD, self.active_user.nick)

    def do_room_settings(self):
        """ Shows current room settings. """
        if self._is_client_owner:
            settings = self.privacy_settings.current_settings()
            self.send_private_msg('*Broadcast Password:* %s' % settings['broadcast_pass'], self.active_user.nick)
            self.send_private_msg('*Room Password:* %s' % settings['room_pass'], self.active_user.nick)
            self.send_private_msg('*Login Type:* %s' % settings['allow_guest'], self.active_user.nick)
            self.send_private_msg('*Directory:* %s' % settings['show_on_directory'], self.active_user.nick)
            self.send_private_msg('*Push2Talk:* %s' % settings['push2talk'], self.active_user.nick)
            self.send_private_msg('*Greenroom:* %s' % settings['greenroom'], self.active_user.nick)

    def do_lastfm_chart(self, chart_items):
        """
        Makes a playlist from the currently most played tunes on last.fm
        :param chart_items: int the amount of tunes we want.
        """
        if self._is_client_mod:
            if chart_items is 0 or chart_items is None:
                self.send_private_msg('Please specify the amount of tunes you want.', self.active_user.nick)
            else:
                try:
                    _items = int(chart_items)
                except ValueError:
                    self.send_private_msg('Only numbers allowed.', self.active_user.nick)
                else:
                    if 0 < _items < 30:
                        self.send_private_msg('Please wait while creating a playlist...', self.active_user.nick)
                        last = apis.lastfm.chart(_items)
                        if last is not None:
                            self.media_manager.add_track_list(self.active_user.nick, last)
                            self.send_private_msg('*Added:* ' + str(len(last)) + ' *tunes from last.fm chart.*',
                                                  self.active_user.nick)
                            if not self.media_manager.has_active_track():
                                track = self.media_manager.get_next_track()
                                self.send_media_broadcast_start(track.type, track.id)
                                self.media_event_timer(track.time)
                        else:
                            self.send_private_msg('Failed to retrieve a result from last.fm.', self.active_user.nick)
                    else:
                        self.send_private_msg('No more than 30 tunes.', self.active_user.nick)

    def do_lastfm_random_tunes(self, max_tunes):
        """
        Creates a playlist from what other people are listening to on last.fm.
        :param max_tunes: int the max amount of tunes.
        """
        if self._is_client_mod:
            if max_tunes is 0 or max_tunes is None:
                self.send_private_msg('Please specify the max amount of tunes you want.', self.active_user.nick)
            else:
                try:
                    _items = int(max_tunes)
                except ValueError:
                    self.send_private_msg('Only numbers allowed.', self.active_user.nick)
                else:
                    if 0 < _items < 50:
                        self.send_private_msg('Please wait while creating a playlist...', self.active_user.nick)
                        last = apis.lastfm.listening_now(max_tunes)
                        if last is not None:
                            self.media_manager.add_track_list(self.active_user.nick, last)
                            self.send_private_msg('*Added:* ' + str(len(last)) + ' *tunes from last.fm*',
                                                  self.active_user.nick)
                            if not self.media_manager.has_active_track():
                                track = self.media_manager.get_next_track()
                                self.send_media_broadcast_start(track.type, track.id)
                                self.media_event_timer(track.time)
                        else:
                            self.send_private_msg('Failed to retrieve a result from last.fm.', self.active_user.nick)
                    else:
                        self.send_private_msg('No more than 50 tunes.', self.active_user.nick)

    def do_search_lastfm_by_tag(self, search_str):
        """
        Searches last.fm for tunes matching the search term and creates a playlist from them.
        :param search_str: str the search term to search for.
        """
        if self._is_client_mod:
            if len(search_str) is 0:
                self.send_private_msg('Missing search tag.', self.active_user.nick)
            else:
                self.send_private_msg('Please wait while creating playlist..', self.active_user.nick)
                last = apis.lastfm.tag_search(search_str)
                if last is not None:
                    self.media_manager.add_track_list(self.active_user.nick, last)
                    self.send_private_msg('*Added:* ' + str(len(last)) + ' *tunes from last.fm*', self.active_user.nick)
                    if not self.media_manager.has_active_track():
                        track = self.media_manager.get_next_track()
                        self.send_media_broadcast_start(track.type, track.id)
                        self.media_event_timer(track.time)
                else:
                    self.send_private_msg('Failed to retrieve a result from last.fm.', self.active_user.nick)

    def do_youtube_playlist_search(self, search_term):
        """
        Searches youtube for a play list matching the search term.
        :param search_term: str the search to search for.
        """
        if self._is_client_mod:
            if len(search_term) is 0:
                self.send_bot_msg('Missing search term.')
            else:
                self.search_list = apis.youtube.playlist_search(search_term)
                if len(self.search_list) is not 0:
                    self.is_search_list_youtube_playlist = True
                    for i in range(0, len(self.search_list)):
                        self.send_owner_run_msg('(%s) *%s*' % (i, self.search_list[i]['playlist_title']))
                else:
                    self.send_bot_msg('Failed to find playlist matching search term: %s' % search_term)

    def do_play_youtube_playlist(self, int_choice):
        """
        Finds the videos from the youtube playlist search.
        :param int_choice: int the index of the play list on the search_list.
        """
        if self._is_client_mod:
            if self.is_search_list_youtube_playlist:
                try:
                    index_choice = int(int_choice)
                except ValueError:
                    self.send_bot_msg('Only numbers allowed.')
                else:
                    if 0 <= index_choice <= len(self.search_list) - 1:
                        self.send_bot_msg('Please wait while creating playlist..')
                        tracks = apis.youtube.playlist_videos(self.search_list[index_choice]['playlist_id'])
                        if len(tracks) is not 0:
                            self.media_manager.add_track_list(self.active_user.nick, tracks)
                            self.send_bot_msg('*Added:* %s *tracks from youtube playlist.*' % len(tracks))
                            if not self.media_manager.has_active_track():
                                track = self.media_manager.get_next_track()
                                self.send_media_broadcast_start(track.type, track.id)
                                self.media_event_timer(track.time)
                        else:
                            self.send_bot_msg('Failed to retrieve videos from youtube playlist.')
                    else:
                        self.send_bot_msg('Please make a choice between 0-%s' % str(len(self.search_list) - 1))
            else:
                self.send_bot_msg('The search list does not contain any youtube playlist id\'s.')

    def do_close_broadcast(self, user_name):
        """
        Close a user broadcasting.
        :param user_name: str the username to close.
        """
        if self._is_client_mod:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.active_user.nick)
            else:
                if self.users.search(user_name) is not None:
                    self.send_close_user_msg(user_name)
                else:
                    self.send_private_msg('No user named: ' + user_name, self.active_user.nick)

    def do_clear(self):
        """ Clears the chat box. """
        if self._is_client_mod:
            for x in range(0, 10):
                self.send_owner_run_msg(' ')
        else:
            clear = '133,133,133,133,133,133,133,133,133,133,133,133,133,133,133'
            self._send_command('privmsg', [clear, u'#262626,en'])

    def do_skip(self):
        """ Play the next item in the playlist. """
        if self._is_client_mod:
            if self.media_manager.is_last_track():
                self.send_private_msg('*This is the last tune in the playlist.*', self.active_user.nick)
            elif self.media_manager.is_last_track() is None:
                self.send_private_msg('*No tunes to skip. The playlist is empty.*', self.active_user.nick)
            else:
                self.cancel_media_event_timer()
                current_type = self.media_manager.track().type
                next_track = self.media_manager.get_next_track()
                if current_type != next_track.type:
                    self.send_media_broadcast_close(media_type=current_type)
                self.send_media_broadcast_start(next_track.type, next_track.id)
                self.media_event_timer(next_track.time)

    def do_delete_playlist_item(self, to_delete):
        """
        Delete item(s) from the playlist by index.
        :param to_delete: str index(es) to delete.
        """
        if self._is_client_mod:
            if len(self.media_manager.track_list) is 0:
                self.send_private_msg('The track list is empty.', self.active_user.nick)
            elif len(to_delete) is 0:
                self.send_private_msg('No indexes to delete provided.', self.active_user.nick)
            else:
                indexes = None
                by_range = False

                try:
                    if ':' in to_delete:
                        range_indexes = map(int, to_delete.split(':'))
                        temp_indexes = range(range_indexes[0], range_indexes[1] + 1)
                        if len(temp_indexes) > 1:
                            by_range = True
                    else:
                        temp_indexes = map(int, to_delete.split(','))
                except ValueError as ve:
                    log.error('wrong format: %s' % ve)
                    # self.send_undercover_msg(self.user.nick, 'Wrong format.(ValueError)')
                else:
                    indexes = []
                    for i in temp_indexes:
                        if i < len(self.media_manager.track_list) and i not in indexes:
                            indexes.append(i)

                if indexes is not None and len(indexes) > 0:
                    result = self.media_manager.delete_by_index(indexes, by_range)
                    if result is not None:
                        if by_range:
                            self.send_private_msg('*Deleted from index:* %s *to index:* %s' %
                                                  (result['from'], result['to']), self.active_user.nick)
                        elif result['deleted_indexes_len'] is 1:
                            self.send_private_msg('*Deleted* %s' % result['track_title'],
                                                  self.active_user.nick)
                        else:
                            self.send_private_msg('*Deleted tracks at index:* %s' %
                                                  ', '.join(result['deleted_indexes']),
                                                  self.active_user.nick)
                    else:
                        self.send_private_msg('Nothing was deleted.', self.active_user.nick)

    def do_media_replay(self):
        """ Replays the last played media."""
        if self._is_client_mod:
            if self.media_manager.track() is not None:
                self.cancel_media_event_timer()
                self.media_manager.we_play(self.media_manager.track())
                self.send_media_broadcast_start(self.media_manager.track().type,
                                                self.media_manager.track().id)
                self.media_event_timer(self.media_manager.track().time)

    def do_play_media(self):
        """ Resumes a track in pause mode. """
        if self._is_client_mod:
            track = self.media_manager.track()
            if track is not None:
                if self.media_manager.has_active_track():
                    self.cancel_media_event_timer()
                if self.media_manager.is_paused:
                    ntp = self.media_manager.mb_play(self.media_manager.elapsed_track_time())
                    self.send_media_broadcast_play(track.type, self.media_manager.elapsed_track_time())
                    self.media_event_timer(ntp)

    def do_media_pause(self):
        """ Pause the media playing. """
        if self._is_client_mod:
            track = self.media_manager.track()
            if track is not None:
                if self.media_manager.has_active_track():
                    self.cancel_media_event_timer()
                self.media_manager.mb_pause()
                self.send_media_broadcast_pause(track.type)

    def do_close_media(self):
        """ Closes the active media broadcast."""
        if self._is_client_mod:
            if self.media_manager.has_active_track():
                self.cancel_media_event_timer()
                self.media_manager.mb_close()
                self.send_media_broadcast_close(self.media_manager.track().type)

    def do_seek_media(self, time_point):
        """
        Seek on a media playing.
        :param time_point str the time point to skip to.
        """
        if self._is_client_mod:
            if ('h' in time_point) or ('m' in time_point) or ('s' in time_point):
                mls = pinylib.string_util.convert_to_millisecond(time_point)
                if mls is 0:
                    self.console_write(pinylib.COLOR['bright_red'], 'invalid seek time.')
                else:
                    track = self.media_manager.track()
                    if track is not None:
                        if 0 < mls < track.time:
                            if self.media_manager.has_active_track():
                                self.cancel_media_event_timer()
                            new_media_time = self.media_manager.mb_skip(mls)
                            if not self.media_manager.is_paused:
                                self.media_event_timer(new_media_time)
                            self.send_media_broadcast_skip(track.type, mls)

    def do_clear_playlist(self):
        """ Clear the playlist. """
        if self._is_client_mod:
            if len(self.media_manager.track_list) > 0:
                pl_length = str(len(self.media_manager.track_list))
                self.media_manager.clear_track_list()
                self.send_private_msg('*Deleted* ' + pl_length + ' *items in the playlist.*', self.active_user.nick)
            else:
                self.send_private_msg('*The playlist is empty, nothing to delete.*', self.active_user.nick)

    def do_playlist_info(self):
        """ Shows the next 5 tracks in the track list. """
        if self._is_client_mod:
            if len(self.media_manager.track_list) > 0:
                tracks = self.media_manager.get_track_list()
                if tracks is not None:
                    i = 0
                    for pos, track in tracks:
                        if i == 0:
                            self.send_private_msg('(%s) *Next track: %s* %s' %
                                                  (pos, track.title, self.format_time(track.time)),
                                                  self.active_user.nick)
                        else:
                            self.send_private_msg('(%s) *%s* %s' %
                                                  (pos, track.title, self.format_time(track.time)),
                                                  self.active_user.nick)
                        i += 1
            else:
                self.send_private_msg('*No tracks in the playlist.*', self.active_user.nick)

    def do_show_search_list(self):
        """ Shows what is in the search list. """
        if len(self.search_list) is 0:
            self.send_private_msg('No items in the search list.', self.active_user.nick)
        elif self.is_search_list_youtube_playlist:
            self.send_private_msg('*Youtube Playlist\'s.*', self.active_user.nick)
            for i in range(0, len(self.search_list)):
                self.send_private_msg('(%s) *%s*' % (i, self.search_list[i]['playlist_title']), self.active_user.nick)
        else:
            self.send_private_msg('*Youtube Tracks.*', self.active_user.nick)
            for i in range(0, len(self.search_list)):
                self.send_private_msg('(%s) *%s* %s' % (i, self.search_list[i]['video_title'],
                                                        self.search_list[i]['video_time']),
                                      self.active_user.nick)

    def do_nick(self, new_nick):
        """
        Set a new nick for the bot.
        :param new_nick: str the new nick.
        """
        if len(new_nick) is 0:
            self.nickname = pinylib.string_util.create_random_string(5, 25)
            self.set_nick()
        else:
            if re.match('^[][{}a-zA-Z0-9_]{1,25}$', new_nick):
                self.nickname = new_nick
                self.set_nick()

    def do_topic(self, topic):
        """
        Sets the room topic.
        :param topic: str the new topic.
        """
        if self._is_client_mod:
            if len(topic) is 0:
                self.send_topic_msg('')
                self.send_private_msg('Topic was cleared.', self.active_user.nick)
            else:
                self.send_topic_msg(topic)
                self.send_private_msg('The room topic was set to: ' + topic, self.active_user.nick)
        else:
            self.send_private_msg('Command not enabled', self.active_user.nick)

    def do_kick(self, user_name):
        """
        Kick a user out of the room.
        :param user_name: str the username to kick.
        """
        if self._is_client_mod:
            if len(user_name) is 0:
                self.send_bot_msg('Missing username.')
            elif user_name == self.nickname:
                self.send_bot_msg('Action not allowed.')
            else:
                if user_name.startswith('*'):
                    user_name = user_name.replace('*', '')
                    _users = self.users.search_containing(user_name)
                    if len(_users) > 0:
                        for i, user in enumerate(_users):
                            if user.nick != self.nickname and user.user_level > self.active_user.user_level:
                                if i <= pinylib.CONFIG.B_MAX_MATCH_BANS - 1:
                                    self.send_ban_msg(user.nick, user.id)
                                    a = pinylib.string_util.random.uniform(0.0, 1.0)
                                    pinylib.time.sleep(a)
                                    self.send_forgive_msg(user.id)
                                    pinylib.time.sleep(0.5)
                else:
                    _user = self.users.search(user_name)
                    if _user is None:
                        self.send_bot_msg('No user named: *%s*' % user_name)
                    elif _user.user_level < self.active_user.user_level:
                        self.send_bot_msg('Not allowed.')
                    else:
                        self.send_ban_msg(user_name, _user.id)
                        self.send_forgive_msg(_user.id)

    def do_ban(self, user_name):
        """
        Ban a user from the room.
        :param user_name: str the username to ban.
        """
        if self._is_client_mod:
            if len(user_name) is 0:
                self.send_bot_msg('Missing username.')
            elif user_name == self.nickname:
                self.send_bot_msg('Action not allowed.')
            else:
                if user_name.startswith('*'):
                    user_name = user_name.replace('*', '')
                    _users = self.users.search_containing(user_name)
                    if len(_users) > 0:
                        for i, user in enumerate(_users):
                            if user.nick != self.nickname and user.user_level > self.active_user.user_level:
                                if i <= pinylib.CONFIG.B_MAX_MATCH_BANS - 1:
                                    self.send_ban_msg(user.nick, user.id)
                                    a = pinylib.string_util.random.uniform(0.0, 1.5)
                                    pinylib.time.sleep(a)
                else:
                    _user = self.users.search(user_name)
                    if _user is None:
                        self.send_bot_msg('No user named: *%s*' % user_name)
                    elif _user.user_level < self.active_user.user_level:
                        self.send_bot_msg('Not allowed.')
                    else:
                        self.send_ban_msg(user_name, _user.id)

    def do_bad_nick(self, bad_nick):
        """
        Adds a username to the nicks bans file.
        :param bad_nick: str the bad nick to write to file.
        """
        if self._is_client_mod:
            if len(bad_nick) is 0:
                self.send_private_msg('Missing username.', self.active_user.nick)
            elif bad_nick in pinylib.CONFIG.B_NICK_BANS:
                self.send_private_msg('*%s* is already in list.' % bad_nick, self.active_user.nick)
            else:
                pinylib.file_handler.file_writer(self.config_path(),
                                                 pinylib.CONFIG.B_NICK_BANS_FILE_NAME, bad_nick)
                self.send_private_msg('*%s* was added to file.' % bad_nick, self.active_user.nick)
                self.load_list(nicks=True)

    def do_remove_bad_nick(self, bad_nick):
        """
        Removes nick from the nicks bans file.
        :param bad_nick: str the bad nick to remove from file.
        """
        if self._is_client_mod:
            if len(bad_nick) is 0:
                self.send_private_msg('Missing username', self.active_user.nick)
            else:
                if bad_nick in pinylib.CONFIG.B_NICK_BANS:
                    rem = pinylib.file_handler.remove_from_file(self.config_path(),
                                                                pinylib.CONFIG.B_NICK_BANS_FILE_NAME, bad_nick)
                    if rem:
                        self.send_private_msg('*%s* was removed.' % bad_nick, self.active_user.nick)
                        self.load_list(nicks=True)

    def do_bad_string(self, bad_string):
        """
        Adds a string to the strings bans file.
        :param bad_string: str the bad string to add to file.
        """
        if self._is_client_mod:
            if len(bad_string) is 0:
                self.send_private_msg('Ban string can\'t be blank.', self.active_user.nick)
            elif len(bad_string) < 3:
                self.send_private_msg('Ban string to short: ' + str(len(bad_string)), self.active_user.nick)
            elif bad_string in pinylib.CONFIG.B_STRING_BANS:
                self.send_private_msg('*%s* is already in list.' % bad_string, self.active_user.nick)
            else:
                pinylib.file_handler.file_writer(self.config_path(),
                                                 pinylib.CONFIG.B_STRING_BANS_FILE_NAME, bad_string)
                self.send_private_msg('*%s* was added to file.' % bad_string, self.active_user.nick)
                self.load_list(strings=True)

    def do_remove_bad_string(self, bad_string):
        """
        Removes a string from the strings bans file.
        :param bad_string: str the bad string to remove from file.
        """
        if self._is_client_mod:
            if len(bad_string) is 0:
                self.send_private_msg('Missing word string.', self.active_user.nick)
            else:
                if bad_string in pinylib.CONFIG.B_STRING_BANS:
                    rem = pinylib.file_handler.remove_from_file(self.config_path(),
                                                                pinylib.CONFIG.B_STRING_BANS_FILE_NAME, bad_string)
                    if rem:
                        self.send_private_msg('*%s* was removed.' % bad_string, self.active_user.nick)
                        self.load_list(strings=True)

    def do_bad_account(self, bad_account_name):
        """
        Adds an account name to the accounts bans file.
        :param bad_account_name: str the bad account name to add to file.
        """
        if self._is_client_mod:
            if len(bad_account_name) is 0:
                self.send_private_msg('Account can\'t be blank.', self.active_user.nick)
            elif len(bad_account_name) < 3:
                self.send_private_msg('Account to short: ' + str(len(bad_account_name)), self.active_user.nick)
            elif bad_account_name in pinylib.CONFIG.B_ACCOUNT_BANS:
                self.send_private_msg('%s is already in list.' % bad_account_name, self.active_user.nick)
            else:
                pinylib.file_handler.file_writer(self.config_path(),
                                                 pinylib.CONFIG.B_ACCOUNT_BANS_FILE_NAME, bad_account_name)
                self.send_private_msg('*%s* was added to file.' % bad_account_name, self.active_user.nick)
                self.load_list(accounts=True)

    def do_remove_bad_account(self, bad_account):
        """
        Removes an account from the accounts bans file.
        :param bad_account: str the bad account name to remove from file.
        """
        if self._is_client_mod:
            if len(bad_account) is 0:
                self.send_private_msg('Missing account.', self.active_user.nick)
            else:
                if bad_account in pinylib.CONFIG.B_ACCOUNT_BANS:
                    rem = pinylib.file_handler.remove_from_file(self.config_path(),
                                                                pinylib.CONFIG.B_ACCOUNT_BANS_FILE_NAME, bad_account)
                    if rem:
                        self.send_private_msg('*%s* was removed.' % bad_account, self.active_user.nick)
                        self.load_list(accounts=True)

    def do_list_info(self, list_type):
        """
        Shows info of different lists/files.
        :param list_type: str the type of list to find info for.
        """
        if self._is_client_mod:
            if len(list_type) is 0:
                self.send_private_msg('Missing list type.', self.active_user.nick)
            else:
                if list_type.lower() == 'nicks':
                    if len(pinylib.CONFIG.B_NICK_BANS) is 0:
                        self.send_private_msg('No items in this list.', self.active_user.nick)
                    else:
                        self.send_private_msg('%s *nicks bans in list.*' % len(pinylib.CONFIG.B_NICK_BANS),
                                              self.active_user.nick)

                elif list_type.lower() == 'words':
                    if len(pinylib.CONFIG.B_STRING_BANS) is 0:
                        self.send_private_msg('No items in this list.', self.active_user.nick)
                    else:
                        self.send_private_msg('%s *string bans in list.*' % pinylib.CONFIG.B_STRING_BANS,
                                              self.active_user.nick)

                elif list_type.lower() == 'accounts':
                    if len(pinylib.CONFIG.B_ACCOUNT_BANS) is 0:
                        self.send_private_msg('No items in this list.', self.active_user.nick)
                    else:
                        self.send_private_msg('%s *account bans in list.*' % pinylib.CONFIG.B_ACCOUNT_BANS,
                                              self.active_user.nick)

                elif list_type.lower() == 'mods':
                    if self._is_client_owner:
                        if len(self.privacy_settings.room_moderators) is 0:
                            self.send_private_msg('*There is currently no moderators for this room.*',
                                                  self.active_user.nick)
                        elif len(self.privacy_settings.room_moderators) is not 0:
                            mods = ', '.join(self.privacy_settings.room_moderators)
                            self.send_private_msg('*Moderators:* ' + mods, self.active_user.nick)

    def do_user_info(self, user_name):
        """
        Shows user object info for a given user name.
        :param user_name: str the user name of the user to show the info for.
        """
        if self._is_client_mod:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.active_user.nick)
            else:
                _user = self.users.search(user_name)
                if _user is None:
                    self.send_private_msg('No user named: %s' % user_name, self.active_user.nick)
                else:
                    if _user.account and _user.tinychat_id is None:
                        user_info = pinylib.core.tinychat_user_info(_user.account)
                        if user_info is not None:
                            _user.tinychat_id = user_info['tinychat_id']
                            _user.last_login = user_info['last_active']
                    self.send_private_msg('*User Level:* %s' % _user.user_level, self.active_user.nick)
                    online_time = (pinylib.time.time() - _user.join_time) * 1000
                    self.send_private_msg('*Online Time:* %s' % self.format_time(online_time), self.active_user.nick)

                    if _user.tinychat_id is not None:
                        self.send_private_msg('*Account:* ' + str(_user.account), self.active_user.nick)
                        self.send_private_msg('*Tinychat ID:* ' + str(_user.tinychat_id), self.active_user.nick)
                        self.send_private_msg('*Last login:* ' + str(_user.last_login), self.active_user.nick)
                    self.send_private_msg('*Last message (Public chat):* ' + str(_user.last_msg), self.active_user.nick)

    def do_youtube_search(self, search_str):
        """
        Searches youtube for a given search term, and returns a list of candidates.
        :param search_str: str the search term to search for.
        """
        if self._is_client_mod:
            if len(search_str) is 0:
                self.send_bot_msg('Missing search term.')
            else:
                self.search_list = apis.youtube.search_list(search_str, results=5)
                if len(self.search_list) is not 0:
                    self.is_search_list_youtube_playlist = False
                    for i in range(0, len(self.search_list)):
                        v_time = self.format_time(self.search_list[i]['video_time'])
                        v_title = self.search_list[i]['video_title']
                        self.send_owner_run_msg('(%s) *%s* %s' % (i, v_title, v_time))
                else:
                    self.send_bot_msg('Could not find: %s' % search_str)

    def do_play_youtube_search(self, int_choice):
        """
        Plays a youtube from the search list.
        :param int_choice: int the index in the search list to play.
        """
        if self._is_client_mod:
            if not self.is_search_list_youtube_playlist:
                if len(self.search_list) > 0:
                    try:
                        index_choice = int(int_choice)
                    except ValueError:
                        self.send_bot_msg('Only numbers allowed.')
                    else:
                        if 0 <= index_choice <= len(self.search_list) - 1:
                            if self.media_manager.has_active_track():
                                track = self.media_manager.add_track(self.active_user.nick,
                                                                     self.search_list[index_choice])
                                self.send_bot_msg('*Added* (%s) *%s* %s' %
                                                  (self.media_manager.last_track_index(), track.title, track.time))
                            else:
                                track = self.media_manager.mb_start(self.active_user.nick,
                                                                    self.search_list[index_choice], mod_play=False)
                                self.send_media_broadcast_start(track.type, track.id)
                                self.media_event_timer(track.time)
                        else:
                            self.send_bot_msg('Please make a choice between 0-%s' % str(len(self.search_list) - 1))
                else:
                    self.send_bot_msg('No youtube track id\'s in the search list.')
            else:
                self.send_bot_msg('The search list only contains youtube playlist id\'s.')

    # == Public Command Methods. ==
    def do_full_screen(self, room_name):
        """ Post a full screen link.
        :param room_name str the room name you want a full screen link for.
        """
        if not room_name:
            self.send_bot_msg('https://www.ruddernation.com/chat')

    def do_who_plays(self):
        """ shows who is playing the track. """
        if self.media_manager.has_active_track():
            track = self.media_manager.track()
            ago = self.format_time(int(pinylib.time.time() - track.rq_time) * 1000)
            self.send_bot_msg('*' + track.owner + '* requested this track: ' + ago + ' ago.')
        else:
            self.send_bot_msg('No track playing.')

    def do_help(self):
        """ Posts a link to github readme/wiki or other page about the bot commands. """
        self.send_undercover_msg(self.active_user.nick, '*Commands:* https://github.com/Tinychat/Tinychat-Bot/wiki')

    def do_uptime(self):
        """ Shows the bots uptime. """
        self.send_bot_msg('*Uptime:* ' + self.format_time(self.get_runtime()))

    def do_pmme(self):
        """ Opens a PM session with the bot. """
        self.send_private_msg('How can I help you *' + self.active_user.nick + '*?', self.active_user.nick)

    #  == Media Related Command Methods. ==
    def do_playlist_status(self):
        """ Shows info about the playlist. """
        if self._is_client_mod:
            if len(self.media_manager.track_list) is 0:
                self.send_bot_msg('*The playlist is empty.*')
            else:
                inquee = self.media_manager.queue()
                if inquee is not None:
                    self.send_bot_msg(str(inquee[0]) + ' *items in the playlist.* ' +
                                      str(inquee[1]) + ' *Still in queue.*')
        else:
            self.send_bot_msg('Not enabled right now..')

    def do_next_tune_in_playlist(self):
        """ Shows next item in the playlist. """
        if self._is_client_mod:
            if self.media_manager.is_last_track():
                self.send_bot_msg('*This is the last track in the playlist.*')
            elif self.media_manager.is_last_track() is None:
                self.send_bot_msg('*No tracks in the playlist.*')
            else:
                pos, next_track = self.media_manager.next_track_info()
                if next_track is not None:
                    self.send_bot_msg('(' + str(pos) + ') *' + next_track.title + '* ' +
                                      self.format_time(next_track.time))
        else:
            self.send_bot_msg('Not enabled right now..')

    def do_now_playing(self):
        """ Shows the currently playing media title. """
        if self._is_client_mod:
            if self.media_manager.has_active_track():
                track = self.media_manager.track()
                if len(self.media_manager.track_list) > 0:
                    self.send_undercover_msg(self.active_user.nick,
                                             '(' + str(self.media_manager.current_track_index()) +
                                             ') *' + track.title + '* ' + self.format_time(track.time))
                else:
                    self.send_undercover_msg(self.active_user.nick, '*' + track.title + '* ' +
                                             self.format_time(track.time))
            else:
                self.send_undercover_msg(self.active_user.nick, '*No track playing.*')

    def do_play_youtube(self, search_str):
        """
        Plays a youtube video matching the search term.
        :param search_str: str the search term.
        """
        log.info('User: %s:%s is searching youtube: %s' % (self.active_user.nick, self.active_user.id, search_str))
        if self._is_client_mod:
            if len(search_str) is 0:
                self.send_bot_msg('Please specify youtube title, id or link.')
            else:
                _youtube = apis.youtube.search(search_str)
                if _youtube is None:
                    log.warning('Youtube request returned: %s' % _youtube)
                    self.send_bot_msg('Could not find video: ' + search_str)
                else:
                    log.info('Youtube found: %s' % _youtube)
                    if self.media_manager.has_active_track():
                        track = self.media_manager.add_track(self.active_user.nick, _youtube)
                        self.send_bot_msg('(' + str(self.media_manager.last_track_index()) + ') *' +
                                          track.title + '* ' + self.format_time(track.time))
                    else:
                        track = self.media_manager.mb_start(self.active_user.nick, _youtube, mod_play=False)
                        self.send_media_broadcast_start(track.type, track.id)
                        self.media_event_timer(track.time)
        else:
            self.send_bot_msg('Not enabled right now..')

    def do_play_private_youtube(self, search_str):
        """
        Plays a youtube matching the search term privately.
        NOTE: The video will only be visible for the message sender.
        :param search_str: str the search term.
        """
        if self._is_client_mod:
            if len(search_str) is 0:
                self.send_private_msg(self.active_user.nick, 'Please specify youtube title, id or link.')
            else:
                _youtube = apis.youtube.search(search_str)
                if _youtube is None:
                    self.send_private_msg(self.active_user.nick, 'Could not find video: %s' % search_str)
                else:
                    self.send_media_broadcast_start(_youtube['type'], _youtube['video_id'],
                                                    private_nick=self.active_user.nick)
        else:
            self.send_private_msg('Not enabled right now..', self.active_user.nick)

    def do_play_soundcloud(self, search_str):
        """
        Plays a soundcloud matching the search term.
        :param search_str: str the search term.
        """
        if self._is_client_mod:
            if len(search_str) is 0:
                self.send_bot_msg('Please specify soundcloud title or id.')
            else:
                _soundcloud = apis.soundcloud.search(search_str)
                if _soundcloud is None:
                    self.send_bot_msg('Could not find soundcloud: %s' % search_str)
                else:
                    if self.media_manager.has_active_track():
                        track = self.media_manager.add_track(self.active_user.nick, _soundcloud)
                        self.send_bot_msg('(' + str(self.media_manager.last_track_index()) + ') *' + track.title +
                                          '* ' + self.format_time(track.time))
                    else:
                        track = self.media_manager.mb_start(self.active_user.nick, _soundcloud, mod_play=False)
                        self.send_media_broadcast_start(track.type, track.id)
                        self.media_event_timer(track.time)
        else:
            self.send_bot_msg('Not enabled right now..')

    def do_play_private_soundcloud(self, search_str):
        """
        Plays a soundcloud matching the search term privately.
        NOTE: The video will only be visible for the message sender.
        :param search_str: str the search term.
        """
        if self._is_client_mod:
            if len(search_str) is 0:
                self.send_private_msg(self.active_user.nick, 'Please specify soundcloud title or id.')
            else:
                _soundcloud = apis.soundcloud.search(search_str)
                if _soundcloud is None:
                    self.send_private_msg(self.active_user.nick, 'Could not find video: ' + search_str)
                else:
                    self.send_media_broadcast_start(_soundcloud['type'], _soundcloud['video_id'],
                                                    private_nick=self.active_user.nick)
        else:
            self.send_private_msg('Not enabled right now..', self.active_user.nick)

    def do_cam_approve(self, user_name):
        """ Send a cam approve message to a user. """
        if self._is_client_mod:
            if self._b_password is None:
                conf = pinylib.core.get_roomconfig_xml(self.roomname, self.room_pass, proxy=self._proxy)
                self._b_password = conf['bpassword']
                self.rtmp_parameter['greenroom'] = conf['greenroom']
            if self.rtmp_parameter['greenroom']:
                if len(user_name) is 0 and self.active_user.is_waiting:
                    self.active_user.is_waiting = False
                    self.send_cam_approve_msg(self.active_user.nick, self.active_user.id)

                elif len(user_name) > 0:
                    _user = self.users.search(user_name)
                    if _user is not None and _user.is_waiting:
                        _user.is_waiting = False
                        self.send_cam_approve_msg(_user.nick, _user.id)
                    else:
                        self.send_bot_msg('No user named: %s' % user_name)

    # == Tinychat API Command Methods. ==
    def do_spy(self, roomname):
        """
        Shows info for a given room.
        :param roomname: str the room name to find info for.
        """
        if self._is_client_mod:
            if len(roomname) is 0:
                self.send_undercover_msg(self.active_user.nick, 'Missing room name.')
            else:
                spy_info = pinylib.core.spy_info(roomname)
                if spy_info is None:
                    self.send_undercover_msg(self.active_user.nick, 'The room is empty.')
                elif spy_info == 'PW':
                    self.send_undercover_msg(self.active_user.nick, 'The room has a password on it.')
                else:
                    self.send_bot_msg('*Room:* ' + '*' + roomname + '*')
                    self.send_bot_msg('*Moderators:* ' + spy_info['mod_count'])
                    self.send_bot_msg('*Broadcasters:* ' + spy_info['broadcaster_count'])
                    self.send_bot_msg('*Chatters:* ' + spy_info['total_count'])
                    if self.has_level(3):
                        users = ', '.join(spy_info['users'])
                        self.send_bot_msg('*Users: ' + users + '*')

    def do_account_spy(self, account):
        """
        Shows info about a tinychat account.
        :param account: str tinychat account.
        """
        if self._is_client_mod:
            if len(account) is 0:
                self.send_undercover_msg(self.active_user.nick, 'Missing username to search for.')
            else:
                tc_usr = pinylib.core.tinychat_user_info(account)
                if tc_usr is None:
                    self.send_undercover_msg(self.active_user.nick, 'Could not find tinychat info for: ' + account)
                else:
                    self.send_bot_msg('*Account:* ' + '*' + account + '*')
                    self.send_bot_msg('*Website:* ' + tc_usr['website'])
                    self.send_bot_msg('*Bio:* ' + tc_usr['biography'])
                    self.send_bot_msg('*Location:* ' + tc_usr['location'])
                    self.send_bot_msg('*Last login:* ' + tc_usr['last_active'])

    # == Other API Command Methods. ==
    def do_search_urban_dictionary(self, search_str):
        """
        Shows urbandictionary definition of search string.
        :param search_str: str the search string to look up a definition for.
        """
        if len(search_str) is 0:
            self.send_bot_msg('Please specify something to look up.')
        else:
            urban = apis.other.urbandictionary_search(search_str)
            if urban is None:
                self.send_bot_msg('Could not find a definition for: ' + search_str)
            else:
                if len(urban) > 80:
                    chunks = pinylib.string_util.chunk_string(urban, 80)
                    for i in range(0, 3):
                        self.send_bot_msg(chunks[i])
                else:
                    self.send_bot_msg(urban)

    def do_weather_search(self, search_str):
        """
        Shows weather info for a given search string.
        :param search_str: str the search string to find weather data for.
        """
        if len(search_str) is 0:
            self.send_bot_msg('Please specify a city to search for.')
        else:
            weather = apis.other.weather_search(search_str)
            if weather is None:
                self.send_bot_msg('Could not find weather data for: %s' % search_str)
            else:
                self.send_bot_msg(weather)

    def do_whois_ip(self, ip_str):
        """
        Shows whois info for a given ip address.
        :param ip_str: str the ip address to find info for.
        """
        if len(ip_str) is 0:
            self.send_bot_msg('Please provide an IP address.')
        else:
            whois = apis.other.whois(ip_str)
            if whois is None:
                self.send_bot_msg('No info found for: %s' % ip_str)
            else:
                self.send_bot_msg(whois)

    def do_advice(self):
        """ Shows a random response from api.adviceslip.com """
        advised = apis.other.advice()
        if advised is not None:
            self.send_bot_msg(advised)

    def do_time(self, location):
        """ Shows the time in a location using Time.is. """
        times = str(apis.other.time_is(location))
        if len(location) is 0:
            self.send_bot_msg(' Please enter a location to fetch the time.')
        else:
            if times is None:
                self.send_bot_msg(' We could not fetch the time in "' + str(location) + '".')
            else:
                self.send_bot_msg('The time in *' + str(location) + '* is: *' + str(times) + "*")

    def do_translate(self, cmd_arg):
        if len(cmd_arg) is 0:
            self.send_bot_msg("Please enter a query to be translated to English, Example: translate jeg er fantastisk")
        else:
            translated_reply = apis.other.translate(query=cmd_arg)
            self.send_bot_msg("In English: " + "*" + translated_reply + "*")

    # == Just For Fun Command Methods. ==
    def do_chuck_norris(self):
        """ Shows a chuck norris joke/quote. """
        chuck = apis.other.chuck_norris()
        if chuck is not None:
            self.send_bot_msg(chuck)

    def do_8ball(self, question):
        """
        Shows magic eight ball answer to a yes/no question.
        :param question: str the yes/no question.
        """
        if len(question) is 0:
            self.send_bot_msg('Question.')
        else:
            self.send_bot_msg('*8Ball* %s' % apis.locals.eight_ball())

    # Private Message Command Handler.
    def private_message_handler(self, private_msg):
        """
        Custom private message commands.
        :param private_msg: str the private message (decoded).
        """
        if private_msg:
            pm_parts = private_msg.split(' ')
            pm_cmd = pm_parts[0].lower().strip()
            pm_arg = ' '.join(pm_parts[1:]).strip()

            # Super admin commands.
            if self.has_level(1):
                if self._is_client_owner:
                    # Only possible if bot is using the room owner account.
                    if pm_cmd == 'mod':
                        threading.Thread(target=self.do_make_mod, args=(pm_arg,)).start()

                    elif pm_cmd == 'removemod':
                        threading.Thread(target=self.do_remove_mod, args=(pm_arg,)).start()

                    elif pm_cmd == 'directory':
                        threading.Thread(target=self.do_directory).start()

                    elif pm_cmd == 'p2t':
                        threading.Thread(target=self.do_push2talk).start()

                    elif pm_cmd == 'green':
                        threading.Thread(target=self.do_green_room).start()

                    elif pm_cmd == 'clearbans':
                        threading.Thread(target=self.do_clear_room_bans).start()

                    elif pm_cmd == 'kill':
                        self.do_kill()

                    elif pm_cmd == 'reboot':
                        self.do_reboot()

                    elif pm_cmd == 'key':
                        self.do_key(pm_arg)

                    elif pm_cmd == 'clearnicks':
                        self.do_clear_bad_nicks()

                    elif pm_cmd == 'clearwords':
                        self.do_clear_bad_strings()

                    elif pm_cmd == 'clearaccounts':
                        self.do_clear_bad_accounts()

            # Admin commands - Bot Controller using key.
            if self.has_level(2):
                if pm_cmd == 'public':
                    self.do_public_cmds()

                elif pm_cmd == 'roompassword':
                    threading.Thread(target=self.do_set_room_pass, args=(pm_arg,)).start()

                elif pm_cmd == 'campassword':
                    threading.Thread(target=self.do_set_broadcast_pass, args=(pm_arg,)).start()

                elif pm_cmd == 'key':
                    self.do_key(pm_arg)

                elif pm_cmd == 'nick':
                    self.do_nick(pm_arg)

            # Mod commands.
            if self.has_level(3):
                # Misc
                if pm_cmd == 'op':
                    self.do_op_user(pm_arg)

                elif pm_cmd == 'deop':
                    self.do_deop_user(pm_arg)

                elif pm_cmd == 'greeting':
                    self.do_greet()

                elif pm_cmd == 'settings':
                    self.do_room_settings()

                elif pm_cmd == 'clear':
                    self.do_clear()

                elif pm_cmd == 'topic':
                    self.do_topic(pm_arg)

                elif pm_cmd == 'list':
                    self.do_list_info(pm_arg)

                elif pm_cmd == 'userinfo':
                    self.do_user_info(pm_arg)

                # Video/Audio
                elif pm_cmd == 'up':
                    self.do_cam_up()

                elif pm_cmd == 'down':
                    self.do_cam_down()

                elif pm_cmd == 'nocam':
                    self.do_nocam()

                elif pm_cmd == 'close':
                    self.do_close_broadcast(pm_arg)

                elif pm_cmd == 'cam':
                    threading.Thread(target=self.do_cam_approve).start()

                # Media
                elif pm_cmd == 'top':
                    threading.Thread(target=self.do_lastfm_chart, args=(pm_arg,)).start()

                elif pm_cmd == 'random':
                    threading.Thread(target=self.do_lastfm_random_tunes, args=(pm_arg,)).start()

                elif pm_cmd == 'tag':
                    threading.Thread(target=self.do_search_lastfm_by_tag, args=(pm_arg,)).start()

                elif pm_cmd == 'playlist':
                    threading.Thread(target=self.do_youtube_playlist_search, args=(pm_arg,)).start()

                elif pm_cmd == 'playpl':
                    threading.Thread(target=self.do_play_youtube_playlist, args=(pm_arg,)).start()

                elif pm_cmd == 'searchlist':
                    self.do_show_search_list()

                elif pm_cmd == 'skip':
                    self.do_skip()

                elif pm_cmd == 'delete':
                    self.do_delete_playlist_item(pm_arg)

                elif pm_cmd == 'replay':
                    self.do_media_replay()

                elif pm_cmd == 'resume':
                    self.do_play_media()

                elif pm_cmd == 'pause':
                    self.do_media_pause()

                elif pm_cmd == 'seek':
                    self.do_seek_media(pm_arg)

                elif pm_cmd == 'stop':
                    self.do_close_media()

                elif pm_cmd == 'clearpl':
                    self.do_clear_playlist()

                # Anti-spam
                elif pm_cmd == 'kick':
                    threading.Thread(target=self.do_kick, args=(pm_arg,)).start()

                elif pm_cmd == 'ban':
                    threading.Thread(target=self.do_ban, args=(pm_arg,)).start()

                elif pm_cmd == 'badnick':
                    self.do_bad_nick(pm_arg)

                elif pm_cmd == 'removenick':
                    self.do_remove_bad_nick(pm_arg)

                elif pm_cmd == 'badword':
                    self.do_bad_string(pm_arg)

                elif pm_cmd == 'removeword':
                    self.do_remove_bad_string(pm_arg)

                elif pm_cmd == 'badaccount':
                    self.do_bad_account(pm_arg)

                elif pm_cmd == 'goodaccount':
                    self.do_remove_bad_account(pm_arg)

                elif pm_cmd == 'guests':
                    self.do_guests()

                elif pm_cmd == 'lurkers':
                    self.do_lurkers()

                elif pm_cmd == 'guestnicks':
                    self.do_guest_nicks()

                elif pm_cmd == 'newusers':
                    self.do_newusers()

            if self.has_level(4):
                if pm_cmd == 'pinfo':
                    self.do_playlist_info()

                elif pm_cmd == 'search':
                    threading.Thread(target=self.do_youtube_search, args=(pm_arg,)).start()

                elif pm_cmd == 'psearch':
                    self.do_play_youtube_search(pm_arg)

                elif pm_cmd == 'minfo':
                    self.do_media_info()

                elif pm_cmd == 'pm':
                    self.do_pm_bridge(pm_parts)

            # Public commands.
            if self.has_level(5):
                if pm_cmd == 'opme':
                    self.do_opme(pm_arg)

                elif pm_cmd == 'pm':
                    self.do_pm_bridge(pm_parts)

                elif pm_cmd == 'private':
                    threading.Thread(target=self.do_play_private_youtube, args=(pm_arg,)).start()

                elif pm_cmd == 'privatesc':
                    threading.Thread(target=self.do_play_private_soundcloud, args=(pm_arg,)).start()

        # Print to console.
        msg = str(private_msg).replace(pinylib.CONFIG.B_KEY, '***KEY***'). \
            replace(pinylib.CONFIG.B_SUPER_KEY, '***SUPER KEY***')
        self.console_write(pinylib.COLOR['white'], 'Private message from %s: %s' % (self.active_user.nick, msg))

    def do_set_room_pass(self, password):
        """
        Set a room password for the room.
        :param password: str the room password
        """
        if self._is_client_owner:
            if not password:
                self.privacy_settings.set_room_password()
                self.send_bot_msg('*The room password was removed.*')
                pinylib.time.sleep(1)
                self.send_private_msg('The room password was removed.', self.active_user.nick)
            elif len(password) > 1:
                self.privacy_settings.set_room_password(password)
                self.send_private_msg('*The room password is:* ' + password, self.active_user.nick)
                pinylib.time.sleep(1)
                self.send_bot_msg('*The room is now password protected.*')

    def do_set_broadcast_pass(self, password):
        """
        Set a broadcast password for the room.
        :param password: str the password
        """
        if self._is_client_owner:
            if not password:
                self.privacy_settings.set_broadcast_password()
                self.send_bot_msg('*The broadcast password was removed.*')
                pinylib.time.sleep(1)
                self.send_private_msg('The broadcast password was removed.', self.active_user.nick)
            elif len(password) > 1:
                self.privacy_settings.set_broadcast_password(password)
                self.send_private_msg('*The broadcast password is:* ' + password, self.active_user.nick)
                pinylib.time.sleep(1)
                self.send_bot_msg('*Broadcast password is enabled.*')

    def do_key(self, new_key):
        """
        Shows or sets a new secret key.
        :param new_key: str the new secret key.
        """
        if len(new_key) is 0:
            self.send_private_msg('The current key is: *%s*' % pinylib.CONFIG.B_KEY, self.active_user.nick)
        elif len(new_key) < 6:
            self.send_private_msg('*Key must be at least 6 characters long:* %s' % len(new_key),
                                  self.active_user.nick)
        elif len(new_key) >= 6:
            # reset all bot controllers back to normal users
            for user in self.users.all:
                if self.users.all[user].user_level is 2 or self.users.all[user].user_level is 4:
                    self.users.all[user].user_level = 5
            pinylib.CONFIG.B_KEY = new_key
            self.send_private_msg('The key was changed to: *%s*' % new_key, self.active_user.nick)

    def do_clear_bad_nicks(self):
        """ Clears the bad nicks file. """
        pinylib.CONFIG.B_NICK_BANS[:] = []
        pinylib.file_handler.delete_file_content(self.config_path(), pinylib.CONFIG.B_NICK_BANS_FILE_NAME)

    def do_clear_bad_strings(self):
        """ Clears the bad strings file. """
        pinylib.CONFIG.B_STRING_BANS[:] = []
        pinylib.file_handler.delete_file_content(self.config_path(), pinylib.CONFIG.B_STRING_BANS_FILE_NAME)

    def do_clear_bad_accounts(self):
        """ Clears the bad accounts file. """
        pinylib.CONFIG.B_ACCOUNT_BANS[:] = []
        pinylib.file_handler.delete_file_content(self.config_path(), pinylib.CONFIG.B_ACCOUNT_BANS_FILE_NAME)

    # == Public PM Command Methods. ==
    def do_opme(self, key):
        """
        Makes a user a bot controller if user provides the right key.
        :param key: str the secret key.
        """
        if len(key) is 0:
            self.send_private_msg('Missing key.', self.active_user.nick)
        elif key == pinylib.CONFIG.B_SUPER_KEY:
            if self._is_client_owner:
                self.active_user.user_level = 1
                self.send_private_msg('*You are now super admin.*', self.active_user.nick)
            else:
                self.send_private_msg('*The client is not using the owner account.*', self.active_user.nick)
        elif key == pinylib.CONFIG.B_KEY:
            if self._is_client_mod:
                self.active_user.user_level = 2
                self.send_private_msg('*You are now a administrator (Level 2).*', self.active_user.nick)
                self.send_private_msg('Commands https://github.com/Tinychat/Tinychat-Bot/wiki#level-2',
                                      self.active_user.nick)
            else:
                self.send_private_msg('*The client is not moderator.*', self.active_user.nick)
        else:
            self.send_private_msg('Wrong key.', self.active_user.nick)

    def do_pm_bridge(self, pm_parts):
        """
        Makes the bot work as a PM message bridge between 2 user who are not signed in.
        :param pm_parts: list the pm message as a list.
        """
        if len(pm_parts) == 1:
            self.send_private_msg('Missing username.', self.active_user.nick)
        elif len(pm_parts) == 2:
            self.send_private_msg('The command is: ' + pinylib.CONFIG.B_PREFIX + 'pm username message',
                                  self.active_user.nick)
        elif len(pm_parts) >= 3:
            pm_to = pm_parts[1]
            msg = ' '.join(pm_parts[2:])
            is_user = self.users.search(pm_to)
            if is_user is not None:
                if is_user.id == self._client_id:
                    self.send_private_msg('Action not allowed.', self.active_user.nick)
                else:
                    self.send_private_msg('*<' + self.active_user.nick + '>* ' + msg, pm_to)
            else:
                self.send_private_msg('No user named: ' + pm_to, self.active_user.nick)

    # Timed auto functions.
    def media_event_handler(self):
        """ This method gets called whenever a media is done playing. """
        if len(self.media_manager.track_list) > 0:
            if self.media_manager.is_last_track():
                if self.is_connected:
                    self.send_bot_msg('*Resetting playlist.*')
                self.media_manager.clear_track_list()
            else:
                track = self.media_manager.get_next_track()
                if track is not None and self.is_connected:
                    self.send_media_broadcast_start(track.type, track.id)
                self.media_event_timer(track.time)

    def media_event_timer(self, video_time):
        """
        Start a media event timer.
        :param video_time: int the time in milliseconds.
        """
        video_time_in_seconds = video_time / 1000
        self.media_timer_thread = threading.Timer(video_time_in_seconds, self.media_event_handler)
        self.media_timer_thread.start()

    # Helper Methods.
    def get_privacy_settings(self):
        """ Parse the privacy settings page. """
        log.info('Parsing %s\'s privacy page. Proxy %s' % (self.account, self._proxy))
        self.privacy_settings = privacy_settings.TinychatPrivacyPage(self._proxy)
        self.privacy_settings.parse_privacy_settings()

    def config_path(self):
        """ Returns the path to the rooms configuration directory. """
        path = pinylib.CONFIG.CONFIG_PATH + self.roomname + '/'
        return path

    def load_list(self, nicks=False, accounts=False, strings=False):
        """
        Loads different list to memory.
        :param nicks: bool, True load nick bans file.
        :param accounts: bool, True load account bans file.
        :param strings: bool, True load ban strings file.
        """
        if nicks:
            pinylib.CONFIG.B_NICK_BANS = pinylib.file_handler.file_reader(self.config_path(),
                                                                          pinylib.CONFIG.B_NICK_BANS_FILE_NAME)
        if accounts:
            pinylib.CONFIG.B_ACCOUNT_BANS = pinylib.file_handler.file_reader(self.config_path(),
                                                                             pinylib.CONFIG.B_ACCOUNT_BANS_FILE_NAME)
        if strings:
            pinylib.CONFIG.B_STRING_BANS = pinylib.file_handler.file_reader(self.config_path(),
                                                                            pinylib.CONFIG.B_STRING_BANS_FILE_NAME)

    def has_level(self, level):
        """ Checks if the active user has correct user level. """
        if self.active_user.user_level is 6:
            return False
        elif self.active_user.user_level <= level:
            return True
        return False

    def cancel_media_event_timer(self):
        """
        Cancel the media event timer if it is running.
        :return: True if canceled, else False
        """
        if self.media_timer_thread is not None:
            if self.media_timer_thread.is_alive():
                self.media_timer_thread.cancel()
                self.media_timer_thread = None
                return True
            return False
        return False

    @staticmethod
    def format_time(milliseconds):
        """
        Converts milliseconds or seconds to (day(s)) hours minutes seconds.
        :param milliseconds: int the milliseconds or seconds to convert.
        :return: str in the format (days) hh:mm:ss
        """
        m, s = divmod(milliseconds / 1000, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)

        if d == 0 and h == 0:
            human_time = '%02d minutes %02d seconds' % (m, s)
        elif d == 0:
            human_time = '%d hours %02dminutes %02d seconds' % (h, m, s)
        else:
            human_time = '%d Day(s) %d hours %02d minutes %02d seconds' % (d, h, m, s)
        return human_time

    def check_msg(self, msg):
        """
        Checks the chat message for bad string.
        :param msg: str the chat message.
        """
        was_banned = False
        chat_words = msg.split(' ')
        for bad in pinylib.CONFIG.B_STRING_BANS:
            if bad.startswith('*'):
                _ = bad.replace('*', '')
                if _ in msg:
                    self.send_ban_msg(self.active_user.nick, self.active_user.id)
                    was_banned = True
            elif bad in chat_words:
                self.send_ban_msg(self.active_user.nick, self.active_user.id)
                was_banned = True
        if was_banned and pinylib.CONFIG.B_FORGIVE_AUTO_BANS:
            self.send_forgive_msg(self.active_user.id)

    def check_nick(self, old, user_info):
        """
        Check a users nick.
        :param old: str old nick.
        :param user_info: object, user object. This will contain the new nick.
        """
        if self._client_id != user_info.id:
            if str(old).startswith('guest-') and self._is_client_mod:
                if str(user_info.nick).startswith('guest-'):
                    if not pinylib.CONFIG.B_ALLOW_GUESTS_NICKS:
                        self.send_ban_msg(user_info.nick, user_info.id)
                        self.send_bot_msg('*Auto-Banned:* (bot nick detected)')
                        return True
                if str(user_info.nick).startswith('newuser'):
                    if not pinylib.CONFIG.B_ALLOW_NEWUSERS:
                        self.send_ban_msg(user_info.nick, user_info.id)
                        self.send_bot_msg('*Auto-Banned:* (wanker detected)')
                        return True
                if len(pinylib.CONFIG.B_NICK_BANS) > 0:
                    for bad_nick in pinylib.CONFIG.B_NICK_BANS:
                        if bad_nick.startswith('*'):
                            a = bad_nick.replace('*', '')
                            if a in user_info.nick:
                                self.send_ban_msg(user_info.nick, user_info.id)
                                self.send_bot_msg('*Auto-Banned:* (*bad nick)')
                                return True
                        elif user_info.nick in pinylib.CONFIG.B_NICK_BANS:
                            self.send_ban_msg(user_info.nick, user_info.id)
                            self.send_bot_msg('*Auto-Banned:* (bad nick)')
                            return True
                return False
