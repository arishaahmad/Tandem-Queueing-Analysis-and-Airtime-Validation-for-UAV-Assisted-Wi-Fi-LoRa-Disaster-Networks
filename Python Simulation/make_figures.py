#!/usr/bin/env python3
"""Make the paper figures from results/*.csv  ->  figures/*.png (+ .pdf)."""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uav_wifi_lora_sim import lora_toa, APP_BYTES

RES = sys.argv[1] if len(sys.argv) > 1 else "results"
OUT = sys.argv[2] if len(sys.argv) > 2 else "figures"
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "axes.grid": True, "grid.alpha": 0.3,
    "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 130,
    "savefig.dpi": 220, "savefig.bbox": "tight",
})
COL = {7: "#0072B2", 8: "#E69F00", 9: "#D55E00"}


def save(fig, name):
    fig.savefig(f"{OUT}/{name}.png")
    fig.savefig(f"{OUT}/{name}.pdf")
    plt.close(fig)


def tag(ax, s):
    """Prefix the existing title with the panel label, left-aligned."""
    t = ax.get_title()
    ax.set_title("")                      # clear the centred copy
    ax.set_title(f"{s} {t}", loc="left")


# ---------------------------------------------------------------- Fig 1
e0 = pd.read_csv(f"{RES}/exp0_baseline.csv")
fig, ax = plt.subplots(1, 3, figsize=(7.4, 2.5))
a = ax[0]
for mode, mk, ls in [("poisson", "o", "-"), ("periodic", "s", "--")]:
    d = e0[(e0.sf == 7) & (e0["mode"] == mode)]
    a.errorbar(d.W, d.pdr, yerr=d.pdr_ci, marker=mk, ms=3.5, ls=ls, lw=1, capsize=2,
               color=COL[7] if mode == "poisson" else "#009E73", label=f"sim, {mode}")
d = e0[(e0.sf == 7) & (e0["mode"] == "poisson")]
a.plot(d.W, d.analytic_pdr, "k:", lw=1.4, label="M/D/1/K analytic")
a.set_xscale("log"); a.set_ylim(76, 100.8)
a.set_xlabel("LoRa waiting room W (reports)"); a.set_ylabel("Packet delivery ratio (%)")
a.set_title("SF7: sim vs analytic"); a.legend(loc="lower right"); tag(a, "(a)")

a = ax[1]
for sf in (8, 9):
    d = e0[(e0.sf == sf) & (e0["mode"] == "poisson")]
    a.errorbar(d.W, d.pdr, yerr=d.pdr_ci, marker="o", ms=3.5, lw=1, capsize=2, color=COL[sf],
               label=f"SF{sf} sim")
    mu = 1 / lora_toa(APP_BYTES, sf)
    a.axhline(100 * mu / 20, color=COL[sf], ls=":", lw=1.2)
    a.text(1.1, 100 * mu / 20 + 1.5, rf"$\mu/\lambda$={100*mu/20:.1f}%", color=COL[sf], fontsize=7)
a.set_xscale("log"); a.set_ylim(25, 70)
a.set_xlabel("LoRa waiting room W (reports)"); a.set_ylabel("Packet delivery ratio (%)")
a.set_title("SF8/9: PDR caps at $\\mu/\\lambda$"); a.legend(loc="center right"); tag(a, "(b)")

a = ax[2]
for sf in (7, 8, 9):
    d = e0[(e0.sf == sf) & (e0["mode"] == "poisson")]
    a.plot(d.W, d.delay_mean_ms / 1e3, marker="o", ms=3.5, lw=1, color=COL[sf], label=f"SF{sf}")
a.set_xscale("log"); a.set_yscale("log")
a.set_xlabel("LoRa waiting room W (reports)"); a.set_ylabel("Mean end-to-end delay (s)")
a.set_title("Overload: delay grows with W"); a.legend(loc="upper left"); tag(a, "(c)")
fig.tight_layout(); save(fig, "fig1_baseline_validation")

# ---------------------------------------------------------------- Fig 2
e1 = pd.read_csv(f"{RES}/exp1_aggregation.csv")
fig, ax = plt.subplots(1, 3, figsize=(7.4, 2.5))
for sf in (7, 8, 9):
    d = e1[e1.sf == sf]
    ax[0].plot(d.bmax, d.pdr, marker="o", ms=3.5, lw=1, color=COL[sf], label=f"SF{sf}")
    ax[1].plot(d.bmax, d.delay_mean_ms / 1e3, marker="o", ms=3.5, lw=1, color=COL[sf], label=f"SF{sf}")
    ax[2].plot(d.bmax, d.aoi_s, marker="o", ms=3.5, lw=1, color=COL[sf], label=f"SF{sf}")
ax[0].set_ylabel("Packet delivery ratio (%)"); ax[0].set_title("Delivery"); tag(ax[0], "(a)")
ax[1].set_ylabel("Mean delay (s)"); ax[1].set_yscale("log"); ax[1].set_title("Delay"); tag(ax[1], "(b)")
ax[2].set_ylabel("Mean AoI (s)"); ax[2].set_yscale("log"); ax[2].set_title("Age of Information"); tag(ax[2], "(c)")
for x in ax:
    x.set_xlabel("Max reports per LoRa frame $B_{max}$")
ax[0].legend(loc="center right")
fig.suptitle("20 devices, 1 report/s (20 pkt/s), no duty-cycle limit, W = 100", y=1.03, fontsize=8)
fig.tight_layout(); save(fig, "fig2_aggregation")

