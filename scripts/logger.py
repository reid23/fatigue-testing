import serial
import struct
import sqlite3
import threading
import queue
import time
import cv2
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as colors
from params import *

DATA_STRUCT = struct.Struct("<IIffI")  # must match MCU exactly

sample_queue = queue.Queue(maxsize=10_000)
plot_queue = queue.Queue(maxsize=50_000)
image_queue = queue.Queue()

stop_event = threading.Event()

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY,
        name TEXT,
        start_time TEXT,
        stop_force REAL,
        clear_force REAL,
        feed_rate REAL,
        retract_rate REAL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS samples (
        run_id INTEGER,
        timestamp_us INTEGER,
        cycle INTEGER,
        force REAL,
        position REAL,
        state INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS images (
        run_id INTEGER,
        timestamp_us INTEGER,
        cycle INTEGER,
        force REAL,
        position REAL,
        state INTEGER,
        image BLOB
    )
    """)

    conn.commit()
    return conn

def serial_reader(port):
    prev_state = None

    while not stop_event.is_set():
        line = port.readline()
        if not line:
            continue

        try:
            raw = bytes.fromhex(line.decode().strip())
            sample = DATA_STRUCT.unpack(raw)
        except Exception:
            continue

        sample_queue.put(sample)
        print(f"\rcycle: {str(sample[0]).rjust(12)}", end='')

         # ---- Plot decimation by cycle ----
                                # cycle
        if ENABLE_LIVE_PLOT and (sample[0] % PLOT_EVERY_N_CYCLES == 0):
            try:                            # cycle    force      pos
                plot_queue.put_nowait((sample[0], sample[2], sample[3]))
            except queue.Full:
                pass  # silently drop, never block

        if prev_state is not None and sample[-1] != prev_state:
            image_queue.put(sample)

        prev_state = sample[-1]

def db_writer(conn, run_id):
    c = conn.cursor()
    buffer = []

    while not stop_event.is_set() or not sample_queue.empty():
        try:
            sample = sample_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        cycle, stamp, force, pos, state = sample
        buffer.append((run_id, stamp, cycle, force, pos, state))
        if len(buffer) >= SQLITE_BATCH_SIZE:
            c.executemany("""
                INSERT INTO samples
                VALUES (?, ?, ?, ?, ?, ?)
            """, buffer)
            conn.commit()
            buffer.clear()

    if buffer:
        c.executemany("""
            INSERT INTO samples
            VALUES (?, ?, ?, ?, ?, ?)
        """, buffer)
        conn.commit()

def image_capturer(conn, run_id):
    cam = cv2.VideoCapture(CAMERA_INDEX)
    c = conn.cursor()
    global tic

    while not stop_event.is_set() or not image_queue.empty():
        ret, frame = cam.read()
        try:
            sample = image_queue.get(timeout=0.01)
        except queue.Empty:
            continue

        if not ret:
            continue

        success, png = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not success:
            continue

        c.execute("""
            INSERT INTO images
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (run_id, sample[0], sample[1], sample[2], sample[3], sample[4], png.tobytes()))
        conn.commit()

    cam.release()

def live_plotter():
    plt.ion()
    fig, ax = plt.subplots()
    sc = None

    cycles = []
    forces = []
    positions = []

    last_update = time.time()

    while not stop_event.is_set():
        try:
            cycle, force, pos = plot_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        cycles.append(cycle)
        forces.append(force)
        positions.append(pos)

        # Prevent unbounded growth
        if len(cycles) > MAX_PLOTTED_POINTS:
            cycles[:] = cycles[-MAX_PLOTTED_POINTS:]
            forces[:] = forces[-MAX_PLOTTED_POINTS:]
            positions[:] = positions[-MAX_PLOTTED_POINTS:]

        now = time.time()
        if now - last_update < 1.0 / PLOT_REFRESH_HZ:
            continue

        last_update = now

        ax.clear()

        norm = colors.Normalize(vmin=min(cycles), vmax=max(cycles))
        cmap = cm.viridis

        sc = ax.scatter(
            positions,
            forces,
            c=cycles,
            cmap=cmap,
            norm=norm,
            s=5,
            alpha=0.7,
        )

        ax.set_xlabel("Position")
        ax.set_ylabel("Force")
        ax.set_title("Force vs Position (colored by cycle)")

        if sc:
            plt.colorbar(sc, ax=ax, label="Cycle")

        plt.pause(0.001)

    plt.ioff()
    plt.close(fig)


def main():
    conn = init_db()
    c = conn.cursor()

    start_time = datetime.now().isoformat()

    c.execute("""
        INSERT INTO runs (name, start_time, stop_force, clear_force, feed_rate, retract_rate)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (RUN_NAME, start_time, STOP_FORCE, CLEAR_FORCE, FEED_RATE, RETRACT_RATE))
    conn.commit()

    run_id = c.lastrowid
    print(f"Started run {RUN_NAME} (id={run_id})")

    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)

    cmd = f"SET {STOP_FORCE} {CLEAR_FORCE} {FEED_RATE} {RETRACT_RATE}\n"
    ser.write(cmd.encode())
    time.sleep(0.1)

    ser.write(b"BEGIN\n")

    threads = [
        threading.Thread(target=serial_reader, args=(ser,), daemon=True),
        threading.Thread(target=db_writer, args=(conn, run_id), daemon=True),
        threading.Thread(target=image_capturer, args=(conn, run_id), daemon=True),
    ]

    if ENABLE_LIVE_PLOT:
        threads.append(
            threading.Thread(target=live_plotter, daemon=True)
        )

    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
        stop_event.set()

    for t in threads:
        t.join()

    ser.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
