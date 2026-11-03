# 01_data_cleaning.py

import argparse
from pathlib import Path
import pandas as pd
import hashlib
import json
import traceback

PIPELINE_VERSION = "cleaning-v1"

REQUIRED_COLUMNS = [
    'session_id', 'started_at', 'ended_at', 'persona_id', 'session_type',
    'source', 'summary', 'model_id', 'message_id', 'message_index', 'role',
    'content', 'message_at', 'message_metadata', 'language_code',
    'language_name'
]

DATE_COLUMNS = ["started_at", "ended_at", "message_at"]

EXPECTED_FIRST_INDEX = 0

# Dates contain explicit timezone offsets.
REPORT_TIMEZONE = "Asia/Kuala_Lumpur"


# Loading and helper functions

def is_blank(series):
    return series.astype("string").fillna("").str.strip().eq("")

def file_hash(path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def load_data(path):
    df = pd.read_csv(
        path,
        dtype="string",
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    missing = [
        column for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if df.empty:
        raise ValueError("The file contains no data rows.")

    return df

# Cleaning and quality checks

def clean_data(raw):
    df = raw.copy()

    # Check exact duplicates before adding derived columns.
    df["is_exact_duplicate"] = raw.duplicated(keep=False)

    df["is_session_id_missing"] = is_blank(df["session_id"])
    df["is_message_id_missing"] = is_blank(df["message_id"])

    valid_session = ~df["is_session_id_missing"]

    df["content_clean"] = (
        df["content"]
        .str.replace("\x00", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    df["content_length"] = df["content"].str.len()
    df["is_content_blank"] = is_blank(df["content_clean"])

    if "source" in df.columns:
        df["is_source_missing"] = is_blank(df["source"])
    else:
        df["is_source_missing"] = True

    df["is_end_missing"] = is_blank(df["ended_at"])

    # Convert numeric fields while preserving source values.
    numeric_columns = ["message_index", "role"]

    if "session_type" in df.columns:
        numeric_columns.append("session_type")

    for column in numeric_columns:
        original = df[column]
        number = pd.to_numeric(original, errors="coerce")

        valid_number = (
            number.notna()
            & number.ge(0)
            & number.le(2**63 - 1)
            & number.mod(1).eq(0)
        )

        df[f"{column}_original"] = original
        df[f"is_{column}_missing"] = is_blank(original)
        df[f"is_{column}_invalid"] = (
            ~is_blank(original) & ~valid_number
        )

        df[column] = number.where(valid_number).astype("Int64")

    df["is_role_unexpected"] = (
        df["role"].notna() & ~df["role"].isin([0, 1])
    )

    # Parse dates and preserve their original strings.
    for column in DATE_COLUMNS:
        original = df[column]
        df[f"{column}_original"] = original

        parsed = pd.to_datetime(
            original,
            format="mixed",
            errors="coerce",
            utc=True,
        )

        df[f"is_{column}_missing"] = is_blank(original)
        df[f"is_{column}_invalid"] = (
            ~is_blank(original) & parsed.isna()
        )

        df[column] = parsed.dt.tz_convert(REPORT_TIMEZONE)

    # Duplicate keys where blank IDs are flagged separately.
    valid_message = (
        valid_session & ~df["is_message_id_missing"]
    )

    df["is_duplicate_message"] = (
        valid_message
        & df.duplicated(
            ["session_id", "message_id"], keep=False
        )
    )

    valid_index = valid_session & df["message_index"].notna()

    df["is_duplicate_index"] = (
        valid_index
        & df.duplicated(
            ["session_id", "message_index"], keep=False
        )
    )

    # Detect conflicting session-level metadata.
    session_fields = [
        column for column in [
            "started_at", "ended_at", "persona_id",
            "session_type", "source", "model_id",
        ]
        if column in df.columns
    ]

    conflicts = (
        df.loc[valid_session]
        .groupby("session_id")[session_fields]
        .nunique(dropna=False)
        .gt(1)
        .any(axis=1)
    )

    df["is_session_metadata_conflict"] = (
        df["session_id"].map(conflicts).fillna(False).astype(bool)
    )

    # Count absent positions without generating a huge list.
    def count_missing_positions(values):
        values = values.dropna().drop_duplicates()

        if values.empty:
            return pd.NA

        maximum = int(values.max())
        expected_count = maximum - EXPECTED_FIRST_INDEX + 1
        observed_count = values.ge(EXPECTED_FIRST_INDEX).sum()

        return max(0, expected_count - int(observed_count))

    missing_positions = (
        df.loc[valid_session]
        .groupby("session_id")["message_index"]
        .apply(count_missing_positions)
    )

    df["missing_index_count"] = (
        df["session_id"].map(missing_positions).astype("Int64")
    )

    df["has_missing_index_positions"] = (
        df["missing_index_count"].gt(0).fillna(False)
    )


    # Reconstruct order before calculating message gaps.
    df = df.sort_values(
        ["session_id", "message_index", "message_at", "message_id"],
        na_position="last",
    ).reset_index(drop=True)

    valid_session = ~df["is_session_id_missing"]
    grouped = df.loc[valid_session].groupby("session_id")

    df["message_count"] = (
        grouped["message_id"].transform("size").astype("Int64")
    )

    df["role_count"] = (
        grouped["role"].transform("nunique").astype("Int64")
    )

    df["session_duration_minutes"] = (
        df["ended_at"] - df["started_at"]
    ).dt.total_seconds() / 60

    df["is_duration_negative"] = (
        df["session_duration_minutes"].lt(0)
    )

    df["message_gap_seconds"] = (
        grouped["message_at"].diff().dt.total_seconds()
    )

    df["is_message_gap_negative"] = (
        df["message_gap_seconds"].lt(0)
    )

    df["is_message_outside_session"] = (
        (df["message_at"] < df["started_at"])
        | (df["message_at"] > df["ended_at"])
    )

    # Local calendar fields for later exploration.
    local_start = df["started_at"].dt.tz_localize(None)

    df["date"] = local_start.dt.date
    df["week"] = local_start.dt.to_period("W").astype("string")
    df["month"] = local_start.dt.to_period("M").astype("string")
    df["hour"] = local_start.dt.hour
    df["minute"] = local_start.dt.minute

    # A review flag does not automatically mean unusable data.
    flag_columns = [
        column for column in df.columns
        if column.startswith("is_")
    ] + ["has_missing_index_positions"]

    df["requires_review"] = (
        df[flag_columns].fillna(False).any(axis=1)
    )

    return df

def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def save_outputs(df, folder, filename):
    folder.mkdir(parents=True, exist_ok=True)
    flags = [c for c in df.columns if c.startswith("is_")]
    flags += [c for c in ["has_missing_index_positions", "requires_review"] if c in df]
    quality = df[flags].sum().rename_axis("check").reset_index(name="affected_message_rows")
    if "translation_status" in df:
        counts = df["translation_status"].value_counts().rename_axis("check").reset_index(name="affected_message_rows")
        counts["check"] = "translation_" + counts["check"]
        quality = pd.concat([quality, counts], ignore_index=True)
    outputs = [(df, folder / filename), (quality, folder / "quality.csv"),
               (df.loc[df["requires_review"]], folder / "review.csv")]
    for table, path in outputs:
        temporary = path.with_suffix(".tmp")
        table.to_csv(temporary, index=False, encoding="utf-8-sig")
        temporary.replace(path)
    return [str(path.resolve()) for _, path in outputs]

def already_done(previous, fingerprint):
    outputs = previous.get("outputs", [])
    return (previous.get("fingerprint") == fingerprint
            and previous.get("version") == PIPELINE_VERSION
            and previous.get("status") == "finished"
            and bool(outputs) and all(Path(p).is_file() for p in outputs))

def main():
    parser = argparse.ArgumentParser(description="Clean new or changed raw CSVs. No translation service required.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="outputs/cleaned")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    source, destination = Path(args.input_dir).resolve(), Path(args.output_dir).resolve()
    if not source.is_dir():
        parser.error(f"Input folder not found: {source}")
    if source == destination or source.is_relative_to(destination):
        parser.error("Output folder must not equal or contain the input folder.")
    destination.mkdir(parents=True, exist_ok=True)
    history_path = destination / "cleaning_history.json"
    history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else {}
    processed = skipped = failed = 0
    files = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    for path in files:
        key = str(path)
        try:
            fingerprint = file_hash(path)
            if not args.force and already_done(history.get(key, {}), fingerprint):
                print(f"SKIP: {path.name}")
                skipped += 1
                continue
            print(f"CLEAN: {path.name}")
            df = clean_data(load_data(path))
            if file_hash(path) != fingerprint:
                raise RuntimeError("Input changed during processing; rerun.")
            outputs = save_outputs(df, destination / path.name, f"{path.stem}[cleaned].csv")
            history[key] = dict(fingerprint=fingerprint, version=PIPELINE_VERSION,
                                status="finished", outputs=outputs)
            write_json(history_path, history)
            processed += 1
            print(f"SAVED: {outputs[0]}")
        except Exception as error:
            failed += 1
            history[key] = dict(status="failed", error=str(error))
            write_json(history_path, history)
            traceback.print_exc()
    print(f"Processed: {processed} | Skipped: {skipped} | Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

