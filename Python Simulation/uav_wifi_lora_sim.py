#!/usr/bin/env python3
"""
UAV-assisted Wi-Fi -> LoRa relay: extended queueing simulation (ICCT2026 revision).

Model (stage by stage)
----------------------
Sources   : N devices, each sends one 11-byte report every `interval` s
            (periodic with random phase, or Poisson for comparison with M/D/1).
Stage 1   : Wi-Fi, single FIFO server, deterministic service T_w (infinite buffer).
Stage 2   : UAV buffer (K reports waiting room, excludes the frame in service)
            + LoRa transmitter. Each LoRa frame carries b reports (b = 1..B_max),
            payload = 11*b bytes, service time = LoRa time-on-air(11*b, SF).
            Policy: start a frame when (queue >= B_min) or (oldest report has
            waited T_to), taking up to B_max reports. B_min = 1 -> greedy.
Duty cycle: after a frame of duration T, the transmitter stays silent for
            T*(1/d - 1)  (d = 0.01 / 0.10 / 1.0).
UAV link  : periodic ON/OFF availability of the LoRa link to the ground gateway
            (UP seconds on, DOWN seconds off). A frame may only start if it
            finishes inside the UP window; otherwise it waits (store-and-forward).
Metrics   : packet delivery ratio (PDR), mean / p95 end-to-end delay,
            mean Age of Information (AoI) at the gateway, all after warm-up,
            10 independent replications, 95 % Student-t confidence intervals.

Everything below the 'LoRa airtime' header is deterministic maths; the only
random inputs are source phases / Poisson arrivals / link-window phase.
"""
import math
import os
import sys
import time

import numpy as np
import pandas as pd
from numba import njit
from scipy import stats

# ----------------------------------------------------------------------------
# LoRa airtime (Semtech SX127x datasheet formula), BW 125 kHz, CR 4/5,
# 8-symbol preamble, explicit header, CRC on.
# ----------------------------------------------------------------------------
APP_BYTES = 11          # type1 + id2 + lat3 + lon3 + status1 + battery1
MAX_LORA_PAYLOAD = 255  # bytes
B_MAX_PHY = MAX_LORA_PAYLOAD // APP_BYTES  # 23 reports per frame


def lora_toa(payload_bytes, sf, bw=125e3, cr=1, n_preamble=8, header=True, crc=True):
    """Time on air in seconds."""
    ts = (2 ** sf) / bw
    de = 1 if (sf >= 11 and bw == 125e3) else 0   # low-data-rate optimisation
    ih = 0 if header else 1
    num = 8 * payload_bytes - 4 * sf + 28 + 16 * int(crc) - 20 * ih
    den = 4 * (sf - 2 * de)
    n_pay = 8 + max(math.ceil(num / den) * (cr + 4), 0)
    return (n_preamble + 4.25) * ts + n_pay * ts


def toa_table(sf, bmax):
    """toa_tab[b] = time on air of a frame with b aggregated reports."""
    tab = np.zeros(bmax + 1)
    for b in range(1, bmax + 1):
        tab[b] = lora_toa(APP_BYTES * b, sf)
    return tab


# Wi-Fi 802.11n, 2.4 GHz, 20 MHz, MCS0 (6.5 Mb/s): airtime of the 77-byte frame
# as given in the progress summary, plus an *approximate* CSMA/CA overhead
# (DIFS 28 us + mean backoff 7.5 slots x 9 us + SIFS 10 us + legacy-rate ACK 44 us).
TW_BASE = 0.142e-3
TW_WITH_MAC = TW_BASE + (28e-6 + 7.5 * 9e-6 + 10e-6 + 44e-6)   # ~0.29 ms, no collisions


# ----------------------------------------------------------------------------
# Traffic generation and Wi-Fi stage
# ----------------------------------------------------------------------------
def gen_arrivals(n_dev, interval, sim_time, rng, mode="periodic"):
    """Return (gen_times sorted, device ids)."""
    if mode == "periodic":
        phases = rng.uniform(0.0, interval, n_dev)
        k = int(sim_time / interval) + 2
        t = phases[:, None] + interval * np.arange(k)[None, :]
        d = np.repeat(np.arange(n_dev)[:, None], k, axis=1)
        t, d = t.ravel(), d.ravel()
        m = t < sim_time
        t, d = t[m], d[m]
    elif mode == "poisson":
        rate = n_dev / interval
        n = int(rate * sim_time * 1.05) + 100
        t = np.cumsum(rng.exponential(1.0 / rate, n))
        t = t[t < sim_time]
        d = rng.integers(0, n_dev, t.size)
    else:
        raise ValueError(mode)
    o = np.argsort(t, kind="stable")
    return t[o], d[o]


def wifi_stage(arr, tw):
    """FIFO deterministic single server: departure times (vectorised Lindley)."""
    n = arr.size
    idx = np.arange(n)
    return np.maximum.accumulate(arr - idx * tw) + (idx + 1) * tw


