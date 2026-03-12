# TTS Socket.IO API Audit Report
- Endpoint: `https://read.bangla.gov.bd:9395`
- SSL Verify: `False`
- Total sent: **93**
- Total received: **93**
- Missing responses: **0**
- Unexpected responses: **0**

## Integrity
- 2xx responses: **93**
- Non-2xx or missing status: **0**
- Schema failures: **51**
- Base64 failures: **0**
- WAV failures: **0**
- Word-duration mismatches (sanity): **7**

## Latency
- RTT p50: **8672 ms**
- RTT p95: **17782 ms**
- RTT max: **18461 ms**

## Robustness
- Burst drop rate: **None**
- Reconnect OK: **None**

## Voice Variance Summary
- See: `outputs/20260312_054158_7dd01249/voice_summary.csv`

Interpretation: if the 4 voices are truly distinct, you should observe consistent differences in
duration/rms/peak distribution and (most importantly) audible timbre/prosody across `voice_tag`.
