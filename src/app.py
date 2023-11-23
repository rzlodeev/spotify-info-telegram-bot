import telebot
from telebot import types
import requests
from emojis import number_emojis

bot = telebot.TeleBot('6400261897:AAH7L9uULa2JbJso6Yko9Np8h-3CzL0rPF8')
CLIENT_ID = 'cf83cb4e4759403ebec9c318d9bcea3b'
CLIENT_SECRET = '32f81a3ce13641a6af60cc290ea969ad'


# Storage for Spotify access token with self update method
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

            if not response.get('error'):
                for key in response:
                    self.__setattr__(key, response[key])
            else:
                print(f'Failed to update token: {response["error_description"]}')


spotify_token = SpotifyAccessToken()


# Start markup
@bot.message_handler(commands=['start'])
def start_command(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    search_button = types.KeyboardButton('🔍Find a playlist/album')
    markup.row(search_button)

    bot.send_message(message.chat.id, 'Select action from menu below⬇️', reply_markup=markup)


@bot.message_handler(regexp='🔍Find a playlist/album')
def find_a_playlist_message_handler(message):
    spotify_token.get_token()
    bot.send_message(message.chat.id, 'Type in name of playlist/album or insert link:')
    bot.register_next_step_handler(message, name_or_link)


# Defines if user text is link to playlist, or it's name
def name_or_link(message):
    if 'spotify.com' in message.text:
        get_playlist_by_link(message)
    else:
        title = message.text
        results_message = bot.send_message(message.chat.id, f'Searching for {title}...',
                                           reply_to_message_id=message.message_id)
        find_playlist(results_message, title)  # Edit results_message and replace content with search results for title


def get_playlist_by_link(message):
    playlist_link: str = message.text
    playlist_type = str(playlist_link.rsplit('/', 2)[1])  # Executes type from user input (album or playlist)
    playlist_id = str(playlist_link.rsplit('/', 1)[1].split('?')[0])  # Executes ID part from user input

    response = requests.get(url=f'https://api.spotify.com/v1/{playlist_type}s/{playlist_id}',
                            headers={"Authorization": f"{spotify_token.token_type} "
                                                      f"{spotify_token.access_token}"}).json()
    response_status = get_response_status(response)
    if response_status == 'Success':
        bot.send_message(message.chat.id,
                         f'Playlist title: {response["name"]}')
    else:
        bot.send_message(message.chat.id, str(response_status))


# Makes request to spotify server with title, organizes response and sends message with list of results
def find_playlist(message, title='', page=0):
    if not title:
        title = message.reply_to_message.text
    # Request to spotify server to search endpoint
    search_limit = 5
    response = requests.get('https://api.spotify.com/v1/search',
                            headers={"Authorization": f"{spotify_token.token_type} {spotify_token.access_token}"},
                            params={
                                "q": f"{title}",
                                "type": "album,playlist",
                                "limit": f"{search_limit}",
                                "offset": search_limit * page
                            }).json()
    response_status = get_response_status(response)
    print(response)

    if response_status == 'Success':
        albums = {}
        playlists = {}

        # Organizing and filtering response in dict variables above.
        # Dict structure: {"result_index": {
        #                      "key": "value",
        #                      ...
        #                  },
        #                  ...}
        for idx, album in enumerate(response['albums']['items'], start=1):
            albums.update({f'{idx}': {
                "name": album['name'],
                "artist": album['artists'][0]["name"],
                "year": album['release_date'][:4],
                "id": album['id'],
                "link": album['external_urls']['spotify'],
                "cover": album['images'][0]['url']
            }})
        for idx, playlist in enumerate(response['playlists']['items'], start=1):
            playlists.update({f'{idx}': {
                "name": playlist['name'],
                "description": playlist['description'],
                "owner": playlist['owner']['display_name'],
                "tracks_total": playlist['tracks']['total'],
                "id": playlist['id'],
                "link": playlist['external_urls']['spotify'],
                "cover": playlist['images'][0]['url']
            }})

        # Make prev/next page buttons markup
        reply_markup = types.InlineKeyboardMarkup(row_width=2)
        prev_button = types.InlineKeyboardButton('◀️Prev', callback_data=f'prev_page_{page}')
        next_button = types.InlineKeyboardButton('Next▶️', callback_data=f'next_page_{page}')
        reply_markup.add(types.InlineKeyboardButton(f'Page: {page + 1}', callback_data='current_page'))
        if response['playlists']['previous'] is not None:  # Adding next\prev buttons
            if response['playlists']['next'] is not None:  # according to their existence
                reply_markup.add(prev_button, next_button)
            else:
                reply_markup.add(prev_button)
        else:
            reply_markup.add(next_button)

        # Organizing text variable to send
        text = f'Results for {title}:\n\n'
        text += 'Albums:\n'

        for key, value in albums.items():
            text += f'{number_emojis.get(f"{key}")}: '  # Adds emoji number from index (key)
            # Adds name of album (with hyperlink), artist and year
            text += f'<a href=\"{value["link"]}\">{value["name"]}</a> by {value["artist"]}, {value["year"]}\n'

        text += '\nPlaylists:\n'

        for key, value in playlists.items():  # Same as in above loop, but for playlists
            text += f'{number_emojis.get(f"{key}")}: '
            text += f'<a href=\"{value["link"]}\">{value["name"]}</a> by {value["owner"]}, ' \
                    f'{value["tracks_total"]} songs\n'

        # Breaks text up in several parts if it's longer than 4096 letters
        # Edit message command template with different txt to send
        def edit_long_message_text(txt):
            return bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id,
                                         text=f'{txt}', parse_mode='HTML',
                                         disable_web_page_preview=True, reply_markup=reply_markup)

        if len(text) > 4096:
            edit_long_message_text(text[:4096])
            for x in range(4096, len(text), 4096):
                edit_long_message_text(text[x:x + 4096])
        else:
            edit_long_message_text(text)
    else:
        bot.send_message(message.chat.id, f'{response_status}')


# Checks if response is valid. Otherwise, returns error code and description
def get_response_status(response):
    if not response.get('error'):
        return 'Success'
    else:
        return f'Connection error {response["error"]["status"]}: 'f'{response["error"]["message"]}'


# Handler of inline keyboard buttons
@bot.callback_query_handler(func=lambda message: True)
def callback_query(call):
    if 'page' in call.data:
        # Previous page in search results
        if call.data.startswith('prev'):
            find_playlist(call.message, page=int(call.data[-1]) - 1)
        # Next page in search results
        if call.data.startswith('next'):
            find_playlist(call.message, page=int(call.data[-1]) + 1)


bot.polling(none_stop=True)
