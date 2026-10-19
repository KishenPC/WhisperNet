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

## Paper order for the professor review

After the letter A example and clean recovery, give about one minute of paper context in this order. These are project-specific priorities, not a ranking of publication quality.

| Order | Paper | Explain this point |
|---:|---|---|
| 1 | [Cabuk and colleagues 2004](https://doi.org/10.1145/1030083.1030108) | This is our base paper: it establishes the runnable timing channel and empirical detection problem. |
| 2 | [Gianvecchio and Wang 2007](https://doi.org/10.1145/1315245.1315284) | This paper explains why timing distributions and temporal dependence both matter to detection. |
| 3 | [Sellke and colleagues 2009](https://doi.org/10.1109/INFCOM.2009.5062145) | This is the noise-model paper: changing path delay distorts the gap, so separation and rate must be traded off. |
| 4 | [CoCo by Houmansadr and Borisov 2011](https://doi.org/10.1007/978-3-642-24178-9_22) | CoCo already separates a known timing baseline from the received signal; our contribution is the measured estimator comparison. |
| 5 | [Zillien and Wendzel 2023](https://doi.org/10.1109/TDSC.2023.3241451) | This paper supports our caution: detector success on one timing pattern need not generalize. |

Then return to the estimator and false-alarm graphs. If asked for more literature, use model-based traffic (Gianvecchio 2008), robustness/spreading (Liu 2009), higher-order timing (Liu 2019), practical mitigation (NetWarden 2020) and measurement fidelity (SketchFeature 2025). The pattern survey (Wendzel 2015) explains why this is an established inter-arrival-time hiding pattern.

The contribution to defend is the controlled estimator comparison and benign-drift evaluation with packet evidence. CoCo already subtracts a known timing sequence; WhisperNet uses intended pilot gaps to estimate residual variability, which measures gap distortion rather than one-way packet-delay variation. The present search does not establish a first-in-literature claim. Do not compare numerical accuracy or bitrate across papers with different datasets, carriers and overhead definitions. No cited coding, neural or P4 system has been added to this application.

The primary computer has 16 validated PDFs in `CNPapers`, a ranked `PAPER_INDEX.md` and full-text notes. The companion `WhisperNet-Literature-Review.docx` explains the methods and caveats. Access-limited candidates are listed separately; Zhang 2019 has no saved PDF. The recent GAF/MTF paper is optional reading because its reported performance tables are inconsistent.
