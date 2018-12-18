# /usr/bin/env python
import logging
from datetime import datetime

import fhem
import pytz
import requests
from telegram.bot import Bot
from telegram.parsemode import ParseMode

from secrets import FHEM, RASPBEE, HEIZ, RASPBEE_IDS, HEIZ_LIST, FHEM_NAMES, TELEGRAM

logging.basicConfig()

fh = fhem.Fhem(FHEM['server'], port=FHEM['port'], protocol=FHEM['protocol'], loglevel=3, cafile=FHEM['cafile'],
               username=FHEM['username'], password=FHEM['password'])


def get_fhem(temp_list):
    temp_list.update({FHEM_NAMES[k]: v for k, v in fh.get_readings(['humidity', 'temperature'], name="Temp.*").items()})


def get_heiz(temp_list):
    temp_list.update(
        {HEIZ_LIST[z['name']]: {"temperature": {"Value": round(z['rawValue'] * 100) / 100, "Time": datetime.now()}}
         for z in requests.get('http://{}:{}/api/v1/live-data/'.format(HEIZ['ip'], HEIZ['port'])).json() if
         z['name'] in HEIZ_LIST})


def get_raspbee(temp_list):
    for k, v in RASPBEE_IDS.items():
        d = {}
        for z, n in v.items():
            x = requests.get("http://{}/api/{}/sensors/{}".format(RASPBEE['ip'], RASPBEE['api_key'], n)).json()['state']
            d[z] = {'Value': x[z] / 100 if not z == 'pressure' else x[z], 'Time': pytz.timezone('UTC').localize(
                datetime.strptime(x['lastupdated'], '%Y-%m-%dT%H:%M:%S')).astimezone(pytz.timezone('Europe/Berlin'))}
        temp_list.update({k: d})


def get_list():
    temp_list = {}
    get_fhem(temp_list)
    get_heiz(temp_list)
    get_raspbee(temp_list)
    return temp_list


def main():
    temp_list = get_list()
    result = []
    for device, values in sorted(temp_list.items()):
        result.append("*{}*".format(device))
        if 'temperature' in values:
            result.append("Temperatur: `{}` °C".format(values['temperature']['Value']))
        if 'humidity' in values:
            result.append("Luftfeuchtigkeit: `{}` %".format(values['humidity']['Value']))
        if 'pressure' in values:
            result.append("Luftdruck: `{}` hPa".format(values['pressure']['Value']))
        if 'temperature' in values:
            result.append("Aktualisiert: _{}_ ".format(datetime.strftime(values['temperature']['Time'], "%Y-%m-%d %H:%M:%S")))
        result.append("")
    Bot(TELEGRAM["token"]).edit_message_text(chat_id=TELEGRAM["chat_id"], message_id=TELEGRAM["msg_id"],
                                        text="\n".join(result), parse_mode=ParseMode.MARKDOWN)


if __name__ == '__main__':
    main()
