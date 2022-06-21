#!/bin/env python3
import logging
import spotifython
import configparser
import json
import os
import sys
import argparse
import time
from distutils.util import strtobool


def dmenu_query(title: str, options: list[str]) -> list[str]:
    import subprocess

    input_str = "\n".join(options) + "\n"

    proc = subprocess.Popen(["dmenu", "-i", "-l", "50", "-p", title], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    return str(proc.communicate(bytes(input_str, encoding="utf-8"))[0], encoding="utf-8").split("\n")


# noinspection PyShadowingNames
def load_authentication(cache_dir: str, config: configparser.ConfigParser = None) -> spotifython.Authentication:
    # try to load authentication data from cache; default to config
    if os.path.exists(os.path.join(cache_dir, "authentication")):
        with open(os.path.join(cache_dir, "authentication"), 'r') as auth_file:
            authentication = spotifython.Authentication.from_dict(json.load(auth_file))
    else:
        authentication = spotifython.Authentication(
            client_id=config["Authentication"]["client_id"],
            client_secret=config["Authentication"]["client_secret"],
            scope="playlist-read-private user-modify-playback-state user-library-read user-read-playback-state user-read-currently-playing user-read-recently-played user-read-playback-position user-read-private"
        )
    return authentication


# noinspection PyShadowingNames
def play(client: spotifython.Client, args: argparse.Namespace, config: configparser.ConfigParser, **_):
    # noinspection PyShadowingNames
    def play_elements(client: spotifython.Client, uri_strings: list[str], device_id: str = None):
        uris = [spotifython.URI(uri_string=uri_string) for uri_string in uri_strings]
        if len(uris) == 1 and issubclass(uris[0].type, spotifython.PlayContext):
            client.play(context=uris[0], device_id=device_id)
            return

        uris = [uri for uri in uris if issubclass(uri.type, spotifython.Playable)]
        if len(uris) == 0:
            client.play(device_id=device_id)
            return
        client.play(uris, device_id=device_id)

    device_id = args.id or config["playback"]["device_id"] if "playback" in config and "device_id" in config["playback"] else None
    shuffle = bool(strtobool(args.shuffle)) if args.shuffle is not None else None
    elements = args.elements
    if args.playlist_dmenu or args.playlist is not None:
        playlists = {"saved tracks": str(client.me.uri) + ":collection"}
        for playlist in client.user_playlists:
            playlists[playlist.name] = str(playlist.uri)

        if args.playlist_dmenu:
            playlist = dmenu_query("playlist to play", options=list(playlists.keys()))
            if len(playlist) > 0 and playlist[0] in playlists:
                elements = [playlists[playlist[0]]]

        if args.playlist is not None:
            elements = [playlists[args.playlist]]

    try:
        play_elements(client, elements, device_id=device_id)
        if shuffle is not None:
            client.set_playback_shuffle(shuffle, device_id=device_id)

    except spotifython.NotFoundException:
        device_id = args.id or config["playback"]["device_id"] if "playback" in config and "device_id" in config["playback"] else client.devices[0]["id"]

        client.transfer_playback(device_id=device_id)
        if shuffle is not None:
            client.set_playback_shuffle(state=False, device_id=device_id)
            if shuffle:
                client.set_playback_shuffle(state=True, device_id=device_id)
        else:
            time.sleep(1)
        play_elements(client, elements, device_id=device_id)


# noinspection PyShadowingNames
def pause(client: spotifython.Client, args: argparse.Namespace, config: configparser.ConfigParser, **_):
    device_id = args.id or config["playback"]["device_id"] if "playback" in config and "device_id" in config["playback"] else None
    client.pause(device_id=device_id)


# noinspection PyShadowingNames
def metadata(client: spotifython.Client, cache_dir: str, args: argparse.Namespace, **_):
    if args.use_cache and os.path.exists(os.path.join(cache_dir, "status")):
        with open(os.path.join(cache_dir, "status")) as cache_file:
            data = {k: client.get_element_from_data(v) if isinstance(v, dict) and "uri" in v.keys() else v for k, v in json.load(cache_file).items()}
    else:
        data = client.get_playing()
    print_data = {}

    data["title"] = data["item"].name if data["item"] is not None else None
    data["images"] = data["item"].images if data["item"] is not None else None
    data["context_name"] = data["context"].name if data["context"] is not None else None
    data["artist"] = data["item"].artists[0] if data["item"] is not None else None
    data["artist_name"] = data["artist"].name if data["artist"] is not None else None
    data["device_id"] = data["device"]["id"]

    for key in data.keys():
        if key in args.fields:
            print_data[key] = data[key]

    if print_data == {}:
        print_data = data

    if args.json:
        for key, item in print_data.items():
            if not isinstance(item, spotifython.Cacheable):
                continue
            print_data[key] = item.to_dict(minimal=True)
        print(json.dumps(print_data))
        return
    if "format" in args and args.format is not None:
        try:
            print(args.format.format(**data))
        except KeyError as e:
            logging.error(f"field {e} not found")
        return
    for key, item in print_data.copy().items():
        if isinstance(item, (spotifython.Cacheable | dict | list)):
            del print_data[key]
    if len(print_data) == 1:
        print(str(print_data[list(print_data.keys())[0]]))
        return
    for (key, value) in print_data.items():
        print(f"{(key + ': '):<24}{str(value)}")


# noinspection PyShadowingNames
def shuffle(client: spotifython.Client, args: argparse.Namespace, **_):
    shuffle = bool(strtobool(args.state))
    client.set_playback_shuffle(state=shuffle, device_id=args.id)


# noinspection PyShadowingNames
def queue_next(client: spotifython.Client, args: argparse.Namespace, **_):
    client.next(device_id=args.id)


# noinspection PyShadowingNames
def queue_prev(client: spotifython.Client, args: argparse.Namespace, **_):
    client.prev(device_id=args.id)


# noinspection PyShadowingNames
def spotifyd(client: spotifython.Client, args: argparse.Namespace, cache_dir: str, config: configparser.ConfigParser, **_):
    # noinspection PyShadowingNames
    def send_notify(title: str, desc: str, image: str = None):
        import subprocess
        if image is None:
            subprocess.run(["notify-send", f'{title}', f'{desc}'])
        else:
            image = "--icon=" + image
            subprocess.run(["notify-send", image, f'{title}', f'{desc}'])

    data = client.get_playing()
    element = data["item"]
    desc = element.artists[0].name + " - " + element.album.name

    do_notify = True
    if os.path.exists(os.path.join(cache_dir, "status")):
        with open(os.path.join(cache_dir, "status"), 'r') as cache_file:
            cached_data = json.load(cache_file)
            if cached_data["item"]["uri"] == str(element.uri):
                do_notify = False

    with open(os.path.join(cache_dir, "status"), 'w') as cache_file:
        json.dump({k: v.to_dict(minimal=True) if isinstance(v, spotifython.Cacheable) else v for k, v in data.items()}, cache_file)

    if not data["is_playing"]:
        quit()

    if "spotifyd" in config.keys() and "notify" in config["spotifyd"].keys() and not config["spotifyd"]["notify"]:
        do_notify = False

    if not args.disable_notify and do_notify:
        images = element.images

        image_path = os.path.join(cache_dir, str(element.uri) + "-image")
        if not os.path.exists(image_path):
            # get smallest image
            if len(images) == 0:
                send_notify(title=element.name, desc=desc)
                return
            elif len(images) == 1:
                image = images[0]
            else:
                image = (sorted_images := {image["width"]: image for image in images})[min(list(sorted_images.keys()))]

            import requests

            response = requests.get(image["url"], allow_redirects=True)
            open(image_path, "wb").write(response.content)

        send_notify(title=element.name, desc=desc, image=image_path)


# noinspection PyShadowingNames
def add_queue_playlist(client: spotifython.Client, args: argparse.Namespace, config: configparser.ConfigParser, **_):
    # noinspection PyShadowingNames
    def add_names(titles: list[str], tracks: dict[str, spotifython.Playable]):
        for title in titles:
            if title not in tracks.keys():
                if title != "":
                    logging.error(f"track {title} not found in playlist {playlist.name}")
                continue
            try:
                client.add_to_queue(tracks[title], device_id=device_id)
            except spotifython.NotFoundException as e:
                error = json.loads(e.args[0])["error"]
                if error["reason"] == "NO_ACTIVE_DEVICE":
                    logging.error("add to queue: no active device found")
                    quit(1)
                raise e

    device_id = args.id or config["playback"]["device_id"] if "playback" in config and "device_id" in config["playback"] else None
    if args.playlist_uri is not None:
        playlist = client.get_playlist(args.playlist_uri, check_outdated=False)
    else:
        playlists = {"saved tracks": client.saved_tracks}
        for playlist in client.user_playlists:
            playlists[playlist.name] = playlist

        if args.playlist_dmenu:
            names = dmenu_query(title="playlist to choose song from: ", options=list(playlists.keys()))
            if len(names) == 0 or names[0] not in playlists.keys():
                quit(1)
            playlist = playlists[names[0]]
        else:
            if args.playlist not in playlists.keys():
                logging.error(f"playlist {args.playlist} not found")
                quit(1)
            playlist = playlists[args.playlist]

    items = playlist.items
    if not issubclass(playlist.uri.type, spotifython.SavedTracks):
        items.reverse()
    tracks = {item.name: item for item in items}

    add_names(titles=args.names, tracks=tracks)

    if not args.dmenu:
        return
    names = dmenu_query("songs to add to queue: ", options=list(tracks.keys()))
    add_names(titles=names, tracks=tracks)


def generate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="command line interface to spotifython intended for use with spotifyd", epilog="use 'spotifython-cli {-h --help}' with an command for more options", prog="spotifython-cli")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-v", "--verbose", action="count", default=0, help="use multiple time to increase verbosity level")
    group.add_argument("-q", "--quiet", action="store_true")
    subparsers = parser.add_subparsers(title="command", required=True)

    play_parser = subparsers.add_parser("play", help=(desc_str := "start playback"), description=desc_str)
    play_parser.add_argument("--device-id", help="id of the device to use for playback", dest="id")
    play_parser.add_argument("-s", "--shuffle", help="True/False")
    play_parser.add_argument("--playlist", help="name of the playlist in the library to play")
    play_parser.add_argument("elements", help="uris of the songs or playlist to start playing", nargs="*")
    play_parser.set_defaults(command=play)

    pause_parser = subparsers.add_parser("pause", help=(desc_str := "pause playback"), description=desc_str)
    pause_parser.add_argument("--device-id", help="id of the device to use for playback", dest="id")
    pause_parser.set_defaults(command=pause)

    metadata_parser = subparsers.add_parser(
        "metadata",
        help=(desc_str := "get metadata about the playback state"),
        description=desc_str + "; print all if no fields are given; some arguments are only valid as json output"
    )
    metadata_group = metadata_parser.add_mutually_exclusive_group()
    metadata_parser.add_argument(
        "fields", nargs="*", default="",
        choices=["item", "title", "context", "context_name", "artist", "artist_name", "device", "device_id", "images", "shuffle_state", "repeat_state", "timestamp",
                 "progress_ms", "currently_playing_type", "actions", "is_playing", ""],
        help="the fields you want to print"
    )
    metadata_group.add_argument("-j", "--json", help="output in json format", action="store_true")
    metadata_group.add_argument("--format", help="string to format with the builtin python method using the fields as kwargs")
    metadata_parser.set_defaults(command=metadata)

    shuffle_parser = subparsers.add_parser("shuffle", help=(desc_str := "set shuffle state"), description=desc_str)
    shuffle_parser.add_argument("--device-id", help="id of the device to use for playback", dest="id")
    shuffle_parser.add_argument("state", default="True", help="True/False", nargs="?")
    shuffle_parser.set_defaults(command=shuffle)

    next_parser = subparsers.add_parser("next", help=(desc_str := "skip to next song"), description=desc_str)
    next_parser.add_argument("--device-id", help="id of the device to use for playback", dest="id")
    next_parser.set_defaults(command=queue_next)

    prev_parser = subparsers.add_parser("prev", help=(desc_str := "skip to previous song"), description=desc_str)
    prev_parser.add_argument("--device-id", help="id of the device to use for playback", dest="id")
    prev_parser.set_defaults(command=queue_prev)

    queue_parser = subparsers.add_parser("queue", help=(desc_str := "add to the queue"), description=desc_str)
    queue_parser.add_argument("--device-id", help="id of the device to use for playback", dest="id")
    queue_sub = queue_parser.add_subparsers(title="sub command", required=True)

    queue_playlist_parser = queue_sub.add_parser("playlist", help=(desc_str := "add songs from a playlist to the queue"), description=desc_str)
    queue_playlist_group = queue_playlist_parser.add_mutually_exclusive_group(required=True)
    queue_playlist_group.add_argument("--playlist", help="name of the playlist to base the search on")
    queue_playlist_group.add_argument("--playlist-uri", help="uri of the playlist to base the search on")
    queue_playlist_parser.add_argument("names", help="names of the songs you want to add", nargs="*")
    queue_playlist_parser.set_defaults(command=add_queue_playlist)

    if sys.platform.startswith("linux"):
        play_parser.add_argument("--playlist-dmenu", help="query the user for a playlist name using dmenu and play it", action="store_true")

        metadata_parser.add_argument("-c", "--use-cache", action="store_true", help="Use the spotifyd cache instead of querying the api. Works only if spotifython-cli is spotifyd song_change_hook. (see 'spotifython-cli spotifyd -h')")

        queue_playlist_group.add_argument("--playlist-dmenu", help="query the user for the playlist name using dmenu", action="store_true")
        queue_playlist_parser.add_argument("--dmenu", help="query the user for additional titles using dmenu", action="store_true")

        spotifyd_parser = subparsers.add_parser("spotifyd", help=(desc_str := "set this in your spotifyd.conf as 'on_song_change_hook'"), description=desc_str)
        spotifyd_parser.add_argument("-n", "--disable-notify", help="don't send a notification via notify-send if the playerstate updates", action="store_true")
        spotifyd_parser.set_defaults(command=spotifyd)

    return parser


def main():
    cache_dir = os.path.expanduser("~/.cache/spotifython-cli")
    if not os.path.exists(cache_dir):
        os.mkdir(cache_dir, mode=0o755)
    config = configparser.ConfigParser()
    config.read(os.path.expanduser("~/.config/spotifython-cli/config"))

    args = generate_parser().parse_args()

    if args.quiet:
        logging.basicConfig(level=logging.ERROR)
    else:
        if args.verbose >= 2:
            logging.basicConfig(level=logging.DEBUG)
        elif args.verbose >= 1:
            logging.basicConfig(level=logging.INFO)
        else:
            logging.basicConfig(level=logging.WARNING)

    authentication = load_authentication(cache_dir=cache_dir, config=config)

    client = spotifython.Client(cache_dir=cache_dir, authentication=authentication)

    args.command(client=client, args=args, cache_dir=cache_dir, config=config)

    # cache authentication data
    with open(os.path.join(cache_dir, "authentication"), 'w') as auth_file:
        json.dump(authentication.to_dict(), auth_file)


if __name__ == "__main__":
    main()
