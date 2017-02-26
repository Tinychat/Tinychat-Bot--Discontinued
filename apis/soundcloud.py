""" Contains functions to fetch info from api.soundcloud.com """
import util.web

API_KEY = 'b59a98b55410a274c03d37a76b263c56'

SEARCH_URL = 'https://api.soundcloud.com/tracks/?filter=streamable&q={1}&limit=25&client_id={0}'

TRACK_DETAILS_URL = 'https://api.soundcloud.com/tracks/{1}?client_id={0}'


def search(search_term):
    """
    Searches soundcloud's API for a track
    matching the search term.

    :param search_term: str the search term to search for.
    :return: dict{'type=soundcloud', 'video_id', 'video_time', 'video_title'} or None on no match or error.
    """
    if search_term:
        url = SEARCH_URL.format(API_KEY, util.web.quote(search_term))
        response = util.web.http_get(url=url, json=True)

        if response['json'] is not None:
            try:
                track_id = response['json'][0]['id']
                track_time = response['json'][0]['duration']
                track_title = response['json'][0]['title'].encode('ascii', 'ignore')
                return {
                    'type': 'soundCloud',
                    'video_id': track_id,
                    'video_time': track_time,
                    'video_title': track_title
                }
            except (IndexError, KeyError):
                return None
        return None


def track_info(track_id):
    if track_id:
        url = TRACK_DETAILS_URL.format(API_KEY, track_id)
        response = util.web.http_get(url=url, json=True)

        if response['json'] is not None:
            try:
                user_id = response['json'][0]['user_id']
                track_time = response['json'][0]['duration']
                track_title = response['json'][0]['title'].encode('ascii', 'ignore')
                return {
                    'type': 'soundCloud',
                    'video_id': track_id,
                    'video_time': track_time,
                    'video_title': track_title,
                    'user_id': user_id
                }
            except (IndexError, KeyError):
                return None
        return None
