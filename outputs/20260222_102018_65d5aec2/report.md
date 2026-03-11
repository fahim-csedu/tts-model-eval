# TTS Socket.IO API Audit Report
- Endpoint: `https://read.bangla.gov.bd:9395`
- SSL Verify: `False`
- Total sent: **1625**
- Total received: **1006**
- Missing responses: **619**
- Unexpected responses: **0**

## Integrity
- 2xx responses: **1006**
- Non-2xx or missing status: **0**
- Schema failures: **0**
- Base64 failures: **0**
- WAV failures: **0**
- Word-duration mismatches (sanity): **25**

## Latency
- RTT p50: **184189 ms**
- RTT p95: **276566 ms**
- RTT max: **295796 ms**

## Robustness
- Burst drop rate: **1.0**
- Reconnect OK: **True**

## Voice Variance Summary
- See: `outputs/20260222_102018_65d5aec2/voice_summary.csv`

Interpretation: if the 4 voices are truly distinct, you should observe consistent differences in
duration/rms/peak distribution and (most importantly) audible timbre/prosody across `voice_tag`.
