from collections.abc import Mapping
import json
import os
import random
import time
import re

import spotifython
import click
from click import shell_completion
import configparser
import logging


def load_authentication(
    cache_dir: str, config: configparser.ConfigParser
) -> spotifython.Authentication:
    # try to load authentication data from cache; default to config
    file_name = os.path.join(cache_dir, "authentication")
    if os.path.exists(file_name):
        with open(file_name, "r") as auth_file:
            authentication = spotifython.Authentication.from_dict(json.load(auth_file))
    else:
        if "client_secret" in config["Authentication"].keys():
            client_secret = config["Authentication"]["client_secret"]
        else:
            assert "client_secret_command" in config["Authentication"].keys()
            import subprocess
            import shlex

            cmdline = shlex.split(config["Authentication"]["client_secret_command"])
            proc = subprocess.Popen(cmdline, stdout=subprocess.PIPE)
            client_secret = str(proc.communicate()[0], encoding="utf-8").strip()

        authentication = spotifython.Authentication(
            client_id=config["Authentication"]["client_id"],
            client_secret=client_secret,
            scope="playlist-read-private user-modify-playback-state user-library-read user-read-playback-state "
            "user-read-currently-playing user-read-recently-played user-read-playback-position user-read-private "
            "playlist-modify-public playlist-modify-private",
        )
    return authentication


