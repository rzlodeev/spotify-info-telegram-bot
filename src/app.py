import pprint
import logging
import telebot
from telebot import types
import requests
import os
from dotenv import load_dotenv
from emojis import number_emojis

load_dotenv()

CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(f'{BOT_TOKEN}')

LOGS_PWD = os.getenv('LOGS_PWD')  # Custom password for checking logs from bot

logging.basicConfig(filename='../logs/logs.log', encoding='utf-8', level=logging.INFO)

# Global variables to remember user choice
title = ''
search_type = ''
item = ''
songs_response = {}
min_bpm = 0
max_bpm = 0
bpm_sorting = 'default'


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

    def send_prev_msg(self):  # Calls function for previous message. Prev variable marks that function
        # is called not for the first time, and it doesn't need to set its message as current.
        if self.head.prev_msg:
            self.head.prev_msg.msg_func(self.head.prev_msg.msg, prev=True)
            self.head = self.head.prev_msg


msgs_list = MessagesList()


# Add inline back button to message
def add_back_button(reply_markup=None, no_delete=False, with_input=False):
    if reply_markup is None:
        reply_markup = types.InlineKeyboardMarkup()
    if with_input:  # If user sends message on previous step, back button deletes 3 previous messages instead of 1
        reply_markup.add(types.InlineKeyboardButton('↩Back', callback_data='back_with_input'))
    elif no_delete:
        reply_markup.add(types.InlineKeyboardButton('↩Back', callback_data='back_no_delete'))
    else:
        reply_markup.add(types.InlineKeyboardButton('↩Back', callback_data='back'))
    return reply_markup


# Start markup
@bot.message_handler(commands=['start'])
def start_command(message, prev=False):
    if not prev:
        global msgs_list
        msgs_list.set_current_msg(message, start_command)

    logging.info(f'Start command by {message.from_user}, {message.date}')

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    search_button = types.KeyboardButton('🔍Find a playlist/album')
    markup.row(search_button)

    bot.send_message(message.chat.id, 'Select action from menu below⬇️', reply_markup=markup)


@bot.message_handler(commands=['logs'])
def logs_command(message):
    bot.send_message(message.chat.id, 'pswd:')
    bot.register_next_step_handler(message, send_logs)


def send_logs(message):
    if message.text == f'{LOGS_PWD}':
        log_file = open('../logs/logs.log', 'rb')
        bot.send_document(message.chat.id, document=log_file)
    else:
        bot.send_message(message.chat.id, 'wrong pswd')


@bot.message_handler(regexp='🔍Find a playlist/album')
def find_a_playlist_message_handler(message, prev=False):
    if not prev:
        global msgs_list
        msgs_list.set_current_msg(message, find_a_playlist_message_handler)

    spotify_token.get_token()

    if prev:
        reply_markup = add_back_button()
    else:
        reply_markup = add_back_button(with_input=True)
    bot.send_message(message.chat.id, 'Type in name of playlist/album or insert link:', reply_markup=reply_markup)
    bot.register_next_step_handler(message, name_or_link)


# Defines if user text is link to playlist, or it's name
def name_or_link(message, prev=False):
    logging.info(f'User {message.from_user} searched for {message.text}')
    if 'spotify.com' in message.text:
        get_playlist_by_link(message)
    else:
        if not prev:
            global msgs_list
            msgs_list.set_current_msg(message, name_or_link)

        global title
        title = message.text

        # Create buttons for user to choose type of search
        reply_markup = types.InlineKeyboardMarkup()
        albums_button = types.InlineKeyboardButton('Albums', callback_data='type_album')
        playlists_button = types.InlineKeyboardButton('Playlists', callback_data='type_playlist')
        both_button = types.InlineKeyboardButton('Both', callback_data='type_album,playlist')
        reply_markup.row(albums_button, playlists_button)
        reply_markup.row(both_button)
        reply_markup = add_back_button(reply_markup, with_input=True)

        if prev:
            bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id + 1,
                                  text=f'Title: {title}\nShould it be album or playlist?',
                                  reply_markup=reply_markup)
        else:
            bot.send_message(message.chat.id, f'Title: {title}\n'
                                              f'Should it be album or playlist?',
                             reply_to_message_id=message.message_id, reply_markup=reply_markup)


def get_playlist_by_link(message):
    playlist_link: str = message.text
    playlist_type = str(playlist_link.rsplit('/', 2)[1])  # Executes type from user input (album or playlist)
    global search_type
    search_type = playlist_type
    playlist_id = str(playlist_link.rsplit('/', 1)[1].split('?')[0])  # Executes ID part from user input

    response = requests.get(url=f'https://api.spotify.com/v1/{playlist_type}s/{playlist_id}',
                            headers={"Authorization": f"{spotify_token.token_type} "
                                                      f"{spotify_token.access_token}"}).json()
    response_status = get_response_status(response)
    if response_status == 'Success':
        global songs_response
        songs_response = response
        send_specific_info(message, from_link=True)
    else:
        bot.send_message(message.chat.id, str(response_status))


