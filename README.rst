spotifython-cli
==============

A command line interface to the Spotify API using `spotifython <https://github.com/vawvaw/spotifython>`_ as a backend.
This tool is developed for the use in scripting on linux and is integrated with the spotifyd player.
All API access except playback modification is readonly.

Dependencies
------------

- `spotifyd <https://github.com/Spotifyd/spotifyd>`_ for player integration
- `dmenu` for interactive selection of content

Example
-------

.. code:: sh

    spotifython-cli play

With dmenu:

.. code:: sh

    spotifython-cli queue playlist --playlist-dmenu --dmenu

Or for scripting:

.. code:: sh

    spotifython-cli metadata --format "{title:.30} - {artist_name:.18}"