def dmenu_query(
    prompt: str, options: list[str], config: configparser.ConfigParser
) -> list[str]:
    import subprocess
    import shlex

    input_str = "\n".join(options) + "\n"

    if "interface" in config and "dmenu_cmdline" in config["interface"]:
        cmdline = shlex.split(
            config["interface"]["dmenu_cmdline"].format(
                prompt=f"'{prompt}'", lines=str(len(options))
            )
        )
    else:
        raise FileNotFoundError("dmenu command")

    proc = subprocess.Popen(cmdline, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    return str(
        proc.communicate(bytes(input_str, encoding="utf-8"))[0], encoding="utf-8"
    ).split("\n")


def dmenu_select(
    prompt: str,
    options: Mapping[str, spotifython.Cacheable],
    config: configparser.ConfigParser,
) -> list[spotifython.Cacheable]:
    selected = dmenu_query(prompt, list(options.keys()), config)

    return [options[sel] for sel in selected if sel in options]


class MutuallyExclusiveOption(click.Option):
    def __init__(self, *args, **kwargs):
        self.mutually_exclusive = set(kwargs.pop("mutually_exclusive", []))
        super(MutuallyExclusiveOption, self).__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        if self.mutually_exclusive.intersection(opts) and self.name in opts:
            raise click.UsageError(
                "Illegal usage: `{}` is mutually exclusive with "
                "arguments `{}`.".format(self.name, ", ".join(self.mutually_exclusive))
            )

        return super(MutuallyExclusiveOption, self).handle_parse_result(ctx, opts, args)


class QuietChoice(click.Choice):
    def get_metavar(self, param: click.Parameter):
        return param.human_readable_name


class UriType(click.ParamType):
    name = "spotify element uri or identifier"

    def convert(
        self, value: str | tuple[spotifython.URI], param, ctx: click.Context | None
    ) -> tuple[spotifython.URI]:
        # param is unused
        del param

        if isinstance(value, tuple):
            return value

        if ctx is not None:
            if (tmp := ctx.find_object(Context)) is not None:
                context: Context = tmp
            else:
                return tuple()
        else:
            return tuple()

        elements = []

        terms = re.split(r"(?<!(?<!\\)\\)@", value)
        match terms.pop(0):
            case "saved":
                if len(terms) == 0:
                    self.fail("no collection specicied")
                options = (
                    {"#saved tracks": context.client.saved_tracks}
                    | {
                        playlist.name.replace("\\", "\\\\")
                        .replace("#", "\\#")
                        .replace("@", "\\@"): playlist
                        for playlist in context.client.user_playlists
                    }
                    | {
                        album.name.replace("\\", "\\\\")
                        .replace("#", "\\#")
                        .replace("@", "\\@"): album
                        for album in context.client.saved_albums
                    }
                )
                term = terms.pop(0)
                if term == "#ask":
                    try:
                        elements = dmenu_select("collection: ", options, context.config)
                    except FileNotFoundError:
                        self.fail(
                            "config option `interface.dmenu_cmdline` is not configured correctly"
                        )
                else:
                    if term not in options:
                        self.fail(f"collection '{term}' not found")
                    elements.append(options[term])
            case "search":
                if len(terms) == 0:
                    self.fail("no search term specicied")
                term = terms.pop(0)
                if term == "#ask":
                    try:
                        term = dmenu_query("search:", [], context.config)[0]
                    except FileNotFoundError:
                        self.fail(
                            "config option `interface.dmenu_cmdline` is not configured correctly"
                        )
                if term == "":
                    return tuple()
                results = context.client.search(
                    term, "track,album,playlist,episode,show", limit=10
                )
                try:
                    options = {
                        f"{type_name:<10}{elem.name}": elem
                        for type_name, elements in results.items()
                        for elem in elements
                    }
                    elements = dmenu_select("results: ", options, context.config)
                except FileNotFoundError:
                    logging.warning(
                        "config option `interface.dmenu_cmdline` is not configured correctly"
                    )
                    if len(results["tracks"]) == 0:
                        self.fail("no search results")
                    elements.append(results["tracks"][0])
            case uri:
                try:
                    elements.append(context.client.get_element(spotifython.URI(uri)))
                except AssertionError as e:
                    self.fail(str(e))

        logging.debug(f"selecting from: {elements}")
        ret = []
        for elem in elements:
            if isinstance(elem, spotifython.Playable):
                ret.append(elem)
                continue

            assert isinstance(elem, spotifython.PlayContext)
            if len(terms) == 0:
                terms = ["#ask"]

            if terms[0] == "#all":
                ret += elem.items
                continue

            if terms[0] == "#ask":
                options = {item.name: item for item in elem.items}
                try:
                    ret += dmenu_select("songs: ", options, context.config)
                except FileNotFoundError:
                    self.fail(
                        "config option `interface.dmenu_cmdline` is not configured correctly"
                    )
            ret += [item for item in elem.items if item.name.startswith(terms[0])]
        logging.debug(f"selected: {ret}")
        return tuple(elem.uri for elem in ret)

    def complete_initial(
        self,
        client: spotifython.Client,
        terms: list[str],
    ) -> (
        list[shell_completion.CompletionItem] | tuple[str, spotifython.Cacheable | None]
    ):
        match terms[0][:2]:
            case "sp":  # spotify uri
                uri_types = ["album", "playlist", "show", "track", "episode"]
                uri_elems = terms[0].split(":")

                if uri_elems[0] != "spotify" or len(uri_elems) == 1:
                    return [
                        shell_completion.CompletionItem("spotify:"),
                        shell_completion.CompletionItem("spotify:_"),
                    ]
                if uri_elems[1] in uri_types:
                    prefix = terms[0]
                    try:
                        uri = spotifython.URI(terms.pop(0))
                        elem = client.get_element(uri)
                        elem.name
                        return (prefix, elem)
                    except:
                        return []
                else:
                    ret = [
                        f"spotify:{t}:" for t in uri_types if t.startswith(uri_elems[1])
                    ]
                    if len(ret) == 1:
                        ret.append(ret[0] + "_")
                    elif len(ret) == 0:
                        ret = [f"spotify:{t}:" for t in uri_types]
                    return [shell_completion.CompletionItem(e) for e in ret]
            case "se":  # search
                if len(terms) < 2:
                    return [
                        shell_completion.CompletionItem("search@"),
                        shell_completion.CompletionItem("search@_"),
                    ]
                if terms[1].startswith("#"):
                    if terms[1] != "#ask":
                        return [
                            shell_completion.CompletionItem("search@#ask"),
                            shell_completion.CompletionItem("search@#ask_"),
                        ]
                    terms.pop(0)
                    terms.pop(0)
                    return ("search@#ask", None)
                elif len(terms) == 2:
                    return []
                else:
                    terms.pop(0)
                    return (f"search@{terms.pop(0)}@", None)
            case "sa":  # saved
                if len(terms) < 2:
                    return [
                        shell_completion.CompletionItem("saved@"),
                        shell_completion.CompletionItem("saved@_"),
                    ]
                if terms[1].startswith("#"):
                    if terms[1] != "#saved tracks":
                        return [
                            shell_completion.CompletionItem("saved@#saved tracks"),
                            shell_completion.CompletionItem("saved@#saved tracks_"),
                        ]
                    terms.pop(0)
                    terms.pop(0)
                    return ("saved@#saved tracks", client.saved_tracks)
                else:
                    options = {
                        playlist.name.replace("\\", "\\\\")
                        .replace("#", "\\#")
                        .replace("@", "\\@"): playlist
                        for playlist in client.user_playlists
                    } | {
                        album.name.replace("\\", "\\\\")
                        .replace("#", "\\#")
                        .replace("@", "\\@"): album
                        for album in client.saved_albums
                    }
                    ret = [o for o in options.keys() if o.startswith(terms[1])]
                    if terms[1] in ret and len(terms) > 2:
                        ret = [terms[1]]
                    if len(ret) == 1:
                        terms.pop(0)
                        terms.pop(0)
                        return (f"saved@{ret[0]}", options[ret[0]])
                    else:
                        if len(ret) == 0 or terms[1] == "":
                            ret = list(options.keys()) + ["#saved tracks"]
                        return [
                            shell_completion.CompletionItem(f"saved@{e}") for e in ret
                        ]
        return [
            shell_completion.CompletionItem("saved@", help="saved collections"),
            shell_completion.CompletionItem("search@", help="spotify general search"),
            shell_completion.CompletionItem("spotify\\:", help="spotify uri"),
        ]

    def shell_complete(
        self, ctx, param, incomplete
    ) -> list[shell_completion.CompletionItem]:
        # param is unused
        del param

        context = Context(ctx.find_root().params)
        client = context.client
        terms = re.split(r"(?<!(?<!\\)\\)@", incomplete)

        try:
            ret = self.complete_initial(client, terms)
        except:
            return []
        if isinstance(ret, list):
            return ret

        prefix = ret[0]
        elem = ret[1]

        if isinstance(elem, spotifython.Playable):
            return [shell_completion.CompletionItem(prefix)]

        if len(terms) == 0:
            return [
                shell_completion.CompletionItem(prefix),
                shell_completion.CompletionItem(prefix + "_"),
            ]

        # assume playlist

        if terms[0].startswith("#"):
            possible = [o for o in ("#ask", "#all") if o.startswith(terms[0])]
            if len(possible) == 1:
                return [shell_completion.CompletionItem(prefix + "@" + possible[0])]
            return [
                shell_completion.CompletionItem(prefix + "@#ask"),
                shell_completion.CompletionItem(prefix + "@#all"),
            ]

        if elem is None:
            return [
                shell_completion.CompletionItem(prefix + "@" + terms[0]),
                shell_completion.CompletionItem(prefix + "@" + terms[0] + "_"),
            ]

        assert isinstance(elem, spotifython.PlayContext)

        options = [item.name for item in elem.items] + ["#ask", "#all"]

        possible = [opt for opt in options if opt.startswith(terms[0])]
        if len(possible) == 0:
            possible = options

        return [shell_completion.CompletionItem(prefix + "@" + opt) for opt in possible]


class Context:
    def __init__(self, cli_params: dict[str, str]):
        self._auth: spotifython.Authentication | None = None
        self.config: configparser.ConfigParser = configparser.ConfigParser()
        self.config.read(cli_params["config"])

        self._cache_dir: str = os.path.join(
            os.getenv(
                "XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache")
            ),
            "spotifython-cli",
        )
        self._auth = load_authentication(cache_dir=self._cache_dir, config=self.config)
        self.client: spotifython.Client = spotifython.Client(
            cache_dir=self._cache_dir,
            authentication=self._auth,
        )

        self.device_id: str | None = (
            cli_params["device_id"] or self.config["playback"].get("device_id", None)
            if "playback" in self.config
            else None
        )

    def __del__(self):
        # cache authentication data
        if self._auth is None:
            return
        try:
            with open(
                os.path.join(self._cache_dir, "authentication"), "w"
            ) as auth_file:
                json.dump(self._auth.to_dict(), auth_file)
        except:
            pass


