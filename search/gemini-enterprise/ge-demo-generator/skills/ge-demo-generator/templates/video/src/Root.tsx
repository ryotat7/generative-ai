import React from "react";
import { Composition } from "remotion";
import { DemoHighlightReel } from "./DemoHighlightReel";
import { VideoManifestProps } from "./types";

const defaultProps: VideoManifestProps = {
  company: "Enterprise Demo",
  role: "AI Operations Director",
  fps: 30,
  width: 1920,
  height: 1080,
  totalFrames: 2700,
  totalDurationSec: 90.0,
  rawVideoFile: "raw_recording.mp4",
  scenes: [
    {
      id: "scene_intro",
      type: "intro_card",
      title: "Enterprise Demo",
      subtitle: "AI Operations Director Walkthrough",
      startFrame: 0,
      durationFrames: 90,
    },
    {
      id: "prompt_1",
      type: "browser_screen",
      title: "Scene 1: Welcome & Overview",
      startFrame: 90,
      durationFrames: 720,
      camera: {
        response: { x: 960, y: 540, scale: 1.10 },
      },
    },
    {
      id: "prompt_3",
      type: "browser_screen",
      title: "Scene 2: Cross-Source Anomaly Detection",
      startFrame: 810,
      durationFrames: 900,
      camera: {
        response: { x: 960, y: 500, scale: 1.10 },
      },
    },
    {
      id: "prompt_4",
      type: "browser_screen",
      title: "Scene 3: Immediate Workflow Execution",
      startFrame: 1710,
      durationFrames: 900,
      camera: {
        response: { x: 960, y: 580, scale: 1.10 },
      },
    },
    {
      id: "scene_outro",
      type: "outro_card",
      title: "Gemini Enterprise for Enterprise Demo",
      subtitle: "Autonomous Agent Orchestration — Powered by Google Cloud",
      startFrame: 2610,
      durationFrames: 90,
    },
  ],
  audioClips: [],
  subtitles: [
    {
      startFrame: 10,
      endFrame: 80,
      text: "Gemini Enterprise 自律型AIエージェントのデモ実演",
    },
    {
      startFrame: 100,
      endFrame: 300,
      text: "基本機能と現在のオペレーション状況を確認します",
    },
    {
      startFrame: 820,
      endFrame: 1100,
      text: "BigQuery注文履歴と外部サプライヤー台帳を突合し、異常値を自律検知",
    },
    {
      startFrame: 1720,
      endFrame: 2000,
      text: "検知された課題に対し、是正アクションをワンクリックで即座に承認・実行",
    },
    {
      startFrame: 2620,
      endFrame: 2690,
      text: "Gemini Enterpriseが企業の基幹業務オペレーションを変革します",
    },
  ],
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition<any, VideoManifestProps>
      id="DemoHighlightReel"
      component={DemoHighlightReel}
      durationInFrames={2700}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={defaultProps}
      calculateMetadata={({ props }) => {
        return {
          durationInFrames: props.totalFrames || 2700,
          fps: props.fps || 30,
          width: props.width || 1920,
          height: props.height || 1080,
          props,
        };
      }}
    />
  );
};
