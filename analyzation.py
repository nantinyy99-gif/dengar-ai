# 05_analysis.py

import argparse
import json
import re
import hashlib
from pathlib import Path
import pandas as pd

# Constants
TIMEZONE = "Asia/Kuala_Lumpur"
SENTIMENT_SCORES = {
    "negative": -1,
    "neutral": 0,
    "positive": 1,
}
MINISTRY_CODES = {"POL", "IMM", "JPN", "CYB", "FWK", "GFB", "OTH"}
CLASSIFICATION_COLUMNS = [
    "conversation_scope",
    "scope_match_score",
    "scope_review",
    "ministry_topic_code",
    "ministry_topic_name",
    "ministry_topic_match_score",
    "ministry_topic_margin",
    "ministry_topic_status",
    "ministry_topic_review",
    "intent",
    "intent_match_score",
    "intent_margin",
    "intent_review",
    "classification_review",
]

# Utility functions
def log(message):
    print(message, flush=True)


def save_csv(df, path):
    temporary = path.with_name(path.name + ".tmp")
    df.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(path)


def parse_dates(series):
    return pd.to_datetime(
        series,
        errors="coerce",
        utc=True,
        format="mixed",
    ).dt.tz_convert(TIMEZONE)


def as_bool(series):
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1"])
    )


def first_nonblank(series):
    values = series.fillna("").astype(str).str.strip()
    values = values[values.ne("")]
    return values.iloc[0] if not values.empty else ""


def has_conflict(series):
    values = series.fillna("").astype(str).str.strip()
    return values[values.ne("")].nunique() > 1


def any_true(series):
    return as_bool(series).any()


def nonnegative_seconds(start, end):
    if pd.isna(start) or pd.isna(end):
        return None

    seconds = (end - start).total_seconds()
    return seconds if seconds >= 0 else None

