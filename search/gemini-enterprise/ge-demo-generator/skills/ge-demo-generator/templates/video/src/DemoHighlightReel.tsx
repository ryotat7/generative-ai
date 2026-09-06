import React from "react";
import { AbsoluteFill, OffthreadVideo, Sequence, staticFile } from "remotion";
import { AudioMixer } from "./components/AudioMixer";
import { DynamicCamera } from "./components/DynamicCamera";
import { FastForwardIndicator } from "./components/FastForwardIndicator";
import { Subtitles } from "./components/Subtitles";
import { IntroCard, OutroCard, TitleBanner } from "./components/TitleCard";
import { VideoManifestProps } from "./types";

export const DemoHighlightReel: React.FC<VideoManifestProps> = (props) => {
  const fps = props.fps || 30;

  return (
    <AbsoluteFill
      style={{
        background: "#FFFFFF",
        overflow: "hidden",
      }}
    >
      {/* 1. Scene Sequences */}
      {props.scenes.map((sc) => {
        if (sc.type === "intro_card") {
          return (
            <Sequence
              key={sc.id}
              from={sc.startFrame}
              durationInFrames={sc.durationFrames}
            >
              <IntroCard company={props.company} role={props.role} />
            </Sequence>
          );
        }

        if (sc.type === "outro_card") {
          return (
            <Sequence
              key={sc.id}
              from={sc.startFrame}
              durationInFrames={sc.durationFrames}
            >
              <OutroCard company={props.company} role={props.role} />
            </Sequence>
          );
        }

        if (sc.type === "browser_screen" && sc.rawVideoTime) {
          const raw = sc.rawVideoTime;
          // Segment A: Typing (1x real speed)
          const typingDurSec = Math.max(0.1, raw.typingEndSec - raw.startSec);
          const typingFrames = Math.round(typingDurSec * fps);

          // Segment B: Thinking / Wait (Fast-forwarded 4x)
          const thinkingDurSec = Math.max(0.1, raw.thinkingEndSec - raw.typingEndSec);
          const ffFactor = sc.fastForward?.factor || 4;
          const ffDurSec = thinkingDurSec / ffFactor;
          const ffFrames = Math.round(ffDurSec * fps);

          // Segment C: Response inspection and narration (1x)
          const respFrames = Math.max(1, sc.durationFrames - (typingFrames + ffFrames));

          const cameraOverview = sc.camera?.overview || { x: 960, y: 540, scale: 1.0 };
          const cameraTyping = sc.camera?.typing || { x: 960, y: 920, scale: 1.25 };
          const cameraResponse = sc.camera?.response || { x: 960, y: 540, scale: 1.10 };

          return (
            <Sequence
              key={sc.id}
              from={sc.startFrame}
              durationInFrames={sc.durationFrames}
            >
              {/* Segment 1: Typing at 1x real speed with prompt input close-up */}
              <Sequence from={0} durationInFrames={typingFrames}>
                <DynamicCamera
                  target={cameraTyping}
                  initialScale={1.0}
                  zoomStartFrame={0}
                  zoomDurationFrames={Math.min(18, Math.round(typingFrames * 0.4))}
                >
                  <OffthreadVideo
                    src={staticFile(`recordings/${props.rawVideoFile}`)}
                    startFrom={Math.round(raw.startSec * fps)}
                    endAt={Math.round(raw.typingEndSec * fps)}
                    playbackRate={1}
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                </DynamicCamera>
              </Sequence>

              {/* Segment 2: Fast-forward thinking wait at 4x */}
              <Sequence from={typingFrames} durationInFrames={ffFrames}>
                <DynamicCamera
                  target={cameraOverview}
                  initialScale={1.25}
                  zoomStartFrame={0}
                  zoomDurationFrames={Math.min(12, Math.round(ffFrames * 0.4))}
                >
                  <OffthreadVideo
                    src={staticFile(`recordings/${props.rawVideoFile}`)}
                    startFrom={Math.round(raw.typingEndSec * fps)}
                    endAt={Math.round(raw.thinkingEndSec * fps)}
                    playbackRate={ffFactor}
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                </DynamicCamera>
                <FastForwardIndicator factor={ffFactor} />
              </Sequence>

              {/* Segment 3: Response inspection and narration at 1x with subtle zoom */}
              <Sequence from={typingFrames + ffFrames} durationInFrames={respFrames}>
                <DynamicCamera
                  target={cameraResponse}
                  initialScale={1.0}
                  zoomStartFrame={0}
                  zoomDurationFrames={Math.min(20, Math.round(respFrames * 0.2))}
                >
                  <OffthreadVideo
                    src={staticFile(`recordings/${props.rawVideoFile}`)}
                    startFrom={Math.round(raw.thinkingEndSec * fps)}
                    endAt={Math.round(raw.completeSec * fps)}
                    playbackRate={1}
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                </DynamicCamera>
              </Sequence>
            </Sequence>
          );
        }

        return null;
      })}

      {/* 2. Global Title Banner (First 1.5s of Scene 1, right after intro) */}
      {props.scenes.find((s) => s.type === "browser_screen") && (
        <Sequence
          from={props.scenes.find((s) => s.type === "browser_screen")!.startFrame}
          durationInFrames={45}
        >
          <TitleBanner
            title={props.company}
            subtitle={`${props.role} — AI Agent Walkthrough`}
          />
        </Sequence>
      )}

      {/* 3. Clean Lower-Third Subtitles */}
      <Subtitles subtitles={props.subtitles} />

      {/* 4. Professional Narration Audio Tracks (Speech Only) */}
      <AudioMixer audioClips={props.audioClips} />
    </AbsoluteFill>
  );
};
