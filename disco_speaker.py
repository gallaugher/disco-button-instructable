# MQTT Disco Subscriber (lights & speakers) WAV & AudioMixer (to reduce pop at song start
# Note - I'll eventually put sound & neopixels in separate builds to better manage power,
# but am using a single subscriber while I debug.
import board, time, neopixel, microcontroller, mount_sd
import os, ssl, socketpool, wifi
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import audiomixer, audiocore
from audiocore import WaveFile
from audiopwmio import PWMAudioOut as AudioOut

from adafruit_led_animation.animation.solid import Solid
from adafruit_led_animation.animation.rainbow import Rainbow
from rainbowio import colorwheel

# Setup Neopixel strip & colors
BLACK = (0, 0, 0) # lights off

strip_num_of_lights = 350
strip = neopixel.NeoPixel(board.GP16, strip_num_of_lights)
strip.fill(BLACK)

# setup animations
solid_strip = Solid(strip, color=BLACK)
rainbow_strip = Rainbow(strip, speed=0.05, period=2)

current_animation = "Solid"

# setup the speaker
audio = AudioOut(board.GP15) # assuming speaker plug tip to GP16

# set path where audio files can be found on device
path = "/sd/songs/"

# create Mixer and attach to audio playback
num_voices = 1 # only playing 1 song at a time
mixer = audiomixer.Mixer(voice_count=num_voices, sample_rate=22050, channel_count=1, bits_per_sample=16, samples_signed=True)
audio.play(mixer)

def play_voice(filename):
    if mixer.voice[0].playing:
        mixer.voice[0].stop()
    # read in all beats & simultaneously play them at audio sound .level = 0 (no volume)
    print(f"About to play: {path+filename}")
    try:
        wave = audiocore.WaveFile(open(path+filename,"rb"))
        mixer.voice[0].play(wave, loop=False )
        mixer.voice[0].level = 1.0
    except OSError as e:
        print(f"An OSError occurred while trying to play audio: {e}")
        time.sleep(10)
        microcontroller.reset()
    except Exception as e:
        print(f"There was a non-OSError problem playing audio: {e}")
        time.sleep(10)

def roll_lights():
    block_size = round(strip_num_of_lights / 14)
    num_of_blocks = int(strip_num_of_lights/block_size)

    for i in range(num_of_blocks):
        strip[i*block_size:(i*block_size)+block_size] = [colorwheel(i*(256/num_of_blocks))] * block_size
        strip.show()
        time.sleep(0.01)

def perform_animation(current_animation):
    if current_animation == "Rainbow":
        try:
            rainbow_strip.animate()
        except Exception as e:
            print(f"ERROR: in Rainbow animation: {e}")

# Get adafruit io username and key from settings.toml
aio_username = os.getenv('AIO_USERNAME')
aio_key = os.getenv('AIO_KEY')

# Setup a feed: This may have a different name than your Dashboard
animation = aio_username + "/feeds/disco_animation"
disco_song_name = aio_username + "/feeds/disco_song_name"
song_list = aio_username + "/feeds/song_list"

# Setup functions to respond to MQTT events

def connected(client, userdata, flags, rc):
    # Connected to broker at adafruit io
    print("Connected to Adafruit IO! Listening for topic changes in feeds I've subscribed to")
    # Subscribe to all changes on the feed.
    client.subscribe(animation)
    client.subscribe(disco_song_name)

def disconnected(client, userdata, rc):
    # Disconnected from the broker at adafruit io
    print("Disconnected from Adafruit IO!")

def message(client, topic, message):
    global current_animation
    # The bulk of your code to respond to MQTT will be here, NOT in while True:
    print(f"topic: {topic}, message: {message}")
    if topic == disco_song_name:
#         play_voice(message+".wav")
        play_voice(message)
    elif topic == animation:
        current_animation = message
        print(f"current_animation from message: {current_animation}")
        if current_animation == "Solid":
            if current_animation == "Solid":
                if mixer.voice[0].playing:
                    print("STOPPING VOICE")
                    mixer.stop_voice(0)
                try:
                    solid_strip.animate()
                except Exception as e:
                    print(f"ERROR: in Solid animation: {e}")
        elif current_animation == "Rainbow":
            roll_lights()
            try:
                rainbow_strip.animate()
            except Exception as e:
                print(f"ERROR: in rainbow_strip animation: {e}")

# Connect to WiFi
print(f"Connecting to WiFi: {os.getenv("WIFI_SSID")}")
try:
    wifi.radio.connect(os.getenv("WIFI_SSID"), os.getenv("WIFI_PASSWORD"))
except Exception as e: # if for some reason you don't connect to Wi-Fi here, reset the board & try again
    microcontroller.reset()
print("Connected!")

# Create a socket pool
pool = socketpool.SocketPool(wifi.radio)

# Set up a MiniMQTT Client - this is our current program that subscribes or "listens")
mqtt_client = MQTT.MQTT(
    broker=os.getenv("BROKER"),
    port=os.getenv("PORT"),
    username=aio_username,
    password=aio_key,
    socket_pool=pool,
    ssl_context=ssl.create_default_context(),
)

# Setup the "callback" mqtt methods above
mqtt_client.on_connect = connected
mqtt_client.on_disconnect = disconnected
mqtt_client.on_message = message

print(f"{aio_username}, {aio_key}, {pool}, {os.getenv("PORT")}, {os.getenv("BROKER")}")

# Setup the "callback" mqtt methods above
mqtt_client.on_connect = connected
mqtt_client.on_disconnect = disconnected
mqtt_client.on_message = message

# Connect to the MQTT broker (adafruit io for us)
print("Connecting to Adafruit IO...")
mqtt_client.connect()

file_list = []
my_iterator = mount_sd.vfs.ilistdir("/songs")
for i in iter(my_iterator):
    first_element = i[0]
    if first_element[0] != ".":
        file_list.append(first_element)

print(file_list)
mqtt_client.publish(song_list, f"{file_list}", retain = True)

play_voice("disco_stu.wav")
while mixer.voice[0].playing:
    pass

# Tell the dashboard to send the latest settings for these feeds
# Publishing to a feed with "/get" added to the feed name
# will send the latest values from that feed.

while True:
    if current_animation != "Solid":
        perform_animation(current_animation)
    # keep checking the mqtt message queue
    try:
        mqtt_client.loop()
    except Exception as e:
        print(f"Failed to get data, retrying: {e}")
        wifi.radio.connect(os.getenv("WIFI_SSID"), os.getenv("WIFI_PASSWORD"))
        mqtt_client.connect()
