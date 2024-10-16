#!/usr/bin/python3

import argparse
import asyncio
import datetime
import logging
import pprint
import sys

import aiohttp
from enum import Enum

#import smarttub, spalight
from smarttub import SmartTub

# old remove
import requests
import time
import json
import math
from requests.exceptions import HTTPError

import logging
import logging.config
import yaml

# local stuff
import influx
import myconfig
import mylogger

pp = pprint.PrettyPrinter(indent=4)

session = requests.Session()
verbose = 0
directory_base = "."

relay_state_map = {"CLOSED": 1.0, "OPEN": 0.0}
calls = 0


def push_data(measurement, data, tags={}):
    json_body = [
        {
            "measurement": measurement,
            "tags": tags,
            # we really should use the time from the call, but whatever
            # "time": datetime.utcfromtimestamp(int(data['ts'])).isoformat(),
            "time": datetime.datetime.utcnow().isoformat(),
            "fields": data,
        }
    ]
    mylogger.logger.debug(pp.pformat(json_body))
    mylogger.logger.debug("Point Json:")
    ic.write_points(json_body)


async def info_command(spas, args):
    for spa in spas:
        measurement = spa.name

        if args.debug:
            print(f"= Spa '{spa.name}' =\n")

        status = await spa.get_status()

########### STATUS

        status_dict = status.properties.copy()

        if args.all or args.status:
            print("== Status ==")
            pp.pprint(status_dict)
            print()

        data2push = {}
        data2push['status_water_temperature'] = status_dict['water']['temperature']
        data2push['status_ambient_temperature'] = status_dict['ambientTemperature']
        data2push['status_current_value'] = status_dict['current']['value']
        data2push['status_current_kwh'] = status_dict['current']['kwh']
        data2push['status_heater'] = status_dict['heater']
        data2push['status_ozone'] = status_dict['ozone']
        data2push['status_set_temperature'] = status_dict['setTemperature']
        data2push['status_state'] = status_dict['state']
        push_data(measurement, data2push, {})

########### PUMPS

        data2push = {}

        if args.all or args.pumps:
            print("== Pumps ==")

        for pump in await spa.get_pumps():
            if args.all or args.pumps:
                print(pump)
            data2push['pump_' + pump.type.name + '-' + pump.id] = pump.state.name

        if args.all or args.pumps:
            print()

        push_data(measurement, data2push, {})


########### LIGHTS

#<SpaLight 1: OFF (R 0/G 0/B 0/W 0) @ 0>    interior
#<SpaLight 2: OFF (R 0/G 0/B 0/W 0) @ 0>    exterior
#<SpaLight 3: OFF (R 0/G 0/B 0/W 0) @ 100>  status
#"<SpaLight {self.zone}: {self.mode.name} (R {self.red}/G {self.green}/B {self.blue}/W {self.white}) @ {self.intensity}>"

        data2push = {}

        class Light_zone(Enum):
            Interior = 1
            Exterior = 2
            Status = 3

        if args.all or args.lights:
            print("== Lights ==")

        try:
            for light in await spa.get_lights():
                if args.all or args.lights:
                    print(light)
                data2push['lights_' + Light_zone(light.zone).name + '_mode'] = light.mode.name
                data2push['lights_' + Light_zone(light.zone).name + '_color'] = light.red + light.green + light.blue + light.white
                data2push['lights_' + Light_zone(light.zone).name + '_intensity'] = light.intensity
            push_data(measurement, data2push, {})
        except KeyError as e:
            print(f'key error trying to find {e}')

        if args.all or args.lights:
            print()

########### ERRORS

        if args.all or args.errors:
            print("== Errors ==")

        # leaving this outside of debug to let us know if we get any errors
        for error in await spa.get_errors():
            print(error)

        if args.all or args.errors:
            print()

########### REMINDERS

#<SpaReminder WATER: INACTIVE/58/False>
#<SpaReminder AIR_FILTER: INACTIVE/58/False>
#<SpaReminder FILTER01: INACTIVE/58/False>
#<SpaReminder {self.id}: {self.state}/{self.remaining_days}/{self.snoozed}>

        data2push = {}

        if args.all or args.reminders:
            print("== Reminders ==")

        for reminder in await spa.get_reminders():
            if args.all or args.reminders:
                print(reminder)
            data2push['reminders_' + reminder.name + '_state'] = reminder.state
            data2push['reminders_' + reminder.name + '_remaining_days'] = reminder.remaining_days
            data2push['reminders_' + reminder.name + '_snoozed'] = reminder.snoozed

        push_data(measurement, data2push, {})

        if args.all or args.reminders:
            print()

