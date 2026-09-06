#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Google Cloud Text-to-Speech Narration & Subtitle Timecode Synthesizer.

Generates professional studio-quality voice audio tracks and synchronized subtitle
timecodes matching the demo's detected language (Japanese, English, German, French, etc.)
using Google Cloud Text-to-Speech API (Neural2 / Journey / Chirp voices).
Outputs a narration_manifest.json containing audio durations and subtitle segment slices.
"""

import argparse
import json
import os
import subprocess
import sys

# Language code to recommended neural voices (Google Cloud Chirp 3 HD foundation voices)
VOICE_MAPPING = {
    "ja-JP": {"voice": "ja-JP-Chirp3-HD-Aoede", "ssml_gender": "FEMALE", "speaking_rate": 1.05},
    "ja": {"voice": "ja-JP-Chirp3-HD-Aoede", "ssml_gender": "FEMALE", "speaking_rate": 1.05},
    "en-US": {"voice": "en-US-Chirp3-HD-Achernar", "ssml_gender": "FEMALE", "speaking_rate": 1.0},
    "en": {"voice": "en-US-Chirp3-HD-Achernar", "ssml_gender": "FEMALE", "speaking_rate": 1.0},
    "de-DE": {"voice": "de-DE-Chirp3-HD-Achernar", "ssml_gender": "FEMALE", "speaking_rate": 1.0},
    "fr-FR": {"voice": "fr-FR-Chirp3-HD-Achernar", "ssml_gender": "FEMALE", "speaking_rate": 1.0},
}


def estimate_speech_duration(text: str, lang: str) -> float:
    """Estimates speech duration in seconds for timing alignment and mock fallback."""
    if lang.startswith("ja"):
        # Average Japanese speech rate: ~5.0 characters per second
        clean_len = len(text.replace(" ", "").replace("\n", ""))
        return max(2.5, round(clean_len / 5.0, 2))
    else:
        # Average English/European speech rate: ~150 words per minute (2.5 words per sec)
        words = len(text.split())
        return max(2.5, round(words / 2.5, 2))


def generate_silent_audio(output_path: str, duration_sec: float):
    """Generates an empty silent MP3 audio track using ffmpeg for mock / fallback mode."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(duration_sec),
        "-q:a", "9",
        "-acodec", "libmp3lame",
        output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except Exception:
        # If ffmpeg is not available, create an empty file
        with open(output_path, "wb") as f:
            f.write(b"")


def synthesize_scene_audio(text: str, output_path: str, lang: str = "ja-JP", mock: bool = False, project: str = "") -> float:
    """Synthesizes speech for a single scene via Google Cloud TTS or fallback."""
    if mock:
        duration = estimate_speech_duration(text, lang)
        generate_silent_audio(output_path, duration)
        return duration

    try:
        from google.cloud import texttospeech
        from google.api_core.client_options import ClientOptions

        quota_project = (
            project
            or os.environ.get("GOOGLE_CLOUD_QUOTA_PROJECT")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
            or os.environ.get("PROJECT_ID")
        )
        if not quota_project:
            try:
                res = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True)
                lines = [l.strip() for l in res.stdout.splitlines() if l.strip() and not l.startswith("Your active configuration")]
                if lines:
                    quota_project = lines[0]
            except Exception:
                pass

        client_options = ClientOptions(quota_project_id=quota_project) if quota_project else None
        client = texttospeech.TextToSpeechClient(client_options=client_options)
        v_info = VOICE_MAPPING.get(lang, VOICE_MAPPING["ja-JP"])
        language_code = lang if "-" in lang else f"{lang}-{lang.upper()}"

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=v_info["voice"],
            ssml_gender=getattr(texttospeech.SsmlVoiceGender, v_info["ssml_gender"])
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=v_info.get("speaking_rate", 1.0)
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )

        with open(output_path, "wb") as out:
            out.write(response.audio_content)

        # Get exact duration via ffprobe if available
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", output_path]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return round(float(res.stdout.strip()), 2)
        return estimate_speech_duration(text, lang)

    except Exception as e:
        print(f"  ⚠️ Cloud TTS failed ({e}), falling back to simulated speech pacing.", file=sys.stderr)
        duration = estimate_speech_duration(text, lang)
        generate_silent_audio(output_path, duration)
        return duration


def split_subtitles(text: str, total_duration: float, lang: str) -> list:
    """Splits a narration text into timed subtitle segments for Remotion lower-thirds."""
    # Split by punctuation
    if lang.startswith("ja"):
        sentences = [s.strip() for s in text.replace("。", "。\n").replace("！", "！\n").split("\n") if s.strip()]
    else:
        sentences = [s.strip() for s in text.replace(".", ".\n").replace("!", "!\n").split("\n") if s.strip()]

    if not sentences:
        return [{"text": text, "start_sec": 0.0, "end_sec": total_duration}]

    total_chars = sum(len(s) for s in sentences)
    slices = []
    curr_time = 0.0

    for idx, s in enumerate(sentences):
        ratio = len(s) / max(1, total_chars)
        dur = round(total_duration * ratio, 2)
        end_time = round(curr_time + dur, 2)
        if idx == len(sentences) - 1:
            end_time = total_duration
        slices.append({
            "text": s,
            "start_sec": curr_time,
            "end_sec": end_time
        })
        curr_time = end_time

    return slices


