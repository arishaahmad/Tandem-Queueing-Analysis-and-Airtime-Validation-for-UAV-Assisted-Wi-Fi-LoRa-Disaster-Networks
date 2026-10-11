[README.md](https://github.com/user-attachments/files/33301639/README.md)
# UAV-Assisted Wi-Fi–LoRa Emergency Communication

A simulation-based research project exploring emergency reporting when terrestrial networks are unavailable. Ground devices send compact **11-byte status reports** to a UAV over **IEEE 802.11n Wi-Fi**; the UAV uses **LoRa** to reach a ground gateway and network server.

## Architecture

**Ground devices → Wi-Fi (2.4 GHz) → UAV relay → LoRa (868 MHz) → Ground gateway → Network server**

## What the project includes

- **OMNeT++ 6 + INET 4.4 + FLoRa 1.1.0:** packet-level Wi-Fi/LoRa network simulations and relay experiments.
- **Python:** a two-stage **M/D/1 queueing approximation** with Poisson report arrivals, airtime-based service times, and finite LoRa buffering.
- **Evaluation:** transmission airtime, packet delivery ratio, end-to-end delay, and the effects of traffic load, spreading factor, and buffer capacity.

## Preliminary findings

A single-device integrated simulation demonstrates the Wi-Fi-to-LoRa communication path, with **0.132 ms Wi-Fi airtime**, **66.816 ms LoRa airtime (SF7)**, and **67.461 ms observed end-to-end delay** for one report. In a separate 20-device experiment, **all 20 reports reached the UAV over Wi-Fi**. The multi-device LoRa forwarding and end-to-end delivery were **not fully established** in that run.

Independent Python queueing simulations indicate that the **LoRa backhaul becomes the bottleneck** as traffic increases. These analytical-model results should not be interpreted as measured end-to-end OMNeT++ delivery rates.

## Research scope

This is a **simulation/prototype research project**, not a deployed emergency communication service. The queueing model idealizes fixed packet airtimes and omits wireless errors, retransmissions, and regulatory duty-cycle constraints.

## Technologies

`OMNeT++` · `INET` · `FLoRa` · `Python` · `IEEE 802.11n` · `LoRa` · `Queueing Theory`
