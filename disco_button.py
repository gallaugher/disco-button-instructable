# Disco Button - Publisher
# Doesn't work perfectly. Often gets stuck or throws an exception & needs to restart
import board, time, neopixel, digitalio, math, microcontroller
from adafruit_debouncer import Button
import displayio, terminalio, adafruit_displayio_ssd1306
from adafruit_display_text import label
from analogio import AnalogIn
import os, ssl, socketpool, wifi
import adafruit_minimqtt.adafruit_minimqtt as MQTT

# Get adafruit io username and key from settings.toml
aio_username = os.getenv('AIO_USERNAME')
aio_key = os.getenv('AIO_KEY')

# Setup a feed: This may have a different name than your Dashboard
animation = aio_username + "/feeds/disco_animation"
disco_song_name = aio_username + "/feeds/disco_song_name"
song_list = aio_username + "/feeds/song_list"

# Setup functions to respond to MQTT events
def connected(client, userdata, flags, rc):
    print("Connected to Adafruit IO!")
    client.subscribe(song_list)

def message(client, topic, message):
    global songs
    # The bulk of your code to respond to MQTT will be here, NOT in while True:
    print(f"*** topic: {topic}, message: {message}")
    if topic == song_list:
        message = message[1:] # remove first character
        message = message[:-1] # remove last character
        message = message.replace('"', '')
        message = message.replace("'", '')
        songs = list(message.split(", "))
        if "disco_stu.wav" in songs:
            songs.remove("disco_stu.wav")

def disconnected(client, userdata, rc):
    print("Disconnected from Adafruit IO!")

# Connect to WiFi
print(f"Connecting to WiFi: {os.getenv("WIFI_SSID")}")
wifi.radio.connect(os.getenv("WIFI_SSID"), os.getenv("WIFI_PASSWORD"))

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

# Connect to the MQTT broker (adafruit io for us)
print("Connecting to Adafruit IO...")
mqtt_client.connect()

# Potentiometer setup
potentiometer = AnalogIn(board.A2) # Could also have used GP26

# display setup:
displayio.release_displays()
i2c = board.STEMMA_I2C() # uses board.SCL and board.SDA
display_bus = displayio.I2CDisplay(i2c, device_address=0x3C)

# Animation Imports
from adafruit_led_animation.animation.solid import Solid
from adafruit_led_animation.animation.rainbow import Rainbow

# setup colors
from rainbowio import colorwheel
BLACK = (0, 0, 0)

# setup neopixel
strip_num_of_lights = 54
strip = neopixel.NeoPixel(board.GP16, strip_num_of_lights)
strip.fill(BLACK)
strip.write()

# setup animations
solid_strip = Solid(strip, color=BLACK)
rainbow_strip = Rainbow(strip, speed=0.05, period=2)

current_animation = "Solid"

# Display Setup
WIDTH = 128
HEIGHT = 32  # Change to 64 if needed
display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=WIDTH, height=HEIGHT)

# Make the display context
splash = displayio.Group()
display.show(splash)

# create a debounced Button
button_input = digitalio.DigitalInOut(board.GP15)
button_input.switch_to_input(pull=digitalio.Pull.UP) # False when pressed, True when not pressed
button = Button(button_input)

# SETUP LED on Button
led = digitalio.DigitalInOut(board.GP14)
led.direction = digitalio.Direction.OUTPUT
led.value = False

def update_display(text):
    splash = displayio.Group()
    display.show(splash)
    text_area = label.Label(
        terminalio.FONT, text=text, color=0xFFFFFF, x=0, y=int(HEIGHT/2) // 2 - 1
    )
    splash.append(text_area)

def prep_song_name(filename):
    song_name = filename.replace("_", " ")
    song_name = song_name.replace("'", "")
    return song_name.replace(".wav", "")

songs = ["Songs Not Loaded\nTurn Speaker-computer off/on"]

song = math.floor(potentiometer.value * len(songs)/65536)
last_song = songs[song]
update_display(last_song)

def perform_animation(current_animation):
    if current_animation == "Solid":
        solid_strip.animate()
    elif current_animation == "Rainbow":
        rainbow_strip.animate()

def roll_lights():
    for i in range(strip_num_of_lights):
        strip[i] = colorwheel(i * 255/strip_num_of_lights)
        strip.show()
        time.sleep(0.01)

# read in songs
# Tell the dashboard to send the latest settings for these feeds
mqtt_client.publish(song_list + "/get", "")

# Verify device is connected with a quick roll of lights
roll_lights()
strip.fill(BLACK)
strip.show()

while True:
    mqtt_client.loop()
    if not mqtt_client.is_connected:
        wifi.radio.connect(os.getenv("WIFI_SSID"), os.getenv("WIFI_PASSWORD"))
        mqtt_client.connect()
    song = math.floor(potentiometer.value * len(songs)/65536)
    if song != last_song:
        song_name = prep_song_name(songs[song])
        update_display(song_name)
        last_song = song
    button.update() # get current state of the button
    if button.pressed: # if button has been pressed
        print("BUTTON PRESSED!")
        led.value = not led.value # turn on or off LED inside the button
        if current_animation == "Rainbow":
            current_animation = "Solid"
            perform_animation(current_animation)
        else:
            current_animation = "Rainbow"
        try:
            print(f"About to publish animation: {current_animation} song {songs[song].split('\n', 1)[0]}")
            mqtt_client.publish(animation, current_animation)
            if current_animation == "Rainbow":
                mqtt_client.publish(disco_song_name, songs[song].split('\n', 1)[0] )
                roll_lights()
        except Exception as e:
            print(f"Failed to get data, restarting {e}")
            wifi.radio.connect(os.getenv("WIFI_SSID"), os.getenv("WIFI_PASSWORD"))
            mqtt_client.connect()
            print(f"About RETRY to publish animation: {current_animation} song {songs[song].split('\n', 1)[0]}")
            mqtt_client.publish(animation, current_animation)
            if current_animation == "Rainbow":
                mqtt_client.publish(disco_song_name, songs[song].split('\n', 1)[0] )
    if current_animation == "Rainbow":
        perform_animation(current_animation)
