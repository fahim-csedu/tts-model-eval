#!/usr/bin/env python3
"""
tts_api_audit.py

Socket.IO TTS tester aligned to vendor spec:
- Endpoint: https://read.bangla.gov.bd:9395
- Client emits: 'text_transmit' with JSON payload fields:
    {text, model, gender, index, speaker}
- Server emits: 'result' with JSON response fields including:
    status_code, audio (base64), guid, index, word_durations (or word_duration)

Features:
- Saves decoded WAVs (validated) per request per voice
- Text prompts from:
    - --text-file (one prompt per line), or
    - --excel (reads sheets Male/Female; uses 'ItemID' and 'Text' columns), or
    - built-in defaults
- Extra checks:
    - response schema validation
    - base64 decode validation
    - WAV container integrity + metadata
    - word_durations sanity vs word count
    - latency stats (p50/p95/max)
    - burst/drop test
    - reconnect test
    - voice variance summaries (audio duration, RMS, peak)

Outputs under outputs/<run_id>/:
- results.jsonl
- results.csv
- summary.json
- report.md
- voice_summary.csv
- audio/<voice_tag>/...wav
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import statistics
import sys
import time
import uuid
import wave
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import socketio
import pandas as pd


# -----------------------------
# Helpers / validation
# -----------------------------

def now_ms() -> int:
    return int(time.time() * 1000)

def safe_int(x: Any) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None

def normalize_status_code(x: Any) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, str) and x.strip().isdigit():
        return int(x.strip())
    return None

def is_probably_wav(data: bytes) -> bool:
    return len(data) > 16 and data[0:4] == b"RIFF" and data[8:12] == b"WAVE"

def wav_metadata_and_stats(data: bytes) -> Dict[str, Any]:
    """
    Parse WAV metadata and compute simple signal stats (RMS, peak).
    Assumes PCM. If non-PCM, stats may fail gracefully.
    """
    import io
    info: Dict[str, Any] = {}
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            fr = wf.getframerate()
            nf = wf.getnframes()
            frames = wf.readframes(nf)

        info["nchannels"] = nch
        info["sampwidth"] = sw
        info["framerate"] = fr
        info["nframes"] = nf
        info["duration_sec"] = nf / float(fr or 1)

        # Basic PCM stats
        # Convert bytes → ints depending on sampwidth
        import struct
        if sw == 1:
            # unsigned 8-bit
            samples = list(frames)
            # center to signed
            samples = [s - 128 for s in samples]
        elif sw == 2:
            fmt = "<" + "h" * (len(frames) // 2)
            samples = list(struct.unpack(fmt, frames))
        elif sw == 4:
            fmt = "<" + "i" * (len(frames) // 4)
            samples = list(struct.unpack(fmt, frames))
        else:
            samples = []

        if samples:
            # If stereo, interleaved; compute over all samples
            peak = max(abs(s) for s in samples)
            rms = (sum((s * s) for s in samples) / float(len(samples))) ** 0.5
            info["peak"] = float(peak)
            info["rms"] = float(rms)
        else:
            info["peak"] = None
            info["rms"] = None

        info["ok"] = True
    except Exception as e:
        info["ok"] = False
        info["error"] = str(e)
    return info

def tokenize_words_bn(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    text = re.sub(r"\s+", " ", text)
    return text.split(" ")

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def safe_filename(s: str, max_len: int = 80) -> str:
    s = re.sub(r"[^\w\-\.\(\)]+", "_", s, flags=re.UNICODE).strip("_")
    return s[:max_len] if len(s) > max_len else s


# -----------------------------
# Data structures
# -----------------------------

@dataclass
class RequestCase:
    case_id: str
    index: int
    item_id: Optional[str]
    text: str
    model: str
    gender: str
    speaker: int
    voice_tag: str
    kind: str  # normal | negative | burst | reconnect

@dataclass
class ResponseCase:
    case_id: str
    index: Optional[int]
    received_ms: int
    status_code: Optional[int]
    guid: Optional[str]
    audio_present: bool
    audio_bytes_len: Optional[int]
    wav_ok: Optional[bool]
    wav_meta: Dict[str, Any]
    audio_path: Optional[str]
    word_durations_key: Optional[str]
    word_durations_len: Optional[int]
    word_count: int
    rtt_ms: Optional[int]
    errors: List[str]


# -----------------------------
# Socket.IO Audit Client
# -----------------------------

class TTSAuditClient:
    def __init__(
        self,
        endpoint: str,
        ssl_verify: Any,
        wait_timeout_sec: int,
        audio_root: Path,
        save_wavs: bool,
        overwrite_wavs: bool,
    ):
        self.endpoint = endpoint
        self.ssl_verify = ssl_verify
        self.wait_timeout_sec = wait_timeout_sec
        self.audio_root = audio_root
        self.save_wavs = save_wavs
        self.overwrite_wavs = overwrite_wavs

        self.sio = socketio.Client(
            ssl_verify=self.ssl_verify,
            reconnection=True,
            reconnection_attempts=5,
            reconnection_delay=1,
            reconnection_delay_max=5,
            logger=False,
            engineio_logger=False,
        )

        self.connected = False

        # Tracking
        self.sent: Dict[int, RequestCase] = {}
        self.sent_at_ms: Dict[int, int] = {}
        self.received: Dict[int, ResponseCase] = {}
        self.unexpected_responses: List[Dict[str, Any]] = []

        # bind events
        self.sio.on("connect", self._on_connect)
        self.sio.on("connect_error", self._on_connect_error)
        self.sio.on("disconnect", self._on_disconnect)
        self.sio.on("result", self._on_result)

    def _on_connect(self):
        self.connected = True
        print("[socket] connected")

    def _on_connect_error(self, data):
        self.connected = False
        print(f"[socket] connect_error: {data}")

    def _on_disconnect(self):
        self.connected = False
        print("[socket] disconnected")

    def _save_wav(self, req: RequestCase, wav_bytes: bytes) -> Optional[str]:
        if not self.save_wavs:
            return None
        voice_dir = self.audio_root / req.voice_tag
        ensure_dir(voice_dir)

        item_part = f"{req.item_id}_" if req.item_id else ""
        text_slug = safe_filename(req.text, 40)
        fname = f"{item_part}idx{req.index}_{req.voice_tag}_{req.kind}_{text_slug}.wav"
        fpath = voice_dir / fname

        if fpath.exists() and not self.overwrite_wavs:
            return str(fpath)

        fpath.write_bytes(wav_bytes)
        return str(fpath)

    def _on_result(self, data):
        received_time = now_ms()
        errors: List[str] = []

        if not isinstance(data, dict):
            self.unexpected_responses.append({"received_ms": received_time, "data": data})
            return

        idx = safe_int(data.get("index"))
        status_code = normalize_status_code(data.get("status_code"))
        guid = data.get("guid")

        audio_b64 = data.get("audio")
        audio_present = bool(audio_b64)

        # word duration ambiguity: accept either key
        wd_key = None
        wd_val = None
        if "word_durations" in data:
            wd_key = "word_durations"
            wd_val = data.get("word_durations")
        elif "word_duration" in data:
            wd_key = "word_duration"
            wd_val = data.get("word_duration")

        wd_len = None
        if wd_val is not None:
            if isinstance(wd_val, list):
                wd_len = len(wd_val)
            else:
                errors.append(f"{wd_key} not a list")

        # Match request
        if idx is None or idx not in self.sent:
            self.unexpected_responses.append({"received_ms": received_time, "data": data})
            return

        req = self.sent[idx]
        sent_ms = self.sent_at_ms.get(idx)
        rtt = (received_time - sent_ms) if sent_ms else None

        # Decode audio
        audio_bytes = None
        audio_len = None
        wav_ok = None
        wav_meta: Dict[str, Any] = {}
        audio_path = None

        if audio_present:
            try:
                audio_bytes = base64.b64decode(audio_b64, validate=True)
                audio_len = len(audio_bytes)
            except Exception as e:
                errors.append(f"base64_decode_failed: {e}")
        else:
            errors.append("missing_audio")

        # WAV validation + save
        if audio_bytes is not None:
            if not is_probably_wav(audio_bytes):
                errors.append("not_wav_header")
                wav_ok = False
                wav_meta = {"ok": False, "error": "RIFF/WAVE header missing"}
            else:
                wav_meta = wav_metadata_and_stats(audio_bytes)
                wav_ok = bool(wav_meta.get("ok"))
                if not wav_ok:
                    errors.append(f"wav_parse_failed: {wav_meta.get('error')}")
                else:
                    audio_path = self._save_wav(req, audio_bytes)

        # Schema checks
        if status_code is None:
            errors.append("missing_or_invalid_status_code")
        if guid is None:
            errors.append("missing_guid")
        if wd_key is None:
            errors.append("missing_word_durations_field")

        # Word-duration sanity (soft)
        wc = len(tokenize_words_bn(req.text))
        if wd_len is not None and wc > 0:
            if abs(wd_len - wc) > 2:
                errors.append(f"word_duration_length_mismatch: word_count={wc}, {wd_key}_len={wd_len}")

        resp = ResponseCase(
            case_id=req.case_id,
            index=idx,
            received_ms=received_time,
            status_code=status_code,
            guid=str(guid) if guid is not None else None,
            audio_present=audio_present,
            audio_bytes_len=audio_len,
            wav_ok=wav_ok,
            wav_meta=wav_meta,
            audio_path=audio_path,
            word_durations_key=wd_key,
            word_durations_len=wd_len,
            word_count=wc,
            rtt_ms=rtt,
            errors=errors,
        )
        self.received[idx] = resp

    def connect(self) -> bool:
        try:
            # Keep connect semantics identical to generate_eval_audio.py unless timeout is set.
            kwargs: Dict[str, Any] = {}
            if self.wait_timeout_sec and self.wait_timeout_sec > 0:
                kwargs["wait"] = True
                kwargs["wait_timeout"] = self.wait_timeout_sec
            self.sio.connect(self.endpoint, **kwargs)
            return self.connected

        except Exception as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                print("[socket] TLS verification failed. Re-run without --ssl-verify.")
            print(f"[socket] connect failed: {type(e).__name__}: {e}")
            return False

    def disconnect(self):
        try:
            if self.sio.connected:
                self.sio.disconnect()
        except Exception:
            pass

    def emit_case(self, req: RequestCase) -> None:
        payload = {
            "text": req.text,
            "model": req.model,
            "gender": req.gender,
            "index": req.index,
            "speaker": req.speaker,
        }
        self.sent[req.index] = req
        self.sent_at_ms[req.index] = now_ms()
        self.sio.emit("text_transmit", payload)

    def wait_for_all(self, indices: List[int], timeout_sec: int, label: str = "phase") -> None:
        total = len(indices)
        if total == 0:
            print(f"[progress] {label}: no requests to wait for")
            return

        print(f"[progress] {label}: waiting for responses 0/{total}")
        start = time.time()
        last_done = -1
        last_log = 0.0
        while True:
            done = sum(1 for i in indices if i in self.received)
            now = time.time()

            if done != last_done and ((now - last_log) >= 1.0 or done == total):
                print(f"[progress] {label}: responses {done}/{total}")
                last_done = done
                last_log = now

            if done >= len(indices):
                print(f"[progress] {label}: complete")
                return
            if (time.time() - start) > timeout_sec:
                print(f"[progress] {label}: timeout after {timeout_sec}s, received {done}/{total}")
                return
            time.sleep(0.05)


# -----------------------------
# Inputs: text file / excel / defaults
# -----------------------------

def default_test_prompts() -> List[Tuple[Optional[str], str]]:
    return [
        (None, "আমি বাংলায় কথা বলি।"),
        (None, "আজকের তারিখ ২০২৪-০৫-২৭।"),
        (None, "পরীক্ষা: সংখ্যা ১২৩৪৫ এবং শতাংশ ৫০%।"),
        (None, "বিশেষ চিহ্ন টেস্ট: @ # % & ( ) - _"),
        (None, "দীর্ঘ বাক্য টেস্ট: এটি একটি অপেক্ষাকৃত দীর্ঘ বাক্য যাতে একাধিক শব্দ রয়েছে এবং গতি, বিরামচিহ্ন ও সাবলীলতা পর্যবেক্ষণ করা যায়।"),
    ]

def read_texts_from_file(p: Path) -> List[Tuple[Optional[str], str]]:
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append((None, line))
    return out

def read_texts_from_excel(xlsx: Path, sheet: str) -> List[Tuple[Optional[str], str]]:
    df = pd.read_excel(xlsx, sheet_name=sheet)
    # Expect ItemID and Text columns (matches your workbook)
    if "Text" not in df.columns:
        raise ValueError(f"Excel sheet '{sheet}' missing required column 'Text'")
    item_col = "ItemID" if "ItemID" in df.columns else None

    out = []
    for _, row in df.iterrows():
        text = str(row["Text"]) if pd.notna(row["Text"]) else ""
        text = text.strip()
        if not text:
            continue
        item_id = str(row[item_col]).strip() if item_col and pd.notna(row[item_col]) else None
        out.append((item_id, text))
    return out

def cap_prompts(prompts: List[Tuple[Optional[str], str]], max_items: Optional[int]) -> List[Tuple[Optional[str], str]]:
    if max_items is None or max_items <= 0:
        return prompts
    return prompts[:max_items]


# -----------------------------
# Case generation / voices
# -----------------------------

def get_voice_matrix(mode: str, base_gender: str, base_speaker: int) -> List[Tuple[str, int]]:
    """
    voices:
      - single: just the passed gender/speaker
      - gender2: same speaker but both genders
      - speakers2: same gender but speaker 0 and 1
      - all4: both genders x speakers 0/1
    """
    if mode == "single":
        return [(base_gender, base_speaker)]
    if mode == "gender2":
        return [("male", base_speaker), ("female", base_speaker)]
    if mode == "speakers2":
        return [(base_gender, 0), (base_gender, 1)]
    if mode == "all4":
        return [("male", 0), ("male", 1), ("female", 0), ("female", 1)]
    raise ValueError(f"Unknown voices mode: {mode}")

def build_cases(
    prompts: List[Tuple[Optional[str], str]],
    model: str,
    voice_pairs: List[Tuple[str, int]],
    start_index: int,
    kind: str,
) -> List[RequestCase]:
    cases: List[RequestCase] = []
    idx = start_index
    for gender, speaker in voice_pairs:
        voice_tag = f"{gender}_spk{speaker}"
        for item_id, text in prompts:
            cases.append(
                RequestCase(
                    case_id=str(uuid.uuid4()),
                    index=idx,
                    item_id=item_id,
                    text=text,
                    model=model,
                    gender=gender,
                    speaker=speaker,
                    voice_tag=voice_tag,
                    kind=kind,
                )
            )
            idx += 1
    return cases


def emit_cases_with_progress(
    client: TTSAuditClient,
    cases: List[RequestCase],
    requests: List[RequestCase],
    sleep_sec: float,
    label: str,
    log_every: int = 25,
) -> None:
    total = len(cases)
    if total == 0:
        print(f"[progress] {label}: no requests to send")
        return
    print(f"[progress] {label}: sending requests 0/{total}")
    for i, c in enumerate(cases, start=1):
        client.emit_case(c)
        requests.append(c)
        if i % log_every == 0 or i == total:
            print(f"[progress] {label}: sent {i}/{total}")
        if sleep_sec > 0:
            time.sleep(sleep_sec)


# -----------------------------
# Reporting
# -----------------------------

def write_outputs(out_dir: Path, requests: List[RequestCase], responses: Dict[int, ResponseCase], unexpected: List[Dict[str, Any]]) -> Tuple[Path, Path, Path]:
    ensure_dir(out_dir)
    jsonl_path = out_dir / "results.jsonl"
    csv_path = out_dir / "results.csv"
    unexpected_path = out_dir / "unexpected_responses.json"

    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in requests:
            resp = responses.get(r.index)
            row = {
                "request": asdict(r),
                "response": asdict(resp) if resp else None,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "index", "case_id", "item_id", "kind", "voice_tag", "model", "gender", "speaker",
                "status_code", "guid", "rtt_ms",
                "audio_present", "audio_bytes_len", "audio_path",
                "wav_ok", "duration_sec", "rms", "peak",
                "word_durations_key", "word_durations_len", "word_count",
                "errors"
            ],
        )
        writer.writeheader()
        for r in requests:
            resp = responses.get(r.index)
            if not resp:
                writer.writerow({
                    "index": r.index, "case_id": r.case_id, "item_id": r.item_id, "kind": r.kind,
                    "voice_tag": r.voice_tag, "model": r.model, "gender": r.gender, "speaker": r.speaker,
                    "status_code": None, "guid": None, "rtt_ms": None,
                    "audio_present": False, "audio_bytes_len": None, "audio_path": None,
                    "wav_ok": None, "duration_sec": None, "rms": None, "peak": None,
                    "word_durations_key": None, "word_durations_len": None, "word_count": len(tokenize_words_bn(r.text)),
                    "errors": "no_response",
                })
            else:
                wm = resp.wav_meta or {}
                writer.writerow({
                    "index": r.index,
                    "case_id": resp.case_id,
                    "item_id": r.item_id,
                    "kind": r.kind,
                    "voice_tag": r.voice_tag,
                    "model": r.model,
                    "gender": r.gender,
                    "speaker": r.speaker,
                    "status_code": resp.status_code,
                    "guid": resp.guid,
                    "rtt_ms": resp.rtt_ms,
                    "audio_present": resp.audio_present,
                    "audio_bytes_len": resp.audio_bytes_len,
                    "audio_path": resp.audio_path,
                    "wav_ok": resp.wav_ok,
                    "duration_sec": wm.get("duration_sec"),
                    "rms": wm.get("rms"),
                    "peak": wm.get("peak"),
                    "word_durations_key": resp.word_durations_key,
                    "word_durations_len": resp.word_durations_len,
                    "word_count": resp.word_count,
                    "errors": ";".join(resp.errors) if resp.errors else "",
                })

    with unexpected_path.open("w", encoding="utf-8") as f:
        json.dump(unexpected, f, ensure_ascii=False, indent=2)

    report_path = out_dir / "report.md"
    return jsonl_path, csv_path, report_path

def compute_voice_summary(csv_path: Path, out_dir: Path) -> Path:
    df = pd.read_csv(csv_path)

    # Only successful-ish rows with WAV parsed OK
    ok = df[(df["wav_ok"] == True) & df["duration_sec"].notna()].copy()  # noqa: E712

    rows = []
    for voice_tag, g in ok.groupby("voice_tag"):
        rtts = [x for x in g["rtt_ms"].dropna().tolist() if x is not None]
        durs = g["duration_sec"].dropna().tolist()
        rmsv = g["rms"].dropna().tolist()
        peakv = g["peak"].dropna().tolist()

        def pct(v, p):
            if not v:
                return None
            v_sorted = sorted(v)
            k = int(round((p / 100.0) * (len(v_sorted) - 1)))
            return float(v_sorted[max(0, min(k, len(v_sorted)-1))])

        rows.append({
            "voice_tag": voice_tag,
            "n_ok": int(len(g)),
            "rtt_p50_ms": float(statistics.median(rtts)) if rtts else None,
            "rtt_p95_ms": pct(rtts, 95),
            "dur_p50_sec": float(statistics.median(durs)) if durs else None,
            "dur_p95_sec": pct(durs, 95),
            "rms_p50": float(statistics.median(rmsv)) if rmsv else None,
            "peak_p50": float(statistics.median(peakv)) if peakv else None,
        })

    if rows:
        vdf = pd.DataFrame(rows).sort_values("voice_tag")
    else:
        vdf = pd.DataFrame(columns=[
            "voice_tag",
            "n_ok",
            "rtt_p50_ms",
            "rtt_p95_ms",
            "dur_p50_sec",
            "dur_p95_sec",
            "rms_p50",
            "peak_p50",
        ])
    out_path = out_dir / "voice_summary.csv"
    vdf.to_csv(out_path, index=False)
    return out_path

def compute_summary_json(out_dir: Path, requests: List[RequestCase], client: TTSAuditClient, csv_path: Path, reconnect_ok: Optional[bool], burst_indices: List[int]) -> Path:
    total_sent = len(requests)
    total_received = len(client.received)
    missing = total_sent - total_received

    schema_fail = 0
    base64_fail = 0
    wav_fail = 0
    wd_mismatch = 0
    success_2xx = 0
    non_2xx = 0
    rtts = []

    for resp in client.received.values():
        if resp.status_code is not None and 200 <= resp.status_code < 300:
            success_2xx += 1
        else:
            non_2xx += 1

        if any(e in ("missing_or_invalid_status_code", "missing_guid", "missing_word_durations_field") for e in resp.errors):
            schema_fail += 1
        if any(e.startswith("base64_decode_failed") for e in resp.errors):
            base64_fail += 1
        if any(e.startswith("wav_parse_failed") or e == "not_wav_header" for e in resp.errors):
            wav_fail += 1
        if any(e.startswith("word_duration_length_mismatch") for e in resp.errors):
            wd_mismatch += 1
        if resp.rtt_ms is not None:
            rtts.append(resp.rtt_ms)

    def pct(v, p):
        if not v:
            return None
        v_sorted = sorted(v)
        k = int(round((p / 100.0) * (len(v_sorted) - 1)))
        return int(v_sorted[max(0, min(k, len(v_sorted)-1))])

    rtt_p50 = int(statistics.median(rtts)) if rtts else None
    rtt_p95 = pct(rtts, 95)
    rtt_max = max(rtts) if rtts else None

    burst_drop_rate = None
    if burst_indices:
        got = sum(1 for i in burst_indices if i in client.received)
        burst_drop_rate = 1.0 - (got / float(len(burst_indices)))

    summary = {
        "endpoint": client.endpoint,
        "ssl_verify": client.ssl_verify,
        "total_sent": total_sent,
        "total_received": total_received,
        "missing_responses": missing,
        "unexpected_responses": len(client.unexpected_responses),
        "success_2xx": success_2xx,
        "non_2xx_or_missing_status": non_2xx,
        "schema_failures": schema_fail,
        "base64_failures": base64_fail,
        "wav_failures": wav_fail,
        "word_duration_mismatches": wd_mismatch,
        "rtt_p50_ms": rtt_p50,
        "rtt_p95_ms": rtt_p95,
        "rtt_max_ms": rtt_max,
        "burst_drop_rate": burst_drop_rate,
        "reconnect_ok": reconnect_ok,
        "results_csv": str(csv_path),
    }

    out_path = out_dir / "summary.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path

def write_markdown_report(out_dir: Path, summary_json: Path, voice_summary: Path) -> Path:
    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    md = []
    md.append("# TTS Socket.IO API Audit Report\n")
    md.append(f"- Endpoint: `{summary['endpoint']}`\n")
    md.append(f"- SSL Verify: `{summary['ssl_verify']}`\n")
    md.append(f"- Total sent: **{summary['total_sent']}**\n")
    md.append(f"- Total received: **{summary['total_received']}**\n")
    md.append(f"- Missing responses: **{summary['missing_responses']}**\n")
    md.append(f"- Unexpected responses: **{summary['unexpected_responses']}**\n\n")

    md.append("## Integrity\n")
    md.append(f"- 2xx responses: **{summary['success_2xx']}**\n")
    md.append(f"- Non-2xx or missing status: **{summary['non_2xx_or_missing_status']}**\n")
    md.append(f"- Schema failures: **{summary['schema_failures']}**\n")
    md.append(f"- Base64 failures: **{summary['base64_failures']}**\n")
    md.append(f"- WAV failures: **{summary['wav_failures']}**\n")
    md.append(f"- Word-duration mismatches (sanity): **{summary['word_duration_mismatches']}**\n\n")

    md.append("## Latency\n")
    md.append(f"- RTT p50: **{summary['rtt_p50_ms']} ms**\n")
    md.append(f"- RTT p95: **{summary['rtt_p95_ms']} ms**\n")
    md.append(f"- RTT max: **{summary['rtt_max_ms']} ms**\n\n")

    md.append("## Robustness\n")
    md.append(f"- Burst drop rate: **{summary['burst_drop_rate']}**\n")
    md.append(f"- Reconnect OK: **{summary['reconnect_ok']}**\n\n")

    md.append("## Voice Variance Summary\n")
    md.append(f"- See: `{voice_summary}`\n\n")
    md.append("Interpretation: if the 4 voices are truly distinct, you should observe consistent differences in\n")
    md.append("duration/rms/peak distribution and (most importantly) audible timbre/prosody across `voice_tag`.\n")

    out_path = out_dir / "report.md"
    out_path.write_text("".join(md), encoding="utf-8")
    return out_path


# -----------------------------
# Negative / burst / reconnect tests
# -----------------------------

def run_negative_tests(client: TTSAuditClient, base_index: int, model: str) -> List[RequestCase]:
    bad = []
    # keep required keys, only invalid values
    bad.append(RequestCase(str(uuid.uuid4()), base_index, None, "নেগেটিভ টেস্ট", model, "robot", 0, "neg_robotgender", "negative"))
    bad.append(RequestCase(str(uuid.uuid4()), base_index + 1, None, "নেগেটিভ টেস্ট", model, "male", 99, "neg_speaker99", "negative"))
    bad.append(RequestCase(str(uuid.uuid4()), base_index + 2, None, "", model, "male", 0, "neg_emptytext", "negative"))
    bad.append(RequestCase(str(uuid.uuid4()), base_index + 3, None, "নেগেটিভ টেস্ট", "unknown_model", "male", 0, "neg_badmodel", "negative"))

    for c in bad:
        client.emit_case(c)
    return bad

def reconnect_test(client: TTSAuditClient, index: int, model: str, gender: str, speaker: int) -> Tuple[bool, List[RequestCase]]:
    cases = []
    try:
        client.disconnect()
        time.sleep(1.0)
        ok = client.connect()
        c = RequestCase(str(uuid.uuid4()), index, None, "রিকানেক্ট টেস্ট: সংযোগ পুনঃস্থাপন", model, gender, speaker, f"{gender}_spk{speaker}", "reconnect")
        cases.append(c)
        if ok:
            client.emit_case(c)
            return True, cases
        return False, cases
    except Exception:
        return False, cases


# -----------------------------
# Main
# -----------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="https://read.bangla.gov.bd:9395")
    ap.add_argument("--ssl-verify", action="store_true", default=False, help="Enable SSL verification.")
    ap.add_argument("--model", default="vits")

    ap.add_argument("--gender", default="female", choices=["male", "female"], help="Base gender for voices mode.")
    ap.add_argument("--speaker", type=int, default=0, help="Base speaker for voices mode.")
    ap.add_argument("--voices", default="single", choices=["single", "gender2", "speakers2", "all4"],
                    help="Which voice matrix to test: single / gender2 / speakers2 / all4.")

    ap.add_argument("--text-file", type=str, default=None)
    ap.add_argument("--excel", type=str, default=None, help="Excel file path. Expects sheets 'Male' and 'Female' with columns ItemID, Text.")
    ap.add_argument("--excel-sheet", type=str, default=None, help="If set, only use this sheet (e.g., Male). Otherwise uses both (Male+Female).")
    ap.add_argument("--max-items", type=int, default=None, help="Cap prompts per source/sheet for quick sampling (e.g., 20).")

    ap.add_argument("--out-dir", type=str, default="outputs")
    ap.add_argument("--timeout-sec", type=int, default=90)

    ap.add_argument("--burst-count", type=int, default=20)
    ap.add_argument("--burst-interval-ms", type=int, default=10)
    ap.add_argument("--skip-negative-tests", action="store_true", default=False)
    ap.add_argument("--skip-burst-test", action="store_true", default=False)
    ap.add_argument("--skip-reconnect-test", action="store_true", default=False)

    ap.add_argument("--save-wavs", action="store_true", default=True)
    ap.add_argument("--no-save-wavs", action="store_false", dest="save_wavs", help="Disable saving decoded WAV files.")
    ap.add_argument("--overwrite-wavs", action="store_true", default=False)

    args = ap.parse_args()

    run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    out_dir = Path(args.out_dir) / run_id
    ensure_dir(out_dir)
    audio_root = out_dir / "audio"
    ensure_dir(audio_root)

    client = TTSAuditClient(
        endpoint=args.endpoint,
        ssl_verify=args.ssl_verify,
        wait_timeout_sec=args.timeout_sec,
        audio_root=audio_root,
        save_wavs=args.save_wavs,
        overwrite_wavs=args.overwrite_wavs,
    )

    if not client.connect():
        print("ERROR: Could not connect to endpoint.")
        sys.exit(2)

    requests: List[RequestCase] = []
    next_index = 0

    # Build prompts
    prompts_default = default_test_prompts()

    if args.excel:
        xlsx = Path(args.excel)
        sheets = [args.excel_sheet] if args.excel_sheet else ["Male", "Female"]
        excel_prompts_by_sheet: Dict[str, List[Tuple[Optional[str], str]]] = {}
        for sh in sheets:
            excel_prompts_by_sheet[sh] = cap_prompts(read_texts_from_excel(xlsx, sh), args.max_items)

        # For Excel: if using both sheets, we bind Male sheet prompts to male, Female sheet prompts to female.
        # If voices=all4, we still run all 4 voices for BOTH sheets so you can compare voice differences on same prompts.
        voice_pairs = get_voice_matrix(args.voices, args.gender, args.speaker)

        # Phase A: normal tests
        for sh, prompts in excel_prompts_by_sheet.items():
            # If voices mode is not all4 and you want strict gender alignment to sheet:
            # - if sh==Male: use male-only voice pairs; if sh==Female: use female-only
            # We'll do gender-binding unless voices=all4 (explicitly wants all).
            if args.voices == "all4":
                vp = voice_pairs
            else:
                sheet_gender = "male" if sh.lower().strip() == "male" else "female"
                # preserve speaker logic per voices mode:
                if args.voices == "single":
                    vp = [(sheet_gender, args.speaker)]
                elif args.voices == "speakers2":
                    vp = [(sheet_gender, 0), (sheet_gender, 1)]
                elif args.voices == "gender2":
                    # gender2 doesn't make sense when sheet is already gendered; treat as all for both genders:
                    vp = [("male", args.speaker), ("female", args.speaker)]
                else:
                    vp = voice_pairs

            normal_cases = build_cases(prompts, args.model, vp, next_index, "normal")
            next_index += len(normal_cases)
            phase_label = f"normal/{sh}"
            emit_cases_with_progress(client, normal_cases, requests, sleep_sec=0.01, label=phase_label)
            client.wait_for_all([c.index for c in normal_cases], timeout_sec=args.timeout_sec, label=phase_label)

    elif args.text_file:
        prompts = read_texts_from_file(Path(args.text_file))
        if not prompts:
            prompts = prompts_default
        prompts = cap_prompts(prompts, args.max_items)

        voice_pairs = get_voice_matrix(args.voices, args.gender, args.speaker)
        normal_cases = build_cases(prompts, args.model, voice_pairs, next_index, "normal")
        next_index += len(normal_cases)
        phase_label = "normal/text-file"
        emit_cases_with_progress(client, normal_cases, requests, sleep_sec=0.01, label=phase_label)
        client.wait_for_all([c.index for c in normal_cases], timeout_sec=args.timeout_sec, label=phase_label)

    else:
        prompts = prompts_default
        prompts = cap_prompts(prompts, args.max_items)
        voice_pairs = get_voice_matrix(args.voices, args.gender, args.speaker)

        normal_cases = build_cases(prompts, args.model, voice_pairs, next_index, "normal")
        next_index += len(normal_cases)
        phase_label = "normal/default-prompts"
        emit_cases_with_progress(client, normal_cases, requests, sleep_sec=0.01, label=phase_label)
        client.wait_for_all([c.index for c in normal_cases], timeout_sec=args.timeout_sec, label=phase_label)

    # Phase B: negative tests (one set)
    if args.skip_negative_tests:
        print("[progress] negative: skipped")
        neg_cases = []
    else:
        neg_cases = run_negative_tests(client, base_index=next_index, model=args.model)
        requests.extend(neg_cases)
        next_index += len(neg_cases)
        client.wait_for_all([c.index for c in neg_cases], timeout_sec=args.timeout_sec, label="negative")

    # Phase C: burst test (uses base gender/speaker)
    burst_indices = []
    if args.skip_burst_test:
        print("[progress] burst: skipped")
    else:
        burst_voice = (args.gender, args.speaker)
        burst_tag = f"{burst_voice[0]}_spk{burst_voice[1]}"
        burst_text = "বার্স্ট টেস্ট: দ্রুত একাধিক অনুরোধ পাঠানো হচ্ছে।"
        for i in range(args.burst_count):
            c = RequestCase(
                case_id=str(uuid.uuid4()),
                index=next_index,
                item_id=None,
                text=burst_text,
                model=args.model,
                gender=burst_voice[0],
                speaker=burst_voice[1],
                voice_tag=burst_tag,
                kind="burst",
            )
            next_index += 1
            burst_indices.append(c.index)
            client.emit_case(c)
            requests.append(c)
            if (i + 1) % 25 == 0 or (i + 1) == args.burst_count:
                print(f"[progress] burst: sent {i + 1}/{args.burst_count}")
            time.sleep(max(args.burst_interval_ms, 0) / 1000.0)
        client.wait_for_all(burst_indices, timeout_sec=args.timeout_sec, label="burst")

    # Phase D: reconnect test (base gender/speaker)
    if args.skip_reconnect_test:
        print("[progress] reconnect: skipped")
        reconnect_ok, reconnect_cases = None, []
    else:
        reconnect_ok, reconnect_cases = reconnect_test(client, index=next_index, model=args.model, gender=args.gender, speaker=args.speaker)
        requests.extend(reconnect_cases)
        if reconnect_cases:
            client.wait_for_all([c.index for c in reconnect_cases], timeout_sec=args.timeout_sec, label="reconnect")

    client.disconnect()

    # Write outputs
    jsonl_path, csv_path, _ = write_outputs(out_dir, requests, client.received, client.unexpected_responses)
    voice_summary_path = compute_voice_summary(csv_path, out_dir)
    summary_json = compute_summary_json(out_dir, requests, client, csv_path, reconnect_ok, burst_indices)
    report_md = write_markdown_report(out_dir, summary_json, voice_summary_path)

    print("\nDONE")
    print(f"- Audio dir:     {audio_root}")
    print(f"- Results CSV:   {csv_path}")
    print(f"- Results JSONL: {jsonl_path}")
    print(f"- Summary JSON:  {summary_json}")
    print(f"- Voice CSV:     {voice_summary_path}")
    print(f"- Report MD:     {report_md}")


if __name__ == "__main__":
    main()
