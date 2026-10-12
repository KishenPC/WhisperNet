"""Plots, CSV measurements and a rubric-aligned report from real experiment outputs."""

import csv
import html
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def mean_ci(values):
    values = [v for v in values if v is not None]
    if not values:
        return None, None
    avg = statistics.mean(values)
    # Run-level bootstrap; intervals with fewer than 3 repeats are intentionally omitted.
    if len(values) < 3:
        return avg, None
    rng = np.random.default_rng(731)
    resampled = rng.choice(values, (2000, len(values)), replace=True).mean(axis=1)
    return avg, np.quantile(resampled, [.025, .975]).tolist()


def generate(folder):
    folder = Path(folder).resolve()
    bundle = json.loads((folder / "summary.json").read_text())
    runs, detection = bundle["runs"], bundle["detection"]
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    modes = ("fixed", "naive", "corrected")
    scenarios = list(dict.fromkeys(r["scenario"] for r in runs))
    colors = {"fixed": "#111111", "naive": "#777777", "corrected": "#444444"}
    hatches = {"fixed": "", "naive": "///", "corrected": "xx"}
    lines = {"fixed": "-", "naive": "--", "corrected": ":"}
    markers = {"fixed": "o", "naive": "s", "corrected": "^"}
    aggregates = []
    for scenario in scenarios:
        for mode in modes:
            group = [r for r in runs if r["scenario"] == scenario and r["mode"] == mode]
            if not group:
                continue
            record = {"scenario": scenario, "mode": mode, "runs": len(group)}
            for field in ("information_failure_rate", "conditional_ber", "erasure_rate", "verified_goodput_bps", "frame_success_rate"):
                avg, ci = mean_ci([r[field] for r in group])
                record[field] = {"mean": avg, "ci95": ci}
            aggregates.append(record)
    write = lambda name, value: (folder / name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    write("aggregates.json", aggregates)
    fields = ["id", "mode", "scenario", "seed", "conditional_ber", "substitution_rate", "erasure_rate",
              "information_failure_rate", "verified_goodput_bps", "frame_success_rate", "observed_packet_loss", "elapsed_seconds"]
    with (folder / "measurements.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(runs)
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for axis, field, label in ((axes[0], "information_failure_rate", "Information failure (substitution + erasure)"),
                               (axes[1], "verified_goodput_bps", "Verified information goodput (bit/s)")):
        x = np.arange(len(scenarios))
        for index, mode in enumerate(modes):
            group = [next((r for r in aggregates if r["scenario"] == s and r["mode"] == mode), None) for s in scenarios]
            values = [r[field]["mean"] if r and r[field]["mean"] is not None else np.nan for r in group]
            axis.bar(x + (index - 1) * .24, values, width=.23, label=mode, color=colors[mode], hatch=hatches[mode], edgecolor="black")
            for pos, value, record in zip(x + (index - 1) * .24, values, group):
                interval = record[field]["ci95"] if record else None
                if interval is not None:
                    axis.errorbar(pos, value, yerr=[[max(0, value - interval[0])], [max(0, interval[1] - value)]],
                                  color="black", capsize=3, linewidth=1)
        axis.set_xticks(x, scenarios)
        axis.set_ylabel(label)
        axis.legend()
        axis.grid(axis="y", alpha=.15)
    figure.suptitle("WhisperNet: actual network trials; error bars are run-level bootstrap intervals")
    figure.tight_layout()
    figure.savefig(folder / "performance.png", dpi=160)
    plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for axis, name in zip(axes, detection["thresholds"]):
        for mode in modes:
            curve = detection["roc"].get(f"{name}/{mode}")
            if curve and curve["auc"] is not None:
                axis.plot(curve["fpr"], curve["tpr"], color=colors[mode], linestyle=lines[mode], label=f"{mode}: AUC {curve['auc']:.2f}")
        axis.plot([0, 1], [0, 1], "--", color="#b0b0b0")
        axis.set(xlabel="False-positive rate", ylabel="True-positive rate", title=name.replace("_", " "), xlim=(0, 1), ylim=(0, 1))
        axis.legend()
    figure.suptitle("Detection from PCAP timestamps; ROC is descriptive, windows are dependent")
    figure.tight_layout()
    figure.savefig(folder / "roc.png", dpi=160)
    plt.close(figure)

    selected = [next((r for r in runs if r["mode"] == mode and r["scenario"] == "abrupt"), None) for mode in modes]
    figure, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for record in selected:
        if not record:
            continue
        origin = record["start_epoch"]
        frames = record["frame_results"]
        x = [f["end_epoch"] - origin for f in frames]
        style = {"color": colors[record["mode"]], "linestyle": lines[record["mode"]], "marker": markers[record["mode"]]}
        axes[0].plot(x, [(f["long"] - f["short"]) * 1000 for f in frames], label=record["mode"], **style)
        axes[1].plot(x, [f["residual_sigma"] * 1000 for f in frames], **style)
        axes[2].plot(x, [int(f["verified"]) for f in frames], **style)
        for change in record["transitions"][1:]:
            for axis in axes:
                axis.axvline(change["offset"], color=colors[record["mode"]], linestyle=":", alpha=.35)
    axes[0].set_ylabel("Symbol separation (ms)")
    if axes[0].lines:
        axes[0].legend()
    axes[1].set_ylabel("Pilot residual std (ms)")
    axes[2].set(ylabel="Frame checksum valid", xlabel="Seconds from trial start", yticks=[0, 1])
    figure.suptitle("Adaptation and recovery: first abrupt trial of each controller")
    figure.tight_layout()
    figure.savefig(folder / "adaptation.png", dpi=160)
    plt.close(figure)

    rates = []
    for scenario in scenarios:
        group = [r for r in runs if r["mode"] == "benign" and r["scenario"] == scenario]
        for name in detection["thresholds"]:
            avg, interval = mean_ci([r["alarm_metrics"][name]["positive_window_rate"] for r in group])
            rates.append({"scenario": scenario, "detector": name, "fpr": avg, "ci95": interval})
    write("false_alarms.json", rates)
    findings = []
    clean = {r["mode"]: r for r in aggregates if r["scenario"] == "clean"}
    if all(mode in clean for mode in modes):
        findings.append("On the clean link, mean verified goodput was " + ", ".join(
            f"{clean[mode]['verified_goodput_bps']['mean']:.2f} bit/s for {mode}" for mode in modes) +
            ". This quantifies the throughput cost of using raw symbol variability as the noise estimate.")
    pacing = {r["detector"]: r["fpr"] for r in rates if r["scenario"] == "pacing" and r["fpr"] is not None}
    if all(name in pacing for name in detection["thresholds"]):
        findings.append(f"During legitimate application pacing changes, mean benign positive-window rates were "
                        f"{pacing['ks_entropy']:.1%} for KS/entropy and {pacing['normalized_temporal']:.1%} for the normalized temporal score.")
    findings_text = " ".join(findings)
    figure, axis = plt.subplots(figsize=(9, 4))
    for index, name in enumerate(detection["thresholds"]):
        values = [next(r["fpr"] for r in rates if r["scenario"] == s and r["detector"] == name) for s in scenarios]
        axis.bar(np.arange(len(scenarios)) + (index - .5) * .30, [v if v is not None else np.nan for v in values], width=.29,
                 label=name.replace("_", " "), color=("white", "#777777")[index], edgecolor="black", hatch=("///", "")[index])
    axis.axhline(detection["target_calibration_fpr"], color="black", linestyle="--", label="Calibration target (not guaranteed test FPR)")
    axis.set(xticks=np.arange(len(scenarios)), xticklabels=scenarios, ylabel="Observed benign positive-window rate", ylim=(0, 1))
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(folder / "false-alarms.png", dpi=160)
    plt.close(figure)

    table = "| Scenario | Controller | Runs | Information failure | Verified goodput | Frame success |\n|---|---|---:|---:|---:|---:|\n"
    for record in aggregates:
        table += (f"| {record['scenario']} | {record['mode']} | {record['runs']} | "
                  f"{record['information_failure_rate']['mean']:.1%} | {record['verified_goodput_bps']['mean']:.2f} bit/s | "
                  f"{record['frame_success_rate']['mean']:.1%} |\n")
    fpr_table = "| Scenario | Detector | Observed FPR |\n|---|---|---:|\n"
    for record in rates:
        fpr_table += f"| {record['scenario']} | {record['detector']} | {record['fpr']:.1%} |\n" if record['fpr'] is not None else ""
    recovery_table = "| Trial | Transition (s) | Recovery (s) |\n|---|---:|---:|\n"
    for record in runs:
        if record["mode"] == "benign":
            continue
        for change in record["recovery"]:
            value = f"{change['recovery_seconds']:.2f}" if change["recovery_seconds"] is not None else "Not observed before regime ended"
            recovery_table += f"| {record['id']} | {change['transition_offset']:.2f} | {value} |\n"
    recovered_messages = "\n".join(f"- {r['id']}: {r['recovered_first_message']!r}" for r in runs if r.get("recovered_first_message") is not None)
    alarm_table = "| Scenario | Controller | Detector | Positive-window rate (TPR) | First alarm (s), observed trials only |\n|---|---|---|---:|---:|\n"
    for scenario in scenarios:
        for mode in modes:
            group = [r for r in runs if r["scenario"] == scenario and r["mode"] == mode]
            for name in detection["thresholds"]:
                avg, _ = mean_ci([r["alarm_metrics"][name]["positive_window_rate"] for r in group])
                delay, _ = mean_ci([r["alarm_metrics"][name]["first_alarm_seconds"] for r in group])
                if avg is not None:
                    observed = f"{delay:.2f}" if delay is not None else "No alarm observed"
                    alarm_table += f"| {scenario} | {mode} | {name} | {avg:.1%} | {observed} |\n"
    body = f"""# WhisperNet project report (draft)

Team members: Kishen Pathiyan Cherumanal and Aarav Gupta  
Team number: 2  
Register numbers: to be supplied by the students  
Course: BCSE308P - Computer Networks Lab  
Faculty: Dr. S. Ebenezer Juliet  
Review date: 21 October 2026  
Date of submission: to be entered by the students  
Run bundle: `{folder.name}` (timestamps and versions are recorded in environment.json)

## Title
WhisperNet: An Adaptive Network Timing Channel with Statistical Detection under Jitter and Packet Loss

## Problem Statement
Packet arrival timing can carry information, but network variation corrupts timing symbols. Increasing symbol separation can improve decoding while reducing throughput and changing statistical detectability. This laboratory measures those effects rather than assuming improvement.

## Objectives
Implement actual UDP timing communication; compare fixed, naive and corrected adaptation; evaluate benign drift false alarms; measure errors, verified goodput, frame recovery and detection from packet captures.

## Network Concepts
UDP sockets, IPv4 addressing, virtual Ethernet, network namespaces, traffic control, delay versus jitter, packet loss/reordering, framing, preambles, CRC integrity checks and an explicit TCP feedback channel. UDP supplies no automatic delivery or ordering guarantee; this implementation records erasures instead of silently interpreting merged intervals.

## Architecture
Sender (10.77.0.1) -> UDP/39001 -> virtual link with netem -> Receiver (10.77.0.2). An offline detector reads only timestamps of UDP packets in the receiver-side PCAP. TCP/39002 carries lab framing metadata and pilot-based feedback separately. It is an unimpeded control plane, a disclosed laboratory simplification, not a stealth protocol. Control, pilots and settling time are counted in end-to-end goodput.

## Requirements
Python 3.10+, NumPy, SciPy, Matplotlib, Linux iproute2, tcpdump and namespace privileges. Windows uses Ubuntu-24.04 in WSL2 through the supplied launcher. The captured environment was `{bundle['environment']['kernel']}`.

## Implementation
Each frame has a constant-size UDP anchor, eight known timing pilot symbols and up to four message bytes encoded into subsequent gaps. A frame/index field supports alignment without carrying message bytes. The fixed controller uses 12/36 ms. Adaptive controllers select separation from four times an observed pilot standard deviation, bounded to 16-160 ms. Naive adaptation uses raw pilot gaps; corrected adaptation subtracts known symbol gaps before measuring variation. Updates take effect on the next frame. The receiver verifies complete frames using CRC32; the offline evaluator also checks original bits.

## Packet Flow
TCP frame metadata -> ready acknowledgement -> UDP anchor -> timed pilot packets -> timed information packets -> bounded drain -> TCP frame-end -> pilot statistics/status feedback -> next frame. Filter: `udp.dstport == 39001`. Open any trial's traffic.pcap in Wireshark and inspect source/destination, constant payload size and inter-arrival times. The packet payload is 12 bytes; it contains magic/frame/index only. CRC and parameters are disclosed on the separate lab control connection.

## Experimental Setup
Actual sender and receiver processes run in separate project-owned Linux namespaces. Each evaluation trial has its own capture. Calibration uses distinct benign clean-link runs (seeds 1001-1003); evaluation uses seeds beginning at 2001. Duration target: {bundle['environment']['duration_target']} seconds; repeats: {bundle['environment']['repeats']}. Scenarios: {', '.join(scenarios)}. Timed changes use a normal-delay model; burst loss uses a Gilbert-Elliott model with approximately 1.92% long-run loss. In the pacing scenario only benign traffic changes its application gap multiplier to 0.55 at sender age 2 seconds and 1.5 at age 5 seconds, on a clean link; the timing channels retain their encoding rules. Netem seed support is recorded per trial; matching seeds do not imply identical noise per symbol across different sending schedules.

## Test Cases
The automated tests cover round-trip bytes, CRC verification, lost/merged intervals, reordered arrivals, estimator contamination, bounded adaptation, metric accounting and PCAP parsing. Separately, these results come from live namespace trials. Application logs, environment metadata and sender/receiver recordings are retained per trial. No simulated trial is presented as a real network measurement.

## Performance Analysis
Information failure includes substitutions and erasures over all transmitted information bits. Conditional BER is explicitly limited to non-erased bits. Verified goodput counts complete correct frames, including all transmission overhead in elapsed time. Run-level bootstrap intervals are produced only with at least three repetitions; windows within a run are dependent. See performance.png, adaptation.png, roc.png and false-alarms.png.

{table}

Detection at the frozen benign-calibrated thresholds (alarm delay averages exclude censored trials, whose status is retained in the JSON):

{alarm_table}

## Comparison
Fixed, naive and corrected controllers share the same topology, message and impairment schedules. Benign controls share the experiment scaffold but use variable application pacing independent of the message. Raw KS plus histogram entropy is compared with a median-normalized KS plus lag-one correlation score. Neither detector reads message bits, controller logs or impairment settings. Detector references and thresholds are frozen before evaluation. Complete run 1001 supplies the reference, and complete runs 1002-1003 supply threshold calibration; evaluation runs beginning at 2001 are held out. Offline detector preparation is separate from transmitted-frame goodput.

The fixed 12/36 ms baseline is a declared reference configuration, not a separately tuned optimum. These results therefore support comparison with that configuration and the naive controller, not a claim that adaptation beats all possible fixed settings.

## Critical Evaluation
This is an active synthetic UDP laboratory channel, not an undetectable production channel or an Internet benchmark. The separate reliable control plane, known pilot pattern, fixed four-byte framing and drain period can create artifacts. CRC32 checks integrity, not authenticity. CPU scheduling, WSL virtualization and network reordering affect results. Trials use a fixed execution order, so host-load drift is a possible confound. Clean calibration need not meet its target false-alarm rate after network drift. Three repetitions provide limited uncertainty evidence. An alarm detects timing distinguishability from this reference, not covert intent. The detector scores combine established components with declared heuristic weights; they are not exact reproductions of the cited papers' detectors. The controller uses pilot variability, holds when samples are scarce and reports packet loss; it does not implement loss-driven redundancy or detector-aware control.

{fpr_table}

## Optimization
The estimator change is the implemented optimization: raw gap variability includes the intended binary timing variation, while pilot residual variability accounts for that variation. The corrected-versus-naive result above is the empirical comparison; an improvement is claimed only where the measured values support it. The controller has a separation cap and holds its parameters when too few valid pilots remain. Neither adaptation nor median normalization is claimed to dominate every condition.

## Demo Evidence
Each trial folder contains traffic.pcap, sender.json, receiver.json, result.json, sender.log, receiver.log and capture.log. The main summary contains actual transition times, per-frame checksum validity, detector alarms and bits delivered before the first alarm. A live demonstration can be reproduced with the demo command; screenshots or a recording of the students' presentation must be attached separately rather than fabricated.

First complete messages reconstructed from checksum-valid frames:

{recovered_messages or 'No complete first-cycle message was verified in this bundle.'}

## Results
The tables above are generated from this run's measured JSON records. Recovery is reported in summary.json as the first pair of consecutive valid complete frames wholly inside a new regime. If recovery or an alarm was not observed, the value is null with an explicit status. No failed run or erased payload is counted as successful information delivery.

{recovery_table}

## Conclusion
{findings_text}

The impairment comparisons show the measured reliability/throughput trade-offs in this bundle; neither controller nor detector is assumed to dominate all conditions. These are outcomes of a synthetic WSL laboratory with limited independent repeats. The current contribution is a reproducible experimental implementation and analysis; publication-level novelty is not established.

## Future Enhancement
Test on native Linux and representative real application traces; broaden independent runs; tune a fixed baseline on separate development runs; evaluate alternative control policies, authenticated feedback and error correction; compare against published channel and detector implementations. These enhancements are not claimed as completed.

## References
- Cabuk, Brodley and Shields (2004). IP Covert Timing Channels: Design and Detection. https://doi.org/10.1145/1030083.1030108
- Gianvecchio and Wang (2007). Detecting Covert Timing Channels: An Entropy-Based Approach. https://www.eecis.udel.edu/~hnw/paper/ccs07.pdf
- Gianvecchio et al. (2008). Model-Based Covert Timing Channels: Automated Modeling and Evasion. https://www.eecis.udel.edu/~hnw/paper/raid08.pdf
- Zhang et al. (2019). A Two-Way VoLTE Covert Channel With Feedback Adaptive to Mobile Network Environment. https://doi.org/10.1109/ACCESS.2019.2937969
- Zillien and Wendzel (2023). Weaknesses of Popular and Recent Covert Channel Detection Methods and a Remedy. https://doi.org/10.1109/TDSC.2023.3241451
- User-supplied project report template and Innovative Practices rubric (BCSE308P, Fall 2026-2027).

AI assistance: Codex assisted implementation, testing and this report. Kishen and Aarav should inspect the code, understand the results and apply their course's disclosure requirements.
"""
    (folder / "report.md").write_text(body, encoding="utf-8")
    cards = "".join(f'<figure><img src="{name}.png" alt="{name} measurements"><figcaption>{name}</figcaption></figure>'
                    for name in ("performance", "adaptation", "roc", "false-alarms"))
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WhisperNet experiment results</title><style>body{{max-width:1100px;margin:40px auto;padding:0 20px;background:white;color:black;font:16px/1.6 Georgia,serif}}h1{{font-size:30px}}img{{width:100%;height:auto}}figure{{margin:32px 0}}pre{{white-space:pre-wrap;font:15px/1.6 Georgia,serif;border-top:1px solid black;padding-top:24px}}a{{color:black}}</style>
<h1>WhisperNet</h1><p>Kishen Pathiyan Cherumanal &amp; Aarav Gupta · BCSE308P · Actual network experiment: {html.escape(folder.name)}</p>
<p><a href="measurements.csv">Measurements CSV</a> · <a href="summary.json">Complete run evidence</a> · <a href="report.pdf">Printable draft</a> · <a href="report.tex">LaTeX source</a> · <a href="report.md">Editable text</a></p>{cards}<h2>Draft report text</h2><pre>{html.escape(body)}</pre></html>'''
    (folder / "index.html").write_text(page, encoding="utf-8")
    from .pdf_report import export
    export(folder)
    from .latex_report import export as export_latex
    export_latex(folder)
    print(f"Report and plots saved to {folder}", flush=True)

