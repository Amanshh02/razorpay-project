"""The one place the dashboard is allowed to run the pipeline.

Stage 9 made the dashboard a pure reader: it imported nothing from
``src.matching``, ``src.detectors`` or ``src.agent``, and a test proved
it by parsing the AST. Stage 10 adds an opt-in "Run reconciliation"
button, which necessarily breaks that.

**The boundary moved; it did not disappear.** It is now:

- ``data.py`` — still imports no engine code at all. The read-only path
  that renders an existing CSV is exactly as isolated as it was.
- ``app.py`` — imports no engine code **at module level**. Rendering the
  dashboard executes no pipeline code.
- ``runner.py`` — this file, the single documented exception, imported
  *lazily* from inside the button handler.

So a reader who loads the dashboard and never presses the button gets
the stage 9 guarantee unchanged: nothing here can recompute a number
they are looking at. Pressing the button is an explicit act.

The pipeline sequence is not restated here. ``src.main.run`` defines it
once and reports each completed step through a callback; this module
only translates those reports into text.
"""

from __future__ import annotations

from src.dashboard.data import format_indian
from src.main import run as _run


def format_step(event):
    """Turn one pipeline event into a line of human-readable narration.

    Every line describes work that has **already finished**, with counts
    taken from the result. Nothing here is a guess about what is about
    to happen.
    """
    phase = event["phase"]

    if phase == "load":
        return f"Read {event['ledger']} — {event['rows']:,} rows"

    if phase == "match":
        return (
            f"Matched {event['orders']:,} orders through the ID chain — "
            f"{event['reconciled']:,} reconciled, "
            f"{event['unreconciled']:,} could not be matched"
        )

    if phase == "detect":
        # Uniform phrasing: several type names are multi-word, and naive
        # pluralisation produced "refund not reflecteds".
        name = event["anomaly_type"].replace("_", " ")
        found = event["found"]
        return f"Ran the {name} detector — {found} found"

    if phase == "classify":
        return (
            f"Agent reviewed {event['routed']} uncertain findings — "
            f"{event['overridden']} relabelled"
        )

    if phase == "report":
        return (
            f"Computed exposure — {event['flagged']} flags, "
            f"{format_indian(event['exposure_paise'])} at risk"
        )

    return phase


def run_with_progress(data_dir, out_dir, *, on_step=None, use_agent=False):
    """Run the real pipeline, reporting each completed step.

    Returns whatever ``src.main.run`` returns:
    ``(report, summary, csv_path)``.
    """
    return _run(data_dir, out_dir, use_agent=use_agent, on_step=on_step)
