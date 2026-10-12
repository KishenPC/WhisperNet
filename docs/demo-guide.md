# Using WhisperNet at the project review

This guide walks through a short live demonstration of the WhisperNet networking lab.

## Before the review

Open PowerShell inside this project folder. Run:

```powershell
.\whispernet.ps1 doctor
.\whispernet.ps1 test
```

`doctor` checks the installed Linux tools and Python dependencies. The test command should report 20 passing tests, including actual UDP socket communication. On this computer setup is already complete. After moving to another computer with Ubuntu-24.04, run `setup` first and follow the README's dependency instructions.

For a short clean-link experiment:

```powershell
.\whispernet.ps1 experiment --duration 4 --repeats 1 --scenarios clean
```

The terminal prints packet counts, information failure, verified goodput and any recovered first message. This is a small functionality check; use the saved three-repeat benchmark to discuss comparative results.

## Demonstration sequence

1. Explain the letter-A example: `01000001`, represented by 12/36 ms gaps, with a 24 ms threshold. Show the address plan and explain the separate TCP lab feedback connection.
2. Run `.\whispernet.ps1 demo`. Allow roughly 2-3 minutes; a slow adaptive frame can make a run exceed its nominal duration. Point out the verified message from the clean-link trial.
3. Explain the abrupt scenario: at about 2 seconds the link changes from 4 ms delay/0.5 ms jitter/no configured loss to 40 ms delay/8 ms jitter/2% configured loss. At about 5 seconds it returns to the clean settings. Actual change times and observed loss are recorded separately.
4. Show the newly generated `index.html` and its adaptation graph. Explain fixed, naive and corrected policies, then point out a failed frame and recovery. Gaps update on the next frame rather than immediately during a frame.
5. Show false alarms on benign traffic. Explain that the detector operates offline on captured arrival times and that an alarm does not identify hidden intent.
6. Open `results/benchmark-verified/index.html` for repeated results. Clean-link mean goodput was 26.56, 13.30 and 29.40 bit/s for fixed, naive and corrected. Under gradual worsening, naive had fewer information failures. Show both findings.

If there is less time, start the live demo while explaining the architecture, then use the saved benchmark for the graphs. Saved captures are recorded experimental evidence; identify them as previous runs rather than presenting them as newly generated.

## Showing packet evidence

Open a successful trial's `traffic.pcap` in Wireshark. Filter with:

```text
udp.dstport == 39001
```

Show source `10.77.0.1`, destination `10.77.0.2`, the 12-byte UDP payload, and the varying arrival intervals. The payload contains a magic value, frame number and symbol index. The information is carried in packet spacing. Inspect `receiver.json` to connect a frame's arrival gaps with its decoded bits, erasures and checksum result. The capture filter excludes the TCP lab control connection.

## Send your own short message

For a simple letter demonstration, open two Ubuntu/WSL terminals. In both, change to the folder containing the project:

```bash
cd "/path/to/CN Project"
```

In the first terminal start the receiver:

```bash
bash scripts/run.sh receive --bind 127.0.0.1 --output results/manual-receiver.json --ready results/manual-ready
```

In the second terminal send a message:

```bash
bash scripts/run.sh send --host 127.0.0.1 --mode fixed --message "A" --output results/manual-sender.json
```

After the receiver finishes, open `results/manual-receiver.json`. For a successful frame it contains `"text": "A"` and `"verified": true`. This example uses loopback without added network impairment. Use the automated namespace demo to demonstrate network changes and compare controllers. Manual JSON files are overwritten when the same commands are repeated.

## Questions to answer clearly

Constant delay shifts all packets together; jitter changes their relative spacing. A lost packet can combine two gaps, so the receiver marks affected symbols unknown. CRC detects an incorrect complete frame; it does not repair it or authenticate the sender. Useful throughput includes pilots, feedback and settling time. The implementation has no error-correcting code or loss-driven redundancy policy. WSL and synthetic benign traffic limit how far these results generalize.

Everyone presenting the project should understand the complete system and accurately describe their own contributions.
