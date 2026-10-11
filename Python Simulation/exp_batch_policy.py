#!/usr/bin/env python3
"""
Batch-threshold / timeout policy under duty cycle: AoI versus batch size.

Policy (implemented in uav_wifi_lora_sim.lora_stage):
  The LoRa transmitter may start a frame when it is free (duty-cycle silence over)
  AND (queue >= B_min  OR  oldest queued report has waited T_to).
  It then sends min(queue, B_max) reports.
  B_min = 1  -> greedy / work-conserving (the policy used elsewhere in the paper).
  B_min > 1  -> deliberately wait for fuller frames to save airtime and duty-cycle budget.
  T_to       -> caps the extra waiting (T_to = inf means "never time out").

Question answered: does waiting for fuller frames ever improve freshness (AoI)
when the duty-cycle limit makes airtime scarce?

Reports still in flight when the simulated horizon ends are *censored* (excluded from
PDR, delay and AoI) rather than flushed, which would otherwise bias B_min > 1 runs.

Usage:  python exp_batch_policy.py [results_dir] [figures_dir] [reps]
"""
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from uav_wifi_lora_sim import (DEFAULT, APP_BYTES, B_MAX_PHY, gen_arrivals, wifi_stage,
                               toa_table, lora_stage, aoi_mean, lora_toa)

# (label, SF, duty cycle d, reporting interval tau [s]); N = 20 devices
SCENARIOS = [
    ("SF7, d=10%, tau=10 s", 7, 0.10, 10.0),
    ("SF7, d=1%, tau=60 s", 7, 0.01, 60.0),
    ("SF9, d=10%, tau=30 s", 9, 0.10, 30.0),
]
B_MINS = [1, 2, 3, 5, 8, 12, 16, 20, 23]
TIMEOUTS = [("T_to = 0.5 tau", 0.5), ("T_to = 2 tau", 2.0), ("no timeout", None)]
SIM_TIME, WARMUP, K = 30000.0, 3000.0, 100


def run_policy_once(sf, duty, tau, bmin, tto, seed, n_dev=20):
    c = {**DEFAULT, "sf": sf, "duty": duty, "interval": tau, "bmax": B_MAX_PHY, "bmin": bmin,
         "tto": 1e18 if tto is None else tto, "K": K, "sim_time": SIM_TIME, "warmup": WARMUP}
    rng = np.random.default_rng(seed)
    gen, dev = gen_arrivals(n_dev, tau, SIM_TIME, rng, "periodic")
    a = wifi_stage(gen, c["tw"])
    tab = toa_table(sf, B_MAX_PHY)
    deliv = lora_stage(a, K, B_MAX_PHY, bmin, c["tto"], tab, duty, 1.0, 0.0, 0.0)

    censored = deliv > SIM_TIME                    # still waiting/transmitting at horizon
    deliv = np.where(censored, np.nan, deliv)
    m = (gen >= WARMUP) & ~censored
    ok = ~np.isnan(deliv)
    got = ok & m
    dly = (deliv - gen)[got]
    times, counts = np.unique(deliv[got], return_counts=True)   # one entry per frame
    airtime = tab[np.minimum(counts, B_MAX_PHY)].sum()
    return dict(
        pdr=100.0 * got.sum() / m.sum(),
        aoi_s=aoi_mean(gen[m], dev[m], deliv[m], n_dev),
        delay_mean_s=dly.mean(),
        mean_batch=got.sum() / times.size,
        budget_used_pct=100.0 * airtime / (duty * (SIM_TIME - WARMUP)),
    )


def sweep(reps=10, seed0=7000):
    rows = []
    tcrit = stats.t.ppf(0.975, reps - 1)
    for label, sf, duty, tau in SCENARIOS:
        lam = 20.0 / tau
        for tlabel, rel in TIMEOUTS:
            tto = None if rel is None else rel * tau
            for bmin in B_MINS:
                rs = pd.DataFrame([run_policy_once(sf, duty, tau, bmin, tto, seed0 + r)
                                   for r in range(reps)])
                row = dict(scenario=label, sf=sf, duty=duty, tau=tau, lam=lam,
                           timeout=tlabel, bmin=bmin)
                for col in rs.columns:
                    row[col] = rs[col].mean()
                    row[col + "_ci"] = tcrit * rs[col].std(ddof=1) / math.sqrt(reps)
                # first-order theory for fill-limited operation (no timeout hit):
                # AoI ~ tau/2 + (B-1)/(2 lambda) + T_L(B) + T_W
                T = lora_toa(APP_BYTES * bmin, sf)
                row["aoi_theory_s"] = tau / 2 + (bmin - 1) / (2 * lam) + T + DEFAULT["tw"]
                row["fill_limited"] = (bmin / lam) >= (T / duty)
                rows.append(row)
    return pd.DataFrame(rows)


DISPLAY = {"T_to = 0.5 tau": r"$T_{to}=0.5\tau$", "T_to = 2 tau": r"$T_{to}=2\tau$ (never reached)",
           "no timeout": "no timeout"}


def make_figure(df, path_png):
    colors = {"T_to = 0.5 tau": "#0072B2", "T_to = 2 tau": "#E69F00", "no timeout": "#D55E00"}
    marks = {"T_to = 0.5 tau": "o", "T_to = 2 tau": "s", "no timeout": "^"}
    plt.rcParams.update({"font.size": 8, "axes.grid": True, "grid.alpha": 0.3,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(2, 3, figsize=(7.4, 4.4), sharex=True)
    for j, (label, sf, duty, tau) in enumerate(SCENARIOS):
        d = df[df.scenario == label]
        for tl, _ in TIMEOUTS:
            e = d[d.timeout == tl]
            ax[0, j].errorbar(e.bmin, e.aoi_s, yerr=e.aoi_s_ci, color=colors[tl], marker=marks[tl],
                              ms=3.5, lw=1, capsize=1.5, label=DISPLAY[tl])
            ax[1, j].plot(e.bmin, e.budget_used_pct, color=colors[tl], marker=marks[tl], ms=3.5,
                          lw=1, label=tl)
        th = d[d.timeout == "no timeout"]
        ax[0, j].plot(th.bmin, th.aoi_theory_s, "k:", lw=1.2,
                      label=r"theory $\tau/2+(B-1)/2\lambda+T_L$")
        ax[0, j].axhline(tau / 2, color="gray", lw=0.8, ls="--")
        pretty = label.replace("tau", r"$\tau$").replace("d=", r"$d$=")
        ax[0, j].set_title(f"({'abc'[j]}) {pretty}", loc="left", fontsize=8)
        ax[1, j].set_xlabel(r"Batch threshold $B_{min}$ (reports)")
    ax[0, 0].set_ylabel("Mean AoI (s)")
    ax[1, 0].set_ylabel("Duty-cycle budget used (%)")
    ax[0, 0].legend(fontsize=6.3, loc="upper left")
    fig.tight_layout()
    fig.savefig(path_png, dpi=220, bbox_inches="tight")
    fig.savefig(path_png.replace(".png", ".pdf"), bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    res = sys.argv[1] if len(sys.argv) > 1 else "results"
    figs = sys.argv[2] if len(sys.argv) > 2 else "figures"
    reps = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    os.makedirs(res, exist_ok=True)
    os.makedirs(figs, exist_ok=True)
    df = sweep(reps)
    df.to_csv(f"{res}/exp4_batch_policy.csv", index=False)
    make_figure(df, f"{figs}/fig6_batch_policy.png")
    print("saved", f"{res}/exp4_batch_policy.csv", "and", f"{figs}/fig6_batch_policy.(png|pdf)")
