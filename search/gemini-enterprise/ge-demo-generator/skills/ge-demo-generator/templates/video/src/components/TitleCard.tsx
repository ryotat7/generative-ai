import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

interface TitleBannerProps {
  title: string;
  subtitle: string;
}

export const TitleBanner: React.FC<TitleBannerProps> = ({ title, subtitle }) => {
  const frame = useCurrentFrame();

  // Fades in over 10 frames, stays for 25 frames, fades out over 10 frames (total ~45 frames = 1.5s)
  const opacity = interpolate(frame, [0, 10, 35, 45], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (frame > 45) {
    return null;
  }

  return (
    <div
      style={{
        position: "absolute",
        top: 32,
        left: "50%",
        transform: "translateX(-50%)",
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "12px 28px",
        borderRadius: 999,
        background: "rgba(15, 23, 42, 0.88)",
        backdropFilter: "blur(12px)",
        border: "1px solid rgba(255, 255, 255, 0.15)",
        boxShadow: "0 8px 32px rgba(0, 0, 0, 0.5)",
        opacity,
        zIndex: 50,
      }}
    >
      <div
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: "#38BDF8",
          boxShadow: "0 0 10px #38BDF8",
        }}
      />
      <span
        style={{
          color: "#FFFFFF",
          fontSize: 18,
          fontWeight: 700,
          fontFamily: "'Google Sans', 'Inter', sans-serif",
          letterSpacing: "0.02em",
        }}
      >
        {title}
      </span>
      <span style={{ color: "rgba(255, 255, 255, 0.3)" }}>|</span>
      <span
        style={{
          color: "#94A3B8",
          fontSize: 16,
          fontWeight: 500,
          fontFamily: "'Roboto', sans-serif",
        }}
      >
        {subtitle}
      </span>
    </div>
  );
};

export const IntroCard: React.FC<{ company: string; role: string }> = ({ company, role }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  const scale = interpolate(frame, [0, 20], [0.96, 1.0], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        background: "#FFFFFF",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "'Google Sans', 'Inter', sans-serif",
        opacity,
        transform: `scale(${scale})`,
        position: "relative",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "8px 20px",
          borderRadius: 999,
          background: "#F1F3F4",
          border: "1px solid #DADCE0",
          marginBottom: 28,
        }}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
          <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" fill="url(#introSparkle)"/>
          <defs>
            <linearGradient id="introSparkle" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#4285F4"/>
              <stop offset="50%" stopColor="#9B72CB"/>
              <stop offset="100%" stopColor="#D96570"/>
            </linearGradient>
          </defs>
        </svg>
        <span style={{ fontSize: 16, fontWeight: 600, color: "#1F1F1F", letterSpacing: "0.02em" }}>
          Gemini Enterprise Demo
        </span>
      </div>

      <h1
        style={{
          fontSize: 56,
          fontWeight: 800,
          color: "#1F1F1F",
          margin: "0 0 16px 0",
          letterSpacing: "-0.02em",
          textAlign: "center",
        }}
      >
        {company}
      </h1>

      <h2
        style={{
          fontSize: 28,
          fontWeight: 500,
          color: "#1A73E8",
          margin: "0 0 32px 0",
          textAlign: "center",
        }}
      >
        {role}
      </h2>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 15,
          color: "#5F6368",
        }}
      >
        <span>Autonomous Multi-Agent Systems & Live Web UI Walkthrough</span>
      </div>
    </div>
  );
};

export const OutroCard: React.FC<{ company: string; role?: string }> = ({ company }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        background: "#FFFFFF",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "'Google Sans', 'Inter', sans-serif",
        opacity,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "8px 20px",
          borderRadius: 999,
          background: "#E8F0FE",
          border: "1px solid #D2E3FC",
          marginBottom: 28,
        }}
      >
        <span style={{ fontSize: 16, fontWeight: 600, color: "#1A73E8" }}>
          Ready for Autonomous Operations
        </span>
      </div>

      <h1
        style={{
          fontSize: 52,
          fontWeight: 800,
          color: "#1F1F1F",
          margin: "0 0 16px 0",
          textAlign: "center",
        }}
      >
        Gemini Enterprise for {company}
      </h1>

      <p
        style={{
          fontSize: 22,
          color: "#5F6368",
          margin: "0 0 40px 0",
          textAlign: "center",
        }}
      >
        Accelerating enterprise decisions with grounded, autonomous AI agents
      </p>

      <div
        style={{
          fontSize: 15,
          color: "#80868B",
          fontWeight: 500,
        }}
      >
        Powered by Google Cloud & Vertex AI Agent Platform
      </div>
    </div>
  );
};