# Core function to analyze one session
def analyse_session(dataset, dataset_source, session_id, original):
    group = original.copy()

    # Prepare helper columns
    group["_index"] = pd.to_numeric(
        group["message_index"], errors="coerce"
    )
    group["_time"] = parse_dates(group["message_at"])
    group["_role"] = pd.to_numeric(group["role"], errors="coerce")

    # Sort messages by index and time
    group = group.sort_values(
        ["_index", "_time"],
        kind="stable",
        na_position="last",
    )

    # Remove duplicate message IDs.
    repeated = (
        group["message_id"].str.strip().ne("")
        & group["message_id"].duplicated(keep="first")
    )
    duplicate_count = int(repeated.sum())
    group = group.loc[~repeated].copy()


    # Split user vs AI messages
    text = group["content"].fillna("").str.strip()
    user = group.loc[group["_role"].eq(0)]
    ai = group.loc[group["_role"].eq(1)]
    user_text = text.loc[user.index]
    ai_text = text.loc[ai.index]

    # Identify non-empty messages
    nonempty_users = user.loc[user_text.ne("")]
    nonempty_ai = ai.loc[ai_text.ne("")]

    # Session starts or end times
    starts = parse_dates(original["started_at"]).dropna()
    ends = parse_dates(original["ended_at"]).dropna()

    started_at = starts.min() if not starts.empty else pd.NaT
    ended_at = ends.max() if not ends.empty else pd.NaT

    start_conflict = starts.nunique() > 1
    end_conflict = ends.nunique() > 1

    duration_invalid = bool(
        pd.notna(started_at)
        and pd.notna(ended_at)
        and ended_at < started_at
    )

    recorded_seconds = nonnegative_seconds(started_at, ended_at)

    if start_conflict or end_conflict:
        recorded_seconds = None

    # Observed messages span
    times = group["_time"].dropna()
    first_message = times.min() if not times.empty else pd.NaT
    last_message = times.max() if not times.empty else pd.NaT
    observed_seconds = nonnegative_seconds(first_message, last_message)

    # Calculate reply gaps (user --> AI)
    # These are timestamp gaps, not verified AI processing latency.
    reply_gaps = []
    rows = list(group[["_role", "_time"]].itertuples(index=False, name=None))

    for previous, current in zip(rows, rows[1:]):
        previous_role, previous_time = previous
        current_role, current_time = current

        if (
            pd.notna(previous_role)
            and pd.notna(current_role)
            and previous_role == 0
            and current_role == 1
        ):
            gap = nonnegative_seconds(previous_time, current_time)
            if gap is not None:
                reply_gaps.append(gap)

    # Engagement type
    user_count = len(nonempty_users)

    if user_count == 0:
        engagement = "no_user_response"
    elif user_count == 1:
        engagement = "one_user_message"
    else:
        engagement = "multiple_user_messages"

    # First user message time
    user_times = nonempty_users["_time"].dropna()
    first_user_time = user_times.min() if not user_times.empty else pd.NaT

    # Check if conversation ends with user
    conversational = group.loc[
        group["_role"].isin([0, 1]) & text.ne("")
    ]
    ends_with_user = bool(
        not conversational.empty
        and conversational["_role"].iloc[-1] == 0
    )

    # Languages used: preserve both the language code and readable name
    language_codes = original["language_code"].fillna("").astype(str).str.strip()
    language_codes = sorted(set(language_codes[language_codes.ne("")]))

    language_names = original["language_name"].fillna("").astype(str).str.strip()
    language_names = sorted(set(language_names[language_names.ne("")]))

    # Return all metrics
    result = {
        "dataset": dataset,
        "dataset_source": dataset_source,
        "session_id": session_id,
        "language_code": ", ".join(language_codes),
        "language_name": ", ".join(language_names),
        "recorded_languages": ", ".join(language_codes),
        "started_at": started_at,
        "ended_at": ended_at,
        "first_message_at": first_message,
        "last_message_at": last_message,
        "first_user_message_at": first_user_time,
        "source": first_nonblank(original["source"]),
        "persona_id": first_nonblank(original["persona_id"]),
        "source_conflict": has_conflict(original["source"]),
        "persona_conflict": has_conflict(original["persona_id"]),
        "exported_row_count": len(original),
        "duplicate_message_rows_excluded": duplicate_count,
        "message_count": len(group),
        "user_message_count": len(user),
        "ai_message_count": len(ai),
        "nonempty_user_message_count": user_count,
        "nonempty_ai_message_count": len(nonempty_ai),
        "unknown_role_message_count": int(
            (~group["_role"].isin([0, 1])).sum()
        ),
        "blank_message_count": int(text.eq("").sum()),
        "user_character_count": int(user_text.str.len().sum()),
        "engagement_type": engagement,
        "has_user_response": user_count > 0,
        "is_single_message_session": len(group) == 1,
        "ends_with_user_message": ends_with_user,
        "recorded_duration_seconds": recorded_seconds,
        "observed_message_span_seconds": observed_seconds,
        "first_user_delay_seconds": nonnegative_seconds(
            started_at, first_user_time
        ),
        "user_to_ai_gap_count": len(reply_gaps),
        "average_user_to_ai_gap_seconds": (
            sum(reply_gaps) / len(reply_gaps) if reply_gaps else None
        ),
        "is_start_missing_or_invalid": pd.isna(started_at),
        "is_end_missing_or_invalid": pd.isna(ended_at),
        "is_duration_invalid": duration_invalid,
        "session_time_conflict": start_conflict or end_conflict,
        "message_time_missing_or_invalid_count": int(
            group["_time"].isna().sum()
        ),
        "cleaning_review_required": (
            any_true(original["requires_review"])
            if "requires_review" in original
            else False
        ),
    }




    # Retain every additional cleaned CSV column at session level, with
    # a namespaced prefix rather than discarding source metadata.
    handled = {"session_id", "message_id", "message_index", "role", "content",
               "message_at", "started_at", "ended_at", "source", "persona_id",
               "language_code", "language_name"}
    for col in original.columns:
        if col not in handled and not col.startswith("_"):
            safe = re.sub(r"[^a-zA-Z0-9_]+", "_", str(col)).strip("_")
            if safe:
                result["raw_" + safe] = first_nonblank(original[col])
    result["session_ai_text"] = "\n".join(ai_text[ai_text.ne("")].tolist())
    result["session_user_text_from_messages"] = "\n".join(user_text[user_text.ne("")].tolist())
    result["user_message_language_codes"] = ", ".join(sorted(set(nonempty_users["language_code"].fillna("").astype(str)) - {""}))
    result["ai_message_language_codes"] = ", ".join(sorted(set(nonempty_ai["language_code"].fillna("").astype(str)) - {""}))
    result["user_language_codes_multiple"] = len(set(nonempty_users["language_code"].fillna("").astype(str)) - {""}) > 1
    result["user_language_vs_session_recorded_mismatch"] = (bool(result["user_message_language_codes"])
        and bool(result["recorded_languages"])
        and not set(result["user_message_language_codes"].split(", ")).issubset(set(result["recorded_languages"].split(", "))))
    result["message_timeline_json"] = json.dumps([
        {"index": str(row.get("message_index", "")),
         "role": str(row.get("role", "")),
         "at": str(row.get("message_at", "")),
         "language_code": str(row.get("language_code", "")),
         "language_name": str(row.get("language_name", "")),
         "content": str(row.get("content", ""))}
        for _, row in group.iterrows()], ensure_ascii=False)
    return result
