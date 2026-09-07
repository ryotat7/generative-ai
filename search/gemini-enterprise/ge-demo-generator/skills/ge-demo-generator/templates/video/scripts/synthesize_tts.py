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


def build_narration_script(company: str, role: str, lang: str, prompts: list = None) -> list:
    """Returns structured narration lines for demo scenes."""
    is_ja = lang.startswith("ja")
    num_prompts = len(prompts) if prompts else 7

    agenda_text_ja = (
        f"本日のデモでは、製造オペレーションを変革する全{num_prompts}つの重要ワークフローをご紹介します。"
        f"初期対話からデータ分析、即時承認、根本原因究明、生産シミュレーション、日次サマリーまで順を追って実演します。"
        if num_prompts >= 7 else
        f"本日のデモでは、主要な全{num_prompts}つの重要ワークフローをご紹介します。"
        f"初期対話からデータ分析、即時承認、そして日次サマリーまで順を追って実演します。"
    )
    agenda_text_en = (
        f"Today's demonstration covers {num_prompts} core operational workflows for enterprise operations. "
        f"We will walk through situational briefing, catalog discovery, anomaly detection, immediate action approval, root cause analysis, simulation, and daily handover."
        if num_prompts >= 7 else
        f"Today's demonstration covers {num_prompts} core operational workflows. "
        f"We will walk through situational briefing, catalog discovery, anomaly detection, immediate action approval, and daily handover."
    )

    scenes = [
        {
            "scene_id": "intro",
            "title": f"{company} AI エージェント デモ" if is_ja else f"{company} AI Agent Demo",
            "text": f"本日は、{company}のために開発されたGemini Enterpriseの自律型エージェント「{role}」の実演をご紹介します。" if is_ja else f"Welcome to this demonstration of {role}, an autonomous AI agent built on Gemini Enterprise for {company}."
        },
        {
            "scene_id": "agenda",
            "title": "実演デモシナリオ一覧" if is_ja else "Walkthrough Agenda",
            "text": agenda_text_ja if is_ja else agenda_text_en
        }
    ]

    # Pre-crafted high-fidelity narrations for the 7 core enterprise scenarios (Lead-in, Thinking, Response & Business Impact)
    script_templates_ja = {
        1: (
            "Scene 1: 初期対話と状況把握",
            "それでは、プラントの初期対話と状況把握の実演を行います。",
            "エージェントが基幹システムと各ラインのシフトログを横断検索し、優先アラートを抽出しています。",
            "リアルタイムにパーソナライズされた挨拶カードと優先タスクが提示され、各ラインの稼働状態や重要アラートが一目で把握できます。朝のダッシュボード巡回やメール確認の工数をゼロにし、即座に重要課題の意思決定に着手できます。"
        ),
        2: (
            "Scene 2: メタデータと製品カタログ探索",
            "続いて、全自動組み立てセルの設備仕様と稼働ステータスの照会を行います。",
            "エージェントが設備マスタとIoTゲートウェイを照合し、各セルの詳細稼働パラメータを収集しています。",
            "生成された一覧表には、セルごとのサイクルタイム、油圧圧力、メンテナンス予定日が網羅的に整理されています。各工場への個別確認を不要にし、設備の健全性とボトルネックを秒速で可視化します。"
        ),
        3: (
            "Scene 3: 複合データ分析と不整合検知",
            "次に、サプライヤーの納品実績と製造オーダーを突合し、部品欠品や納期の不整合を検知します。",
            "エージェントがBigQuery上の納品履歴とERPの生産スケジュールを自律突合し、納品遅延の影響を分析しています。",
            "分析結果では、Apex社からのタービンブレードに5日間の遅延が発生し、ライン停止の重大リスクがあることが特定されました。複数データソースの高度なクロス分析を自然言語で完了し、サプライチェーンの寸断を未然に防ぎます。"
        ),
        4: (
            "Scene 4: 即時アクションとワークフロー承認",
            "それでは、タービンラインの欠品を解消するための緊急在庫移管プランを策定し、承認指示書を起票します。",
            "エージェントが近隣倉庫の安全在庫と輸送リードタイムを計算し、ERP移管申請データを自動生成しています。",
            "画面にはオースティン倉庫から40個を緊急転送するプランと、ワンクリックで実行できる承認カードが表示されます。承認ボタンを押すだけでERP台帳が即座に更新され、部門間の調整工数を95％削減して即時対応を可能にします。"
        ),
        5: (
            "Scene 5: 根本原因分析と品質検査",
            "続いて、センサーの振動テレメトリと不良ログを解析し、鋳造異常の根本原因を究明します。",
            "エージェントが高周波振動波形と加熱バッチ履歴を統計解析し、異常振動の発生パターンを特定しています。",
            "詳細レポートにより、第3サイクルの高調波振動が油圧ダンパーのキャリブレーション不良に起因していることが判明しました。熟練技術者の勘に頼っていた品質調査をAIが自動化し、不良品の流出と手戻りを確実に根絶します。"
        ),
        6: (
            "Scene 6: 生産計画シミュレーションと予測的配分",
            "次に、現在の供給制約下における翌日のラインスループットをシミュレーションし、最適なスケジュールを再配分します。",
            "エージェントが代替ラインの設備能力と部材納期を考慮し、最適な負荷分散シナリオを計算しています。",
            "シミュレーション結果として、第2セルへの工程シフトによりスループットを12％改善し、納期を順守する最適配分案が提示されました。突発的な供給変動に対しても、納期を厳守する最適な生産体制を即座に再構築できます。"
        ),
        7: (
            "Scene 7: 業務サマリーと推奨事項",
            "最後に、本日の対応実績サマリーと明日に向けた発注推奨事項を作成します。",
            "エージェントが本日の緊急移管実績、設備メンテナンスログ、明日の発注優先度を統括レポートに集約しています。",
            "出力されたエグゼクティブサマリーには、本日の対処結果と明朝発注すべきサプライヤー推奨数量が整然と構造化されています。業務の引き継ぎ漏れを根絶し、属人化を排除した継続的なオペレーションエクセレンスを確立します。"
        ),
    }

    script_templates_en = {
        1: (
            "Scene 1: Welcome & Situational Briefing",
            "Now, let's begin with our situational operational briefing by querying current assembly alerts.",
            "While the agent queries active line status and cross-references shift logs across manufacturing plants, it isolates critical equipment warnings.",
            "The agent returns a structured welcome briefing with priority operational alerts, highlighting turbine cell throughput and pending material handovers. This completely eliminates morning dashboard hopping, providing plant leadership with immediate situational clarity."
        ),
        2: (
            "Scene 2: Metadata & Catalog Discovery",
            "Next, let's inspect component specifications and operational status across all automated assembly cells.",
            "The agent scans the enterprise asset registry, correlating cell telemetry, operating parameters, and scheduled maintenance intervals.",
            "A comprehensive equipment specifications table is generated, detailing cycle times, hydraulic pressure thresholds, and active health metrics for cells one through four. Plant managers gain instant visibility into machine health across facilities without manual database queries or engineering escalations."
        ),
        3: (
            "Scene 3: Cross-Source Anomaly Detection",
            "We now proceed to cross-reference recent supplier shipments against active production orders to detect component shortages.",
            "The agent autonomously joins BigQuery supplier dispatch ledgers with ERP production schedules to uncover shipment variances.",
            "The resulting analysis table isolates a critical five-day delay on titanium turbine blades from Apex Aerospace, pinpointing an impending line stoppage. Autonomous cross-source reconciliation surfaces supply chain vulnerabilities before they cascade into plant downtime."
        ),
        4: (
            "Scene 4: Immediate Workflow Execution",
            "Now, let's formulate an emergency component transfer plan to resolve the turbine line shortage and prepare the authorization.",
            "The agent evaluates safety stock across secondary warehouses, calculates transit lead times, and prepares a formal ERP transfer order.",
            "It presents an emergency transfer plan reallocating forty units from the Austin depot, complete with an interactive one-click authorization card. Clicking the approval executes the transfer instantly in ERP, slashing inter-facility logistics coordination from hours to seconds."
        ),
        5: (
            "Scene 5: Root Cause Analysis & Quality Inspection",
            "Next, let's perform root cause analysis on sensor vibration telemetry and defect logs to investigate recent casting anomalies.",
            "The agent performs deep statistical correlation between high-frequency vibration spikes, furnace temperatures, and raw material heat batches.",
            "The diagnostic report pinpoints high vibration harmonics during casting cycle three, isolating an uncalibrated hydraulic dampener. Predictive vibration analytics prevents defective castings from reaching downstream assembly, safeguarding product quality and warranty margins."
        ),
        6: (
            "Scene 6: Predictive Planning & Line Simulation",
            "Moving to predictive planning, let's simulate tomorrow's line throughput under current supply constraints and rebalance the schedule.",
            "The agent models machine capacity across alternative cell routings, factoring in operator availability and component lead times.",
            "The simulation projects a twelve percent throughput uplift by rerouting sub-assemblies to Cell Two, maintaining customer delivery commitments. Dynamic production rebalancing empowers operations teams to absorb supply shocks without compromising schedule integrity."
        ),
        7: (
            "Scene 7: Operational Summary & Recommendations",
            "Finally, let's generate the executive end-of-day operations summary, capturing today's reallocations and tomorrow's procurement priorities.",
            "The agent synthesizes today's emergency transfer records, defect resolutions, and line balancing adjustments into an executive handover.",
            "The resulting executive report summarizes resolved alerts, confirms forty diverted turbine blades, and outlines high-priority supplier purchase orders. This guarantees seamless shift handovers, prevents operational blind spots, and establishes institutional excellence across all manufacturing operations."
        ),
    }

    prompts_to_iterate = prompts if prompts else [f"Prompt {i}" for i in range(1, 8)]
    for idx, p in enumerate(prompts_to_iterate):
        s_num = idx + 1
        if is_ja:
            if s_num in script_templates_ja:
                title, lead_text, think_text, resp_text = script_templates_ja[s_num]
            else:
                title = f"Scene {s_num}: デモシナリオ {s_num}"
                lead_text = f"それでは、続いてのデモシナリオの実演に移ります。"
                think_text = f"エージェントが基幹データソースを照会し、要求されたワークフローを自律的に推論しています。"
                resp_text = f"画面に構造化された分析結果が表示され、多角的な知見が整理されます。これにより、高度なエンタープライズ業務を迅速かつ確実に遂行できます。"
        else:
            if s_num in script_templates_en:
                title, lead_text, think_text, resp_text = script_templates_en[s_num]
            else:
                title = f"Scene {s_num}: Demonstration Scenario {s_num}"
                lead_text = f"Now, let's proceed to demonstration scenario {s_num}."
                think_text = f"The agent queries underlying enterprise data stores and synthesizes the required workflow actions."
                resp_text = f"As the structured results appear, the agent consolidates multi-source metrics into clear recommendations. This accelerates complex operational workflows while maintaining enterprise data governance."

        scenes.append({
            "scene_id": f"prompt_{s_num}",
            "title": title,
            "lead_text": lead_text,
            "think_text": think_text,
            "resp_text": resp_text,
            "text": f"{lead_text} {think_text} {resp_text}".strip()
        })

    scenes.append({
        "scene_id": "outro",
        "title": "まとめ" if is_ja else "Conclusion",
        "text": f"このように、{company}の業務オペレーションをGemini Enterpriseが強力に加速します。ご清聴ありがとうございました。" if is_ja else f"Gemini Enterprise empowers {company} to transform manual reviews into seamless autonomous operations. Thank you."
    })
    return scenes


