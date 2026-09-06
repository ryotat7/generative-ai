import React from "react";
import { Audio, Sequence, staticFile } from "remotion";
import { AudioClip } from "../types";

interface AudioMixerProps {
  audioClips?: AudioClip[];
}

export const AudioMixer: React.FC<AudioMixerProps> = ({ audioClips = [] }) => {
  return (
    <>
      {/* Voice Narration Clips (Clean Speech Only, No BGM) */}
      {audioClips.map((clip) => (
        <Sequence
          key={clip.id}
          from={clip.startFrame}
          durationInFrames={clip.durationFrames}
        >
          <Audio src={staticFile(`audio/${clip.file}`)} volume={1.0} />
        </Sequence>
      ))}
    </>
  );
};
