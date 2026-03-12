# TTS Socket.IO API Audit Report
- Endpoint: `https://read.bangla.gov.bd:9395`
- SSL Verify: `False`
- Total sent: **1225**
- Total received: **1225**
- Missing responses: **0**
- Unexpected responses: **0**

## Integrity
- 2xx responses: **1225**
- Non-2xx or missing status: **0**
- Schema failures: **335**
- Base64 failures: **0**
- WAV failures: **0**
- Word-duration mismatches (sanity): **174**

## Latency
- RTT p50: **115578 ms**
- RTT p95: **313002 ms**
- RTT max: **345512 ms**

## Robustness
- Burst drop rate: **0.0**
- Reconnect OK: **True**

## Voice Variance Summary
- See: `outputs/20260312_052439_78db0a7b/voice_summary.csv`

Interpretation: if the 4 voices are truly distinct, you should observe consistent differences in
duration/rms/peak distribution and (most importantly) audible timbre/prosody across `voice_tag`.
