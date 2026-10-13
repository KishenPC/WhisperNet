# WhisperNet

WhisperNet is a working networking lab that sends a message through the time gaps between UDP packets. The receiver decodes the message from arrival timestamps. The lab then measures how jitter, packet loss, and changing application rates affect communication and statistical detection.

## How the project works

For a simple example, the letter **A** is the byte `01000001`. The fixed sender represents `0` with a **12 ms** gap and `1` with a **36 ms** gap. A receiver threshold of **24 ms** recovers the bits. The intended information gaps are:

```text
Bits       0   1   0   0   0   0   0   1
Gaps ms   12  36  12  12  12  12  12  36
```

The 12-byte UDP payload contains a magic value, frame number, and symbol index. Message bytes are represented by the gaps. A frame adds one anchor packet and eight known pilots, so the one-byte A example uses 17 packets. A full four-byte information frame uses 41 packets.

```text
Sender 10.77.0.1/24                       Receiver 10.77.0.2/24
message -> bits -> timed UDP/39001 -> netem -> timestamps -> decoder
                     virtual Ethernet                       |
          <--- TCP/39002 parameters and pilot feedback ------+

Receiver-side packet capture -> offline timing detector -> alarms
Sender and receiver logs -> evaluator -> verified goodput and errors
```

The two endpoints run as separate Linux network namespaces. `netem` changes UDP delay, jitter, and loss. The TCP connection supplies reliable lab metadata and feedback; its elapsed time is included in useful throughput. This is a disclosed laboratory simplification.

Missing or reordered packets produce unknown bits called **erasures**. Complete frames are checked using CRC32. CRC detects errors; the implementation measures failed frames rather than repairing them.

## What the comparison tests

| Mode | Timing rule |
|---|---|
| Fixed | Keep 12/36 ms gaps. |
| Naive adaptive | Estimate variation directly from received pilot gaps. |
| Corrected adaptive | Subtract each pilot's intended gap before estimating variation. |
| Benign | Generate application pacing independently of information bits. |

Both adaptive policies set gap separation to four times their estimated standard deviation, clipped to 16–160 ms. The short gap stays at 12 ms; settings change on the next frame. Raw pilot variation includes the deliberately different symbol gaps, which can make the naive policy widen its own gap separation.

The detector uses captured UDP arrival times, with 32 gaps per window. It compares a raw KS/entropy score with a score using median-normalized gaps and lag-one correlation. Complete benign runs supply the reference and threshold calibration; evaluation runs cannot update them. The nominal calibration false-alarm target is 5%.

The experiment includes clean, abrupt/recovery, gradual, burst-loss, and legitimate application-pacing conditions. It measures conditional bit error, erasures, information failure, verified goodput, recovery, and timing-window alarms. Timing channels and these statistical methods have prior work; the project studies their controlled trade-offs.

## Install and check

### Windows with WSL2

Install **Ubuntu-24.04** in WSL2. In Ubuntu, install the system dependencies:

```bash
sudo apt-get update
sudo apt-get install python3-venv tcpdump iproute2
```

Clone this repository and open PowerShell in its folder:

```powershell
git clone https://github.com/KishenPC/WhisperNet.git
cd WhisperNet
```

Then run:

```powershell
.\whispernet.ps1 setup
.\whispernet.ps1 doctor
.\whispernet.ps1 test
.\whispernet.ps1 build
```

Setup creates the Linux environment at `~/.local/share/whispernet/venv`. Doctor checks the Python dependencies and Linux tools. The test suite contains 25 tests, including actual socket recovery, clock readiness and service cleanup. Build produces the wheel and source distribution in `dist/`.

### Native Linux

```bash
sudo apt-get update
sudo apt-get install python3-venv tcpdump iproute2
bash scripts/setup.sh
bash scripts/run.sh test
bash scripts/run.sh build
sudo env WHISPERNET_VENV="$HOME/.local/share/whispernet/venv" bash scripts/run.sh demo
```

Live experiments need Linux networking privileges. Unit tests, building, and offline reports do not need root. The Windows launcher requests root only for demo/experiment, and the lab removes its uniquely named `wn-...` namespaces when finished.

## Demonstrate WhisperNet

1. Explain the A example and the two endpoint addresses above.
2. Start the live demo while explaining the frame and feedback flow:

   ```powershell
   .\whispernet.ps1 demo
   ```

3. Allow roughly 2–3 minutes. On native Linux, initial clock synchronization may add up to a minute. The clean fixed trial prints a verified message. Then show a noisy-link failure and the adaptive gap changes. Complete frames can make trials exceed their target duration.
4. Find the new result folder from the terminal output or `results/latest.txt`. Open its `index.html`; show the adaptation plot, useful-throughput comparison, and false alarms on benign traffic.
5. Open a trial's `traffic.pcap` in Wireshark. Use `udp.dstport == 39001`; show the addresses, constant payload size, and varying packet gaps. Connect this to decoded bits, erasures, and CRC status in `receiver.json`.
6. Discuss one improvement and one limitation. Wider gaps sometimes reduce errors, so corrected adaptation does not win every comparison. Detector alarms show unusual timing relative to a reference; they do not establish covert intent.

For a shorter clean-link check:

```powershell
.\whispernet.ps1 experiment --duration 4 --repeats 1 --scenarios clean
```

For repeated comparison across all conditions:

```powershell
.\whispernet.ps1 experiment --duration 8 --repeats 3
```

Do not run timing experiments concurrently when comparing performance. Instructions for a custom A message from two WSL terminals are in [the demo guide](docs/demo-guide.md).

On WSL, the lab temporarily stops an active guest `systemd-timesyncd` service during experiments to avoid clock steps competing with host time. It restarts that service after a normal finish or Python exception, without changing its enabled configuration or the Windows clock. On native Linux it waits for the first update when that service is active. A backwards clock step still aborts the capture rather than silently altering timestamps. After forcibly terminating a WSL run, check the service and start it if necessary with `sudo systemctl start systemd-timesyncd`.

If a run reports `Capture timestamps are not ordered`, retain it as an invalid diagnostic and investigate host/guest clock synchronization before retrying. Matching packet counts alone does not establish valid timing evidence. On some WSL installations, later guest clock adjustments can invalidate a run even after the initial time update.

## Results and evidence

Each result bundle contains raw JSON logs, packet captures, CSV measurements, charts, a browser results page, and editable Markdown/LaTeX plus a PDF report. These files are generated locally and are not tracked in Git.

The verified three-repeat benchmark contained 60 evaluation runs and three separate calibration runs. Clean-link mean verified goodput was 26.56, 13.30, and 29.40 bit/s for fixed, naive, and corrected timing. Under gradual worsening, naive adaptation had fewer information failures. For benign pacing changes, raw and normalized detector false-positive rates were 76.7% and 6.7%, respectively; normalization did not improve every network-drift case. See [measured results](docs/measured-results.md) for definitions and limits.

Regenerate outputs from a saved bundle with:

```powershell
.\whispernet.ps1 report results/your-run-folder
```

## Scope and limitations

The agreed laboratory is implemented end to end. Its evidence is from WSL2, synthetic benign pacing, fixed-order trials, and three benchmark repeats per condition. The fixed baseline is not tuned to an optimum, and the installed `tc` version does not support seeded netem noise. Real Internet paths and native Linux have not been validated. Error correction, automatic retransmission, authentication, and encryption are future work.