# ---------------------------------------------------------------- Fig 3
e2 = pd.read_csv(f"{RES}/exp2_duty.csv")
fig, ax = plt.subplots(1, 3, figsize=(7.4, 2.3))
for a, duty, ttl in zip(ax, [1.0, 0.10, 0.01], ["No duty-cycle limit", "10 % duty cycle", "1 % duty cycle"]):
    p = e2[e2.duty == duty].pivot(index="sf", columns="interval", values="pdr").sort_index()
    im = a.imshow(p.values, vmin=0, vmax=100, cmap="RdYlGn", aspect="auto")
    a.set_xticks(range(p.shape[1])); a.set_xticklabels(p.columns)
    a.set_yticks(range(p.shape[0])); a.set_yticklabels([f"SF{s}" for s in p.index])
    for i in range(p.shape[0]):
        for j in range(p.shape[1]):
            v = p.values[i, j]
            a.text(j, i, f"{v:.0f}" if v < 99.5 else "100", ha="center", va="center", fontsize=6.5,
                   color="white" if (v >= 99.5 or v < 12) else "black")
    a.set_xlabel("Reporting interval per device (s)"); a.set_title(ttl); a.grid(False)
tag(ax[0], "(a)"); tag(ax[1], "(b)"); tag(ax[2], "(c)")
fig.suptitle("PDR (%) for 20 devices, $B_{max}$ = 23 reports/frame, W = 100", y=1.04, fontsize=8)
fig.tight_layout(); save(fig, "fig3_duty_cycle_pdr")

# ---------------------------------------------------------------- Fig 4
fig, ax = plt.subplots(1, 2, figsize=(6.2, 2.5), sharey=True)
ivs = np.array([1, 2, 5, 10, 30, 60, 120])
for a, duty, ttl in zip(ax, [0.10, 0.01], ["10 % duty cycle", "1 % duty cycle"]):
    for sf in (7, 8, 9):
        for b, ls, lab in [(23, "-", "aggregated (23/frame)"), (1, "--", "one report/frame")]:
            cap = b * duty / lora_toa(APP_BYTES * b, sf)
            a.plot(ivs, cap * ivs, ls=ls, color=COL[sf], lw=1.2)
    a.axhline(20, color="k", ls=":", lw=1)
    a.text(1.05, 22, "20 devices", fontsize=7)
    a.set_xscale("log"); a.set_yscale("log"); a.set_xlabel("Reporting interval per device (s)")
    a.set_title(ttl)
ax[0].set_ylabel("Max sustainable devices")
from matplotlib.lines import Line2D
h = [Line2D([], [], color="k", ls="-", lw=1.2, label="aggregated (23 reports/frame)"),
     Line2D([], [], color="k", ls="--", lw=1.2, label="one report per frame")]
h += [Line2D([], [], color=COL[sf], lw=2, label=f"SF{sf}") for sf in (7, 8, 9)]
ax[0].legend(handles=h, loc="lower right", fontsize=6.3)
tag(ax[0], "(a)"); tag(ax[1], "(b)")
fig.tight_layout(); save(fig, "fig4_max_devices")

# ---------------------------------------------------------------- Fig 5
e3 = pd.read_csv(f"{RES}/exp3_outage.csv")
lam = 20 / 5.0
fig, ax = plt.subplots(1, 3, figsize=(7.4, 2.5))
cm = plt.cm.viridis(np.linspace(0, 0.9, 5))
for c, (down, d) in zip(cm, e3.groupby("down")):
    ax[0].errorbar(d.K, d.pdr, yerr=d.pdr_ci, marker="o", ms=3, lw=1, color=c, capsize=1.5,
                   label=f"outage {down:.0f} s")
    if down > 0:
        ax[0].axvline(lam * down, color=c, ls=":", lw=1)
ax[0].set_xscale("log"); ax[0].set_xlabel("UAV buffer K (reports)")
ax[0].set_ylabel("Packet delivery ratio (%)"); ax[0].set_title("Buffer needed $\\approx\\lambda D$")
h0, l0 = ax[0].get_legend_handles_labels()
tag(ax[0], "(a)")
d = e3[e3.K == 1000]
ax[1].plot(d.down, d.aoi_s, marker="o", ms=3.5, color="#0072B2")
ax[1].set_xlabel("Outage D (s), 300 s up-window"); ax[1].set_ylabel("Mean AoI (s)")
ax[1].set_title("Age of Information"); tag(ax[1], "(b)")
ax[2].plot(d.down, d.delay_mean_ms / 1e3, marker="o", ms=3.5, color="#D55E00", label="mean")
ax[2].plot(d.down, d.delay_p95_ms / 1e3, marker="s", ms=3.5, color="#D55E00", ls="--", label="p95")
ax[2].set_yscale("log"); ax[2].set_xlabel("Outage D (s), 300 s up-window")
ax[2].set_ylabel("End-to-end delay (s)"); ax[2].set_title("Delay (K = 1000)")
ax[2].legend(); tag(ax[2], "(c)")
fig.suptitle("Store-and-forward under UAV link outages: SF7, 20 devices at 1 report/5 s ($\\lambda$ = 4 pkt/s)",
             y=1.03, fontsize=8)
fig.tight_layout()
fig.legend(h0, l0, loc="lower center", ncol=5, fontsize=6.5, bbox_to_anchor=(0.5, -0.09), frameon=False)
save(fig, "fig5_uav_outage")
print("figures written to", OUT)
