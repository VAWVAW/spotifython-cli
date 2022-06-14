#!/bin/env python3
import logging
import spotifython
import configparser
import json
import os
import sys
import argparse
import time


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
def play(client: spotifython.Client, args: argparse.Namespace, **_):
    # noinspection PyShadowingNames
    def play_elements(client: spotifython.Client, uri_strings: list[str]):
        uris = [spotifython.URI(uri_string=uri_string) for uri_string in uri_strings]
        if len(uris) == 1 and issubclass(uris[0].type, spotifython.PlayContext):
            client.play(context=uris[0])
            return

        uris = [uri for uri in uris if issubclass(uri.type, spotifython.Playable)]
        if len(uris) == 0:
            client.play()
            return
        client.play(uris)

    try:
        play_elements(client, args.elements)
    except spotifython.NotFoundException:
        device_id = args.id or client.devices[0]["id"]

        client.transfer_playback(device_id=device_id)
        client.set_playback_shuffle(state=False, device_id=device_id)
        if args.shuffle:
            client.set_playback_shuffle(state=True, device_id=device_id)
        else:
            time.sleep(1)
        play_elements(client, args.elements)


# noinspection PyShadowingNames
def pause(client: spotifython.Client, args: argparse.Namespace, **_):
    device_id = args.id or client.get_playing()["device"]["id"]
    client.pause(device_id=device_id)


# noinspection PyShadowingNames
def metadata(client: spotifython.Client, cache_dir: str, args: argparse.Namespace, **_):
    if args.use_cache and os.path.exists(os.path.join(cache_dir, "status")):
        with open(os.path.join(cache_dir, "status")) as cache_file:
            data = {k: client.get_element_from_data(v) if isinstance(v, dict) and "uri" in v.keys() else v for k, v in json.load(cache_file).items()}
    else:
        data = client.get_playing()
    print_data = {}

    data["title"] = data["item"].name
    data["images"] = data["item"].images
    data["context_name"] = data["context"].name
    data["artist"] = data["item"].artists[0]
    data["artist_name"] = data["artist"].name
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
    if "format" in args:
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
    client.set_playback_shuffle(state=args.state, device_id=args.id)


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
            image = "--icon="+image
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

            
def generate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="command line interface to spotifython intended for use with spotifyd", epilog="use 'spotifython-cli {-h --help}' with an command for more options")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-v", "--verbose", action="count", default=0, help="use multiple time to increase verbosity level")
    group.add_argument("-q", "--quiet", action="store_true")
    subparsers = parser.add_subparsers(title="command", required=True)

    play_parser = subparsers.add_parser("play", help=(desc_str := "start playback"), description=desc_str)
    play_parser.add_argument("--device-id", help="id of the device to use for playback", dest="id")
    play_parser.add_argument("-s", "--shuffle", action="store_true")
    play_parser.add_argument("elements", help="the songs or playlist to start playing", nargs="*")
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
        "fields", nargs="*",
        help="possible values are: device device_id shuffle_state repeat_state timestamp context context_name artist artist_name track progress_ms title currently_playing_type actions is_playing images item"
    )
    metadata_group.add_argument("-j", "--json", help="output in json format", action="store_true")
    metadata_group.add_argument("--format", help="string to format with the builtin python method using the fields as kwargs")
    metadata_parser.set_defaults(command=metadata)

    shuffle_parser = subparsers.add_parser("shuffle", help=(desc_str := "set shuffle state"), description=desc_str)
    shuffle_parser.add_argument("--device-id", help="id of the device to use for playback", dest="id")
    shuffle_parser.add_argument("state", type=bool, default=True, help="True/False")
    shuffle_parser.set_defaults(command=shuffle)

    next_parser = subparsers.add_parser("next", help=(desc_str := "skip to next song"), description=desc_str)
    next_parser.add_argument("--device-id", help="id of the device to use for playback", dest="id")
    next_parser.set_defaults(command=queue_next)

    prev_parser = subparsers.add_parser("prev", help=(desc_str := "skip to previous song"), description=desc_str)
    prev_parser.add_argument("--device-id", help="id of the device to use for playback", dest="id")
    prev_parser.set_defaults(command=queue_prev)

    if sys.platform.startswith("linux"):
        metadata_parser.add_argument("-c", "--use-cache", action="store_true", help="Use the spotifyd cache instead of querying the api. Works only if spotifython-cli is spotifyd song_change_hook. (see 'spotifython-cli spotifyd -h')")

        spotifyd_parser = subparsers.add_parser("spotifyd", help=(desc_str := "set this in your spotifyd.conf as 'on_song_change_hook'"), description=desc_str)
        spotifyd_parser.add_argument("-n", "--disable-notify", help="don't send a notification via notify-send if the playerstate updates", action="store_true")
        spotifyd_parser.set_defaults(command=spotifyd)

    return parser


if __name__ == "__main__":
    cache_dir = os.path.expanduser("~/.cache/spotifython-cli")
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
