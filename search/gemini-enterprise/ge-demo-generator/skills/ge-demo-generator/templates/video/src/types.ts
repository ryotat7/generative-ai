export interface CameraTarget {
  x: number;
  y: number;
  scale: number;
}

export interface SubtitleItem {
  startFrame: number;
  endFrame: number;
  text: string;
}

export interface AudioClip {
  id: string;
  file: string;
  startFrame: number;
  durationFrames: number;
}

export interface SceneConfig {
  id: string;
  type: "intro_card" | "browser_screen" | "outro_card";
  title: string;
  subtitle?: string;
  startFrame: number;
  durationFrames: number;
  rawVideoTime?: {
    startSec: number;
    typingEndSec: number;
    thinkingEndSec: number;
    completeSec: number;
  };
  fastForward?: {
    startFrame: number;
    durationFrames: number;
    factor: number;
  };
  camera?: {
    typing?: CameraTarget;
    response?: CameraTarget;
    overview?: CameraTarget;
  };
}

export interface VideoManifestProps extends Record<string, unknown> {
  company: string;
  role: string;
  fps: number;
  width: number;
  height: number;
  totalFrames: number;
  totalDurationSec: number;
  rawVideoFile: string;
  scenes: SceneConfig[];
  audioClips: AudioClip[];
  subtitles: SubtitleItem[];
}
