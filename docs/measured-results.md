# Results to explain at the project review

These numbers come from `results/benchmark-verified`, generated on 12 October 2026 in Ubuntu-24.04 on WSL2. There are 60 evaluation trials: four traffic modes, five scenarios, three repetitions. Three separate clean benign runs provide detector reference/threshold calibration. All 63 captures match the receiver's packet counts, with zero capture drops. The earlier development bundles marked `INVALID_CAPTURE.txt` are excluded.

## Communication findings

| Condition | Fixed goodput | Naive goodput | Corrected goodput |
|---|---:|---:|---:|
| Clean | 26.56 bit/s | 13.30 bit/s | 29.40 bit/s |
| Abrupt change/recovery | 13.25 bit/s | 8.17 bit/s | 13.36 bit/s |
| Gradually worsening | 8.20 bit/s | 9.41 bit/s | 8.17 bit/s |
| Burst-loss period | 13.87 bit/s | 8.36 bit/s | 14.32 bit/s |

On the clean link every information frame was verified for all three controllers. The corrected controller is about 2.2 times as fast as the naive controller in these runs. This supports the estimator-contamination argument: raw pilot variability includes the deliberate short/long symbol difference, so the naive controller unnecessarily widens that difference.

This is not a universal reliability improvement. Under gradual worsening, mean information failure was 17.6% for fixed, 6.0% for naive and 16.3% for corrected. The naive controller's larger separation helps decoding in that condition. Under burst loss, corrected mean information failure was 12.2%, versus 11.9% for fixed and 6.8% for naive. The plots include intervals across the three run summaries; this is limited evidence, not a strong general statistical claim.

In a short impairment regime, two consecutive wholly contained verified frames may not occur. Recovery is then recorded as not observed, rather than zero or a guessed recovery time. Slower controllers can fail this observation criterion even when they later recover a valid frame.

## Detector findings

For legitimate application pacing changes on a clean link, the raw KS/entropy detector flagged a mean 76.7% of benign windows. The normalized temporal detector flagged 6.7%. Under abrupt network changes, those rates were 18.5% and 11.1%. Under gradual network drift they were 14.8% and 18.5%, so normalization does not solve every false-alarm problem.

Calibration used complete run 1001 as the reference and complete runs 1002-1003 for thresholds. Evaluation runs beginning at 2001 were held out. The target was 5% during calibration; observed test FPR is a measured outcome. These scores use declared heuristic combinations of established statistics. They are not exact reproductions of published detectors.

## A simple review explanation

"Our strongest result is that the controller can confuse its own timing symbols with network noise. Correcting that estimate prevents a large clean-link slowdown. But wider timing gaps sometimes produce fewer errors, so the corrected controller does not always win under noise. We also show that ordinary traffic-rate changes can trigger a detector, and that normalizing the time scale greatly reduces that particular false-alarm problem in our laboratory."

## Limits of these conclusions

The fixed reference uses 12/36 ms and was not tuned to an optimum. Benign traffic is synthetic, packet windows within a run are dependent, trials have a fixed execution order, netem seeds are unavailable in this installed iproute2 version, and WSL scheduling contributes timing variation. The separate reliable TCP control channel exposes frame settings and CRC. Conclusions apply to this controlled laboratory and these configurations.

Use the full JSON/CSV and generated report for precise measurements. Use the shorter `demo-final` bundle for presentation; do not combine its individual-run numbers with the repeated benchmark averages.
