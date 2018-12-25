# /usr/bin/env python
import json
import logging
import os
import sys
from datetime import datetime, timedelta

import fhem
import pytz
import requests
from telegram.bot import Bot
from telegram.ext.callbackqueryhandler import CallbackQueryHandler
from telegram.ext.updater import Updater
from telegram.inline.inlinekeyboardbutton import InlineKeyboardButton
from telegram.inline.inlinekeyboardmarkup import InlineKeyboardMarkup
from telegram.parsemode import ParseMode

from secrets import FHEM, RASPBEE, HEIZ, RASPBEE_IDS, HEIZ_LIST, FHEM_NAMES, TELEGRAM, SENSORS, GROUPS, DEBUG

if DEBUG:
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format='%(levelname)s - %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        filename="{}/{}".format(os.path.dirname(os.path.realpath(__file__)),
                                                'log/temperature_channel.log'))
logger = logging.getLogger(__name__)

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


def group_temps(temp_list):
    grouped_list = {}
    for s in SENSORS:
        if not s['group'] in grouped_list:
            grouped_list[s['group']] = {}
        grouped_list[s['group']][s['name']] = temp_list[s['id']]
    return grouped_list


def less():
    g_list = get_list()
    result = ""
    for g, v in sorted(g_list.items()):
        result += "*{}*\n".format(GROUPS[g])
        for t, vs in sorted(v.items()):
            if 'temperature' in vs:
                result += ("`{}°C `".format(round(float(vs['temperature']['Value']) * 10) / 10)).replace('.', ',')
            if 'humidity' in vs:
                result += ("`{}% `".format(round(float(vs['humidity']['Value']) * 10) / 10)).replace('.', ',')
            result += "{}\n".format(t)
        result += "\n"
    result += "_Aktualisiert: {}_".format(datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S"))
    return result


def more():
    g_list = get_list()
    result = ""
    for g, v in sorted(g_list.items()):
        result += "\n*{}*\n".format(GROUPS[g].upper())
        for t, vs in sorted(v.items()):
            result += "*{}*\n".format(t)
            if 'temperature' in vs:
                result += ("Temperatur: `{} °C\n`".format(vs['temperature']['Value']))
            if 'humidity' in vs:
                result += ("Luftfeuchtigkeit: `{} %\n`".format(vs['humidity']['Value']))
            if 'pressure' in vs:
                result += ("Luftdruck: `{} hPa\n`".format(vs['pressure']['Value']))
            if 'temperature' in vs:
                result += (
                    "Aktualisiert: _{}_\n".format(datetime.strftime(vs['temperature']['Time'], "%Y-%m-%d %H:%M:%S")))
            result += "\n"
    result += "_Nachricht aktualisiert: {}_".format(datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S"))
    return result


def get_list():
    temp_list = {}
    get_fhem(temp_list)
    get_heiz(temp_list)
    get_raspbee(temp_list)
    return group_temps(temp_list)


def get_keyboard(full):
    if not full:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Erweitert", callback_data="more")]])
    else:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Kompakt", callback_data="less")]])


def send(bot=None, full=False, force=False):
    with open("{}/{}".format(os.path.dirname(os.path.realpath(__file__)), 'data.json'), "r") as read_file:
        data = json.load(read_file)
    if not force and data and datetime.strptime(data[0][:19], '%Y-%m-%dT%H:%M:%S') > datetime.utcnow() - timedelta(
            minutes=3):
        full = True
    if not bot:
        bot = Bot(TELEGRAM["token"])
    bot.edit_message_text(chat_id=TELEGRAM["chat_id"], message_id=TELEGRAM["msg_id"], parse_mode=ParseMode.MARKDOWN,
                          text=more() if full else less(), reply_markup=get_keyboard(full))


def answer_callback(bot, update):
    update.callback_query.answer()
    if update.callback_query.data == "more":
        send(bot, full=True)
        with open("{}/{}".format(os.path.dirname(os.path.realpath(__file__)), 'data.json'), 'w') as write_file:
            json.dump([datetime.utcnow().isoformat()], write_file)
    elif update.callback_query.data == "less":
        send(bot, force=True)
        with open("{}/{}".format(os.path.dirname(os.path.realpath(__file__)), 'data.json'), 'w') as write_file:
            json.dump([], write_file)
    logger.info("{} - {} - {}".format(update.callback_query.data, update.callback_query.from_user.first_name,
                                      update.callback_query.from_user.id))


def main():
    updater = Updater(TELEGRAM["token"])
    dp = updater.dispatcher

    dp.add_handler(CallbackQueryHandler(answer_callback))
    updater.start_polling()

    updater.idle()


if __name__ == '__main__':
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "1":
            send()
        else:
            main()
    except Exception as e:
        logger.error(e)