# --- ADDITIONAL SCORING AND SESSION-JOURNEY ANALYSIS ---
DIMENSIONS = ("issue_clarity", "evidence_strength", "impact_severity", "request_actionability", "urgency")

def flatten_values(value, prefix, result):
    """Preserve ALL rubric leaves in columns; lists as UTF-8 JSON for lossless CSV."""
    if isinstance(value, dict):
        for k, v in value.items():
            safe = re.sub(r"[^a-zA-Z0-9_]+", "_", str(k)).strip("_")
            flatten_values(v, prefix + "_" + safe, result)
    elif isinstance(value, list):
        result[prefix] = json.dumps(value, ensure_ascii=False)
    else:
        result[prefix] = value


def scoring_table(folder, extra_paths=()):
    """Read scoring JSONL from input directory or named files; join by dataset/source + session ID."""
    sources = [Path(p) for p in extra_paths if p]
    sources += sorted(folder.rglob("*scoring.jsonl"))
    sources += sorted(folder.parent.glob("*scoring.jsonl"))
    unique = {p.resolve(): p for p in sources if p.is_file()}
    rows = []
    for path in unique.values():
        log(f"Scoring records: {path}")
        with path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    log(f"WARNING: invalid scoring JSONL {path.name}:{line_no}: {exc}")
                    continue
                sid = str(obj.get("session_id", "")).strip()
                if not sid:
                    continue
                ds = str(obj.get("dataset", "")).lower()
                file_hint = (ds + " " + path.name.lower())
                source = "SP1" if "sp1" in file_hint else "SP9" if "sp9" in file_hint else "Unknown"
                r = {"dataset": obj.get("dataset", ""), "session_id": sid,
                     "ai_scoring_available": True, "ai_scoring_file": path.name,
                     "ai_scoring_dataset": obj.get("dataset", ""),
                     "ai_scoring_full_json": json.dumps(obj, ensure_ascii=False)}
                for key in ("model", "rubric_version", "text_sha256", "key"):
                    r["ai_" + key] = obj.get(key, "")
                flatten_values(obj.get("raw_ai_result", {}), "ai_raw", r)
                flatten_values(obj.get("calculated", {}), "ai_calc", r)
                calc = obj.get("calculated", {})
                r["ai_human_review_required"] = calc.get("human_review_required", False)
                r["ai_human_review_reason"] = calc.get("review_reason", "")
                raw = obj.get("raw_ai_result", {})
                r["ai_principal_issue"] = raw.get("principal_issue", "")
                r["ai_validated_topic_code"] = raw.get("validated_topic_code", "")
                audit = []
                for dim in DIMENSIONS:
                    d = calc.get("dimensions", {}).get(dim, {})
                    for k in ("status", "score", "coverage", "review", "reason", "route", "override"):
                        r[f"ai_{dim}_{k}"] = d.get(k)
                    coverage = pd.to_numeric(d.get("coverage"), errors="coerce")
                    score = pd.to_numeric(d.get("score"), errors="coerce")
                    # Screening only; gateways/overrides require manual audit.
                    flagged = pd.notna(score) and pd.notna(coverage) and coverage < 0.60
                    r[f"ai_{dim}_coverage_audit"] = bool(flagged)
                    if flagged:
                        audit.append(dim)
                r["ai_coverage_audit_dimensions"] = ", ".join(audit)
                r["ai_coverage_audit_required"] = bool(audit)
                rows.append(r)
    if not rows:
        log("No scoring JSONL found: master CSV will retain sessions without AI scores.")
        return pd.DataFrame(columns=["dataset", "session_id", "ai_scoring_available"])
    scores = pd.DataFrame(rows)
    ndup = scores.duplicated(["dataset", "session_id"], keep="last").sum()
    if ndup:
        log(f"WARNING: {ndup} duplicated scoring keys, last record retained")
        scores = scores.drop_duplicates(["dataset", "session_id"], keep="last")
    return scores


