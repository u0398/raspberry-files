# Copyright (c) 2023 Peter McDermott
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with this program. If not, see <https://www.gnu.org/licenses/>.

# Author: Peter McDermott (ux0398@gmail.com)
# Repository: https://github.com/u0398/raspberry-files
# Version: 0.2
#
# Description: A script that oledlays information on a oled, button, and
# LED attached to a Raspberry Pi. Functions include information oledlay,
# reboot/shutdown commands, and rudimentary disk i/o indication.
#
# Requirements: python3-pip python3-pil python3-smbus i2c-tools psutil
# tzlocal adafruit-circuitpython-ssd1306

import argparse
import logging
import time
import tzlocal
from datetime import datetime
from datetime import timedelta
import re
import subprocess
import adafruit_ssd1306
from board import SCL, SDA
import busio
import psutil
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont
from gpiozero import PWMLED, Button

VERSION = "0.2"

led = PWMLED(23)
button = Button(20)

logging.basicConfig(level=logging.INFO)

# I/O activity source
IOFILE = '/proc/diskstats'
IO_FIELD = 12

# oled timer at startup
ACTION_INITIAL_TIMEOUT = 10
# oled timer between button actions
ACTION_TIMEOUT = 20
# time considered a long press
ACTION_PRESS = timedelta(seconds=2)
# the countdown timer after a button press
action_time = ACTION_INITIAL_TIMEOUT
action_cancel = False

# Countdown before executing a reboot/shutdown
REBOOT_COUNTDOWN = 6
SHUTDOWN_COUNTDOWN = 6

# Subset of oled_display states treated as cycleable menu screens
MENU = ["INFO", "INFO2", "CLOCK", "REBOOT", "SHUTDOWN"]
menu_state = None

# Tracking button events
button_down_start = None
button_down_last = None
# Flag indicating a short button press/release 
button_clicked = False

# Create the I2C interface
i2c = busio.I2C(SCL, SDA)

# Create the SSD1306 OLED class.
# The first two parameters are the pixel width and pixel height. Change these
# to the right size for your oled display.
oled = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)

# Clear oledlay.
oled.rotation = 0
oled.fill(0)
oled.show()

# LED resting brightness
led_resting  = 0.25

# Create blank image for drawing
# Make sure to create image with mode '1' for 1-bit color
width = oled.width
height = oled.height
image = Image.new("1", (width, height))

# Get drawing object to draw on image
draw = ImageDraw.Draw(image)

# First define some constants to allow easy resizing of shapes
padding = -2
top = padding
bottom = height - padding

# Load default font.
font = ImageFont.load_default()
font_large = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSansMono-Bold.ttf", 24)

# anything that changes the display
def oled_display(state="", count=0):
    # Draw a black filled box to clear the image.
    draw.rectangle((0, 0, width, height), outline=0, fill=0)

    if state == "BOOTUP":
        # Startup Info
        draw.rectangle((1,1,width-3,height-2), outline=1, fill=0)
        draw.text((6, top+6),  "Loading Info Screen", font=font, fill=255)
        draw.text((6, top+18), "Version: "+VERSION, font=font, fill=255)
    if state  == "INFO":
        # Shell scripts for system monitoring from here : https://unix.stackexchange.com/questions/119126/command-to-oledlay-memory-usage-disk-usage-and-cpu-load
        cmd = "hostname"
        HOSTNAME = subprocess.check_output(cmd, shell = True)
        cmd = "hostname -I | cut -d\' \' -f1"
        IP = subprocess.check_output(cmd, shell = True )

        # Examples of getting system information from psutil : https://www.thepythoncode.com/article/get-hardware-system-information-python#CPU_info
        CPU = "{:3.0f}".format(psutil.cpu_percent())
        svmem = psutil.virtual_memory()
        MemUsage = "{:2.0f}".format(svmem.percent)

        hostName = "{:>16}".format(HOSTNAME.decode('UTF-8'))
        ipAddress = "{:>16}".format(IP.decode('UTF-8'))

        draw.text((0, top),      "NAME: " + hostName, font=font, fill=255)
        draw.text((0, top+12),   "IP  : " + ipAddress,  font=font, fill=255)
        draw.text((0, top+24),   "CPU : " + CPU + "% | MEM: " + MemUsage + "%", font=font, fill=255)
    if state == "INFO2":
        cmd = "uptime -p"
        UPTIME_P = subprocess.check_output(cmd, shell = True)
        upTime = format(UPTIME_P.decode('UTF-8'))
        replace_list = {"up ": "", " days,": "d", " hours,": "h", " minutes": "m"}
        for char in replace_list.keys():
            upTime = re.sub(char, replace_list[char], upTime)
        upTime = "{:>15}".format(upTime)

        cmd = "uptime"
        UPTIME = subprocess.check_output(cmd, shell = True)
        load = format(UPTIME.decode('UTF-8'))
        load = re.sub(r'^.*?load average:', '', load)
        load = re.sub(",", "", load)
        load = "{:>17}".format(load)

        cmd = "uname -r"
        KERNEL = subprocess.check_output(cmd, shell = True)
        kernel = format(KERNEL.decode('UTF-8'))
        kernel = "{:>20}".format(kernel)

        draw.text((0, top),      "UPTIME:" + upTime, font=font, fill=255)
        draw.text((0, top+12),   "LOAD:" + load, font=font, fill=255)
        draw.text((0, top+24),   "K:" + kernel, font=font, fill=255)
    if state == "CLOCK":
        timestamp = time.strftime('%H:%M:%S')
        timezone = tzlocal.get_localzone_name()
        w = draw.textlength(timestamp, font_large)
        draw.text(((width-w)/2, top),      timestamp, font=font_large, fill=255)
        w = draw.textlength(timezone, font)
        draw.text(((width-w)/2, top+24),   timezone, font=font, fill=255)
    if state == "REBOOT":
        draw.text((0, top),      "       REBOOT?      ", font=font, fill=255)
        draw.text((0, top+12),   "   Press and hold   ", font=font, fill=255)
        draw.text((0, top+24),   "     to execute.    ", font=font, fill=255)
    if state == "REBOOTING":
        draw.text((0, top),      " Rebooting...     "+str(count), font=font, fill=255)
        draw.text((0, top+24),   " (press to cancle)  ", font=font, fill=255)
    if state == "SHUTDOWN":
        draw.text((0, top),      "     SHUTDOWN?      ", font=font, fill=255)
        draw.text((0, top+12),   "   Press and hold   ", font=font, fill=255)
        draw.text((0, top+24),   "     to execute.    ", font=font, fill=255)
    if state == "SHUTTING_DOWN":
        draw.text((0, top),      " Shutting Down... "+str(count), font=font, fill=255)
        draw.text((0, top+24),   " (press to cancel)  ", font=font, fill=255)
    oled.image(image)
    oled.show()

