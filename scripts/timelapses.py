import sqlite3
import cv2
import numpy as np
import os
import sys
from params import *

STATE_NAMES = {
    0: "FWD",
    1: "REV",
    2: "REV_CLEAR",
    3: "IDLE",
}

os.makedirs(OUTPUT_DIR, exist_ok=True)


def overlay_text(img, timestamp_us, cycle, force, position, state):
    lines = [
        f"State: {STATE_NAMES.get(state, state)}",
        f"Timestamp: {timestamp_us} us",
        f"Cycle: {cycle}",
        f"Force: {force:.3f}",
        f"Position: {position:.4f}",
    ]

    y = MARGIN + LINE_SPACING
    for line in lines:
        cv2.putText(
            img,
            line,
            (MARGIN, y),
            FONT,
            FONT_SCALE,
            TEXT_COLOR,
            FONT_THICKNESS,
            cv2.LINE_AA,
        )
        y += LINE_SPACING

    return img


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        "SELECT id FROM runs WHERE name = ?",
        (RUN_NAME,),
    )
    row = c.fetchone()

    if row is None:
        print(f"ERROR: run name '{RUN_NAME}' not found.")
        sys.exit(1)

    run_id = row[0]
    print(f"Creating timelapses for run '{RUN_NAME}' (id={run_id})")

    c.execute("""
        SELECT
            timestamp_us,
            cycle,
            force,
            position,
            state,
            image
        FROM images
        WHERE run_id = ?
        ORDER BY state, timestamp_us
    """, (run_id,))

    rows = c.fetchall()
    conn.close()

    if not rows:
        print("No images found for this run.")
        return

    writers = {}

    for cycle, timestamp_us, force, position, state, blob in rows:
        img_array = np.frombuffer(blob, dtype=np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if frame is None:
            continue

        frame = overlay_text(
            frame,
            timestamp_us,
            cycle,
            force,
            position,
            state,
        )

        if state not in writers:
            h, w = frame.shape[:2]

            out_path = os.path.join(
                OUTPUT_DIR,
                f"{RUN_NAME}_state_{STATE_NAMES.get(state, state)}.mp4",
            )

            writers[state] = cv2.VideoWriter(
                out_path,
                cv2.VideoWriter_fourcc(*"mp4v"),
                FPS,
                (w, h),
            )

            print(f"Writing {out_path}")

        writers[state].write(frame)

    for writer in writers.values():
        writer.release()

    print("Timelapse generation complete.")


if __name__ == "__main__":
    main()
