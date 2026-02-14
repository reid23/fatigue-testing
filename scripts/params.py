###* logging

SERIAL_PORT = "/dev/serial/by-id/usb-Teensyduino_USB_Serial_15749420-if00"
BAUDRATE = 2500000

DB_PATH = "fatigue_data.db"
RUN_NAME = "raw_noodle_50N_flat_plate"

STOP_FORCE = 50.0 # N
CLEAR_FORCE = 0.5 # N
FEED_RATE = 50.0 # mm/s
RETRACT_RATE = 100.0 # mm/s

CAMERA_INDEX = "/dev/v4l/by-id/usb-Ingenic_Semiconductor_CO.__LTD._HD_Web_Camera_Ucamera001-video-index0"

SQLITE_BATCH_SIZE = 500  # commit every N samples


###* live plotting
ENABLE_LIVE_PLOT = False

PLOT_EVERY_N_CYCLES = 20     # only plot 1 / N cycles
PLOT_REFRESH_HZ = 2         # how often to redraw
MAX_PLOTTED_POINTS = 200_000


###* post-run plotting

MAX_POINTS = 700_000
EVERY_NTH_CYCLE = 50

# Scatter plot settings
POINT_SIZE = 2
ALPHA = 1
FIG_DPI = 150
OUTPUT_FILE = f"{RUN_NAME}_force_vs_position.png"

###* timelapse generation
import cv2

OUTPUT_DIR = "timelapses"
TIMELAPSE_DOWNSAMPLE = 5
FPS = 30
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.6
FONT_THICKNESS = 2
TEXT_COLOR = (0, 255, 0)
LINE_SPACING = 22
MARGIN = 10

