chimera-supervisor plugin
=========================

This is a plugin for the chimera observatory control system https://github.com/astroufsc/chimera. It provides a
"observatory supervisor" controller. A supervisor is responsible for autonomously controlling the observatory. Its tasks
includes, but are not limited to, schedule a queue for the night, check the weather conditions and allow the telescope
to open or close under certain limits and send logging information to human watchers.

This module is extremely flexible. The user sets up a checklist, each item in the list has a series of checking
routines and can have a series of responses. Therefore, it is possible to configure the supervisor to check several
different actions on several different conditions and answer with a set of responses.

It also implements a Telegram bot, responsible for broadcasting messages from the module. User can also be queried
 to answer to specific actions.

Usage
-----

This controller uses a da

Installation
------------

Installation instructions. Dependencies, etc...

::

   pip install -U chimera_supervisor

or

::

    pip install -U git+https://github.com/astroufsc/chimera-supervisor.git


Configuration Example
---------------------

Here goes an example of the configuration to be added on ``chimera.config`` file.

::

    controller:
        type: Supervisor
        name: MyObservatoryManager
        freq: 0.025
        telegram-token: some-telegram-bot-token
        telegram-broascast-ids: user or group chat id
        telegram-listen-ids: user or group chat id
        telescope: /FakeTelescope/fake
        camera: /FakeCamera/fakeT80Cam
        dome: /FakeDome/fake
        weatherstations: /FakeWeatherStation/fake1,/FakeWeatherStation/fake2
        scheduler: /Scheduler/fake
        robobs: /RobObs/fake


Supervisor Configuration Example
--------------------------------

This is how you setup an action. Drop this to an yaml file and load it with the chimera-supervisor script.

::

    checklist:
      - name: Test3
        eager: False
        active: False
        check:
          - type: CheckInstrumentFlag
            instrument: telescope
            mode: 1
            flag: READY
        responses:
          - type: SendPhoto
            path: /Users/tiago/Downloads/filters_response.png
            message: This is a test...


Contact
-------

For more information, contact us on chimera's discussion list:
https://groups.google.com/forum/#!forum/chimera-discuss

Bug reports and patches are welcome and can be sent over our GitHub page:
https://github.com/astroufsc/chimera-manager/
