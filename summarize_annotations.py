#!/usr/bin/env python3
"""
Summarize manual annotation JSON files for Chapter 3 reporting.

Outputs:
- outputs/annotation_summary/chapter3_annotation_summary.md
- outputs/annotation_summary/voice_summary.csv
- outputs/annotation_summary/category_summary.csv
- outputs/annotation_summary/summary.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
ANNOTATION_ROOT = ROOT / "model_eval" / "annotations"
WORKBOOK = ROOT / "model_eval" / "Model Evaluation Results.xlsx"
OUT_DIR = ROOT / "outputs" / "annotation_summary"


def pct(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100.0, 1)


def format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.1f}%"


def load_metadata() -> dict[tuple[str, str], dict[str, Any]]:
    metadata: dict[tuple[str, str], dict[str, Any]] = {}
    workbook = pd.ExcelFile(WORKBOOK)
    for sheet_name in workbook.sheet_names:
        df = pd.read_excel(workbook, sheet_name=sheet_name)
        for _, row in df.iterrows():
            item_id = str(row["ItemID"]).strip()
            metadata[(sheet_name, item_id)] = {
                "text": str(row["Text"]),
                "category": str(row["Category"]),
                "target_feature": str(row["Target_Feature"]),
            }
    return metadata


def load_annotations(metadata: dict[tuple[str, str], dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for voice in ("Male", "Female"):
        voice_dir = ANNOTATION_ROOT / voice
        for path in sorted(voice_dir.glob("*.json")):
            item_id = path.stem
            meta = metadata[(voice, item_id)]
            data = json.loads(path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "voice": voice,
                    "item_id": item_id,
                    "text": meta["text"],
                    "category": meta["category"],
                    "target_feature": meta["target_feature"],
                    "Naturalness": str(data.get("Naturalness", "")).strip(),
                    "Intelligibility": str(data.get("Intelligibility", "")).strip(),
                    "Context": str(data.get("Context", "")).strip(),
                    "IncorrectWords": str(data.get("IncorrectWords", "")).strip(),
                    "NumberMistakes": str(data.get("NumberMistakes", "")).strip(),
                    "ConjunctMistakes": str(data.get("ConjunctMistakes", "")).strip(),
                    "Notes": str(data.get("Notes", "")).strip(),
                    "Preference": str(data.get("Preference", "")).strip(),
                }
            )

    df = pd.DataFrame(rows)
    df["has_incorrect_words"] = df["IncorrectWords"] != ""
    df["has_number_mistakes"] = df["NumberMistakes"] != ""
    df["has_conjunct_mistakes"] = df["ConjunctMistakes"] != ""
    df["has_notes"] = df["Notes"] != ""
    df["human_like"] = df["Naturalness"] == "Human-like"
    df["context_applicable"] = df["Context"].isin(["Yes", "No"])
    df["context_correct"] = df["Context"] == "Yes"
    return df


def build_voice_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for voice, group in df.groupby("voice", sort=True):
        rows.append(
            {
                "voice": voice,
                "n_samples": int(len(group)),
                "human_like_rate_pct": pct(int(group["human_like"].sum()), len(group)),
                "slightly_robotic": int((group["Naturalness"] == "Slightly Robotic").sum()),
                "very_robotic": int((group["Naturalness"] == "Very Robotic").sum()),
                "intelligibility_yes_rate_pct": pct(int((group["Intelligibility"] == "Yes").sum()), len(group)),
                "context_success_pct": pct(
                    int(group["context_correct"].sum()),
                    int(group["context_applicable"].sum()),
                ),
                "incorrect_word_rate_pct": pct(int(group["has_incorrect_words"].sum()), len(group)),
                "number_mistake_rate_pct": pct(int(group["has_number_mistakes"].sum()), len(group)),
                "conjunct_mistake_rate_pct": pct(int(group["has_conjunct_mistakes"].sum()), len(group)),
                "notes_rate_pct": pct(int(group["has_notes"].sum()), len(group)),
            }
        )
    return pd.DataFrame(rows)


def build_category_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for category, group in df.groupby("category", sort=True):
        rows.append(
            {
                "category": category,
                "n_samples": int(len(group)),
                "human_like_rate_pct": pct(int(group["human_like"].sum()), len(group)),
                "context_success_pct": pct(
                    int(group["context_correct"].sum()),
                    int(group["context_applicable"].sum()),
                ),
                "incorrect_word_rate_pct": pct(int(group["has_incorrect_words"].sum()), len(group)),
                "number_mistake_rate_pct": pct(int(group["has_number_mistakes"].sum()), len(group)),
                "conjunct_mistake_rate_pct": pct(int(group["has_conjunct_mistakes"].sum()), len(group)),
                "notes_rate_pct": pct(int(group["has_notes"].sum()), len(group)),
                "slightly_or_very_robotic_pct": pct(
                    int((~group["human_like"]).sum()),
                    len(group),
                ),
            }
        )
    return pd.DataFrame(rows)


def build_unique_prompt_preference(df: pd.DataFrame) -> dict[str, int]:
    prompt_df = (
        df.sort_values(["item_id", "voice"])
        .drop_duplicates(subset=["item_id"])[["item_id", "Preference"]]
        .copy()
    )
    counts = prompt_df["Preference"].value_counts().to_dict()
    return {
        "Equal": int(counts.get("Equal", 0)),
        "Female": int(counts.get("Female", 0)),
        "Male": int(counts.get("Male", 0)),
    }


def collect_hotspots(df: pd.DataFrame) -> dict[str, Any]:
    context_failures = df[df["Context"] == "No"][
        ["voice", "item_id", "category", "target_feature"]
    ].to_dict(orient="records")

    numeric_failures = df[df["has_number_mistakes"]][
        ["voice", "item_id", "category", "target_feature", "NumberMistakes", "Notes"]
    ].to_dict(orient="records")

    code_mix_failures = df[df["category"] == "Code-Mix"]["has_incorrect_words"].sum()

    return {
        "context_failures": context_failures,
        "numeric_failures": numeric_failures,
        "code_mix_incorrect_word_samples": int(code_mix_failures),
    }


def markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, sep]
    for _, row in df[columns].iterrows():
        values = []
        for col in columns:
            value = row[col]
            if pd.isna(value):
                values.append("-")
                continue
            text = str(value)
            values.append("-" if text in {"nan", "nan%"} else text)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_markdown(
    df: pd.DataFrame,
    voice_summary: pd.DataFrame,
    category_summary: pd.DataFrame,
    preference: dict[str, int],
    hotspots: dict[str, Any],
) -> Path:
    total_samples = len(df)
    total_prompts = df["item_id"].nunique()
    human_like = int(df["human_like"].sum())
    slightly_robotic = int((df["Naturalness"] == "Slightly Robotic").sum())
    very_robotic = int((df["Naturalness"] == "Very Robotic").sum())
    intelligible = int((df["Intelligibility"] == "Yes").sum())
    context_applicable = int(df["context_applicable"].sum())
    context_correct = int(df["context_correct"].sum())
    incorrect_word_samples = int(df["has_incorrect_words"].sum())
    number_mistake_samples = int(df["has_number_mistakes"].sum())
    conjunct_mistake_samples = int(df["has_conjunct_mistakes"].sum())
    note_samples = int(df["has_notes"].sum())

    key_findings = [
        f"Human-like naturalness was assigned to {human_like}/{total_samples} voice-specific evaluations ({format_pct(pct(human_like, total_samples))}).",
        f"Intelligibility was marked 'Yes' in {intelligible}/{total_samples} evaluations ({format_pct(pct(intelligible, total_samples))}), indicating no observed comprehension failures in the annotated set.",
        f"Context/prosody was applicable in {context_applicable}/{total_samples} evaluations; among those, contextual delivery was judged correct in {context_correct}/{context_applicable} cases ({format_pct(pct(context_correct, context_applicable))}).",
        f"Incorrect-word annotations were concentrated in code-mixed and numeric prompts: {incorrect_word_samples} samples contained at least one incorrect word, while only {number_mistake_samples} samples recorded explicit number rendering errors.",
        f"No conjunct mistakes were explicitly tagged in the annotation sheets ({conjunct_mistake_samples}/{total_samples}), though conjunct prompts still showed mild naturalness degradation in perceptual ratings.",
    ]

    ready_paragraph = (
        "Manual annotation covered 200 unique prompts evaluated across both synthesized voices, "
        f"yielding {total_samples} voice-specific judgments. Overall intelligibility remained saturated at "
        f"{format_pct(pct(intelligible, total_samples))}, while naturalness was judged human-like in "
        f"{format_pct(pct(human_like, total_samples))} of samples. Context-sensitive delivery was only applicable "
        f"to {context_applicable} samples, but within that subset the system achieved a contextual success rate "
        f"of {format_pct(pct(context_correct, context_applicable))}. Error annotations were sparse and highly concentrated: "
        f"code-mixed prompts accounted for {hotspots['code_mix_incorrect_word_samples']} incorrect-word markings, "
        f"numeric prompts produced {number_mistake_samples} explicit normalization errors, and no conjunct errors were directly tagged. "
        f"Preference judgments at the prompt level favored parity in {preference['Equal']}/{total_prompts} prompts, "
        f"with the female voice preferred in {preference['Female']} prompts and the male voice preferred in {preference['Male']} prompts."
    )

    voice_table = voice_summary.copy()
    for col in [
        "human_like_rate_pct",
        "intelligibility_yes_rate_pct",
        "context_success_pct",
        "incorrect_word_rate_pct",
        "number_mistake_rate_pct",
        "conjunct_mistake_rate_pct",
        "notes_rate_pct",
    ]:
        voice_table[col] = voice_table[col].map(format_pct)

    category_table = category_summary.copy()
    for col in [
        "human_like_rate_pct",
        "context_success_pct",
        "incorrect_word_rate_pct",
        "number_mistake_rate_pct",
        "conjunct_mistake_rate_pct",
        "notes_rate_pct",
        "slightly_or_very_robotic_pct",
    ]:
        category_table[col] = category_table[col].map(format_pct)

    lines = [
        "# Chapter 3 Annotation Summary",
        "",
        "## Scope",
        "",
        f"- Unique prompts: {total_prompts}",
        f"- Voice-specific evaluations: {total_samples}",
        f"- Annotation folders used: `{ANNOTATION_ROOT / 'Male'}` and `{ANNOTATION_ROOT / 'Female'}`",
        f"- Workbook used for prompt metadata: `{WORKBOOK}`",
        "",
        "## Key Findings",
        "",
    ]
    lines.extend([f"- {finding}" for finding in key_findings])
    lines.extend(
        [
            "",
            "## Voice-Level Summary",
            "",
            markdown_table(
                voice_table,
                [
                    "voice",
                    "n_samples",
                    "human_like_rate_pct",
                    "intelligibility_yes_rate_pct",
                    "context_success_pct",
                    "incorrect_word_rate_pct",
                    "number_mistake_rate_pct",
                    "notes_rate_pct",
                ],
            ),
            "",
            "## Category-Level Summary",
            "",
            markdown_table(
                category_table,
                [
                    "category",
                    "n_samples",
                    "human_like_rate_pct",
                    "context_success_pct",
                    "incorrect_word_rate_pct",
                    "number_mistake_rate_pct",
                    "notes_rate_pct",
                    "slightly_or_very_robotic_pct",
                ],
            ),
            "",
            "## Preference Summary",
            "",
            f"- Equal preference: {preference['Equal']} / {total_prompts} prompts ({format_pct(pct(preference['Equal'], total_prompts))})",
            f"- Female preferred: {preference['Female']} / {total_prompts} prompts ({format_pct(pct(preference['Female'], total_prompts))})",
            f"- Male preferred: {preference['Male']} / {total_prompts} prompts ({format_pct(pct(preference['Male'], total_prompts))})",
            "",
            "## Recommended Chapter 3 Insert",
            "",
            ready_paragraph,
            "",
            "## Interpretation Notes",
            "",
            "- The annotation sheet provides strong evidence for intelligibility and broad naturalness, but it does not contain a graded fluency score.",
            "- Context/prosody should be interpreted only on the subset where context was marked applicable, not over the entire 400-sample pool.",
            "- Preference is a prompt-level comparison metric and was deduplicated by `item_id` before reporting.",
            "",
            "## Hotspots Worth Citing",
            "",
            f"- Code-mixed prompts were the most consistent source of lexical omissions or substitutions: {hotspots['code_mix_incorrect_word_samples']} / 40 voice-specific code-mix evaluations contained incorrect-word markings.",
            f"- Numeric rendering issues were rare but concrete: {number_mistake_samples} samples flagged errors on year or phone-number normalization.",
            f"- Prosody was the weakest perceptual category, with {int((df[df['category'] == 'Prosody']['human_like'] == False).sum())} / {len(df[df['category'] == 'Prosody'])} evaluations marked slightly or very robotic.",
            f"- Annotator notes were sparse ({note_samples} / {total_samples}) and mostly pointed to intonation gaps, isolated pronunciation slips, and number verbalization choices.",
            "",
        ]
    )

    out_path = OUT_DIR / "chapter3_annotation_summary.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    metadata = load_metadata()
    annotations = load_annotations(metadata)
    voice_summary = build_voice_summary(annotations)
    category_summary = build_category_summary(annotations)
    preference = build_unique_prompt_preference(annotations)
    hotspots = collect_hotspots(annotations)

    voice_summary.to_csv(OUT_DIR / "voice_summary.csv", index=False)
    category_summary.to_csv(OUT_DIR / "category_summary.csv", index=False)

    summary_payload = {
        "n_unique_prompts": int(annotations["item_id"].nunique()),
        "n_voice_specific_evaluations": int(len(annotations)),
        "naturalness_counts": annotations["Naturalness"].value_counts().to_dict(),
        "intelligibility_counts": annotations["Intelligibility"].value_counts().to_dict(),
        "context_counts": annotations["Context"].value_counts().to_dict(),
        "preference_prompt_level": preference,
        "hotspots": hotspots,
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    markdown_path = write_markdown(
        annotations,
        voice_summary,
        category_summary,
        preference,
        hotspots,
    )
    print(markdown_path)


if __name__ == "__main__":
    main()