@click.group()
@click.option("-v", "--verbose", count=True)
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True, dir_okay=False),
    default=lambda: os.path.join(
        os.getenv("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config")),
        "spotifython-cli",
        "config",
    ),
)
@click.option("--device-id", help="id of the device to use for playback")
@click.version_option()
@click.pass_context
def cli(ctx, verbose: int, device_id: str, config: str):
    # param is unused
    del device_id, config

    if verbose >= 2:
        logging.basicConfig(level=logging.DEBUG)
    elif verbose >= 1:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    ctx.obj = Context(ctx.params)


@cli.command("play")
@click.option("-s/-S", "--shuffle/--no-shuffle")
@click.option("-r/-R", "--reverse/--no-reverse")
@click.option(
    "--queue", is_flag=True, help="add elements to queue instead of playing them"
)
@click.option(
    "--from-ask", is_flag=True, help="query using dmenu from which track to start"
)
@click.option(
    "--to-ask", is_flag=True, help="query using dmenu until which track to play"
)
@click.argument("elements", nargs=-1, type=UriType())
@click.pass_context
def play(
    context: click.Context,
    shuffle: bool,
    reverse: bool,
    queue: bool,
    from_ask: bool,
    to_ask: bool,
    elements: tuple[tuple[spotifython.URI]],
):
    """
    start playback


    Elements begin with either a spotify uri or the literal string "search" or "saved". Specifiers are seperated by an '@'.

    After "saved" must be the name of a saved playlist, saved album or "#saved tracks".

    After "search" must be the search term. The search results will be displayed using the config value `interface.dmenu_cmdline`. If that is not specicied, the first song will be used.

    After a collection is selected, the next literal will select the track.
    The special value "#all" selects all entries.
    If no selector is specified, the implementation will default to "#ask".
    If a track is selected, this will be ignored.

    Every literal may be replaced by "#ask" in which case `interface.dmenu_cmdline` will be used.
    A backslash '\\' can be used to escape a literal '@', '#' or '\\'.
    """
    if (tmp := context.find_object(Context)) is not None:
        ctx: Context = tmp
    else:
        raise Exception("code structure invalid")

    if ctx.device_id is not None:
        device_id: str | None = ctx.device_id
    else:
        try:
            device_id = str(ctx.client.devices[0]["id"])
        except IndexError:
            device_id = None

    uris = [uri for uri_list in elements for uri in uri_list]

    if shuffle:
        random.shuffle(uris)
    elif reverse:
        uris.reverse()

    if from_ask:
        options = {ctx.client.get_element(uri).name: uri for uri in uris}
        first = dmenu_query("first:", list(options.keys()), ctx.config)
        if len(first) > 0 and first[0] in options:
            while uris[0] != options[first[0]]:
                uris.pop(0)

    if to_ask:
        uris.reverse()
        options = {ctx.client.get_element(uri).name: uri for uri in uris}
        last = dmenu_query("last:", list(options.keys()), ctx.config)
        if len(last) > 0 and last[0] in options:
            while uris[0] != options[last[0]]:
                uris.pop(0)
        uris.reverse()

    if queue:
        for uri in uris[:50]:
            ctx.client.add_to_queue(uri, device_id=device_id)
        return

    # spotify api can't handle more elements
    uris = uris[:700]

    if len(uris) == 0:
        uris = None

    try:
        ctx.client.play(uris, device_id=device_id)
    except spotifython.NotFoundException:
        if device_id is not None:
            ctx.client.transfer_playback(device_id=device_id)
            time.sleep(1)
            ctx.client.play(uris, device_id=device_id)


