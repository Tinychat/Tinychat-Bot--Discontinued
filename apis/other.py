""" Contains functions to fetch info from different simple online APIs."""
import util.web
from bs4 import BeautifulSoup
import goslate
gs = goslate.Goslate()


def urbandictionary_search(search):
    """
    Searches urbandictionary's API for a given search term.
    :param search: The search term str to search for.
    :return: definition str or None on no match or error.
    """
    if str(search).strip():
        urban_api_url = 'http://api.urbandictionary.com/v0/define?term=%s' % search
        response = util.web.http_get(url=urban_api_url, json=True)
        if response['json'] is not None:
            try:
                definition = response['json']['list'][0]['definition']
                return definition.encode('ascii', 'ignore')
            except (KeyError, IndexError):
                return None
    else:
        return None


def weather_search(city):
    """
    Searches worldweatheronline's API for weather data for a given city.
    You must have a working API key to be able to use this function.
    :param city: The city str to search for.
    :return: weather data str or None on no match or error.
    """
    if str(city).strip():
        api_key = '500d22f9d3f17b1c01d7584d19741'
        if not api_key:
            return 'Missing api key.'
        else:
            weather_api_url = 'https://api.worldweatheronline.com/free/v2/weather.ashx?' \
                              'q=%s&format=json&key=%s' % (city, api_key)

            response = util.web.http_get(weather_api_url, json=True)

            if response['json'] is not None:
                try:
                    weatherdesc = response['json']['data']['current_condition'][0]['weatherDesc'][0]['value']
                    winddir16point = response['json']['data']['current_condition'][0]['winddir16Point']
                    windspeedmiles = response['json']['data']['current_condition'][0]['windspeedMiles']
                    windspeedkmph = response['json']['data']['current_condition'][0]['windspeedKmph']
                    feelslikec = response['json']['data']['current_condition'][0]['FeelsLikeC']
                    feelslikef = response['json']['data']['current_condition'][0]['FeelsLikeF']
                    temp_c = response['json']['data']['current_condition'][0]['temp_C']
                    temp_f = response['json']['data']['current_condition'][0]['temp_F']
                    query = response['json']['data']['request'][0]['query'].encode('ascii', 'ignore')
                    result = query + ' - ' + weatherdesc + ', ' + temp_c + 'C (' + temp_f + 'F), ' \
                                     'Feels Like: ' + feelslikec + 'C (' + feelslikef + 'F) , ' \
                                     'Wind Speed: ' + windspeedmiles + ' mph (' + windspeedkmph + ' kph), ' \
                                     'Wind Direction: ' + winddir16point
                    return result
                except (IndexError, KeyError):
                    return None
    else:
        return None


def whois(ip):
    """
    Searches ip-api for information about a given IP.
    :param ip: The ip str to search for.
    :return: information str or None on error.
    """
    if str(ip).strip():
        url = 'http://ip-api.com/json/%s' % ip
        response = util.web.http_get(url=url, json=True)
        if response['json'] is not None:
            try:
                city = response['json']['city']
                country = response['json']['country']
                isp = response['json']['isp']
                org = response['json']['org']
                region = response['json']['regionName']
                zipcode = response['json']['zip']
                info = country + ', ' + city + ', ' + region + ', Zipcode: ' + zipcode + '  Isp: ' + isp + '/' + org
                return info
            except KeyError:
                return None
    else:
        return None


def chuck_norris():
    """
    Finds a random Chuck Norris joke/quote.
    :return: joke str or None on failure.
    """
    url = 'https://api.icndb.com/jokes/random/?escape=javascript'
    response = util.web.http_get(url=url, json=True)
    if response['json'] is not None:
        if response['json']['type'] == 'success':
            joke = response['json']['value']['joke'].decode('string_escape')
            return joke
        return None


def advice():
    """
    Random sentences of advice.
    :return:
    """
    url = "http://api.adviceslip.com/advice"
    json_data = util.web.http_get(url=url, json=True)
    if json_data['json']:
        advised = json_data['json']['slip']['advice'].decode('string_escape')
        return advised
    else:
        return None


def time_is(location):
    """
    Retrieves the time in a location by parsing the time element in the html from Time.is .
    :param location: str location of the place you want to find time (works for small towns as well).
    :return: time str or None on failure.
    """
    if BeautifulSoup:
        header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/51.0.2704.106 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Referrer': 'http://time.is/',
        }

        post_url = 'http://time.is/' + str(location)
        time_data = util.web.http_get(post_url, header=header)
        time_html = time_data['content']
        soup = BeautifulSoup(time_html, "html.parser")

        time = ''
        try:
            for hit in soup.findAll(attrs={'id': 'twd'}):
                time = hit.contents[0].strip()
        except KeyError:
            pass

        return time
    else:
        return None


def translate(query, en=True):
    if en is True:
        return str(gs.translate(str(query), 'en'))
    else:
        pass