# Makes request to spotify server with title, organizes response and sends message with list of results
def find_playlist(message, request_search_type=search_type, page=0, prev=False):
    if not prev:
        global msgs_list
        msgs_list.set_current_msg(message, find_playlist)
    global search_type

    global title

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
                                "type": f"{search_type}",
                                "limit": f"{search_limit}",
                                "offset": search_limit * page
                            }).json()
    response_status = get_response_status(response)

    if response_status == 'Success':
        # Make prev/next page buttons markup
        inline_markup = types.InlineKeyboardMarkup(row_width=5)
        prev_button = types.InlineKeyboardButton('◀️Prev page', callback_data=f'prev_page_{page}')
        next_button = types.InlineKeyboardButton('Next page▶️', callback_data=f'next_page_{page}')
        inline_markup.add(types.InlineKeyboardButton(f'Page: {page + 1}', callback_data='current_page'))

        if response[list(response)[0]]['previous'] is not None:  # Adding next\prev buttons
            if response[list(response)[0]]['next'] is not None:  # according to their existence
                inline_markup.add(prev_button, next_button)
            else:
                inline_markup.add(prev_button)
        else:
            inline_markup.add(next_button)

        inline_markup = add_back_button(inline_markup, no_delete=True)

        user_choice_buttons = {}  # Dict with inline keyboard buttons, for integrating them in further results loop
        # in structure "item number": "type_id" (for callback data)

        # Organizing and filtering response in dict variables above according to search type.
        # Dict structure: {"result_index": {
        #                      "key": "value",
        #                      ...
        #                  },
        #                  ...}

        text = f'Results for {title}:\n\n'

        if search_type == 'album' or search_type == 'album,playlist':
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
                item_symbol = f'A{number_emojis.get(f"{key}")}'  # Adds emoji number from index
                text += f'{item_symbol}: '
                # Adds name of album (with hyperlink), artist and year
                text += f'<a href=\"{value["link"]}\">{value["name"]}</a> by {value["artist"]}, {value["year"]}\n'
                user_choice_buttons.update({f'{item_symbol}': f'album_{value["id"]}'})
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
                item_symbol = f'P{number_emojis.get(f"{key}")}'
                text += f'{item_symbol}: '
                text += f'<a href=\"{value["link"]}\">{value["name"]}</a> by {value["owner"]}, ' \
                        f'{value["tracks_total"]} songs\n'
                user_choice_buttons.update({f'{item_symbol}': f'playlist_{value["id"]}'})

        # Adding user choice buttons
        buttons_list = []
        for name, cb_data in user_choice_buttons.items():
            buttons_list.append(types.InlineKeyboardButton(f'{name}', callback_data=f'{cb_data}'))
        inline_markup.add(*buttons_list, row_width=5)

        bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id,
                              text=f'{text}', parse_mode='HTML',
                              disable_web_page_preview=True, reply_markup=inline_markup)
    else:
        bot.send_message(message.chat.id, f'{response_status}')


# Checks if response is valid. Otherwise, returns error code and description
def get_response_status(response):
    if not response.get('error'):
        return 'Success'
    else:
        return f'Connection error {response["error"]["status"]}: 'f'{response["error"]["message"]}'


def get_item_by_id(message):  # Executes when user press button with item choice.
    global item
    item_type = str(str(item).split('_')[0])  # Get item type
    item_id = str(str(item).split('_')[1])  # Get item id

    # Send response to get list of songs in item
    response = requests.get(url=f'https://api.spotify.com/v1/{item_type}s/{item_id}',
                            headers={"Authorization": f"{spotify_token.token_type} "
                                                      f"{spotify_token.access_token}"}).json()
    response_status = get_response_status(response)
    if response_status == 'Success':
        global songs_response
        global search_type
        songs_response = response
        search_type = item_type
        send_specific_info(message)
    else:
        bot.send_message(message.chat.id, str(response_status))


