# WhisperNet demonstration walkthrough

This walkthrough explains how to run the project, open its dashboard and use it in a professor review.

## What the dashboard is

Each run creates a local `index.html` that displays its plots and links to the CSV, JSON evidence and generated report. It is a static file: open it in a browser; no server is required. A short demonstration checks that the system works. Use the separate repeated benchmark dashboard for comparative averages.

## Before the review

Open PowerShell in the project folder. On a fresh WSL setup, install the Ubuntu prerequisites listed in the README, then run setup once. Check the environment and package before the presentation:

```powershell
.\whispernet.ps1 setup   # only on a new computer
.\whispernet.ps1 doctor
.\whispernet.ps1 test
.\whispernet.ps1 build
```

The existing review-ready demonstration is in `results/review-ready-20261019`. It completed seven evaluation configurations plus three calibration runs. To open it now:

```powershell
Start-Process .\results\review-ready-20261019\index.html
```

For the review date, create a new run folder so its results do not overwrite the prepared snapshot:

```powershell
.\whispernet.ps1 demo --output results\professor-review-20261021
Start-Process .\results\professor-review-20261021\index.html
```

The launcher runs the network experiment in Ubuntu-24.04 on WSL2. The demo takes a few minutes because a slow adaptive frame may overrun its target duration. WSL experiments temporarily pause an active guest `systemd-timesyncd` service and restore it after a normal completion or Python exception.

## What to show, in order

1. **Start with the letter A.** A is `01000001`; fixed mode maps 0 to a 12 ms gap and 1 to 36 ms. The receiver uses a 24 ms threshold.
2. **Show the live clean result.** In the terminal, point out the recovered `WhisperNet` message from the clean fixed configuration. Explain that the payload carries frame/index metadata; the bits are carried by the gaps.
3. **Open the fresh run dashboard.** Show the adaptation and performance plots, then the false-alarm plot for benign traffic. Keep the fresh run’s per-configuration results separate from benchmark averages.
4. **Open the repeated benchmark dashboard.** Run `Start-Process .\results\benchmark-verified\index.html`. Explain it contains 60 evaluation runs (four modes × five conditions × three repeats) plus three separate calibration runs. Use it for mean comparisons and error bars.
5. **Show one packet capture.** Open `results\review-ready-20261019\clean-fixed-2001\traffic.pcap` in Wireshark and filter with `udp.dstport == 39001`. Show the two addresses, 12-byte UDP payload and packet arrival gaps. Open that trial’s `receiver.json` to connect the gaps to decoded symbols, erasures and CRC status.
6. **End with one finding and one limitation.** Correcting pilot contamination avoids a clean-link slowdown, but the naive controller had fewer failures during gradual worsening. The benign-pacing detector result improves substantially with normalization, but not for every network-drift case.

## Dashboard figures in plain language

- **Adaptation:** fixed spacing remains level; naive spacing grows because it treats intended 0/1 pilot differences as network variation; corrected spacing tracks residual variation. The graph is one representative abrupt trial.
- **Performance:** the left chart reports substitutions plus erasures; the right chart reports correct bits from fully verified frames per total sender time. Goodput includes pilot, feedback and settling overhead.
- **False alarms:** the dashed 5% level is a calibration target, not a guarantee. On benign pacing changes, the raw detector flagged 76.7% of windows and the normalized score 6.7%. On gradual network drift, normalization was worse (18.5% vs 14.8%).
- **ROC:** the curve shows the trade-off between detecting labeled channel windows and false alarms as the score threshold changes. These windows are dependent, so this ROC describes this controlled dataset rather than proving general performance.

## Packet-level story

The namespaces use 10.77.0.1/24 and 10.77.0.2/24. UDP/39001 carries timed data through netem; TCP/39002 carries reliable laboratory settings, pilot feedback and CRC status. The 12-byte UDP payload contains a marker, frame number and symbol index. It does not carry the user’s message bytes. A missing or reordered packet can destroy gap alignment, so affected symbols are marked as erasures. CRC32 detects a bad complete frame but does not repair it or authenticate a sender.

## If the professor asks for a manual A test

Open two Ubuntu terminals in the repository. Start the receiver first, then run the sender:

```bash
bash scripts/run.sh receive --bind 127.0.0.1 --output results/manual-receiver.json --ready results/manual-ready
```

In the second terminal:

```bash
bash scripts/run.sh send --host 127.0.0.1 --mode fixed --message A --output results/manual-sender.json
```

This loopback example demonstrates encoding and decoding. It has no netem impairment; use the namespace demo for impairment and controller behavior.

## Claims to keep precise

The benchmark is from WSL2 with synthetic benign pacing, three repeats per configuration and a fixed trial order. The fixed reference was not tuned to an optimum. The TCP lab control path is visible. Native Linux, real application traffic, error-correcting codes, retransmission-based repair, authentication and encryption are outside this implementation. A detector alarm indicates unusual timing relative to its reference, not covert intent.

For the complete technical explanation and paper roles, see the Word teammate guide in `output/docx/WhisperNet-Teammate-Guide.docx` and the separate paper library in the `CNPapers` folder on the primary project computer (share that folder separately if needed).