@cli.command("pause")
@click.pass_context
def pause(context: click.Context):
    """
    pause playback
    """
    if (tmp := context.find_object(Context)) is not None:
        ctx: Context = tmp
    else:
        raise Exception("code structure invalid")
    ctx.client.pause(device_id=ctx.device_id)


@cli.command("play-pause")
@click.pass_context
def play_pause(context: click.Context):
    """
    toggle between play/pause
    """
    if (tmp := context.find_object(Context)) is not None:
        ctx: Context = tmp
    else:
        raise Exception("code structure invalid")
    data = ctx.client.get_playing()

    if data is None or not data["is_playing"]:
        try:
            ctx.client.play(device_id=ctx.device_id)
        except spotifython.NotFoundException:
            if ctx.device_id is not None:
                device_id: str | None = ctx.device_id
            else:
                try:
                    device_id = str(ctx.client.devices[0]["id"])
                except IndexError:
                    device_id = None
            if device_id is not None:
                ctx.client.transfer_playback(device_id=device_id)
                time.sleep(1)
                ctx.client.play(device_id=device_id)
    else:
        ctx.client.pause(device_id=ctx.device_id)


@cli.command("next")
@click.pass_context
def next(context: click.Context):
    """
    skip to next song
    """
    if (tmp := context.find_object(Context)) is not None:
        ctx: Context = tmp
    else:
        raise Exception("code structure invalid")
    ctx.client.next(device_id=ctx.device_id)


