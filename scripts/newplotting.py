import sqlite3
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as colors
from params import *
import pandas as pd

def plot_run(data, name, ax, axins):
    df = pd.DataFrame(data, columns=["cycle", "force", "pos"])
    print(len(df["cycle"].unique()))
    print(df["cycle"].max())
    zero_deflection = df[df["force"]>0.1]["pos"].min()
    df2 = pd.DataFrame(columns=["x_max", "e_end"])
    for cycle, d in df.groupby("cycle"):
        if len(d)<5: 
           print(f"skipping cycle {cycle} (only {len(d)}<5 datapoints)")
           continue
        maxidx = d["pos"].idxmax()

        df2.loc[cycle] = (
            d["pos"].loc[maxidx] - zero_deflection,
            (d["force"].loc[maxidx]-d["force"].loc[maxidx-1])/(d["pos"].loc[maxidx]-d["pos"].loc[maxidx-1])
        )

    ax[0].plot(df2.index+1, df2["x_max"], label=name)
    axins[0].plot(df2.index+1, df2["x_max"])
    ax[0].set_xlabel("Cycle")
    ax[0].set_ylabel("Deflection at Threshold Force (mm)")
    ax[1].plot(df2.index+1, df2["e_end"], label=name)
    axins[1].plot(df2.index+1, df2["e_end"])
    ax[1].set_xlabel("Cycle")
    ax[1].set_ylabel("Stiffness at Threshold Force (N/mm)")
    

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    plt.rcParams["font.family"] = "serif"
    plt.rcParams["font.serif"] = ["Times New Roman"] + plt.rcParams["font.serif"]
    fig, ax = plt.subplots(1, 2)
    fig.suptitle("Deflection and Stiffness at Threshold Force vs Cycle for Raw and Reinforced Samples")
#    ax[0].set_xscale('log')
#    ax[1].set_xscale('log')
#    ax[0].set_yscale('log')
#    ax[1].set_yscale('log')

    axins0 = ax[0].inset_axes(
    	[0.4, 0.05, 0.57, 0.5],
    	xlim=(0, 25000), ylim=(12.5, 29.5))
    indicators = ax[0].indicate_inset_zoom(axins0, edgecolor="black")
    indicators.connectors[0].set_visible(True)
    indicators.connectors[1].set_visible(True)
    indicators.connectors[2].set_visible(True)
    indicators.connectors[3].set_visible(True)

    axins1 = ax[1].inset_axes([0.3, 0.05, 0.67, 0.5],
        xlim=(0, 25000), ylim=(5, 15))
    indicators = ax[1].indicate_inset_zoom(axins1, edgecolor="black")
    indicators.connectors[0].set_visible(True)
    indicators.connectors[1].set_visible(True)
    indicators.connectors[2].set_visible(True)
    indicators.connectors[3].set_visible(True)

    for run, plot_name in [("raw_noodle_50N_flat_plate", "Raw Foam"), ("heat_shrink_flat_plate_2", "Reinforced ID")]:
        run_id = c.execute("SELECT id FROM runs WHERE name = ?", (run,)).fetchone()[0]
        ncycles = c.execute("SELECT MAX(cycle) FROM samples WHERE run_id = ?", (run_id,)).fetchone()[0]
        print(f"run id {run_id} had {ncycles} cycles")
        c.execute("""
            SELECT cycle, force, position
            FROM samples
            WHERE run_id = ? AND state=0 AND cycle % ? = 0
            ORDER BY cycle, timestamp_us
        """, (run_id, max(int(ncycles/20000), 1)))

        data = c.fetchall()
        plot_run(data, plot_name, ax, (axins0, axins1))
    ax[0].legend()
    ax[1].legend()

    conn.close()
    plt.show()
    




if __name__ == "__main__":
    main()