def add_journey_metrics(frame):
    """Only compare within source/dataset; never infer identity from timing."""
    out = frame.copy()
    timestamps = pd.to_datetime(out["started_at"], errors="coerce", utc=True)
    out["_sort_time"] = timestamps
    out = out.sort_values(["dataset_source", "_sort_time", "session_id"], kind="stable")
    groups = out.groupby("dataset_source", sort=False)
    for direction, shift in (("previous", 1), ("next", -1)):
        for field in ("session_id", "engagement_type", "language_code", "language_name",
                      "nonempty_user_message_count", "session_user_text", "ministry_topic_code"):
            if field in out:
                out[f"{direction}_{field}"] = groups[field].shift(shift)
        out[f"{direction}_started_at"] = groups["_sort_time"].shift(shift)
    out["previous_start_gap_seconds"] = (out["_sort_time"] - out["previous_started_at"]).dt.total_seconds()
    out["next_start_gap_seconds"] = (out["next_started_at"] - out["_sort_time"]).dt.total_seconds()
    end_time = pd.to_datetime(out["ended_at"], errors="coerce", utc=True)
    previous_end = end_time.groupby(out["dataset_source"]).shift(1)
    out["previous_end_to_start_seconds"] = (out["_sort_time"] - previous_end).dt.total_seconds()
    out["previous_session_overlap"] = out["previous_end_to_start_seconds"].lt(0)
    out["previous_language_changed"] = (out["language_code"].fillna("").astype(str).str.lower() != out["previous_language_code"].fillna("").astype(str).str.lower()) & out["previous_session_id"].notna()
    out["next_language_changed"] = (out["language_code"].fillna("").astype(str).str.lower() != out["next_language_code"].fillna("").astype(str).str.lower()) & out["next_session_id"].notna()
    out["transition_from_previous"] = out["previous_engagement_type"].fillna("no_previous") + " -> " + out["engagement_type"].fillna("unknown")
    out["transition_to_next"] = out["engagement_type"].fillna("unknown") + " -> " + out["next_engagement_type"].fillna("no_next")
    valid = out["previous_start_gap_seconds"].between(0, 300)
    out["potential_continuation_5min"] = valid & out["has_user_response"] & out["previous_session_id"].notna()
    out["prior_empty_within_5min"] = valid & out["previous_engagement_type"].eq("no_user_response") & out["has_user_response"]
    prevprev = groups["engagement_type"].shift(2)
    gap2 = groups["previous_start_gap_seconds"].shift(1)
    out["zero_one_multiple_sequence_end"] = (out["engagement_type"].eq("multiple_user_messages") & out["previous_engagement_type"].eq("one_user_message") & prevprev.eq("no_user_response") & valid & gap2.between(0, 300))
    out["start_gap_band"] = pd.cut(out["previous_start_gap_seconds"], bins=[-0.001,30,60,120,180,300,600,float("inf")], labels=["0-30s","30-60s","1-2m","2-3m","3-5m","5-10m",">10m"]).astype("string")
    out = out.drop(columns=["_sort_time"])
    return out


