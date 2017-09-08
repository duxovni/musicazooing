import redis
import time
import re
import json
import os
import subprocess
from mplayer import Player

from musicautils import *

current_uuid = None
should_be_paused = False

display_video = (os.getenv("MZ_VIDEO") == "true")

if display_video:
        os.environ["DISPLAY"] = ":0.0"

player_args = ("-fs", "--xineramascreen=1") if display_video else ("-vo", "null")
player = Player(args=player_args)

redis = redis.Redis()

if display_video:
	subprocess.check_call(os.path.join(os.path.dirname(os.path.abspath(__file__)), "configure-screen.sh"))

def start_playing(uuid, ytid):
	global current_uuid, should_be_paused
	if current_uuid is not None:
		stop_playing()
	assert player.filename is None
	if os.path.exists(path_for(ytid)):
		current_uuid = uuid
		player.loadfile(path_for(ytid))
		should_be_paused = False

def stop_playing():
	global current_uuid
	assert current_uuid is not None
	current_uuid = None
	player.stop()

def playback_pause():
	global should_be_paused
	should_be_paused = not should_be_paused
	player.pause()

def check_finished_uuid():
	global current_uuid
	if player.filename is None:
		uuid = current_uuid
		current_uuid = None
		return uuid
	else:
		return False

def control_callback(message):
	if player.filename is not None:
		playback_pause()

p = redis.pubsub(ignore_subscribe_messages=True)
p.subscribe(**{'musicacontrol': control_callback})

def status_update():
	redis.set("musicastatus", json.dumps({"paused": player.paused, "time": player.time_pos or 0, "length": player.length or 0}))

while True:
	if player.filename is not None and player.paused != should_be_paused:
		player.pause()
	status_update()
	p.get_message()
	quent = redis.lindex("musicaqueue", 0)
	removed_uuid = check_finished_uuid()
	if removed_uuid and quent and removed_uuid == json.loads(quent.decode())["uuid"]:
		print("DEQUEUE")
		ent = redis.lpop("musicaqueue")
		redis.set("musicatime.%s" % json.loads(quent.decode())["ytid"], time.time())
		redis.rpush("musicaudit", "dequeued entry %s at %s because process ended" % (ent, time.ctime()));
		quent = redis.lindex("musicaqueue", 0)
	if quent:
		quent = json.loads(quent.decode())
		if quent["uuid"] != current_uuid:
			redis.set("musicatime.%s" % quent["ytid"], time.time())
			start_playing(quent["uuid"], quent["ytid"])
	elif current_uuid is not None:
		stop_playing()
	time.sleep(0.5)
