# TTS Socket.IO API Audit Report
- Endpoint: `https://read.bangla.gov.bd:9395`
- SSL Verify: `False`
- Total sent: **49**
- Total received: **49**
- Missing responses: **0**
- Unexpected responses: **0**

## Integrity
- 2xx responses: **49**
- Non-2xx or missing status: **0**
- Schema failures: **28**
- Base64 failures: **0**
- WAV failures: **0**
- Word-duration mismatches (sanity): **4**

## Latency
- RTT p50: **9421 ms**
- RTT p95: **13814 ms**
- RTT max: **14327 ms**

## Robustness
- Burst drop rate: **None**
- Reconnect OK: **None**

## Voice Variance Summary
- See: `outputs/20260312_054958_2c9b971f/voice_summary.csv`

Interpretation: if the 4 voices are truly distinct, you should observe consistent differences in
duration/rms/peak distribution and (most importantly) audible timbre/prosody across `voice_tag`.
