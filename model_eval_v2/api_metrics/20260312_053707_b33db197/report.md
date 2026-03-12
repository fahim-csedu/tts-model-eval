# TTS Socket.IO API Audit Report
- Endpoint: `https://read.bangla.gov.bd:9395`
- SSL Verify: `False`
- Total sent: **169**
- Total received: **169**
- Missing responses: **0**
- Unexpected responses: **0**

## Integrity
- 2xx responses: **169**
- Non-2xx or missing status: **0**
- Schema failures: **93**
- Base64 failures: **0**
- WAV failures: **0**
- Word-duration mismatches (sanity): **12**

## Latency
- RTT p50: **16622 ms**
- RTT p95: **31226 ms**
- RTT max: **33008 ms**

## Robustness
- Burst drop rate: **None**
- Reconnect OK: **None**

## Voice Variance Summary
- See: `outputs/20260312_053707_b33db197/voice_summary.csv`

Interpretation: if the 4 voices are truly distinct, you should observe consistent differences in
duration/rms/peak distribution and (most importantly) audible timbre/prosody across `voice_tag`.
