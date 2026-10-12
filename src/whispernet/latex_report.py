"""Standalone, monochrome LaTeX with figure data embedded for Overleaf."""

import json
import math
from pathlib import Path
import re


def escape(text):
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
                    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
                    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(char, char) for char in text)


def inline(text):
    parts = re.split(r"(`[^`]+`|https?://\S+)", text)
    return "".join(r"\texttt{" + escape(p[1:-1]) + "}" if p.startswith("`") else
                   r"\url{" + p + "}" if p.startswith(("https://", "http://")) else escape(p) for p in parts)


def export(folder, destination=None):
    folder = Path(folder)
    destination = Path(destination) if destination else folder / "report.tex"
    destination.parent.mkdir(parents=True, exist_ok=True)
    markdown = (folder / "report.md").read_text(encoding="utf-8").splitlines()
    # The title page supplies metadata. The remaining course sections retain their text.
    start = markdown.index("## Problem Statement")
    output = [r"""% Standalone source: upload this file to Overleaf and select pdfLaTeX.
% All chart coordinates and references are included; no external assets are required.
\documentclass[11pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage[margin=25mm]{geometry}
\usepackage{booktabs,longtable,array}
\usepackage[hidelinks]{hyperref}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\setlength{\emergencystretch}{3em}
\title{WhisperNet\\[5pt]\large An Adaptive Network Timing Channel with Statistical Detection under Jitter and Packet Loss}
\author{Kishen Pathiyan Cherumanal\\Aarav Gupta}
\date{BCSE308P: Computer Networks Lab\\Faculty: Dr. S. Ebenezer Juliet\\Project review: 21 October 2026}
\begin{document}
\maketitle
\noindent Team: 2\qquad Register numbers: \underline{\hspace{60mm}}

\noindent Date of submission: \underline{\hspace{45mm}}

\noindent\textit{Working draft. Student details and presentation evidence remain to be completed.}
""", "\nMeasured run bundle: " + r"\texttt{" + escape(folder.name) + "}.\n"]
    index = start
    while index < len(markdown):
        line = markdown[index].strip()
        if line.startswith("|"):
            rows = []
            while index < len(markdown) and markdown[index].strip().startswith("|"):
                cells = [c.strip() for c in markdown[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                index += 1
            count = len(rows[0])
            if any(len(row) != count for row in rows):
                raise ValueError("Inconsistent report table columns")
            columns = r">{\raggedright\arraybackslash}p{\dimexpr\linewidth/" + str(count) + r"-2\tabcolsep\relax}"
            header = " & ".join(r"\textbf{" + inline(c) + "}" for c in rows[0]) + r" \\"
            output.extend([r"{\small", r"\begin{longtable}{" + columns * count + "}",
                           r"\toprule", header, r"\midrule\endfirsthead", r"\toprule", header,
                           r"\midrule\endhead", r"\bottomrule\endfoot"])
            output.extend(" & ".join(inline(c) for c in row) + r" \\" for row in rows[1:])
            output.extend([r"\end{longtable}", "}"])
            continue
        if line.startswith("## "):
            output.append(r"\section{" + escape(line[3:]) + "}")
        elif line.startswith("- "):
            output.append(r"\begin{itemize}")
            while index < len(markdown) and markdown[index].strip().startswith("- "):
                output.append(r"\item " + inline(markdown[index].strip()[2:]))
                index += 1
            output.append(r"\end{itemize}")
            continue
        else:
            output.append(inline(line) if line else "")
        index += 1

    aggregates = json.loads((folder / "aggregates.json").read_text())
    rates = json.loads((folder / "false_alarms.json").read_text())
    scenarios = list(dict.fromkeys(row["scenario"] for row in rates))
    def bars(title, ylabel, groups, values, caption, maximum=None):
        observed = [v for g in groups for s in scenarios if (v := values(g, s)) is not None]
        maximum = maximum or max(10, math.ceil(max(observed, default=0) / 10) * 10)
        output.extend([r"\begin{figure}[p]\centering", r"\setlength{\unitlength}{.4mm}",
                       r"\begin{picture}(380,200)(-25,-40)",
                       r"\put(0,140){\makebox(340,10){" + escape(title + " (" + ylabel + ")") + "}}",
                       r"\put(0,0){\line(1,0){340}}", r"\put(0,0){\line(0,1){130}}"])
        for tick in range(6):
            y = tick * 26
            output.append(r"\put(-3," + str(y) + r"){\line(1,0){3}}")
            output.append(r"\put(-24," + str(y - 3) + r"){\makebox(19,6)[r]{\scriptsize " + f"{maximum * tick / 5:g}" + "}}")
        step = 330 / max(1, len(scenarios))
        for index, scenario in enumerate(scenarios):
            center = (index + .5) * step
            output.append(r"\put(" + f"{center - 25:.2f},-14" + r"){\makebox(50,6){\scriptsize " + escape(scenario) + "}}")
            for group_index, group in enumerate(groups):
                value = values(group, scenario)
                if value is None:
                    continue
                x, height = center + (group_index - (len(groups) - 1) / 2) * 16 - 6, value / maximum * 130
                output.append(r"\put(" + f"{x:.2f},0" + r"){\framebox(12," + f"{height:.2f}" + "){}}")
                if group_index == 1:
                    output.append(r"\put(" + f"{x:.2f},0" + r"){\rule{4.8mm}{" + f"{height * .4:.3f}mm" + "}}")
                elif group_index == 2:
                    for stripe in range(3, int(height), 6):
                        output.append(r"\put(" + f"{x:.2f},{stripe}" + r"){\line(1,0){12}}")
        for index, group in enumerate(groups):
            style = ("outline", "solid", "striped")[index]
            x = index * (350 / len(groups))
            output.append(r"\put(" + f"{x:.2f},-32" + r"){\makebox(110,8){\scriptsize " + escape(group.replace("_", " ") + " (" + style + ")") + "}}")
        output.extend([r"\end{picture}", r"\caption{" + caption + "}", r"\end{figure}"])

    output.extend([r"\clearpage", r"\appendix", r"\section{Figures from the recorded benchmark}"])
    def goodput(mode, scenario):
        row = next((r for r in aggregates if r["mode"] == mode and r["scenario"] == scenario), None)
        return row["verified_goodput_bps"]["mean"] if row else None
    bars("Verified information goodput", "bit/s", ("fixed", "naive", "corrected"), goodput,
         "Mean verified goodput from the recorded runs. Means are shown here; run-level uncertainty intervals are retained in aggregates.json.")
    def false_alarm(detector, scenario):
        return next((r["fpr"] for r in rates if r["detector"] == detector and r["scenario"] == scenario), None)
    bars("Benign false alarms", "Positive-window rate", ("ks_entropy", "normalized_temporal"), false_alarm,
         "Observed false alarms under network and application drift. A clean-link calibration target does not guarantee the same test false-alarm rate.", 1)
    output.append(r"\end{document}")
    destination.write_text("\n".join(output) + "\n", encoding="utf-8")
    return destination