# ----------------------------------------------------------------------------
# LoRa stage (event-driven, numba)
# ----------------------------------------------------------------------------
@njit(cache=True)
def lora_stage(arr, K, bmax, bmin, tto, toa_tab, duty, up, down, phase):
    """
    arr      : sorted arrival times of reports at the UAV buffer
    K        : waiting-room size (reports), excludes the frame being sent
    returns  : delivery time at the gateway per report (nan = dropped)
    """
    n = arr.shape[0]
    deliv = np.full(n, np.nan)
    queue = np.empty(n, np.int64)
    head = 0
    tail = 0
    free_at = 0.0
    t_last = 0.0
    period = up + down
    i = 0
    while True:
        t_next = arr[i] if i < n else np.inf
        # start as many frames as possible before the next arrival
        while tail - head > 0:
            qlen = tail - head
            if qlen >= bmin:
                s = max(free_at, t_last)
            else:
                s = max(free_at, arr[queue[head]] + tto)
            nb = qlen if qlen < bmax else bmax
            toa = toa_tab[nb]
            if down > 0.0:
                pos = (s - phase) % period
                if pos >= up or pos + toa > up:
                    s = s + (period - pos)          # wait for next UP window
            if s > t_next:
                break
            for j in range(nb):
                deliv[queue[head + j]] = s + toa
            head += nb
            free_at = s + toa / duty                # duty-cycle off-time included
        if i >= n:
            break
        t_last = arr[i]
        if tail - head < K:
            queue[tail] = i
            tail += 1
        i += 1
    return deliv


# ----------------------------------------------------------------------------
# One replication -> metrics
# ----------------------------------------------------------------------------
def aoi_mean(gen, dev, deliv, n_dev):
    """Time-average AoI at the gateway, averaged over devices."""
    ok = ~np.isnan(deliv)
    vals = []
    for j in range(n_dev):
        m = ok & (dev == j)
        g, d = gen[m], deliv[m]
        if g.size < 2:
            continue
        o = np.argsort(d, kind="stable")
        g, d = g[o], d[o]
        area = 0.5 * np.sum((d[1:] - g[:-1]) ** 2 - (d[:-1] - g[:-1]) ** 2)
        span = d[-1] - d[0]
        if span > 0:
            vals.append(area / span)
    return float(np.mean(vals)) if vals else np.nan


DEFAULT = dict(
    n_dev=20, interval=1.0, mode="periodic", sim_time=5500.0, warmup=500.0,
    sf=7, K=20, bmax=1, bmin=1, tto=1e9, duty=1.0, up=1.0, down=0.0,
    tw=TW_BASE,
)


def run_once(cfg, seed):
    c = {**DEFAULT, **cfg}
    rng = np.random.default_rng(seed)
    gen, dev = gen_arrivals(c["n_dev"], c["interval"], c["sim_time"], rng, c["mode"])
    a = wifi_stage(gen, c["tw"])
    tab = toa_table(c["sf"], c["bmax"])
    if c["down"] > 0:
        assert c["up"] > tab[c["bmax"]], "UP window shorter than a frame"
    phase = rng.uniform(0, c["up"] + c["down"]) if c["down"] > 0 else 0.0
    deliv = lora_stage(a, c["K"], c["bmax"], c["bmin"], c["tto"], tab,
                       c["duty"], c["up"], c["down"], phase)
    m = gen >= c["warmup"]
    dl = ~np.isnan(deliv)
    gen_n = int(m.sum())
    rec_n = int((dl & m).sum())
    delay = (deliv - gen)[dl & m]
    return dict(
        generated=gen_n, received=rec_n,
        pdr=100.0 * rec_n / gen_n,
        delay_mean_ms=1e3 * delay.mean() if delay.size else np.nan,
        delay_p95_ms=1e3 * np.percentile(delay, 95) if delay.size else np.nan,
        aoi_s=aoi_mean(gen[m], dev[m], deliv[m], c["n_dev"]),
    )


def replicate(cfg, reps=10, seed0=1000):
    rows = [run_once(cfg, seed0 + r) for r in range(reps)]
    df = pd.DataFrame(rows)
    out = {}
    tcrit = stats.t.ppf(0.975, reps - 1)
    for col in ["pdr", "delay_mean_ms", "delay_p95_ms", "aoi_s"]:
        x = df[col].to_numpy(float)
        out[col] = np.nanmean(x)
        out[col + "_ci"] = tcrit * np.nanstd(x, ddof=1) / math.sqrt(np.sum(~np.isnan(x))) \
            if np.sum(~np.isnan(x)) > 1 else np.nan
    out["generated"] = int(df.generated.mean())
    return out


# ----------------------------------------------------------------------------
# Analytical M/D/1/K blocking probability (embedded Markov chain)
# ----------------------------------------------------------------------------
def md1k_blocking(lam, T, W):
    """Blocking probability of M/D/1 with W waiting places (system size W+1)."""
    Ks = W + 1
    rho = lam * T
    kmax = 400 + int(10 * rho)
    a = stats.poisson.pmf(np.arange(kmax), rho)
    P = np.zeros((Ks, Ks))
    for i in range(Ks):
        base = max(i - 1, 0)
        for j in range(base, Ks - 1):
            P[i, j] = a[j - base]
        P[i, Ks - 1] = max(0.0, 1.0 - P[i, :Ks - 1].sum())
    A = P.T - np.eye(Ks)
    A[-1, :] = 1.0
    b = np.zeros(Ks)
    b[-1] = 1.0
    pi = np.linalg.solve(A, b)
    return 1.0 - 1.0 / (pi[0] + rho)


