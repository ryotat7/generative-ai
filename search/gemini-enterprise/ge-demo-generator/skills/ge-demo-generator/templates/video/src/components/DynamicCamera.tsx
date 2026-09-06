import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { CameraTarget } from "../types";

export interface DynamicCameraProps {
  target?: CameraTarget;
  initialScale?: number;
  zoomStartFrame?: number;
  zoomDurationFrames?: number;
  children: React.ReactNode;
}

export const DynamicCamera: React.FC<DynamicCameraProps> = ({
  target,
  initialScale = 1.0,
  zoomStartFrame = 0,
  zoomDurationFrames = 15,
  children,
}) => {
  const frame = useCurrentFrame();

  const targetScale = target?.scale ?? 1.0;
  const targetX = target?.x ?? 960;
  const targetY = target?.y ?? 540;

  let scale = targetScale;
  if (zoomDurationFrames > 0 && initialScale !== targetScale) {
    scale = interpolate(
      frame,
      [zoomStartFrame, zoomStartFrame + zoomDurationFrames],
      [initialScale, targetScale],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }
    );
  }

  const originX = `${(targetX / 1920) * 100}%`;
  const originY = `${(targetY / 1080) * 100}%`;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        transformOrigin: `${originX} ${originY}`,
        transform: `scale(${scale})`,
      }}
    >
      {children}
    </div>
  );
};
