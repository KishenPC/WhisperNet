# WhisperNet — teammate guide and professor pitch

For Kishen and Aarav. Read Sections 1–6 first to understand the idea, Sections 7–10 to explain the evidence, and Sections 11–14 to rehearse the demonstration.

Repository: https://github.com/KishenPC/WhisperNet

## 1. What the project actually is

WhisperNet is a working computer-networking experiment. A sender represents message bits using **short and long gaps between UDP packets**. A receiver reconstructs those bits from packet arrival times. We deliberately introduce delay variation and packet loss, compare three timing policies, and test whether a statistical detector mistakes ordinary traffic changes for suspicious communication.

The project combines socket programming, IPv4 addressing, Linux network namespaces, network emulation, packet capture, signal estimation and statistical evaluation.

The central question is:

> How do timing adaptation and statistical detection behave when the network changes—and can the controller confuse its own encoding with network noise?

It is a controlled laboratory study. The implementation is complete for that scope. It is not a production messaging service, a secure communication product or a claim that timing channels were invented here.

### A 30-second opening

> Our project is WhisperNet. Instead of placing a message in UDP packet contents, we encode its bits in the time gaps between packets. We investigate how jitter and loss affect decoding, compare fixed timing with two adaptive policies, and measure statistical detection. Our main finding is that a naive controller can mistake its own short and long symbols for network noise. Correcting that estimate improves clean-link throughput, but wider gaps can still be more reliable under impairment. We also measure false alarms caused by legitimate changes in normal traffic.

## 2. Start with the letter A

The character `A` has the eight-bit representation `01000001`.

| Information bit | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Intended gap in milliseconds | 12 | 36 | 12 | 12 | 12 | 12 | 12 | 36 |

For fixed timing, the receiver compares each valid arrival gap with **24 ms**:

- At or below 24 ms: decode `0`.
- Above 24 ms: decode `1`.

The eight decoded bits become the original byte and therefore the character `A`.

The application still sends real UDP packets. Their contents identify the frame and symbol position; the message bytes themselves are represented by timing. This metadata lets the receiver identify missing packets without pretending that a merged interval represents one valid bit.

**Delay versus jitter:** a constant added delay shifts arrivals together and ideally preserves gaps. Jitter changes delays from packet to packet, so it can change a short observed gap into a long one. Very late packets can also miss the receiver's frame timing limits.

## 3. The system architecture

