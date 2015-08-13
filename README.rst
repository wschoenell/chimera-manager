chimera-manager plugin
=======================

This is a plugin for the chimera observatory control system https://github.com/astroufsc/chimera. It provides a
"observatory manager" controller. A manager is responsible for autonomously controlling the observatory. Its tasks
includes, but are not limited to, schedule a queue for the night, check the weather conditions and allow the telescope
to open or close under certain limits and send logging information to human watchers.

Usage
-----

This controller

Installation
------------

Installation instructions. Dependencies, etc...

::

   pip install -U chimera_template

or

::

    pip install -U git+https://github.com/astroufsc/chimera-template.git


Configuration Example
---------------------

Here goes an example of the configuration to be added on ``chimera.config`` file.

::

    controller:
        name: MyObservatoryManager
        type: manager
        max_wind: 60 # maximum allowed wind speed in km/h
        max_humidity: 85 # maximum allowed external humidity in %
        min_temp: 1.0 # minimum allowed external temperature in Celsius
        min_dewpoint: 3.0 # minimum allowed external dew point temperature in Celsius
        min_sun_alt: -18  # Sun altitude at the beginning/end of the night in degrees
                          # (when the observations should start/end)
        close_on_none: True # Close if there is no information about the weather
        close_on_network: True # Close if there is no network connectivity
        scheduler_script: /path/to/scheduler # Command line path to the scheduler script. This is executed after the
                                             # end of the night clean up in preparation for next night


Contact
-------

For more information, contact us on chimera's discussion list:
https://groups.google.com/forum/#!forum/chimera-discuss

Bug reports and patches are welcome and can be sent over our GitHub page:
https://github.com/astroufsc/chimera-manager/
