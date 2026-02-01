import sqlite3
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as colors
from params import *

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get the run id
    c.execute("SELECT id FROM runs WHERE name = ?", (RUN_NAME,))
    row = c.fetchone()
    if row is None:
        print(f"Run '{RUN_NAME}' not found.")
        return
    run_id = row[0]

    # Fetch all sample points for this run
    c.execute("""
        SELECT cycle, force, position
        FROM samples
        WHERE run_id = ? AND state=0
        ORDER BY cycle, timestamp_us
    """, (run_id,))

    data = c.fetchall()
    conn.close()

    if not data:
        print("No samples found for this run.")
        return

    # Extract data
    cycles = []
    forces = []
    positions = []

    for cycle, force, pos in data:
        cycles.append(cycle)
        forces.append(force)
        positions.append(pos)
        if len(cycles) >= MAX_POINTS:
            break  # prevent memory issues

    # Create scatter plot
    plt.figure(figsize=(10, 6))
    norm = colors.Normalize(vmin=min(cycles), vmax=max(cycles))
    scatter = plt.scatter(
        positions,
        forces,
        c=cycles,
        cmap="RdBu",
        norm=norm,
        s=POINT_SIZE,
        alpha=ALPHA,
    )
    plt.xlabel("Position (mm)")
    plt.ylabel("Force (N)")
    plt.title(f"Force vs Position for run '{RUN_NAME}'")
    cbar = plt.colorbar(scatter)
    cbar.set_label("Cycle")

    plt.tight_layout()
    plt.savefig(OUTPUT_FILE, dpi=FIG_DPI)
    plt.show()

    print(f"Plot saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
