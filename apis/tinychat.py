""" Contains functions to fetch info from tinychat's API. """
import time

import util.web


def user_info(tc_account):
    """
    Finds info for a given tinychat account name.
    :param tc_account: str the account name.
    :return: dict {'username', 'tinychat_id', 'last_active', 'name', 'location', 'biography'} or None on error.
    """
    url = 'https://tinychat.com/api/tcinfo?username=%s' % tc_account
    response = util.web.http_get(url=url, json=True)
    if response['json'] is not None:
        if 'error' not in response['json']:
            username = response['json']['username']
            # user_id = response['json']['id']
            last_active = time.ctime(int(response['json']['last_active']))
            name = response['json']['name']
            location = response['json']['location']
            biography = response['json']['biography']
            website = response['json']['website']

            return {
                'username': username,
                # 'tinychat_id': user_id,
                'last_active': last_active,
                'name': name,
                'location': location,
                'biography': biography,
                'website': website
            }
        else:
            return None


def spy_info(room):
    """
    Finds info for a given room name.

    The info shows how many mods, broadcasters and total users(list)

    :param room: str the room name to get spy info for.
    :return: dict{'mod_count', 'broadcaster_count', 'total_count', list('users')} or {'error'}.
    """
    url = 'https://api.tinychat.com/%s.json' % room
    response = util.web.http_get(url, json=True)
    if response['json'] is not None:
        if 'error' not in response['json']:
            mod_count = str(response['json']['mod_count'])
            broadcaster_count = str(response['json']['broadcaster_count'])
            total_count = str(response['json']['total_count'])
            if total_count > 0:
                users = response['json']['names']
                return {
                    'mod_count': mod_count,
                    'broadcaster_count': broadcaster_count,
                    'total_count': total_count,
                    'users': users
                }
        else:
            return {'error': response['json']['error']}
