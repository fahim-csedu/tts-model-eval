# Chapter 3 Annotation Summary

## Scope

- Unique prompts: 200
- Voice-specific evaluations: 400
- Annotation folders used: `/Users/fahimarefin/Desktop/ict/TTS D3/tts-model-eval/model_eval/annotations/Male` and `/Users/fahimarefin/Desktop/ict/TTS D3/tts-model-eval/model_eval/annotations/Female`
- Workbook used for prompt metadata: `/Users/fahimarefin/Desktop/ict/TTS D3/tts-model-eval/model_eval/Model Evaluation Results.xlsx`

## Key Findings

- Human-like naturalness was assigned to 323/400 voice-specific evaluations (80.8%).
- Intelligibility was marked 'Yes' in 400/400 evaluations (100.0%), indicating no observed comprehension failures in the annotated set.
- Context/prosody was applicable in 38/400 evaluations; among those, contextual delivery was judged correct in 25/38 cases (65.8%).
- Incorrect-word annotations were concentrated in code-mixed and numeric prompts: 55 samples contained at least one incorrect word, while only 4 samples recorded explicit number rendering errors.
- No conjunct mistakes were explicitly tagged in the annotation sheets (0/400), though conjunct prompts still showed mild naturalness degradation in perceptual ratings.

## Voice-Level Summary

| voice | n_samples | human_like_rate_pct | intelligibility_yes_rate_pct | context_success_pct | incorrect_word_rate_pct | number_mistake_rate_pct | notes_rate_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Female | 200 | 78.0% | 100.0% | 55.6% | 14.0% | 1.0% | 5.5% |
| Male | 200 | 83.5% | 100.0% | 75.0% | 13.5% | 1.0% | 5.0% |

## Category-Level Summary

| category | n_samples | human_like_rate_pct | context_success_pct | incorrect_word_rate_pct | number_mistake_rate_pct | notes_rate_pct | slightly_or_very_robotic_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Code-Mix | 40 | 85.0% | 0.0% | 95.0% | 0.0% | 0.0% | 15.0% |
| Conjuncts | 60 | 83.3% | 50.0% | 0.0% | 0.0% | 6.7% | 16.7% |
| Long_Form | 40 | 100.0% | - | 5.0% | 0.0% | 0.0% | 0.0% |
| Named_Entity | 40 | 100.0% | - | 0.0% | 0.0% | 0.0% | 0.0% |
| Numbers | 60 | 80.0% | 66.7% | 16.7% | 6.7% | 6.7% | 20.0% |
| Phonetics | 60 | 63.3% | 33.3% | 5.0% | 0.0% | 11.7% | 36.7% |
| Prosody | 60 | 55.0% | 73.1% | 3.3% | 0.0% | 10.0% | 45.0% |
| Stress_Test | 40 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% |

## Preference Summary

- Equal preference: 106 / 200 prompts (53.0%)
- Female preferred: 55 / 200 prompts (27.5%)
- Male preferred: 39 / 200 prompts (19.5%)

## Recommended Chapter 3 Insert

Manual annotation covered 200 unique prompts evaluated across both synthesized voices, yielding 400 voice-specific judgments. Overall intelligibility remained saturated at 100.0%, while naturalness was judged human-like in 80.8% of samples. Context-sensitive delivery was only applicable to 38 samples, but within that subset the system achieved a contextual success rate of 65.8%. Error annotations were sparse and highly concentrated: code-mixed prompts accounted for 38 incorrect-word markings, numeric prompts produced 4 explicit normalization errors, and no conjunct errors were directly tagged. Preference judgments at the prompt level favored parity in 106/200 prompts, with the female voice preferred in 55 prompts and the male voice preferred in 39 prompts.

## Interpretation Notes

- The annotation sheet provides strong evidence for intelligibility and broad naturalness, but it does not contain a graded fluency score.
- Context/prosody should be interpreted only on the subset where context was marked applicable, not over the entire 400-sample pool.
- Preference is a prompt-level comparison metric and was deduplicated by `item_id` before reporting.

## Hotspots Worth Citing

- Code-mixed prompts were the most consistent source of lexical omissions or substitutions: 38 / 40 voice-specific code-mix evaluations contained incorrect-word markings.
- Numeric rendering issues were rare but concrete: 4 samples flagged errors on year or phone-number normalization.
- Prosody was the weakest perceptual category, with 27 / 60 evaluations marked slightly or very robotic.
- Annotator notes were sparse (21 / 400) and mostly pointed to intonation gaps, isolated pronunciation slips, and number verbalization choices.