# Display "bootup" screen
oled_display("BOOTUP")
led.pulse(0.4,0.4)
time.sleep(ACTION_INITIAL_TIMEOUT)
oled_display()
led.value = led_resting

# Main loop
while True:

    # The button has been recently pressed
    if action_time > 0:
        time.sleep(0.1)
        action_time -= 0.1
        # Catch if the timer dropped to zero
        if action_time <= 0:
            oled_display()
            menu_state = None
        logging.debug("action_time = %s", action_time)
    else:
        # Check if there has been I/O activity
        s = open(IOFILE,mode='r')
        io = s.read()
        disk_active = False
        for l in io.split('\n'):
            try:
                if int(l.split()[IO_FIELD - 1]):
                    disk_active = True
                    break
            except IndexError:
                pass
        if disk_active:
            # Fake disk activity flashing
            led.pulse(0.1,0.1)
        else:
            led.value = led_resting
        # Balance between responsiveness in first button click, and resource consumption
        time.sleep(0.4)
    
    while button.is_pressed:
        # Record the latest time while pressed & and the first time while pressed 
        button_down = datetime.now()
        if button_down_start is None:
            button_down_start = button_down
            logging.debug("button_down_start = %s", button_down_start)
        # There needs to be a delay to avoid reading multiple signals when button is depressed
        time.sleep(0.05)
        # Start with the info screen
        if action_time <= 0:
            oled_display("INFO")
        # Reset the action count down
        action_time = ACTION_TIMEOUT
        # Duration the button was depressed
        press_delta = button_down - button_down_start
        logging.debug("press_delta = %s", press_delta)

        # If the button was held down long enough, interupt the menu 
        if not action_cancel and press_delta > ACTION_PRESS:
            if MENU[menu_state] == "REBOOT":
                time.sleep(1)
                count = REBOOT_COUNTDOWN
                while count > 0:
                    oled_display("REBOOTING", count)
                    count -= 1
                    time.sleep(1)
                    if button.is_pressed:
                        action_cancel = True
                        break
                if action_cancel:
                    menu_state = 0
                else:
                    oled_display()
                    cmd = "sudo reboot now"
                    subprocess.Popen(cmd, shell = True)
                    exit()
            if MENU[menu_state] == "SHUTDOWN":
                time.sleep(1)
                count = SHUTDOWN_COUNTDOWN
                while count > 0:
                    oled_display("SHUTTING_DOWN", count)
                    count -= 1
                    time.sleep(1)
                    if button.is_pressed:
                        action_cancel = True
                        break
                if action_cancel:
                    menu_state = 1
                else:
                    oled_display()
                    cmd = "sudo shutdown now"
                    subprocess.Popen(cmd, shell = True)
                    exit()
        else:
            # Flag indicating a short button press/release 
            button_clicked = True

    if button_clicked:
        # Reset action cancel and click flags
        action_cancel = False
        button_clicked = False
        
        logging.debug("button_down = %s\n\n", button_down)
        button_up = datetime.now()
        logging.debug("button_up = %s", button_up)
        button_down_start = None
        button_down_last = button_down
        if menu_state is None or menu_state == len(MENU) - 1:
            logging.debug("menu_state MAX reset from %s", len(MENU)-1)
            menu_state = 0
        else:
            logging.debug("menu_state iterated from %s to %s", menu_state, menu_state+1)
            menu_state += 1
        oled_display(MENU[menu_state])
