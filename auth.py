from bs4 import BeautifulSoup
from util import web


class Account:
    def __init__(self, account, password, proxy=None):
        self.account = account
        self.password = password
        self._proxy = proxy
        self._token = None

    def _parse_token(self, response=None):
        token_url = 'https://tinychat.com/start?#signin'
        if response is None:
            response = web.http_get(url=token_url, referer=token_url, proxy=self._proxy)

        if response is not None and response['content'] is not None:
            soup = BeautifulSoup(response['content'], 'html.parser')

            token = soup.find(attrs={'name': 'csrf-token'})
            self._token = token['content']

    @staticmethod
    def logout():
        _cookies = ['user', 'pass', 'hash']
        for cookie in _cookies:
            web.delete_cookie(cookie)

    @staticmethod
    def is_logged_in():
        _has_cookie = web.has_cookie('pass')
        if _has_cookie:
            _is_expired = web.is_cookie_expired('pass')
            if _is_expired:
                return False
            return True
        return False

    def login(self):
        if self._token is None:
            self._parse_token()

        _post_url = 'https://tinychat.com/login'

        form_data = {
            'login_username': self.account,
            'login_password': self.password,
            'remember': '1',
            'next': 'https://tinychat.com/',
            '_token': self._token
        }

        login_response = web.http_post(post_url=_post_url, post_data=form_data,
                                       follow_redirect=True, proxy=self._proxy)
        self._parse_token(response=login_response)