########### LOCKS

#<SpaLock temperature: UNLOCKED>
#<SpaLock spa: UNLOCKED>
#<SpaLock access: UNLOCKED>
#<SpaLock maintenance: UNLOCKED>
#<SpaLock {self.kind}: {self.state}>

        data2push = {}

        if args.all or args.locks:
            print("== Locks ==")
        for lock in status.locks.values():
            data2push['locks_' + lock.kind + '_state'] = lock.state
            if args.all or args.locks:
                print(lock)

        if args.all or args.locks:
            print()

        push_data(measurement, data2push, {})

########### ENERGY

#[{'key': '2024-10-14', 'value': 0.3512727272727273},
# {'key': '2024-10-13', 'value': 0.4330909090909091},
# {'key': '2024-10-08', 'value': 0.5465454545454546}]

        if args.all or args.energy:
            energy_usage_day = spa.get_energy_usage(
                spa.EnergyUsageInterval.DAY,
                end_date=datetime.date.today(),
                start_date=datetime.date.today() - datetime.timedelta(days=7),
            )

            print("== Energy usage ==")
            pp.pprint(await energy_usage_day)
            print()

########### DEBUG

#{   'battery': {'percentCharge': None, 'voltage': None},
#    'freeMemory': 2685792,
#    'lastResetReason': 'RESET_REASON_POWER_DOWN',
#    'powerStatus': 'DC',
#    'resetCount': 22,
#    'uptime': {'connection': 273718, 'system': 274567, 'tubController': 274537}}

        data2push = {}

        debug_status = await spa.get_debug_status()

        if args.all or args.debug:
            print("== Debug status ==")
            pp.pprint(debug_status)
            print()

        for thing1 in debug_status:
            if type(debug_status[thing1]) is dict:
                for thing2 in debug_status[thing1]:
                    data2push['debug_' + thing1 + '_' + thing2] = debug_status[thing1][thing2]
            else:
                data2push['debug_' + thing1] = debug_status[thing1]

        push_data(measurement, data2push, {})



async def set_command(spas, args):
    for spa in spas:
        if args.temperature:
            await spa.set_temperature(args.temperature)

        if args.light_mode:
            for light in await spa.get_lights():
                if args.verbosity > 0:
                    print(light)
                mode = light.LightMode[args.light_mode]
                if mode == light.LightMode.OFF:
                    await light.set_mode(mode, 0)
                else:
                    await light.set_mode(mode, 50)

        if args.snooze_reminder:
            reminder_id, days = args.snooze_reminder
            days = int(days)
            reminder = next(
                reminder
                for reminder in await spa.get_reminders()
                if reminder.id == reminder_id
            )
            await reminder.snooze(days)

        if args.reset_reminder:
            reminder_id, days = args.reset_reminder
            days = int(days)
            reminder = next(
                reminder
                for reminder in await spa.get_reminders()
                if reminder.id == reminder_id
            )
            await reminder.reset(days)

        if args.lock:
            status = await spa.get_status()
            lock = status.locks[args.lock.lower()]
            await lock.lock()
            print("OK")

        if args.unlock:
            status = await spa.get_status()
            lock = status.locks[args.unlock.lower()]
            await lock.unlock()
            print("OK")


async def main(argv):
    global ic

    # create influx client
    ic = influx.InfluxClient()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbosity", action="count", default=0)
    parser.set_defaults(func=info_command)
    parser.add_argument(
        "-a", "--all", action="store_true", default=False,
        help="Show all info except location"
    )
    parser.add_argument("--spas", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument(
        "--location", action="store_true", help="Show GPS location"
    )
    parser.add_argument("--pumps", action="store_true")
    parser.add_argument("--lights", action="store_true")
    parser.add_argument("--errors", action="store_true")
    parser.add_argument("--reminders", action="store_true")
    parser.add_argument("--locks", action="store_true")
    parser.add_argument("--debug", default=False, action="store_true")
    parser.add_argument("--energy", action="store_true")

    args = parser.parse_args(argv)

    if args.verbosity > 1:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logging.basicConfig(level=log_level)

    async with aiohttp.ClientSession() as session:
        st = SmartTub(session)
        await st.login(myconfig.config["smarttub"]["username"], myconfig.config["smarttub"]["password"])

        account = await st.get_account()

        spas = await account.get_spas()

        await args.func(spas, args)


asyncio.run(main(sys.argv[1:]))
