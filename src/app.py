import telebot
from telebot import types
import requests

bot = telebot.TeleBot('6400261897:AAH7L9uULa2JbJso6Yko9Np8h-3CzL0rPF8')
CLIENT_ID = 'cf83cb4e4759403ebec9c318d9bcea3b'
CLIENT_SECRET = '32f81a3ce13641a6af60cc290ea969ad'


class SpotifyAccessToken:
    def __init__(self):
        # Expected response keys
        self.access_token = ''
        self.token_type = ''
        self.expires_in = 0

    def get_token(self):
        if self.expires_in == 0:
            url = 'https://accounts.spotify.com/api/token'
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            payload = {'grant_type': 'client_credentials',
                                     'client_id': f'{CLIENT_ID}',
                                     'client_secret': f'{CLIENT_SECRET}'}
            response = requests.post(url, data=payload, headers=headers).json()

            for key in response:
                self.__setattr__(key, response[key])


spotify_token = SpotifyAccessToken()


@bot.message_handler(commands=['start'])
def start_command(message):
    spotify_token.get_token()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    search_button = types.KeyboardButton('🔍Find a playlist/album')
    markup.row(search_button)

    bot.send_message(message.chat.id, 'Select action from menu below⬇️', reply_markup=markup)


@bot.message_handler(regexp='🔍Find a playlist/album')
def find_a_playlist(message):
    bot.send_message(message.chat.id, 'Send a link of playlist/album:')
    bot.register_next_step_handler(message, get_playlist_by_link)


def get_playlist_by_link(message):
    playlist_link: str = message.text
    if 'open.spotify.com' in playlist_link:
        playlist_type = str(playlist_link.rsplit('/', 2)[1])  # Executes type from user input (album or playlist)
        playlist_id = str(playlist_link.rsplit('/', 1)[1].split('?')[0])  # Executes ID part from user input



        response = requests.get(url=f'https://api.spotify.com/v1/{playlist_type}s/{playlist_id}',
                                headers={"Authorization": f"{spotify_token.token_type} {spotify_token.access_token}"}).json()

        bot.send_message(message.chat.id, f'{response["name"]}')
    else:
        bot.send_message(message.chat.id, 'Please provide valid spotify link')
        bot.register_next_step_handler(message, get_playlist_by_link)


bot.polling(none_stop=True)
