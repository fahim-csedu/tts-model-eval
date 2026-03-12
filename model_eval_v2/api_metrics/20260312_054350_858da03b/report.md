# TTS Socket.IO API Audit Report
- Endpoint: `https://read.bangla.gov.bd:9395`
- SSL Verify: `False`
- Total sent: **89**
- Total received: **89**
- Missing responses: **0**
- Unexpected responses: **0**

## Integrity
- 2xx responses: **89**
- Non-2xx or missing status: **0**
- Schema failures: **49**
- Base64 failures: **0**
- WAV failures: **0**
- Word-duration mismatches (sanity): **6**

## Latency
- RTT p50: **8542 ms**
- RTT p95: **16567 ms**
- RTT max: **17587 ms**

## Robustness
- Burst drop rate: **None**
- Reconnect OK: **None**

## Voice Variance Summary
- See: `outputs/20260312_054350_858da03b/voice_summary.csv`

Interpretation: if the 4 voices are truly distinct, you should observe consistent differences in
duration/rms/peak distribution and (most importantly) audible timbre/prosody across `voice_tag`.
