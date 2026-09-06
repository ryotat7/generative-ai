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

"""Compiles Browser Recording Telemetry and TTS Audio into Remotion Video Props.

Merges `actions.json` and `narration_manifest.json` into `video_props.json`.
Calculates exact frame timelines (30fps), 4x-5x wait-time acceleration, dynamic camera
coordinates (zoom/pan), synchronized subtitle tracks, and audio ducking schedules.
"""

import argparse
import json
import os
import sys

FPS = 30
INTRO_DURATION_SEC = 3.0
OUTRO_DURATION_SEC = 3.0
FAST_FORWARD_FACTOR = 4.0


def build_manifest(actions_path: str, narration_path: str, output_path: str) -> dict:
    """Builds complete Remotion composition props JSON."""
    with open(actions_path, "r", encoding="utf-8") as f:
        actions_data = json.load(f)

    with open(narration_path, "r", encoding="utf-8") as f:
        narration_data = json.load(f)

    company = narration_data.get("company", "Enterprise")
    role = narration_data.get("role", "AI Operations Director")
    raw_video_path = actions_data.get("raw_video_path", "raw_recording.mp4")

    # Map narration scenes by scene_id
    narration_by_id = {s["scene_id"]: s for s in narration_data.get("scenes", [])}

    current_frame = 0
    timeline_scenes = []
    audio_clips = []
    all_subtitles = []

    # 1. Intro Card
    intro_narration = narration_by_id.get("intro")
    intro_dur_sec = max(INTRO_DURATION_SEC, intro_narration.get("duration_sec", INTRO_DURATION_SEC) + 0.8) if intro_narration else INTRO_DURATION_SEC
    intro_frames = int(intro_dur_sec * FPS)
    if intro_narration:
        audio_clips.append({
            "id": "audio_intro",
            "file": intro_narration["audio_file"],
            "startFrame": current_frame + 10,
            "durationFrames": int(intro_narration["duration_sec"] * FPS)
        })
        for sub in intro_narration.get("subtitles", []):
            all_subtitles.append({
                "startFrame": current_frame + 10 + int(sub["start_sec"] * FPS),
                "endFrame": current_frame + 10 + int(sub["end_sec"] * FPS),
                "text": sub["text"]
            })

    timeline_scenes.append({
        "id": "scene_intro",
        "type": "intro_card",
        "title": company,
        "subtitle": f"{role} Demo",
        "startFrame": current_frame,
        "durationFrames": intro_frames,
        "camera": {
            "typing": {"x": 960, "y": 540, "scale": 1.0},
            "response": {"x": 960, "y": 540, "scale": 1.0},
            "overview": {"x": 960, "y": 540, "scale": 1.0}
        }
    })
    current_frame += intro_frames

    # 2. Main Recorded Action Scenes (P1, P3, P4)
    actions = actions_data.get("actions", [])
    for idx, act in enumerate(actions):
        scene_id = act.get("scene_id", f"prompt_{idx + 1}")
        scene_narr = narration_by_id.get(scene_id)
        if not scene_narr:
            content_narration = [s for s in narration_data.get("scenes", []) if s["scene_id"] not in ("intro", "outro")]
            if idx < len(content_narration):
                scene_narr = content_narration[idx]

        t_type_start = act.get("t_type_start", 0.0)
        t_type_end = act.get("t_type_end", 3.0)
        t_submit = act.get("t_submit", t_type_end + 0.5)
        t_resp_comp = act.get("t_response_complete", t_submit + 5.0)

        # Raw end of this scene in raw_recording.mp4
        if idx + 1 < len(actions):
            t_scene_raw_end = actions[idx + 1].get("t_type_start", t_resp_comp + 10.0)
        else:
            t_scene_raw_end = actions_data.get("total_duration_sec", t_resp_comp + 15.0)

        # Timeline segments for this scene:
        # Segment A: Typing (1x real speed)
        dur_typing_sec = max(1.5, t_submit - t_type_start)
        # Segment B: Thinking / Wait / Generation (Fast-forwarded 4x)
        raw_wait_sec = max(0.5, t_resp_comp - t_submit)
        ff_wait_sec = raw_wait_sec / FAST_FORWARD_FACTOR
        # Segment C: Response display & narration (1x real speed)
        dur_resp_sec = max(4.0, t_scene_raw_end - t_resp_comp)
        if scene_narr and scene_narr.get("duration_sec"):
            # Ensure enough time for the narration to play comfortably
            dur_resp_sec = max(dur_resp_sec, scene_narr["duration_sec"] + 1.0)

        scene_total_sec = dur_typing_sec + ff_wait_sec + dur_resp_sec
        scene_frames = int(scene_total_sec * FPS)

        # Camera focus:
        focus_rect = act.get("focus_rect", {"x": 480, "y": 420, "width": 960, "height": 450})
        center_x = focus_rect["x"] + focus_rect["width"] / 2
        center_y = focus_rect["y"] + focus_rect["height"] / 2

        timeline_scenes.append({
            "id": scene_id,
            "type": "browser_screen",
            "title": act.get("title", f"Scene {idx + 1}"),
            "startFrame": current_frame,
            "durationFrames": scene_frames,
            "rawVideoTime": {
                "startSec": t_type_start,
                "typingEndSec": t_submit,
                "thinkingEndSec": t_resp_comp,
                "completeSec": t_scene_raw_end
            },
            "fastForward": {
                "startFrame": current_frame + int(dur_typing_sec * FPS),
                "durationFrames": int(ff_wait_sec * FPS),
                "factor": FAST_FORWARD_FACTOR
            },
            "camera": {
                "typing": {"x": 960, "y": 920, "scale": 1.25},
                "response": {"x": center_x, "y": center_y, "scale": 1.10},
                "overview": {"x": 960, "y": 540, "scale": 1.0}
            }
        })

        # Add voice narration clip during the response phase
        if scene_narr:
            narr_start_frame = current_frame + int((dur_typing_sec + ff_wait_sec + 0.3) * FPS)
            audio_clips.append({
                "id": f"audio_{scene_id}",
                "file": scene_narr["audio_file"],
                "startFrame": narr_start_frame,
                "durationFrames": int(scene_narr["duration_sec"] * FPS)
            })
            for sub in scene_narr.get("subtitles", []):
                all_subtitles.append({
                    "startFrame": narr_start_frame + int(sub["start_sec"] * FPS),
                    "endFrame": narr_start_frame + int(sub["end_sec"] * FPS),
                    "text": sub["text"]
                })

        current_frame += scene_frames

    # 3. Outro Card
    outro_narration = narration_by_id.get("outro")
    outro_dur_sec = max(OUTRO_DURATION_SEC, outro_narration.get("duration_sec", OUTRO_DURATION_SEC) + 0.8) if outro_narration else OUTRO_DURATION_SEC
    outro_frames = int(outro_dur_sec * FPS)
    if outro_narration:
        audio_clips.append({
            "id": "audio_outro",
            "file": outro_narration["audio_file"],
            "startFrame": current_frame + 10,
            "durationFrames": int(outro_narration["duration_sec"] * FPS)
        })
        for sub in outro_narration.get("subtitles", []):
            all_subtitles.append({
                "startFrame": current_frame + 10 + int(sub["start_sec"] * FPS),
                "endFrame": current_frame + 10 + int(sub["end_sec"] * FPS),
                "text": sub["text"]
            })

    timeline_scenes.append({
        "id": "scene_outro",
        "type": "outro_card",
        "title": f"Gemini Enterprise for {company}",
        "subtitle": "Next Step: Explore your custom agents today",
        "startFrame": current_frame,
        "durationFrames": outro_frames,
        "camera": {
            "typing": {"x": 960, "y": 540, "scale": 1.0},
            "response": {"x": 960, "y": 540, "scale": 1.0},
            "overview": {"x": 960, "y": 540, "scale": 1.0}
        }
    })
    current_frame += outro_frames

    total_duration_sec = round(current_frame / FPS, 2)

    props = {
        "company": company,
        "role": role,
        "fps": FPS,
        "width": 1920,
        "height": 1080,
        "totalFrames": current_frame,
        "totalDurationSec": total_duration_sec,
        "rawVideoFile": os.path.basename(raw_video_path),
        "scenes": timeline_scenes,
        "audioClips": audio_clips,
        "subtitles": all_subtitles,
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(props, f, indent=2, ensure_ascii=False)

    print(f"🎬 Video manifest created: {output_path}")
    print(f"   Total Composition Duration: {total_duration_sec}s ({current_frame} frames @ {FPS}fps)")
    print(f"   Scenes: {len(timeline_scenes)} | Audio Clips: {len(audio_clips)} | Subtitles: {len(all_subtitles)}")
    return props


def main():
    parser = argparse.ArgumentParser(description="Build Remotion video properties from actions and narration.")
    parser.add_argument("--actions", required=True, help="Path to actions.json")
    parser.add_argument("--narration", required=True, help="Path to narration_manifest.json")
    parser.add_argument("--output", default="./output/video_props.json", help="Path to write video_props.json")
    args = parser.parse_args()

    build_manifest(args.actions, args.narration, args.output)


if __name__ == "__main__":
    main()