def send_specific_info(
        message, from_link=False, prev=False, sorting=bpm_sorting, page=0
):  # Sends specific info about item in message

    if not prev:
        global msgs_list
        msgs_list.set_current_msg(message, send_specific_info)

    if from_link:  # If user got here from pasting link, not from search menu
        inline_markup = add_back_button(with_input=True)
    else:
        inline_markup = add_back_button(no_delete=True)

    sort_by_bpm_asc_button = types.InlineKeyboardButton('Sort by BPM ↓', callback_data="sort_bpm_asc")
    sort_by_bpm_desc_button = types.InlineKeyboardButton('Sort by BPM ↑', callback_data="sort_bpm_desc")
    inline_markup.add(sort_by_bpm_asc_button, sort_by_bpm_desc_button)

    global songs_response
    global search_type
    # Response to get additional info
    ids = ''
    if search_type == 'album':
        for song in songs_response["tracks"]["items"]:
            ids += f'{song["id"]},'
    elif search_type == 'playlist':
        for song in songs_response["tracks"]["items"]:
            ids += f'{song["track"]["id"]},'
    additional_songs_response = requests.get(url='https://api.spotify.com/v1/audio-features',
                                             headers={"Authorization": f"{spotify_token.token_type} "
                                                                       f"{spotify_token.access_token}"},
                                             params={'ids': f'{ids}'}).json()

    text = f'{songs_response["type"]} {songs_response["name"]}:\n' \
           f'(Press on number to open track on spotify)\n'

    # Storage for item songs and their info
    songs = {}

    # Iterating through item to get songs id and name
    if search_type == 'album':
        for idx, song in enumerate(songs_response["tracks"]["items"], start=1):
            songs.update({f'{idx}': {
                "id": song["id"],
                "name": song["name"],
                "link": song["external_urls"]["spotify"]
            }})
            if len(song["external_urls"]) > 1:
                print(song["external_urls"])
    elif search_type == 'playlist':
        for idx, song in enumerate(songs_response["tracks"]["items"], start=1):
            songs.update({f'{idx}': {
                "id": song["track"]["id"],
                "name": song["track"]["name"],
                "link": song["track"]["external_urls"]["spotify"]
            }})
            if len(song["tracks"]["external_urls"]) > 1:
                print(song["external_urls"])
    # Iterating through additional info response and updating songs dict
    for idx, song in enumerate(additional_songs_response['audio_features'], start=1):
        songs[str(idx)].update({
            "duration": f'{song["duration_ms"]}',
            "tempo": f'{song["tempo"]}'
        })

    if sorting != 'default':
        songs = {k: songs[k] for k in sorted(songs, key=lambda itm_idx: int(songs[itm_idx]['tempo']),
                                             reverse=True if sorting == 'desc' else False)}

    print('Sorting: ' + str(sorting))

    songs_on_page = 20
    low_item_in_list_idx = page * songs_on_page
    high_item_in_list_idx = (page + 1) * songs_on_page
    pages_total = len(songs.items()) / songs_on_page + 1

    for idx, song in songs.items():  # Add line for each song
        if low_item_in_list_idx < int(idx) < high_item_in_list_idx:
            text += f'<a href="{song["link"]}">{idx}</a>: {song["name"]}, {song["tempo"]} BPM\n'

    prev_page_button = types.InlineKeyboardButton('Prev page', callback_data=f"songs_prev_{page}")
    next_page_button = types.InlineKeyboardButton('Next page', callback_data=f"songs_next_{page}")
    if page:  # If page is not first
        if page != pages_total:  # If page is not last
            inline_markup.add(prev_page_button, next_page_button)
        else:
            inline_markup.add(prev_page_button)
    else:
        inline_markup.add(next_page_button)

    if from_link:
        bot.send_message(chat_id=message.chat.id, text=text, reply_markup=inline_markup, parse_mode='HTML')
    else:
        bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id,
                              text=text, reply_markup=inline_markup, parse_mode='HTML')

    # Split message if it is longer than 4096 letters
    # if len(text) > 4096:
    #     edit_long_message_text(text[:4096])
    #     for x in range(4096, len(text), 4096):
    #         edit_long_message_text(text[x:x + 4096])
    # else:
    #     edit_long_message_text(text)


# Handler of inline keyboard buttons
@bot.callback_query_handler(func=lambda message: True)
def callback_query(call):
    global search_type
    # Triggers when user selects type of search
    if call.data.startswith('type_'):
        search_type = ''
        search_type = str(call.data).replace('type_', '')
        find_playlist(call.message, request_search_type=search_type)

    # Triggers when user changes page in album search
    if 'page' in call.data:
        # Previous page in search results
        if call.data.startswith('prev'):
            find_playlist(call.message, request_search_type=search_type, page=int(call.data[-1]) - 1, prev=True)
        # Next page in search results
        if call.data.startswith('next'):
            find_playlist(call.message, request_search_type=search_type, page=int(call.data[-1]) + 1, prev=True)

    # Triggers when user makes choice of item. Callback structure: type_id (album_f3gsb4, playlist_bvw4bv2, etc.)
    if call.data.startswith('album') or call.data.startswith('playlist'):
        global item
        item = call.data

        get_item_by_id(call.message)

    # Triggers when user presses back button
    if call.data.startswith('back'):
        bot.clear_step_handler(call.message)
        if call.data != 'back_no_delete':
            bot.delete_message(call.message.chat.id, call.message.id)
        if call.data == 'back_with_input':
            bot.delete_message(call.message.chat.id, call.message.id - 1)
            bot.delete_message(call.message.chat.id, call.message.id - 2)
        global msgs_list
        msgs_list.send_prev_msg()

    global bpm_sorting
    # Triggers when user press "sort" button
    if call.data == 'sort_bpm_asc':
        bpm_sorting = 'asc'
        send_specific_info(call.message, prev=True)
    if call.data == 'sort_bpm_asc':
        bpm_sorting = 'desc'
        send_specific_info(call.message, prev=True)

    # Triggers when user changes pages on result songs page
    if 'songs_prev' in call.data:
        send_specific_info(call.message, prev=True, page=int(call.data[-1]) - 1)
    if 'songs_next' in call.data:
        send_specific_info(call.message, prev=True, page=int(call.data[-1]) + 1)


print('Bot polling...')
bot.infinity_polling(timeout=10, long_polling_timeout=5)
