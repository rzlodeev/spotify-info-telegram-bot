import telebot
from telebot import types
import requests
from emojis import number_emojis

bot = telebot.TeleBot('6400261897:AAH7L9uULa2JbJso6Yko9Np8h-3CzL0rPF8')
CLIENT_ID = 'cf83cb4e4759403ebec9c318d9bcea3b'
CLIENT_SECRET = '32f81a3ce13641a6af60cc290ea969ad'

# Global variables to remember user choice
search_type = ''


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


class LocalMessage:  # Storage for message object and function that sends it
    def __init__(self, msg=None, msg_func=None, prev_msg=None):
        self.msg = msg  # Telebot message object
        self.msg_func = msg_func  # Function that executes sending of msg
        self.prev_msg = prev_msg  # Recursion for further previous messages


# Linked list of messages
class MessagesList:
    def __init__(self):
        self.head = None

    def set_current_msg(self, msg, func):  # Sets current step as properties
        new_message = LocalMessage(msg=msg, msg_func=func)
        if self.head is None:
            self.head = new_message
            return
        else:
            new_message.prev_msg = self.head
            self.head = new_message

    def send_prev_msg(self):  # Calls function for previous message. Prev variable marks that called function
        # doesn't need to set its message as current.
        if self.head.prev_msg:
            self.head.prev_msg.msg_func(self.head.prev_msg.msg, prev=True)
            self.head = self.head.prev_msg


msgs_list = MessagesList()


# Add inline back button to message
def add_back_button(reply_markup=None):
    if reply_markup is None:
        reply_markup = types.InlineKeyboardMarkup()
    reply_markup.add(types.InlineKeyboardButton('↩Back', callback_data='back'))
    return reply_markup


# Start markup
@bot.message_handler(commands=['start'])
def start_command(message, prev=False):
    if not prev:
        global msgs_list
        msgs_list.set_current_msg(message, start_command)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    search_button = types.KeyboardButton('🔍Find a playlist/album')
    markup.row(search_button)

    bot.send_message(message.chat.id, 'Select action from menu below⬇️', reply_markup=markup)


@bot.message_handler(regexp='🔍Find a playlist/album')
def find_a_playlist_message_handler(message, prev=False):
    if not prev:
        global msgs_list
        msgs_list.set_current_msg(message, find_a_playlist_message_handler)

    spotify_token.get_token()

    reply_markup = add_back_button()
    bot.send_message(message.chat.id, 'Type in name of playlist/album or insert link:', reply_markup=reply_markup)
    bot.register_next_step_handler(message, name_or_link)


# Defines if user text is link to playlist, or it's name
def name_or_link(message, prev=False):
    if not prev:
        global msgs_list
        msgs_list.set_current_msg(message, name_or_link)

    if 'spotify.com' in message.text:
        get_playlist_by_link(message)
    else:
        title = message.text

        # Create buttons for user to choose type of search
        reply_markup = types.InlineKeyboardMarkup()
        albums_button = types.InlineKeyboardButton('Albums', callback_data='type_album')
        playlists_button = types.InlineKeyboardButton('Playlists', callback_data='type_playlist')
        both_button = types.InlineKeyboardButton('Both', callback_data='type_both')
        reply_markup.row(albums_button, playlists_button)
        reply_markup.row(both_button)
        reply_markup = add_back_button(reply_markup)

        bot.send_message(message.chat.id, f'Title: {title}\n'
                                          f'Should it be album or playlist?',
                         reply_to_message_id=message.message_id, reply_markup=reply_markup)


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
def find_playlist(message, request_search_type=search_type, page=0, prev=False):
    if not prev:
        global msgs_list
        msgs_list.set_current_msg(message, find_playlist)
    print(search_type)

    title = message.reply_to_message.text

    # Modify search_type variable to pass it into request
    if request_search_type == 'both':
        request_search_type = 'album,playlist'
    else:
        request_search_type = str(request_search_type)

    # Request to spotify server to search endpoint
    search_limit = 5
    response = requests.get('https://api.spotify.com/v1/search',
                            headers={"Authorization": f"{spotify_token.token_type} {spotify_token.access_token}"},
                            params={
                                "q": f"{title}",
                                "type": f"{request_search_type}",
                                "limit": f"{search_limit}",
                                "offset": search_limit * page
                            }).json()
    response_status = get_response_status(response)
    print(response)

    if response_status == 'Success':
        # Organizing and filtering response in dict variables above according to search type.
        # Dict structure: {"result_index": {
        #                      "key": "value",
        #                      ...
        #                  },
        #                  ...}
        text = f'Results for {title}:\n\n'
        print(request_search_type)

        if request_search_type == 'album' or request_search_type == 'album,playlist':
            albums = {}

            for idx, album in enumerate(response['albums']['items'], start=1):
                albums.update({f'{idx}': {
                    "name": album['name'],
                    "artist": album['artists'][0]["name"],
                    "year": album['release_date'][:4],
                    "id": album['id'],
                    "link": album['external_urls']['spotify'],
                    "cover": album['images'][0]['url']
                }})

            text += 'Albums:\n'

            for key, value in albums.items():
                text += f'{number_emojis.get(f"{key}")}: '  # Adds emoji number from index (key)
                # Adds name of album (with hyperlink), artist and year
                text += f'<a href=\"{value["link"]}\">{value["name"]}</a> by {value["artist"]}, {value["year"]}\n'
            text += '\n'

        if request_search_type == 'playlist' or request_search_type == 'album,playlist':
            playlists = {}

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

            text += 'Playlists:\n'

            for key, value in playlists.items():  # Same as in album loop, but for playlists
                text += f'{number_emojis.get(f"{key}")}: '
                text += f'<a href=\"{value["link"]}\">{value["name"]}</a> by {value["owner"]}, ' \
                        f'{value["tracks_total"]} songs\n'

        # Make prev/next page buttons markup
        reply_markup = types.InlineKeyboardMarkup(row_width=2)
        prev_button = types.InlineKeyboardButton('◀️Prev page', callback_data=f'prev_page_{page}')
        next_button = types.InlineKeyboardButton('Next page▶️', callback_data=f'next_page_{page}')
        reply_markup.add(types.InlineKeyboardButton(f'Page: {page + 1}', callback_data='current_page'))

        if response[list(response)[0]]['previous'] is not None:  # Adding next\prev buttons
            if response[list(response)[0]]['next'] is not None:  # according to their existence
                reply_markup.add(prev_button, next_button)
            else:
                reply_markup.add(prev_button)
        else:
            reply_markup.add(next_button)
        reply_markup = add_back_button(reply_markup)

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
    global search_type
    # Triggers when user selects type of search
    if call.data.startswith('type_'):
        search_type = ''
        search_type = str(call.data).replace('type_', '')
        find_playlist(call.message, request_search_type=search_type)

    # Triggers when user changes page
    if 'page' in call.data:
        # Previous page in search results
        if call.data.startswith('prev'):
            find_playlist(call.message, request_search_type=search_type, page=int(call.data[-1]) - 1, prev=True)
        # Next page in search results
        if call.data.startswith('next'):
            find_playlist(call.message, request_search_type=search_type, page=int(call.data[-1]) + 1, prev=True)

    if call.data == 'back':
        bot.clear_step_handler(call.message)
        bot.delete_message(call.message.chat.id, call.message.id)
        global msgs_list
        msgs_list.send_prev_msg()


bot.polling(none_stop=True)
