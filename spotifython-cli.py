import spotifython
import configparser
import json
import os


if __name__ == "__main__":
    cache_dir = os.path.expanduser("~/.cache/spotifython-cli")

    config = configparser.ConfigParser()
    config.read(os.path.expanduser("~/.config/spotifython-cli/config"))

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

    client = spotifython.Client(cache_dir=cache_dir, authentication=authentication)

    for playlist in client.user_playlists:
        print(playlist.name)

    # cache authentication data
    with open(os.path.join(cache_dir, "authentication"), 'w') as auth_file:
        json.dump(authentication.to_dict(), auth_file)
