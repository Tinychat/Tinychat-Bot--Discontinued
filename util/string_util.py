""" Functions to do different string operations with. """
import random


def chunk_string(input_str, length):
    """
    Splits a string in to smaller chunks.
    NOTE: http://stackoverflow.com/questions/18854620/
    :param input_str: str the input string to chunk.
    :param length: int the length of each chunk.
    :return: list of input str chunks.
    """
    return list((input_str[0 + i:length + i] for i in range(0, len(input_str), length)))


def create_random_string(min_length, max_length, upper=False):
    """
    Creates a random string of letters and numbers.
    :param min_length: int the minimum length of the string
    :param max_length: int the maximum length of the string
    :param upper: bool do we need upper letters
    :return: random str of letters and numbers
    """
    randlength = random.randint(min_length, max_length)
    junk = 'abcdefghijklmnopqrstuvwxyz0123456789'
    if upper:
        junk += 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    return ''.join((random.choice(junk) for _ in xrange(randlength)))


def convert_to_millisecond(duration):
    """
    Converts a ISO 8601 unicode duration str to milliseconds.
    :param duration: The ISO 8601 unicode duration str
    :return:  int milliseconds
    """
    duration_string = duration.replace('PT', '').upper()
    seconds = 0
    number_string = ''

    for char in duration_string:
        if char.isnumeric():
            number_string += char
        try:
            if char == 'H':
                seconds += (int(number_string) * 60) * 60
                number_string = ''
            if char == 'M':
                seconds += int(number_string) * 60
                number_string = ''
            if char == 'S':
                seconds += int(number_string)
        except ValueError:
            return 0
    return seconds * 1000