def synthesize_all(args) -> dict:
    """Synthesizes audio tracks and subtitle manifests for all scenes."""
    os.makedirs(args.outdir, exist_ok=True)
    lang = args.lang or ("ja-JP" if os.environ.get("CURRENCY_SYMBOL") in ("¥", "円") else "en-US")
    company = args.company or os.environ.get("COMPANY_NAME", "Enterprise Demo")
    role = args.role or os.environ.get("DEMO_DISPLAY_NAME", "Operations Director")

    script_scenes = build_narration_script(company, role, lang, prompts=getattr(args, "prompts", None))
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

        scene_entry = {
            "scene_id": scene_id,
            "title": sc["title"],
            "narration_text": sc["text"],
            "audio_file": audio_filename,
            "duration_sec": dur,
            "subtitles": subtitles
        }

        # If scene has structured phases (lead, thinking, response), synthesize per-phase audio
        if "lead_text" in sc and "think_text" in sc and "resp_text" in sc:
            lead_filename = f"audio_{scene_id}_lead.mp3"
            think_filename = f"audio_{scene_id}_think.mp3"
            resp_filename = f"audio_{scene_id}_resp.mp3"

            dur_lead = synthesize_scene_audio(sc["lead_text"], os.path.join(args.outdir, lead_filename), lang=lang, mock=args.mock, project=getattr(args, "project", ""))
            dur_think = synthesize_scene_audio(sc["think_text"], os.path.join(args.outdir, think_filename), lang=lang, mock=args.mock, project=getattr(args, "project", ""))
            dur_resp = synthesize_scene_audio(sc["resp_text"], os.path.join(args.outdir, resp_filename), lang=lang, mock=args.mock, project=getattr(args, "project", ""))

            subs_lead = split_subtitles(sc["lead_text"], dur_lead, lang=lang)
            subs_think = split_subtitles(sc["think_text"], dur_think, lang=lang)
            subs_resp = split_subtitles(sc["resp_text"], dur_resp, lang=lang)

            scene_entry["phases"] = {
                "lead": {
                    "text": sc["lead_text"],
                    "audio_file": lead_filename,
                    "duration_sec": dur_lead,
                    "subtitles": subs_lead
                },
                "thinking": {
                    "text": sc["think_text"],
                    "audio_file": think_filename,
                    "duration_sec": dur_think,
                    "subtitles": subs_think
                },
                "response": {
                    "text": sc["resp_text"],
                    "audio_file": resp_filename,
                    "duration_sec": dur_resp,
                    "subtitles": subs_resp
                }
            }
            print(f"    Phase tracks: lead={dur_lead:.2f}s, think={dur_think:.2f}s, response={dur_resp:.2f}s")

        manifest_scenes.append(scene_entry)
        print(f"    Total Audio duration: {dur:.2f}s ({len(subtitles)} subtitle slices)")

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
    parser.add_argument("--prompts", nargs="+", help="Custom demo prompt strings")
    parser.add_argument("--mock", action="store_true", help="Simulate speech durations with silent audio (no Google Cloud TTS call)")
    args = parser.parse_args()

    synthesize_all(args)


if __name__ == "__main__":
    main()
