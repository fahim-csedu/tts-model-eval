# TTS Socket.IO API Audit Report
- Endpoint: `https://read.bangla.gov.bd:9395`
- SSL Verify: `False`
- Total sent: **20**
- Total received: **20**
- Missing responses: **0**
- Unexpected responses: **0**

## Integrity
- 2xx responses: **20**
- Non-2xx or missing status: **0**
- Schema failures: **10**
- Base64 failures: **0**
- WAV failures: **0**
- Word-duration mismatches (sanity): **0**

## Latency
- RTT p50: **2042 ms**
- RTT p95: **3476 ms**
- RTT max: **4192 ms**

## Robustness
- Burst drop rate: **None**
- Reconnect OK: **None**

## Voice Variance Summary
- See: `outputs/20260222_112845_3e07fa57/voice_summary.csv`

Interpretation: if the 4 voices are truly distinct, you should observe consistent differences in
duration/rms/peak distribution and (most importantly) audible timbre/prosody across `voice_tag`.