def build_narration_script(company: str, role: str, lang: str) -> list:
    """Returns structured narration lines for the 3 key demo scenes."""
    if lang.startswith("ja"):
        return [
            {
                "scene_id": "intro",
                "title": f"{company} AI エージェント デモ",
                "text": f"本日は、{company}のために開発されたGemini Enterpriseの自律型エージェント「{role}」の実演をご紹介します。"
            },
            {
                "scene_id": "prompt_1",
                "title": "Scene 1: 初期対話と状況把握",
                "text": f"まずはエージェントの基本機能と現在のオペレーション状況を確認します。リアルタイムに挨拶カードと利用可能な推奨アクションが提示されます。"
            },
            {
                "scene_id": "prompt_3",
                "title": "Scene 2: 複合データ分析と不整合検知",
                "text": "続いて、BigQueryの注文履歴と外部サプライヤー台帳を突合し、データの不整合や配送遅延の異常値を自律的に検知・可視化します。"
            },
            {
                "scene_id": "prompt_4",
                "title": "Scene 3: 即時アクションとワークフロー承認",
                "text": "検知された課題に対し、是正アクションを即座に起票。確認カードからワンクリックで承認を実行し、基幹データベースをリアルタイムに更新します。"
            },
            {
                "scene_id": "outro",
                "title": "まとめ",
                "text": f"このように、{company}の業務オペレーションをGemini Enterpriseが強力に加速します。ご清聴ありがとうございました。"
            }
        ]
    else:
        return [
            {
                "scene_id": "intro",
                "title": f"{company} AI Agent Demo",
                "text": f"Welcome to this demonstration of {role}, an autonomous AI agent built on Gemini Enterprise for {company}."
            },
            {
                "scene_id": "prompt_1",
                "title": "Scene 1: Welcome & Overview",
                "text": "We start with a situational briefing. The agent introduces its operational capabilities with an interactive welcome card and quick action chips."
            },
            {
                "scene_id": "prompt_3",
                "title": "Scene 2: Cross-Source Anomaly Detection",
                "text": "Next, the agent queries BigQuery order tables and cross-references them against supplier audit ledgers to identify discrepancies."
            },
            {
                "scene_id": "prompt_4",
                "title": "Scene 3: Immediate Workflow Execution",
                "text": "To resolve the detected issue, the agent proposes an immediate correction. With a single click on the interactive card, the workflow is executed."
            },
            {
                "scene_id": "outro",
                "title": "Conclusion",
                "text": f"Gemini Enterprise empowers {company} to transform manual reviews into seamless autonomous operations. Thank you."
            }
        ]


def synthesize_all(args) -> dict:
    """Synthesizes audio tracks and subtitle manifests for all scenes."""
    os.makedirs(args.outdir, exist_ok=True)
    lang = args.lang or ("ja-JP" if os.environ.get("CURRENCY_SYMBOL") in ("¥", "円") else "en-US")
    company = args.company or os.environ.get("COMPANY_NAME", "Enterprise Demo")
    role = args.role or os.environ.get("DEMO_DISPLAY_NAME", "Operations Director")

    script_scenes = build_narration_script(company, role, lang)
    manifest_scenes = []
    total_audio_duration = 0.0

    print(f"🎙️ Synthesizing narration audio (Language: {lang}, Company: {company}, Role: {role})...")

    for idx, sc in enumerate(script_scenes):
        scene_id = sc["scene_id"]
        audio_filename = f"audio_{scene_id}.mp3"
        audio_path = os.path.join(args.outdir, audio_filename)

        print(f"  Generating voice track for {scene_id}...")
        dur = synthesize_scene_audio(sc["text"], audio_path, lang=lang, mock=args.mock, project=getattr(args, "project", ""))
        total_audio_duration += dur

        subtitles = split_subtitles(sc["text"], dur, lang=lang)

        manifest_scenes.append({
            "scene_id": scene_id,
            "title": sc["title"],
            "narration_text": sc["text"],
            "audio_file": audio_filename,
            "duration_sec": dur,
            "subtitles": subtitles
        })
        print(f"    Audio duration: {dur:.2f}s ({len(subtitles)} subtitle slices)")

    manifest_data = {
        "company": company,
        "role": role,
        "language": lang,
        "total_audio_duration_sec": round(total_audio_duration, 2),
        "scenes": manifest_scenes
    }

    manifest_path = os.path.join(args.outdir, "narration_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Narration synthesis complete! Saved to {manifest_path}")
    return manifest_data


def main():
    parser = argparse.ArgumentParser(description="Synthesize voice narration and subtitles for demo video.")
    parser.add_argument("--outdir", default="./output/narration", help="Output directory for audio and manifest")
    parser.add_argument("--company", default="", help="Company name")
    parser.add_argument("--role", default="", help="Agent role / display name")
    parser.add_argument("--lang", default="", help="Language code (e.g. ja-JP, en-US)")
    parser.add_argument("--project", default="", help="Google Cloud project ID for quota / billing")
    parser.add_argument("--mock", action="store_true", help="Simulate speech durations with silent audio (no Google Cloud TTS call)")
    args = parser.parse_args()

    synthesize_all(args)


if __name__ == "__main__":
    main()
