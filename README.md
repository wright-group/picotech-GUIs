# yaqd-picotech


[![yaq](https://img.shields.io/badge/framework-yaq-orange)](https://yaq.fyi/)
[![black](https://img.shields.io/badge/code--style-black-black)](https://black.readthedocs.io/)
[![ver](https://img.shields.io/badge/calver-YYYY.0M.MICRO-blue)](https://calver.org/)
[![log](https://img.shields.io/badge/change-log-informational)](https://gitlab.com/yaq/yaqd-picotech/-/blob/master/CHANGELOG.md)



This package contains GUI script python files using the following yaq daemon(s):

- https://yaq.fyi/daemons/yaqd-picotech-adc-triggered

which requires the daemon and associated yaqd_core repositories (Gitlab).

To get started, please copy or paste the text of the enclosed config.toml file into the config folder of this daemon.   This config can be easily accessed after daemon installation via the command `yaqd edit-config picotech-adc-triggered` .

# Scripts

--Yaq picotech picoscope 2000 series shot averager and chart recorder GUI for [Pico Technologies](https://www.picotech.com/) oscilloscopes and data loggers. The GUIs' default code is meant for triggering to be on channel A and signal collection on channel B of your Picoscope.   Internal triggering, if activated via the config.toml, requires a cable connect between the Picoscope AWG and the trigger channel.   The signal channel can be changed in the script as needed. Running the script requires python 3.8 or higher, the daemon to be running, and opening a command prompt and typing `python picotech_chart_gui.py [port]`  where `[port]` is the number found in the config.toml. Data (as `shotsdata.dat` and `chartdata.dat`) is saved in the folder containing this script.  You must rename this data and move to a new folder, as it will be overwritten on the next save.



# Installation

You will need the ps2000 drivers, which are available in the [Picotech SDK](https://www.picotech.com/downloads)  Additional modules may require installation.

