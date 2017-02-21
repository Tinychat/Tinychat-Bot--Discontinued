import time


class Track:
    """ A class representing a track. """
    def __init__(self, nick=None, **kwargs):
        self.owner = nick
        self.rq_time = time.time()
        self.id = kwargs.get('video_id', None)
        self.type = kwargs.get('type', None)
        self.title = kwargs.get('video_title', None)
        self.time = kwargs.get('video_time', 0)
        self.track_start_time = 0
        self.pause_time = 0


class MediaManager:
    """

    """
    def __init__(self):
        self.track_list = []
        self.track_list_index = 0
        self.current_media = None
        self.is_paused = False
        self.is_mod_playing = False

    def track(self):
        """ Returns the last track object that has been played, or None if no tracks has been played yet. """
        return self.current_media

    def current_track_index(self):
        """ Returns the track index of the current track playing. """
        return self.track_list_index

    def last_track_index(self):
        """ Returns the last track index. """
        if len(self.track_list) is 0:
            return 0
        else:
            return len(self.track_list) - 1

    def we_play(self, track_obj):
        """
        This will be called when ever we play from playlist.
        :param track_obj: object the track object of the next track.
        """
        self.is_mod_playing = False
        if track_obj is not None:
            self.current_media = track_obj
            self.current_media.track_start_time = int(time.time() * 1000)
            self.is_paused = False

    def mb_start(self, nick, track_info, mod_play=True):
        """
        This method must be called when ever a track is started either by us or a mod.
        If we start the track, then mod_play must be set to False.
        :param nick: str the nick of the one who started the track.
        :param track_info: dict the track info.
        :param mod_play: bool True if a mod in the room started it, False if we started the track
        :return: object the track object
        """
        self.is_mod_playing = mod_play
        self.current_media = Track(nick, **track_info)
        self.current_media.track_start_time = int(time.time() * 1000)
        self.is_paused = False
        return self.current_media

    def mb_pause(self):
        """ This method must be called when ever someone pauses a track. """
        self.is_paused = True
        self.current_media.pause_time = int(time.time() * 1000) - self.current_media.track_start_time

    def mb_close(self):
        """ This method must be called when a track gets closed. """
        self.is_paused = False
        self.current_media.track_start_time = 0
        self.current_media.pause_time = 0

    def mb_play(self, time_point=None):  # DEV
        """
        This method must be called when a user resumes a track from a pause state.
        :param time_point: int the milliseconds in the track to start playing from.
        :return int the time left of the track.
        """
        # NOTE: Remove the need for a time point when we are calling this from tinybot.do_play_media()
        # bad = self.media_manager.mb_play(self.media_manager.elapsed_track_time())
        if self.is_paused:  # when mbpl is called a track can only be in pause state..
            self.current_media.track_start_time = int(time.time() * 1000) - self.current_media.pause_time
            self.is_paused = False
        else:
            self.current_media.track_start_time = self.current_media.track_start_time - time_point
        track_time_left = self.current_media.time - self.elapsed_track_time()
        return track_time_left

    def mb_skip(self, time_point):
        """
        This method must be called when a user skips(seeks) a track.
        :param time_point: int the milliseconds in the track to skip to.
        :return: int milliseconds left of the track
        """
        if self.is_paused:
            self.current_media.pause_time = time_point
        else:
            self.current_media.track_start_time = int(time.time() * 1000) - time_point
        track_time_left = self.current_media.time - time_point
        return track_time_left

    def has_active_track(self):
        """ Checks the media manager to see if a track is currently active. """
        if self.is_paused:
            return True
        if self.elapsed_track_time() is 0:
            return False
        if self.elapsed_track_time() > 0:
            return True
        return False

    def add_track(self, nick, track_info):
        """
        Add a track to the track list.
        :param nick: str the track owner nick.
        :param track_info: dict the track info.
        :return: object the track, now as a class object.
        """
        if track_info is not None:
            new_track = Track(nick, **track_info)
            self.track_list.append(new_track)
            return new_track

    def add_track_list(self, nick, track_list):
        """
        Add a list af tracks to the track list.
        :param nick: str the owner of the tracks.
        :param track_list: list of track dict's.
        """
        if len(track_list) > 0:
            for track in track_list:
                self.add_track(nick, track)

    def get_next_track(self):
        """
        This method is used to get the next track from the play list.
        We use this method when we play from the play list,
        and we want next track in the play list.
        :return: object of the next track or None if no track list exists.
        """
        if len(self.track_list) > 0:
            if self.track_list_index <= len(self.track_list):
                next_track = self.track_list[self.track_list_index]
                self.we_play(next_track)
                self.track_list_index += 1  # prepare the next track.
                return next_track
            return None

    def clear_track_list(self):
        """
        Delete all items in the track list.
        :return: bool True if deleted else False.
        """
        if len(self.track_list) > 0:
            self.track_list[:] = []
            self.track_list_index = 0
            return True
        return False

    def elapsed_track_time(self):
        """
        Returns the current tracks elapsed time.
        :return: int the current track's elapsed time in milliseconds,
        or 0 if elapsed > track.time, or current track is None.
        """
        if self.current_media is not None:
            if self.is_paused:
                return self.current_media.pause_time
            elapsed = int(time.time() * 1000) - self.current_media.track_start_time
            if elapsed > self.current_media.time:
                return 0
            return elapsed
        return 0

    def remaining_time(self):  # DEV
        if self.current_media is not None:
            track_time_left = self.current_media.time - self.elapsed_track_time()
            return track_time_left
        return 0

    def is_last_track(self):
        """
        Checks if we have reached the end of the track list.
        :return: True if last track, False if not last track, or None if no track list exists.
        """
        if len(self.track_list) > 0:
            if self.track_list_index >= len(self.track_list):  # - 1
                return True
            return False
        return None  # no track list exists.

    def get_track_list(self, tracks=5, from_track_index=True):
        """
        Get a list of track objects from the play list.
        :param tracks: int the max amount of tracks the list returned should contain.
        :param from_track_index: bool True, start from the track we are at,
        meaning result[0] will be the next track.
        If False, start from the start of the track list (track_list[0])
        :return: list of track objects.
        """
        start_index = 0
        if len(self.track_list) > 0:
            if from_track_index:
                start_index = self.track_list_index
            ic = 0
            result = list()
            for i in range(start_index, len(self.track_list)):
                if ic <= tracks - 1:
                    info = (i, self.track_list[i])
                    result.append(info)
                    ic += 1
            return result

    def queue(self):
        """
        Get the queue of the playlist.
        :return tuple (int(length of the track list), int(tracks in queue))
        """
        if len(self.track_list) > 0:
            q = len(self.track_list) - self.track_list_index
            queue = (len(self.track_list), q)
            return queue

    def next_track_info(self, jump=0):
        """
        Get next track info.
        :param jump: int
        :return: object track.
        """
        if jump != 0:
            if self.track_list_index + jump < len(self.track_list):
                return self.track_list_index + jump, self.track_list[self.track_list_index + jump]
        elif self.track_list_index < len(self.track_list):
            return self.track_list_index, self.track_list[self.track_list_index]

    def delete_by_index(self, indexes, by_range):
        """
        Delete track by index.

        Indexes should be a list of int(indexes) we want to delete from the track list.
        :param indexes: list int indexes.
        :param by_range: bool, True if deleting a range.
        :return: dict, or None if nothing was deleted.
        """
        track_list_copy = list(self.track_list)
        deleted_indexes = []
        for i in sorted(indexes, reverse=True):
            if self.track_list_index <= i < len(self.track_list):
                del self.track_list[i]
                deleted_indexes.append(str(i))
        deleted_indexes.reverse()
        if len(deleted_indexes) > 0:
            _result = dict()
            if by_range:
                _result['from'] = deleted_indexes[0]
                _result['to'] = deleted_indexes[-1]
            elif len(deleted_indexes) is 1:
                _result['track_title'] = track_list_copy[int(deleted_indexes[0])].title
            _result['deleted_indexes'] = deleted_indexes
            _result['deleted_indexes_len'] = len(deleted_indexes)
            return _result
        return None