@cli.command("prev")
@click.pass_context
def prev(context: click.Context):
    """
    skip to previous song
    """
    if (tmp := context.find_object(Context)) is not None:
        ctx: Context = tmp
    else:
        raise Exception("code structure invalid")
    ctx.client.prev(device_id=ctx.device_id)


def device_complete(ctx: click.Context, param, incomplete: str):
    del param

    context = Context(ctx.find_root().params)

    devices = context.client.devices

    devices.append({"id": "#ask", "name": "query user"})

    options = [device for device in devices if device["id"].startswith(incomplete)]
    return [shell_completion.CompletionItem(o["id"], help=o["name"]) for o in options]


@cli.command("device")
@click.argument("device-id", shell_complete=device_complete)
@click.pass_context
def device(context: click.Context, device_id: str):
    """
    select device to play on
    """
    if (tmp := context.find_object(Context)) is not None:
        ctx: Context = tmp
    else:
        raise Exception("code structure invalid")

    if device_id == "#ask":
        options = [f"{d['id']} - {d['name']}" for d in ctx.client.devices]
        selected = [
            s for s in dmenu_query("device: ", options, ctx.config) if s in options
        ]

        if len(selected) == 0:
            return
        device_id = selected[0].split(" - ")[0]

    ctx.client.transfer_playback(device_id, True)


@cli.command("metadata")
@click.option(
    "--format",
    help="string to format with the builtin python method using the fields as kwargs",
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["output-json"],
)
@click.option(
    "-j",
    "--output-json",
    is_flag=True,
    help="output in json format",
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["format"],
)
@click.argument(
    "fields",
    nargs=-1,
    type=QuietChoice(
        [
            "item",
            "title",
            "context",
            "context_name",
            "artist",
            "artist_name",
            "device",
            "device_id",
            "images",
            "shuffle_state",
            "repeat_state",
            "timestamp",
            "progress_ms",
            "currently_playing_type",
            "actions",
            "is_playing",
        ],
        case_sensitive=False,
    ),
)
@click.pass_context
def metadata(
    context: click.Context, output_json: bool, format: str | None, fields: tuple[str]
):
    """
    get metadata about the playback state

    Possible fields are: item, title, context, context_name, artist, artist_name, device, device_id, images, shuffle_state, repeat_state, timestamp, progress_ms, currently_playing_type, actions, is_playing

    NOTE: The options `output-json` and `format` are mutually exclusive.
    """
    if (tmp := context.find_object(Context)) is not None:
        ctx: Context = tmp
    else:
        raise Exception("code structure invalid")

    data = ctx.client.get_playing() or {
        "is_playing": False,
        "item": None,
        "context": None,
        "device": None,
    }
    print_data = {}

    data["title"] = data["item"].name if data["item"] is not None else None
    data["images"] = data["item"].images if data["item"] is not None else None
    data["context_name"] = data["context"].name if data["context"] is not None else None
    data["artist"] = data["item"].artists[0] if data["item"] is not None else None
    data["artist_name"] = data["artist"].name if data["artist"] is not None else None
    data["device_id"] = data["device"]["id"] if data["device"] is not None else None

    for field in fields:
        print_data[field] = data[field]

    if print_data == {}:
        print_data = data

    if output_json:
        for key, item in print_data.items():
            if not isinstance(item, spotifython.Cacheable):
                continue
            print_data[key] = item.to_dict(minimal=True)
            print_data[key].pop("requested_time", None)
        print(json.dumps(print_data))
        return
    if format is not None:
        try:
            print(format.format(**data))
        except KeyError as e:
            logging.error(f"field {e} not found")
        return
    for key, item in print_data.copy().items():
        if isinstance(item, (spotifython.Cacheable | dict | list)):
            del print_data[key]
    if len(print_data) == 1:
        print(str(print_data[list(print_data.keys())[0]]))
        return
    for key, value in print_data.items():
        print(f"{(key + ': '):<24}{str(value)}")