# ----------------------------------------------------------------------------
# Experiments
# ----------------------------------------------------------------------------
SFS = [7, 8, 9]
WAITING_ROOMS = [1, 5, 10, 15, 20, 30, 40, 50, 75, 100]


def exp0_baseline(reps):
    """Reproduce the progress-summary baseline + Poisson vs periodic + M/D/1/K."""
    rows = []
    for sf in SFS:
        T = lora_toa(APP_BYTES, sf)
        for W in WAITING_ROOMS:
            for mode in ["poisson", "periodic"]:
                r = replicate(dict(sf=sf, K=W, mode=mode), reps)
                rows.append(dict(sf=sf, W=W, mode=mode, **r,
                                 analytic_pdr=100 * (1 - md1k_blocking(20.0, T, W))))
    return pd.DataFrame(rows)


def exp_wifi_sensitivity(reps):
    rows = []
    for tw in [0.142e-3, TW_WITH_MAC, 1e-3, 5e-3, 20e-3, 40e-3]:
        r = replicate(dict(sf=7, K=20, tw=tw, mode="poisson"), reps)
        rows.append(dict(tw_ms=tw * 1e3, wifi_util=20 * tw, **r))
    return pd.DataFrame(rows)


def exp1_aggregation(reps):
    """20 pkt/s, no duty cycle: effect of batching on PDR, delay, AoI."""
    rows = []
    for sf in SFS:
        for b in [1, 2, 3, 5, 8, 12, 16, 20, 23]:
            r = replicate(dict(sf=sf, K=100, bmax=b), reps)
            rows.append(dict(sf=sf, bmax=b, toa_ms=1e3 * lora_toa(APP_BYTES * b, sf),
                             cap_pps=b / lora_toa(APP_BYTES * b, sf), **r))
    return pd.DataFrame(rows)


def capacity_table():
    """Saturation capacity of the LoRa stage (reports/s) and max devices."""
    rows = []
    for sf in SFS:
        for duty in [1.0, 0.10, 0.01]:
            for b in [1, 5, 10, 23]:
                toa = lora_toa(APP_BYTES * b, sf)
                cap = b * duty / toa
                row = dict(sf=sf, duty=duty, bmax=b, toa_ms=1e3 * toa, cap_pps=cap)
                for iv in [1, 5, 10, 30, 60]:
                    row[f"N_max@{iv}s"] = int(math.floor(cap * iv))
                rows.append(row)
    return pd.DataFrame(rows)


def exp2_duty(reps):
    """20 devices, vary reporting interval and duty cycle; greedy batching B<=23."""
    rows = []
    for duty in [1.0, 0.10, 0.01]:
        for sf in SFS:
            for iv in [1, 2, 5, 10, 30, 60, 120]:
                r = replicate(dict(sf=sf, K=100, bmax=B_MAX_PHY, duty=duty, interval=iv,
                                   sim_time=30000.0, warmup=3000.0), reps)
                rows.append(dict(duty=duty, sf=sf, interval=iv, **r))
    return pd.DataFrame(rows)


def exp3_outage(reps):
    """Store-and-forward during UAV link outages (SF7, aggregation, 4 reports/s)."""
    rows = []
    UP = 300.0
    for down in [0.0, 15.0, 30.0, 60.0, 120.0]:
        for K in [10, 25, 50, 100, 200, 300, 500, 1000]:
            r = replicate(dict(sf=7, K=K, bmax=B_MAX_PHY, interval=5.0, up=UP, down=down,
                               sim_time=40000.0, warmup=2000.0), reps)
            rows.append(dict(down=down, K=K, availability=UP / (UP + down), **r))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "results"
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    # sanity: airtimes must match the progress summary
    for sf, ref in zip(SFS, [41.216, 82.432, 144.384]):
        assert abs(1e3 * lora_toa(APP_BYTES, sf) - ref) < 1e-3, (sf, lora_toa(APP_BYTES, sf))
    print("airtime check OK; Tw with MAC overhead = %.3f ms" % (1e3 * TW_WITH_MAC))

    for name, fn in [("exp0_baseline", exp0_baseline), ("exp_wifi_sensitivity", exp_wifi_sensitivity),
                     ("exp1_aggregation", exp1_aggregation), ("exp2_duty", exp2_duty),
                     ("exp3_outage", exp3_outage)]:
        t = time.time()
        df = fn(reps)
        df.to_csv(f"{out}/{name}.csv", index=False)
        print(f"{name}: {len(df)} rows in {time.time() - t:.1f}s", flush=True)
    capacity_table().to_csv(f"{out}/capacity_table.csv", index=False)
    print(f"done in {time.time() - t0:.1f}s")
