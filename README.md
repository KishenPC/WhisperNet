# WhisperNet

WhisperNet is a reproducible Linux/WSL2 lab for studying UDP timing channels, adaptive timing estimation, and statistical detection under changing network conditions.

## Run from Windows

Open PowerShell in this project folder. Ubuntu-24.04 must have Python venv support, iproute2 and tcpdump.

```powershell
.\whispernet.ps1 setup
.\whispernet.ps1 doctor
.\whispernet.ps1 test
.\whispernet.ps1 build
.\whispernet.ps1 demo
.\whispernet.ps1 experiment
```

Each run creates a new folder inside `results/`. Open its `index.html` in a browser to view charts, `report.pdf` for the printable draft, `report.tex` for editable LaTeX, or `report.md` for editable text. Reports and charts use black-and-white formatting. `results/latest.txt` records the latest completed bundle. Open `traffic.pcap` from an individual trial in Windows Wireshark.

For a longer repeated benchmark:

```powershell
.\whispernet.ps1 experiment --duration 12 --repeats 5
```

For a smaller first check:

```powershell
.\whispernet.ps1 experiment --duration 4 --repeats 1 --scenarios clean
```

Root is used only for commands that create the network laboratory (`demo` and `experiment`). They operate on uniquely named `wn-...` namespaces and remove those exact resources after a normal finish or an exception. Dependencies live in the default Ubuntu user's `~/.local/share/whispernet/venv`.

## Run on native Linux

```bash
sudo apt-get update
sudo apt-get install python3-venv tcpdump iproute2
bash scripts/setup.sh
bash scripts/run.sh test
sudo env WHISPERNET_VENV="$HOME/.local/share/whispernet/venv" bash scripts/run.sh experiment
```

Install the wheel from `dist/` in another Python environment to use the `whispernet` command. Live experiments require Linux namespace and traffic-control privileges; unit tests and offline reporting do not.

## What is implemented

- Sender and receiver as actual processes in separate Linux network namespaces.
- UDP timing encoding, constant-size packets, frame/index synchronization, known pilots and CRC32 validation.
- Fixed gaps, raw-variation adaptation, and known-symbol-residual adaptation.
- Clean, abrupt/recovery, gradual and burst-loss schedules applied with Linux netem.
- Non-idle benign pacing under identical schedules, plus legitimate application-rate changes on a clean link.
- Kernel receive timestamps where supported and receiver-side tcpdump captures.
- Offline KS/entropy and normalized/temporal detector baselines calibrated on separate benign runs.
- Substitutions, erasures, conditional BER, information failure, verified goodput, message-frame success, recovery and detection-delay measurements.
- CSV, raw JSON evidence, plots, a browser results page, and editable reports.

## Architecture

```text
Sender: 10.77.0.1/24                         Receiver: 10.77.0.2/24
message -> timing encoder -> UDP/39001 -> netem -> timestamps -> decoder
                                   virtual Ethernet              |
                <----- TCP/39002 lab metadata/feedback ----------+

Receiver-side PCAP -> timing-only detector -> ROC and false alarms
Sender/receiver logs -> offline evaluator -> reliability and goodput
```

The reliable TCP control plane communicates parameters and CRC, not plaintext message bytes. It is excluded from netem's UDP-only impairment and from timing-detector features, but its time cost is included in goodput. This is an explicit laboratory simplification, not a covert control protocol. The 12-byte UDP payload carries a magic value, frame number and symbol index. The information message is carried by packet gaps.

Each frame contains a timing anchor, eight known pilot symbols, and at most four message bytes. The receiver classifies a gap only when the two consecutive packet indices are adjacent. A missing packet therefore produces erasures rather than a guessed bit from a merged interval. Reordering and duplication are recorded. Complete frames are checked against CRC32, then the evaluator compares the original bits as well.

## Interpretation and limitations

- **No research novelty guarantee:** adaptive channels and statistical detection already exist. The experiment focuses on recovery, benign drift and estimator contamination.
- **No universal stealth claim:** these scores quantify distinguishability from the selected benign references. They do not identify hidden intent.
- **No assumed winner:** adaptation can improve or worsen different metrics. The report uses actual outcomes.
- **Loss is not hidden:** conditional BER is separate from erasure rate; verified goodput counts complete correct frames only.
- **Calibration is frozen:** evaluation windows cannot alter references or thresholds. The 5% calibration target is not a promised FPR under network changes.
- **Window dependence:** ROC windows are descriptive; confidence intervals are calculated from run-level values when at least three repeats are available. A small experiment is not strong statistical evidence.
- **Realism boundaries:** WSL scheduling, synthetic benign pacing, fixed pilots and a reliable lab control channel limit generalization. Native Linux and real traffic evaluation remain future work.
- **Recovery definition:** two consecutive checksum-valid frames wholly within a new regime; a missing observation is explicitly recorded, not assigned zero seconds.
- **Noise reproducibility:** application seeds and settings are logged; netem seed support is detected. Different packet schedules do not receive identical realized noise just because seeds match.

## Demonstration and measured results

Read `docs/demo-guide.md` for a live demonstration sequence, packet inspection, and sending a short message from two WSL terminals. `docs/measured-results.md` describes the repeated benchmark and its limitations. Benchmark run folders and packet captures are generated locally and are not included in this repository.

Each completed run includes a black-and-white LaTeX report with embedded chart data. No separate figures or bibliography files are needed to compile that report.

## Benchmark data

- The documented benchmark comprises 60 evaluation trials across five conditions with three repetitions, plus three separate calibration runs. The corresponding result folders and packet captures are generated locally and are not tracked here.
- `docs/measured-results.md`: a plain explanation of the benchmark outcomes and limits.

To regenerate charts, Markdown and the PDF from a completed bundle:

```powershell
.\whispernet.ps1 report results/benchmark-verified
```

