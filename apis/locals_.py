"""
Contains functions that are not online APIs.
"""
import random


def eight_ball():
    """ Magic eight ball.

    :return: A random answer.
    :rtype: str
    """
    answers = [
                'It is certain', 'It is decidedly so', 'Not a fucking chance!', 'without a doubt', 'Yes definitely',
                'I suppose so', 'Maybe', ' No fucking way!', 'Sure :D', 'hahahaha no you plank! :P ', 'Ohhh yes!',
                'You may rely on it', 'As I see it, yes', 'Most likely', 'Outlook good', 'Yes', 'Signs point to yes',
                'Try again', 'Ask again later', 'Better not tell you now as you may cry like a little girl',
                'Cannot predict now', 'Fucking dead right!', 'Ohhhh most definitely',
                'Concentrate and ask again', 'Don\'t count on it', 'My reply is no', 'My sources say no',
                'Outlook not so good', 'Very doubtful', 'Possibly, but I think you need to chillout!'
    ]
    return random.choice(answers)


def flip_coin():
    """ Flip a coin.

    :return: Heads or tails.
    :rtype: str
    """
    coin = ['heads', 'tails']
    return random.choice(coin)


def roll_dice():
    """ Roll a 6 sided dice.

    :return: A number between 1 and 6.
    :rtype: str
    """
    numbers = ['1', '2', '3', '4', '5', '6']
    return random.choice(numbers)
