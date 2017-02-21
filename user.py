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
        self.user_level = 0
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
        """
        All the users in the room.
        :return: dict key value (User)
        """
        return self._users

    @property
    def mods(self):
        """
        All the moderators in the room.
        :return: list all of the moderators objects (User) in the room.
        """
        _mods = []
        for user in self.all:
            if self.all[user].is_mod:
                _mods.append(self.all[user])
        return _mods

    @property
    def signed_in(self):
        """
        All user in the room using an account.
        :return: list all the signed in users objects (User) in the room.
        """
        _signed_ins = []
        for user in self.all:
            if self.all[user].account:
                _signed_ins.append(self.all[user])
        return _signed_ins

    @property
    def lurkers(self):
        """
        All the lurkers in the room.
        :return: list of all the lurker objects (User) in the room.
        """
        _lurkers = []
        for user in self.all:
            if self.all[user].lf:
                _lurkers.append(self.all[user])
        return _lurkers

    @property
    def norms(self):
        """
        All the normal users in the room.
        e.g users that are not moderators or lurkers.
        :return: list of all the normal users objects (User) in the room.
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
        """
        Add a user to the users dict.
        :param user_info dict, tinychat user info.
        :return user info object (User)
        """
        if user_info['nick'] not in self.all:
            self._users[user_info['nick']] = User(**user_info)
        return self.all[user_info['nick']]

    def change(self, old_nick, new_nick, user_info):
        """
        Change a user nickname.
        :param old_nick: str the user's old nickname.
        :param new_nick: str the user's new nickname.
        :param user_info: object, the user's user info (User)
        :return: True if changed, else False.
        """
        if self.delete(old_nick):
            if new_nick not in self.all:
                self._users[new_nick] = user_info
                return True
            return False
        return False

    def delete(self, user_name):
        """
        Delete a user from the Users class.
        :param user_name: str the user to delete.
        :return: True if deleted, else False.
        """
        if user_name in self.all:
            del self._users[user_name]
            return True
        return False

    def search(self, user_name):
        """
        Search the Users class by nick name for a user.
        :param user_name: str the user to find.
        :return: if user name is found, object (User) else None
        """
        if user_name in self.all:
            return self.all[user_name]
        return None

    def search_by_id(self, user_id):
        """
        Search for a user by id.
        :param user_id: str the users ID
        :return if user id is found, object (User) else None
        """
        for user in self.all:
            if str(self.all[user].id) == user_id:
                return self.all[user]
        return None

    def search_containing(self, contains):
        """
        Search users for a matching string within the user nick.
        :param contains: str the string to search for in the nick.
        :return: list of object (User) matching the contains string
        """
        _users_containing = []
        for user in self.all:
            if str(contains) in self.all[user].nick:
                _users_containing.append(self.all[user])
        return _users_containing