![WhisperNet system architecture](https://raw.githubusercontent.com/KishenPC/WhisperNet/main/docs/whispernet-architecture.png)

| Component | What it does |
|---|---|
| Sender | Converts UTF-8 bytes to bits and schedules UDP packets. |
| Virtual network | Connects isolated endpoints and applies controlled impairment to UDP traffic. |
| Receiver | Records arrivals, decodes gaps, checks complete frames and returns pilot feedback. |
| Packet capture | Records receiver-side UDP traffic in a PCAP file. |
| Offline detector | Uses captured arrival times to calculate timing scores and alarms. |
| Experiment/report pipeline | Runs comparisons and generates logs, CSV, plots, HTML and printable reports. |

The sender and receiver run in separate **Linux network namespaces**: isolated network environments with their own interfaces and addresses. A virtual Ethernet link connects them.

| Setting | Value |
|---|---|
| Sender address | `10.77.0.1/24` |
| Receiver address | `10.77.0.2/24` |
| Timing data | UDP destination port `39001` |
| Laboratory control and feedback | TCP port `39002` |
| UDP application payload | 12 bytes |

`netem`, a Linux traffic-control facility, adds delay, jitter and loss. These are actual processes and packets in a virtual network, rather than a spreadsheet simulation.

**Why UDP?** UDP allows the application to control its sending schedule without TCP retransmission and congestion control changing the data stream. Reliability is measured explicitly instead of being supplied automatically by the transport.

**Why also TCP?** A separate reliable laboratory connection coordinates frames, supplies parameters and CRC32, and returns feedback. It is excluded from the UDP impairment. Its elapsed-time overhead still counts in goodput. This makes the experiment reproducible, but exposes metadata and limits claims about real-world covertness.

## 4. Exactly what happens during transmission

1. The sender converts the message to UTF-8 bytes and splits it into chunks of at most **four bytes**.
2. It selects timing parameters for the next frame.
3. TCP sends the frame number, information length, timing parameters and CRC32. The receiver acknowledges readiness.
4. The sender emits an **anchor packet**, which supplies the starting timestamp.
5. It sends eight known pilot symbols: `01011010`.
6. It sends the information symbols, one gap per bit.
7. It waits **180 ms** for outstanding data, then sends a frame-end marker over TCP.
8. The receiver classifies valid gaps, marks unknown information as erasures, and checks CRC32 when a frame is complete.
9. The receiver returns pilot statistics and frame status. The sender can update timing for the next frame.

This repeats until the message has been sent. Timed experiments can repeat message chunks until their target duration is reached. Frames finish normally, so a trial can overrun that target.

### What is inside the UDP payload?

| Field | Bytes | Purpose |
|---|---:|---|
| `WN01` | 4 | Identify WhisperNet data packets. |
| Frame number | 4 | Identify the current frame. |
| Symbol index | 4 | Identify the packet position within the frame. |

The **12 bytes exclude Ethernet, IP and UDP headers**. In Wireshark, distinguish application payload size from total packet size.

A full four-byte frame contains **41 packets**: one anchor, eight pilots and 32 information symbols. A one-byte `A` frame contains **17 packets**: one anchor, eight pilots and eight information symbols. The pilots estimate variation; the anchor defines the first pilot interval.

### Loss, reordering and CRC

The receiver only classifies gaps between consecutive symbol indices arriving in order. If a packet is missing, two intervals can merge. That merged interval is not guessed as a single bit; affected information is marked unknown, or an **erasure**. Duplicate packets are counted without repeatedly decoding the same index.

A **substitution** is a decoded bit with the wrong value. An **erasure** is a bit the receiver cannot decode reliably from the available sequence.

CRC32 checks complete reconstructed frames. It detects corruption; it does not repair missing information, authenticate the sender or encrypt the message. The implementation has no automatic retransmission or error-correcting code.

## 5. The three timing policies

| Policy | Estimate | Response |
|---|---|---|
| Fixed | No adaptation | Always use 12/36 ms gaps. |
| Naive adaptive | Standard deviation of observed pilot gaps | Increase separation when raw variation rises. |
| Corrected adaptive | Standard deviation after subtracting each pilot's intended gap | Adapt using variation remaining after the known timing signal is removed. |

For both adaptive policies:

`separation = clip(4 × estimated standard deviation, 16 ms, 160 ms)`

`short gap = 12 ms; long gap = 12 ms + separation`

Thus adaptive long gaps range from **28 to 172 ms**. Updates apply to the **next frame**, not midway through the current one. With fewer than four valid pilot measurements, the controller holds its previous setting.

### Why correction matters

Imagine a perfect network with balanced 12/36 ms pilots. Their raw standard deviation is already **12 ms**, even though the network introduced no noise. The naive controller therefore selects 48 ms separation, producing **12/60 ms** gaps. Repeating this feedback can widen the timing further because its own larger symbol difference increases raw variation.

The corrected estimator subtracts 12 ms from intended short pilots and 36 ms from intended long pilots. In the ideal case all residuals are zero. It therefore uses the 16 ms separation floor, producing **12/28 ms** gaps.

The point is not simply that adaptation exists. It is that the noise estimate must account for the signal deliberately created by the encoder.

Wider gaps have a benefit as well: they can make the two timing classes easier to distinguish under jitter. Consequently, faster corrected timing does not necessarily produce fewer errors.

## 6. Statistical detection and benign controls

The detector runs **offline after capture**. Its input is UDP arrival timestamps from the receiver's PCAP. It does not read message bits, controller feedback or impairment schedules to construct its timing features. The experiment evaluator separately uses known modes and expected bits to measure performance.

Consecutive arrival times become gaps. The detector uses non-overlapping windows of **32 gaps**, including gaps between frames. It discards an incomplete final window.

Two scores are compared:

| Score | Meaning |
|---|---|
| Raw KS/entropy | Compare the gap distribution with a benign reference, plus a difference in histogram entropy. |
| Normalized temporal | Divide each window's gaps by its median, compare that distribution, and add a difference in neighboring-gap correlation. |

**KS distance** measures how far two empirical distributions differ. **Entropy** summarizes how gap observations spread across fixed bins. **Lag-one correlation** measures the relationship between neighboring gaps. Normalization reduces sensitivity to a simple change in timing scale.

The implemented scores are:

- Raw: `KS distance + abs(window entropy − reference entropy) / 4`.
- Normalized: `KS distance after median normalization + abs(window correlation − reference correlation) / 2`.

These are declared combinations of established statistics, rather than exact replicas of a published detector.

### Calibration is separate from evaluation

Three complete benign runs are reserved for calibration. Run `1001` supplies the reference; runs `1002` and `1003` supply threshold calibration. Evaluation runs beginning at `2001` remain held out. Evaluation traffic cannot update the thresholds.

The nominal calibration target is **5% false alarms**. This is not a guarantee that only 5% of new benign windows will be flagged, especially when network or application behavior changes.

**Benign traffic** uses random application pacing independent of message bits. It retains the framing scaffold so that comparable experiment machinery is used. It is tested under network changes and under deliberate legitimate rate changes on a clean link. Communication BER and goodput are not meaningful for this mode, because it has no timing-encoded information message.

An alarm means timing differs from the tested benign reference. It does not prove malicious intent. ROC curves compare true-positive and false-positive rates as the threshold varies; the labels come from the controlled experiment.

## 7. What conditions are tested?

| Condition | Schedule |
|---|---|
| Clean | 4 ms delay, 0.5 ms jitter, no configured loss. |
| Abrupt | At 2 s: 40 ms delay, 8 ms jitter, 2% loss. At 5 s: return to clean settings. |
| Gradual | At 2/4/6 s: delay 20/30/40 ms, jitter 3/6/8 ms, loss 0/1/2%. |
| Burst | Abrupt schedule with correlated Gilbert–Elliott loss, about 1.92% long-run average in the configured bad period. |
| Pacing | Clean network; benign application gap multiplier becomes 0.55 at 2 s and 1.5 at 5 s. |

The repeated benchmark has **four modes × five conditions × three repetitions = 60 evaluation trials**, plus three independent calibration trials. Trial targets are eight seconds, with complete-frame overrun allowed.

The short demonstration instead uses seven evaluation trials: fixed/clean, fixed/abrupt, naive/abrupt, corrected/abrupt, benign/clean, benign/abrupt and benign/pacing. It also performs three calibration trials. It does not rerun the entire benchmark.

Configured loss is a probability or model setting, not the exact realized loss. Actual changes and measurements are saved. The tested `tc` version does not support seeded netem noise, so matching application seeds do not guarantee identical network noise.

## 8. How to read the metrics

| Metric | Definition and interpretation |
|---|---|
| Conditional BER | Wrong decoded bits divided by non-erased information bits. Can look low even when many bits are missing. |
| Erasure rate | Unknown information bits divided by all transmitted information bits. |
| Information failure | Wrong plus erased information bits divided by all transmitted information bits. |
| Frame success | Fraction of complete frames that pass CRC and match expected information during evaluation. |
| Verified goodput | Correct information bits in verified complete frames divided by total sender elapsed time. Includes pilot, control and settling overhead. |
| Recovery | Time to two consecutive verified frames fully contained in the changed regime. If this is not observed before that regime ends, recovery is censored, not assigned zero. |
| False-positive rate | Fraction of benign windows flagged by the detector. |
| True-positive rate | Fraction of timing-channel windows flagged under the evaluation labels. |

For example, with 100 information bits, 10 erasures and five substitutions, conditional BER is `5/90 = 5.6%`, but information failure is `15/100 = 15%`. This is why showing BER alone would be misleading.

Goodput is stricter still: a partly correct frame that fails verification contributes no verified frame bits.

## 9. The results we can defend

The following are means from the recorded three-repeat benchmark. They are not promises about a new live run.

| Condition | Fixed goodput | Naive goodput | Corrected goodput |
|---|---:|---:|---:|
| Clean | 26.56 bit/s | 13.30 bit/s | 29.40 bit/s |
| Abrupt change/recovery | 13.25 bit/s | 8.17 bit/s | 13.36 bit/s |
| Gradual worsening | 8.20 bit/s | 9.41 bit/s | 8.17 bit/s |
| Burst loss | 13.87 bit/s | 8.36 bit/s | 14.32 bit/s |

Corrected timing achieved about **2.21× naive goodput on the clean link**. All clean information frames were verified. This supports the finding that raw symbol variation can unnecessarily slow the naive controller.

The counterexample matters: under gradual worsening, mean information failure was **17.6% fixed, 6.0% naive and 16.3% corrected**. The naive policy's wider gaps helped decoding. Do not say the corrected policy always wins.

For benign application pacing changes, mean false-positive rates were **76.7% raw** and **6.7% normalized**. Under gradual network drift they were **14.8% raw** and **18.5% normalized**. Normalization helps one kind of drift substantially, but does not solve every false-alarm problem.

All 63 accepted benchmark captures matched receiver packet counts with zero capture drops. This establishes capture completeness for those records; valid timestamp ordering is checked separately.

There are only three independent repetitions per condition. Plotted intervals describe uncertainty across those run summaries and should not be presented as broad proof of superiority.

## 10. Novelty and practical value

Timing channels, adaptive communication, KS-based comparison, entropy and temporal detection all have prior work. Our defensible contribution is a runnable, controlled study connecting three issues:

1. **Estimator contamination:** distinguish deliberately different pilot symbols from network variation and measure the resulting controller behavior.
2. **Transitions:** measure frames and recovery around changing impairment, instead of comparing only stationary clean/noisy cases.
3. **Benign drift:** test legitimate network and application changes so detector alarms are interpreted against realistic alternative explanations.

The value is the experimental comparison, packet evidence and interpretation of trade-offs. It is suitable for demonstrating networking knowledge and evaluation skills. A claim of publication-level originality would require broader literature comparison and further validation.

Relevant background includes Cabuk, Brodley and Shields on timing-channel design/detection; Gianvecchio and Wang on entropy-based detection; Zhang and colleagues on feedback-adaptive communication; Zillien and Wendzel on detector weaknesses; and Zander, Armitage and Branch's broader survey. The formal report contains the complete bibliography and technical standards/documentation references.

### A useful answer to “What is innovative?”

> We are not claiming a new way to encode a bit using delay. Our contribution is the controlled investigation of a feedback mistake: a controller can treat its own symbol variation as network noise. We compare raw and corrected estimators under changing conditions, then use benign drift controls to examine detector false alarms. The implementation produces packet-level evidence for the throughput, reliability and detection trade-offs.

## 11. Install, test, build and run

### Windows with WSL2

The tested distribution is **Ubuntu-24.04**. This project uses Linux networking tools, so ordinary Windows Python alone cannot run the namespace/netem experiments.

In Ubuntu, install the system dependencies:

```bash
sudo apt-get update
sudo apt-get install python3-venv tcpdump iproute2
```

In PowerShell:

```powershell
git clone https://github.com/KishenPC/WhisperNet.git
cd WhisperNet
.\whispernet.ps1 setup
.\whispernet.ps1 doctor
.\whispernet.ps1 test
.\whispernet.ps1 build
```

For an existing clone, open PowerShell in that checkout rather than cloning inside it. Setup creates the Linux Python environment at `~/.local/share/whispernet/venv`. The suite currently has **25 tests**, including real socket recovery and clock/service cleanup. Build creates a wheel and source distribution in `dist/`.

Run a fresh demonstration and open its results:

```powershell
$runFolder = "results/review-" + (Get-Date -Format "yyyyMMdd-HHmmss")
.\whispernet.ps1 demo --output $runFolder
if (Test-Path (Join-Path $runFolder "index.html")) {
    Start-Process (Join-Path $runFolder "index.html")
}
```

Allow roughly **2–3 minutes**, potentially longer on a busy host. Run only one timing experiment at a time. Use a new output-folder name on each attempt; existing experiment folders are protected from overwrite.

For a smaller clean-only comparison:

```powershell
.\whispernet.ps1 experiment --duration 4 --repeats 1 --scenarios clean
```

Four seconds is the target per evaluation trial, not the total command duration. Calibration and all four clean-mode trials add time.

For the complete repeated comparison:

```powershell
.\whispernet.ps1 experiment --duration 8 --repeats 3
```

This is a longer benchmark, not a classroom quick check. Prepare it before the review.

### Send A yourself in two WSL terminals

Open both terminals in the repository folder. In the first:

```bash
mkdir -p results
bash scripts/run.sh receive --bind 127.0.0.1 --output results/manual-receiver.json --ready results/manual-ready
```

In the second:

```bash
bash scripts/run.sh send --host 127.0.0.1 --mode fixed --message "A" --output results/manual-sender.json
```

The receiver result should contain `"text": "A"` and `"verified": true` for a successful frame. This uses loopback without netem. Use the automated demonstration for isolated endpoints and changing network conditions. Repeating these manual commands overwrites the same manual JSON files.

### What the dashboard is

`index.html` is a generated **results viewer**. It displays experiment charts and links to recorded measurements. It can be opened directly in a browser and does not require a web-server installation. It is not a continuously updating control dashboard; detection and report generation occur after the experiment.

## 12. What to demonstrate to the professor

1. **Explain A first.** Point to the 12/36 ms table and the 24 ms decision threshold.
2. **Show the architecture.** Explain the endpoint addresses, UDP data path, TCP control path and receiver capture.
3. **Start the demo.** Explain framing and adaptation while it runs. Point out the clean-link recovered message and verification status.
4. **Open the new results viewer.** Show the adaptation plot and a reliability/throughput outcome under impairment. Explain what actually happened in this run.
5. **Open a PCAP in Wireshark.** Filter with `udp.dstport == 39001`. Show the addresses, UDP payload size and changing time intervals. Under time-display settings, show the delta from the previous displayed packet when examining the filtered data stream.
6. **Connect packet evidence to decoding.** Use frame/index fields and `receiver.json` to explain one valid sequence or erasure, then show the frame's CRC status.
7. **Discuss repeated evidence.** On Kishen's existing machine, `results/benchmark-verified/index.html` contains the repeated comparison. Explain the clean-link gain and the gradual-loss counterexample.
8. **Finish with false alarms and limits.** Ordinary pacing changes can trigger a detector; normalized timing helps that case but not every drift condition.

Use the live run for functionality and the repeated benchmark for comparative averages. Describe saved captures as recorded runs. A failed impaired frame is a useful result when it is correctly explained.

### Two-person speaking plan

**Kishen, about two minutes:** problem, A example, why UDP, topology, frame structure and loss-aware decoding.

**Aarav, about two minutes:** naive versus corrected estimates, detector/calibration, benchmark results and novelty.

**Together, about two to three minutes:** run the demo, inspect a capture, explain a trade-off and answer questions. This is a speaking plan; both members should understand the complete system.

## 13. Likely questions and clear answers

| Question | Answer |
|---|---|
| Why send timing information? | To study a communication side channel and the networking effects that corrupt or reveal it. |
| Why not simply put A in the UDP payload? | That would demonstrate ordinary UDP messaging, not recovery from arrival timing. Our payload supplies alignment metadata. |
| Is this fully covert? | No. Frame/index metadata and the TCP control plane are visible laboratory simplifications. We measure timing detectability, not complete invisibility. |
| Is the message encrypted? | No. CRC checks integrity of complete frames; it does not provide encryption or authentication. |
| How does the receiver know timing settings? | The TCP frame-start message supplies them. Feedback influences the next frame. |
| Does the detector know the message? | Its timing features use PCAP timestamps only. The separate evaluator knows labels and expected bits for scoring. |
| Why does naive adaptation slow down? | Its raw variability includes the short/long encoding it created, so its own feedback can widen the separation. |
| Is corrected adaptation always better? | No. It improves clean-link goodput here, but naive adaptation had lower information failure under gradual worsening. |
| Does a high detector score prove an attack? | No. Ordinary timing changes can produce false positives. That is why benign drift controls are included. |
| Why not report only BER? | BER among surviving bits hides missing information. Erasures, frame success and verified goodput expose delivery failures. |
| Is a missing recovery measurement zero seconds? | No. It means the defined two-frame recovery criterion was not observed within that regime. |
| Does this use real networking? | Yes: separate processes, UDP/TCP sockets, Linux virtual interfaces and real receiver packet captures. The network is controlled and virtualized. |
| Would it work on the Internet? | That has not been validated. Internet paths, host scheduling, control-plane exposure and larger delays require further work. |
| What comes next? | Fairer fixed-policy tuning, more repetitions, randomized trial order, real benign traffic/native-Linux validation, then optional error correction or retransmission. |

### Operational issues to recognize

- A slow WSL cold start can delay even dependency checks. Wait for `doctor` to finish before beginning the demonstration.
- An unordered-timestamp error invalidates timing evidence. Do not sort timestamps to make a trace pass. Keep the failed run as a diagnostic and investigate host/guest clock behavior.
- The lab temporarily pauses an active WSL `systemd-timesyncd` service and restores it after normal completion or a Python exception. This leaves the Windows clock unchanged. Forced termination can bypass cleanup; check the guest service and project-owned namespaces before retrying.
- On a fresh teammate clone, historical result bundles do not exist. Generate new results, or obtain the recorded benchmark separately from Kishen.
- Setup may need internet access for dependencies. Prepare the machine before the review rather than installing during the presentation.

## 14. Files, deliverables and readiness

### Code map

| File | Responsibility |
|---|---|
| `src/whispernet/core.py` | Bits/bytes, timing settings, controller update, decoding and communication metrics. |
| `src/whispernet/endpoint.py` | UDP/TCP sockets, frame exchange, arrival timestamps and feedback. |
| `src/whispernet/network.py` | Namespace/link setup, impairment, clock checks and cleanup. |
| `src/whispernet/experiment.py` | Scenarios, trial orchestration, capture validation, calibration and recovery measurement. |
| `src/whispernet/detection.py` | PCAP timing extraction, windows, scores, thresholds and ROC. |
| `src/whispernet/report.py` | Aggregation, charts and the HTML results viewer; other exporters produce printable/editable reports. |
| `src/whispernet/cli.py` | Command-line entry points. |
| `whispernet.ps1` | Windows entry point that runs the Linux tools in Ubuntu-24.04. |
| `tests/` | Automated protocol, detector, socket and environment-cleanup checks. |

### What a result folder contains

At bundle level: `summary.json`, `environment.json`, `measurements.csv`, `index.html`, plots and generated reports. Each trial contains `sender.json`, `receiver.json`, `result.json`, `traffic.pcap` and process/capture logs. `results/latest.txt` records the most recently completed bundle path.

The formal course report is distinct from the machine-generated report inside each experiment folder.

### What is shared through GitHub

The repository contains the application, tests, launchers, architecture image, README and this guide. Final course documents, generated results, raw captures, temporary files and built packages are excluded from Git by the current project configuration.

On Kishen's project computer, the final course deliverables are:

- `output/docx/WhisperNet-Project-Report.docx` — formal 16-page Word report with 11 references.
- `output/pdf/WhisperNet-Project-Report.pdf` — matching printable report.
- `output/pptx/WhisperNet-Project-Review-Ready.pptx` — current 15-slide presentation; use this copy for review.

Share those three files separately with the teammate. A clone supplies the runnable code and guide, but not those local documents or the historical benchmark. Declaration signatures still need to be added by the candidates.

### What readiness means

Readiness is supported by passing automated tests, successful package builds, an actual end-to-end rehearsal, capture checks and reviewed course artifacts. The latest local check is recorded in `output/review-readiness-20261019.json`; this file is not distributed with a fresh clone. A new machine should still complete its own setup and clean-link check.

The report follows the supplied updated structure, and the general rubric separates **25 implementation/demo marks** from **5 report marks**. Understanding, application, analysis and evaluation are assessed individually. The report provides evidence; both students must explain it.

Before walking into the review, each person should be able to explain the A example, one frame, the estimator correction, one capture, one measured benefit, one counterexample and one limitation without reading the slides.