def add_user_language_signals(frame):
    """Script-level Unicode hints are not reliable language identification."""
    out = frame.copy()
    user_text = out.get(
        "session_user_text",
        pd.Series("", index=out.index)
    ).fillna("").astype(str).astype(object)

    out["user_has_tamil_script"] = user_text.str.contains(
        "[\u0B80-\u0BFF]", regex=True, na=False
    )

    out["user_has_arabic_script"] = user_text.str.contains(
        "[\u0600-\u06FF]", regex=True, na=False
    )

    out["user_has_cjk_script"] = user_text.str.contains(
        "[\u4E00-\u9FFF]", regex=True, na=False
    )

    scripts = ["tamil", "arabic", "cjk"]

    for name in scripts:
        out[f"user_{name}_script_present"] = out[f"user_has_{name}_script"]
    out["user_script_types_count"] = sum(out[f"user_has_{name}_script"].astype(int) for name in scripts)
    out["user_multiple_scripts"] = out["user_script_types_count"].ge(2)
    out["actual_user_language_status"] = "not_detected_script_hints_only"
    return out


# Main script entry point
def main():
    parser = argparse.ArgumentParser(
        description="Create one analysed row per dataset and session."
    )
    parser.add_argument("--input-dir", default="output data")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path; default is input-dir/analyzed.csv",
    )
    parser.add_argument("--scoring-jsonl", action="append", default=[], help="Optional scoring JSONL path (repeatable)")
    args = parser.parse_args()

    folder = Path(args.input_dir)
    summary_path = folder / "session_summary.csv"
    output_path = (
        Path(args.output) if args.output else folder / "analyzed.csv"
    )

    if not folder.is_dir():
        parser.error(f"Folder not found: {folder.resolve()}")

    if not summary_path.is_file():
        parser.error(
            "session_summary.csv not found. "
            "Finish 03_sentiment_topic.py first."
        )

    files = sorted(
        path for path in folder.rglob("*.csv")
        if path.name.endswith("[cleaned].csv")
    )

    if not files:
        parser.error("No [cleaned].csv files found.")

    protected_paths = {path.resolve() for path in files}
    protected_paths.add(summary_path.resolve())

    if output_path.resolve() in protected_paths:
        parser.error("--output must be a new analysis file.")

    summary = pd.read_csv(
        summary_path,
        dtype="string",
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    summary_required = {
        "dataset",
        "session_id",
        "session_user_text",
        "session_sentiment",
        "session_sentiment_score",
        "first_user_sentiment",
        "last_user_sentiment",
        "session_primary_topic",
        "session_topic_keywords",
        "topic_status",
        *CLASSIFICATION_COLUMNS,
    }

    missing = summary_required - set(summary.columns)
    if missing:
        raise ValueError(
            "session_summary.csv is missing columns: "
            f"{sorted(missing)}. Rerun 03_sentiment_topic.py first."
        )

    keys = ["dataset", "session_id"]

    if summary.duplicated(keys).any():
        raise ValueError(
            "session_summary.csv contains duplicate dataset/session IDs."
        )

    if summary["topic_status"].eq("pending").any():
        raise ValueError(
            "Topic modelling is still pending. "
            "Finish script 03 before running script 04."
        )

    log(f"Cleaned files found: {len(files)}")
    records = []

    required = {
        "session_id",
        "message_id",
        "message_index",
        "role",
        "content",
        "message_at",
        "started_at",
        "ended_at",
        "source",
        "persona_id",
        "language_code",
        "language_name",
    }

    for path in files:
        log(f"Analysing: {path.name}")

        df = pd.read_csv(
            path,
            dtype="string",
            keep_default_na=False,
            encoding="utf-8-sig",
        )

        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"{path.name}: missing {sorted(missing)}")

        dataset = path.relative_to(folder).as_posix()

        # Normalize the source label so both datasets use the same filter values
        path_label = dataset.lower()

        if "sp1" in path_label:
            dataset_source = "SP1"
        elif "sp9" in path_label:
            dataset_source = "SP9"
        else:
            dataset_source = Path(dataset).stem.replace("[cleaned]", "")
            log(f"  INFO: Using dataset label {dataset_source} for {dataset}")

        valid = df["session_id"].str.strip().ne("")

        log(f"  Rows with missing session ID: {int((~valid).sum())}")

        for session_id, group in df.loc[valid].groupby(
            "session_id", sort=False
        ):
            records.append(
                analyse_session(dataset, dataset_source, session_id, group)
            )

    if not records:
        raise ValueError("No valid sessions to analyse.")

    metrics = pd.DataFrame(records)

    # Confirm script 03 and the cleaned files contain the same sessions.
    coverage = metrics[keys].merge(
        summary[keys],
        on=keys,
        how="outer",
        indicator=True,
        validate="one_to_one",
    )

    if not coverage["_merge"].eq("both").all():
        raise ValueError(
            "Cleaned datasets and session_summary.csv do not match. "
            "Rerun script 03 for the current datasets."
        )

    # Use newly calculated metadata where both files have the same column.
    overlap = [
        column for column in metrics.columns
        if column in summary.columns and column not in keys
    ]
    summary = summary.drop(columns=overlap)

    analysed = metrics.merge(
        summary,
        on=keys,
        how="left",
        validate="one_to_one",
    )

    # Restore CSV boolean fields for calculations.
    boolean_columns = [
        "has_user_response",
        "is_single_message_session",
        "is_start_missing_or_invalid",
        "is_end_missing_or_invalid",
        "is_duration_invalid",
        "session_time_conflict",
        "source_conflict",
        "persona_conflict",
        "cleaning_review_required",
        "session_sentiment_review",
        "session_topic_language_review",
        "topic_text_truncated",
        "scope_review",
        "ministry_topic_review",
        "intent_review",
        "classification_review",
    ]

    for column in boolean_columns:
        if column in analysed:
            analysed[column] = as_bool(analysed[column])

    # 1. Calendar fields for dashboard time filters

    started = parse_dates(analysed["started_at"])

    analysed["session_date"] = started.dt.strftime("%Y-%m-%d")
    analysed["session_month"] = started.dt.strftime("%Y-%m")

    iso_calendar = started.dt.isocalendar()
    analysed["session_week"] = (
        iso_calendar["year"].astype("string")
        + "-W"
        + iso_calendar["week"].astype("string").str.zfill(2)
    )

    analysed["weekday"] = started.dt.day_name()
    analysed["weekday_number"] = started.dt.dayofweek
    analysed["session_hour"] = started.dt.hour
    analysed["session_minute"] = started.dt.minute

    analysed["session_hour_bucket"] = started.dt.strftime(
        "%Y-%m-%d %H:00"
    )
    analysed["session_minute_bucket"] = started.dt.strftime(
        "%Y-%m-%d %H:%M"
    )

    analysed["is_weekend"] = started.dt.dayofweek.ge(5).astype("boolean")
    analysed.loc[started.isna(), "is_weekend"] = pd.NA

    # 2. Duration fields

    analysed["recorded_duration_seconds"] = pd.to_numeric(
        analysed["recorded_duration_seconds"], errors="coerce"
    )
    analysed["observed_message_span_seconds"] = pd.to_numeric(
        analysed["observed_message_span_seconds"], errors="coerce"
    )

    analysed["recorded_duration_minutes"] = (
        analysed["recorded_duration_seconds"] / 60
    )
    analysed["observed_message_span_minutes"] = (
        analysed["observed_message_span_seconds"] / 60
    )

    # 3. Sentiment movement

    analysed["session_sentiment_score"] = pd.to_numeric(
        analysed["session_sentiment_score"], errors="coerce"
    )

    first_score = analysed["first_user_sentiment"].map(SENTIMENT_SCORES)
    last_score = analysed["last_user_sentiment"].map(SENTIMENT_SCORES)

    analysed["sentiment_change_score"] = last_score - first_score
    analysed["sentiment_direction"] = "not_comparable"

    comparable = (
        analysed["nonempty_user_message_count"].ge(2)
        & first_score.notna()
        & last_score.notna()
    )

    analysed.loc[
        comparable & analysed["sentiment_change_score"].gt(0),
        "sentiment_direction",
    ] = "more_positive"

    analysed.loc[
        comparable & analysed["sentiment_change_score"].lt(0),
        "sentiment_direction",
    ] = "more_negative"

    analysed.loc[
        comparable & analysed["sentiment_change_score"].eq(0),
        "sentiment_direction",
    ] = "same_label"

    analysed.loc[
        ~comparable, "sentiment_change_score"
    ] = float("nan")

    # 4. Classification indicators for charts and filters

    analysed["has_assigned_bertopic_topic"] = (
        analysed["topic_status"].eq("assigned")
    )

    analysed["has_ministry_topic"] = (
        analysed["ministry_topic_status"].eq("assigned")
        & analysed["ministry_topic_code"].isin(MINISTRY_CODES)
    )

    analysed["has_intent"] = (
        analysed["intent"].ne("")
        & analysed["intent"].ne("needs_review")
    )

    analysed["is_ministry_related"] = (
        analysed["conversation_scope"].eq("ministry_related")
    )

    analysed["is_persona_chat"] = (
        analysed["conversation_scope"].eq("persona_chat")
    )

    analysed["is_unrelated_conversation"] = (
        analysed["conversation_scope"].eq("unrelated")
    )

    # Keep classification review separate, then include it in the
    # overall analysis review flag.
    analysed["classification_review_required"] = (
        analysed["scope_review"]
        | analysed["ministry_topic_review"]
        | analysed["intent_review"]
        | analysed["classification_review"]
    )

    # 5. Combined data/model review flag

    analysed["analysis_review_required"] = (
        analysed["cleaning_review_required"]
        | analysed["is_start_missing_or_invalid"]
        | analysed["is_end_missing_or_invalid"]
        | analysed["is_duration_invalid"]
        | analysed["session_time_conflict"]
        | analysed["source_conflict"]
        | analysed["persona_conflict"]
        | analysed["duplicate_message_rows_excluded"].gt(0)
        | analysed["message_time_missing_or_invalid_count"].gt(0)
        | analysed["unknown_role_message_count"].gt(0)
        | analysed["classification_review_required"]
    )

    for column in [
        "session_sentiment_review",
        "session_topic_language_review",
        "topic_text_truncated",
    ]:
        if column in analysed:
            analysed["analysis_review_required"] |= analysed[column]

    # Merge scoring without dropping original classification/metadata columns.
    scores = scoring_table(folder, args.scoring_jsonl)
    analysed = analysed.merge(scores, on=["dataset", "session_id"], how="left", validate="one_to_one")
    analysed["ai_scoring_available"] = analysed["ai_scoring_available"].fillna(False).astype(bool)
    analysed = add_journey_metrics(analysed)
    analysed = add_user_language_signals(analysed)

    analysed = analysed.sort_values(
        ["started_at", "dataset", "session_id"],
        kind="stable",
        na_position="last",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_csv(analysed, output_path)

    # 6. Console summary

    total = len(analysed)
    engaged = int(analysed["has_user_response"].sum())

    log(f"\nSaved: {output_path.resolve()}")
    log(f"Total sessions: {total}")
    log(f"Sessions with user response: {engaged}")
    log(f"Sessions without user response: {total - engaged}")
    log(f"User response rate: {engaged / total:.1%}")

    log("\nSessions by dataset:")
    log(analysed.groupby("dataset").size().to_string())

    log("\nSession sentiment:")
    log(analysed["session_sentiment"].value_counts().to_string())

    log("\nMinistry topic assignments:")
    log(
        analysed["ministry_topic_code"]
        .replace("", "No assigned Ministry topic")
        .value_counts()
        .to_string()
    )

    log("\nIntent assignments:")
    log(
        analysed["intent"]
        .replace("", "No intent")
        .value_counts()
        .to_string()
    )

    log("\nConversation scope:")
    log(analysed["conversation_scope"].value_counts().to_string())

    log(
        "\nSessions flagged for classification review: "
        f"{int(analysed['classification_review_required'].sum())}"
    )
    log(
        "Sessions flagged for any analysis review: "
        f"{int(analysed['analysis_review_required'].sum())}"
    )

    assigned = analysed.loc[analysed["has_assigned_bertopic_topic"]]

    log("\nTop 10 exploratory BERTopic topics by session count:")
    if assigned.empty:
        log("No assigned BERTopic topics.")
    else:
        top_topics = (
            assigned.groupby(
                ["session_primary_topic", "session_topic_keywords"]
            )
            .size()
            .sort_values(ascending=False)
            .head(10)
            .rename("session_count")
        )
        log(top_topics.to_string())

    log("\nFINISHED — ready for the dashboard.")


if __name__ == "__main__":
    main()