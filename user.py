import time


class User:
    """ class representing a users information. """
    def __init__(self, **kwargs):
        self.lf = kwargs.get('lf')
        self.account = kwargs.get('account', '')
        self.is_owner = kwargs.get('own', False)
        self.gp = kwargs.get('gp', 0)
        self.alevel = kwargs.get('alevel', '')
        self.bf = kwargs.get('bf', False)
        self.nick = kwargs.get('nick')
        self.btype = kwargs.get('btype', '')
        self.id = kwargs.get('id', -1)
        self.stype = kwargs.get('stype', 0)
        self.is_mod = kwargs.get('mod', False)
        self.join_time = time.time()
        self.tinychat_id = None
        self.last_login = None
        self.user_level = 5
        self.is_waiting = False
        # Extras.
        self.last_msg = None


class Users:
    """
    This class represents the users in the room.

    Each user name is a dict key where the value of the key is represented by the User class.
    It contains methods to do various user based operations with.
    """
    def __init__(self):
        # Create a dictionary to store each user key value in.
        self._users = dict()

    @property
    def all(self):
        """ All the users in the room.

        :return: Key value of users.
        :rtype: dict
        """
        return self._users

    @property
    def mods(self):
        """ All the moderators in the room.

        :return: A list of all of the moderators User objects in the room.
        :rtype: list
        """
        _mods = []
        for user in self.all:
            if self.all[user].is_mod:
                _mods.append(self.all[user])
        return _mods

    @property
    def signed_in(self):
        """ All user in the room using an account.

        :return: A list of all the signed in User objects in the room.
        :rtype: list
        """
        _signed_ins = []
        for user in self.all:
            if self.all[user].account:
                _signed_ins.append(self.all[user])
        return _signed_ins

    @property
    def lurkers(self):
        """ All the lurkers in the room.

        :return: A list of all the lurker User objects in the room.
        :rtype: list
        """
        _lurkers = []
        for user in self.all:
            if self.all[user].lf:
                _lurkers.append(self.all[user])
        return _lurkers

    @property
    def norms(self):
        """ All the normal users in the room.

        e.g users that are not moderators or lurkers.
        :return: A list of all the normal User objects in the room.
        :rtype: list
        """
        _regs = []
        for user in self.all:
            if not self.all[user].is_mod and not self.all[user].lf:
                _regs.append(self.all[user])
        return _regs

    def clear(self):
        """ Delete all the users. """
        self._users.clear()

    def add(self, user_info):
        """ Add a user to the users dict.

        :param user_info Tinychat user info.
        :type user_info: dict
        :return User info object
        :rtype: User
        """
        if user_info['nick'] not in self.all:
            self._users[user_info['nick']] = User(**user_info)
        return self.all[user_info['nick']]

    def change(self, old_nick, new_nick, user_info):
        """ Change a user nickname.

        :param old_nick: The user's old nickname.
        :type old_nick: str
        :param new_nick: The user's new nickname.
        :type new_nick: str
        :param user_info: The user's user info.
        :type user_info: User
        :return: True if changed, else False.
        :rtype: bool
        """
        if self.delete(old_nick):
            if new_nick not in self.all:
                self._users[new_nick] = user_info
                return True
            return False
        return False

    def delete(self, user_name):
        """ Delete a user from the Users class.

        :param user_name: The user to delete.
        :type user_name: str
        :return: True if deleted, else False.
        :rtype: bool
        """
        if user_name in self.all:
            del self._users[user_name]
            return True
        return False

    def search(self, user_name):
        """ Search the Users class by nick name for a user.

        :param user_name: The user to find.
        :type user_name: str
        :return: If user name is found, User else None.
        :rtype: User | None
        """
        if user_name in self.all:
            return self.all[user_name]
        return None

    def search_by_id(self, user_id):
        """ Search the Users class for a user by id.

        :param user_id: The users ID
        :type user_id: int | str
        :return If user id is found, User else None
        :rtype: User | None
        """
        for user in self.all:
            if str(self.all[user].id) == user_id:
                return self.all[user]
        return None

    def search_containing(self, contains):
        """ Search users for a matching string within the user nick.

        :param contains: The string to search for in the nick.
        :type contains: str | int
        :return: A list of User objects matching the contains string
        :rtype: list
        """
        _users_containing = []
        for user in self.all:
            if str(contains) in self.all[user].nick:
                _users_containing.append(self.all[user])
        return _users_containing
