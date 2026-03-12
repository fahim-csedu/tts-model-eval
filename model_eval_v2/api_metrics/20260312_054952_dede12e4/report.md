# TTS Socket.IO API Audit Report
- Endpoint: `https://read.bangla.gov.bd:9395`
- SSL Verify: `False`
- Total sent: **51**
- Total received: **51**
- Missing responses: **0**
- Unexpected responses: **0**

## Integrity
- 2xx responses: **51**
- Non-2xx or missing status: **0**
- Schema failures: **29**
- Base64 failures: **0**
- WAV failures: **0**
- Word-duration mismatches (sanity): **3**

## Latency
- RTT p50: **6185 ms**
- RTT p95: **10550 ms**
- RTT max: **11044 ms**

## Robustness
- Burst drop rate: **None**
- Reconnect OK: **None**

## Voice Variance Summary
- See: `outputs/20260312_054952_dede12e4/voice_summary.csv`

Interpretation: if the 4 voices are truly distinct, you should observe consistent differences in
duration/rms/peak distribution and (most importantly) audible timbre/prosody across `voice_tag`.
