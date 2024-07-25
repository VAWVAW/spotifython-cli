spotifython-cli
===============

A command line interface to the Spotify API using `spotifython <https://github.com/vawvaw/spotifython>`_ as a backend.
This tool is developed for the use in scripting on linux and is integrated with the spotifyd player.
All API access except playback modification is readonly.

Installation
------------
**python 3.10 or higher is required**

.. code:: sh

    # Linux/macOS
    python3 -m pip install -U spotifython-cli
.. code:: sh

    # Windows
    py -3 -m pip install -U spotifython-cli

To install the development version, run:

.. code:: sh

    git clone https://github.com/vawvaw/spotifython-cli
    cd spotipython-cli
    python3 -m pip install -U .

Dependencies
++++++++++++

- `spotifyd <https://github.com/Spotifyd/spotifyd>`_ for player integration
- `dmenu` for interactive selection of content

Example
-------

.. code:: sh

    spotifython-cli play

With dmenu:

.. code:: sh

    spotifython-cli play --queue 'saved@#ask@#ask'

Or for scripting:

.. code:: sh

    spotifython-cli metadata --format "{title:.30} - {artist_name:.18}"

Config
------

`~/.config/spotifython-cli/config`

.. code::

    [Authentication]
    client_id = "your client id
    client_secret = "your client secret"
    # alternative to client_secret
    client_secret_command = "cat /path/to/client_secret"

    [spotifyd]
    notify = true   # optional

    [playback]
    device_id = "your playback device"  # optional

    [interface]
    # dmenu with custom options or a program with a similar interface (gets options on stdin and writes results to stdout)
    dmenu_cmdline = dmenu -i -l 50 -p {prompt} # optional

For help on how to obtain client id and secret refer to the `spotifython documentation <https://github.com/vawvaw/spotifython>`_.
