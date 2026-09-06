// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import React from "react";

interface FastForwardIndicatorProps {
  factor?: number;
}

export const FastForwardIndicator: React.FC<FastForwardIndicatorProps> = ({ factor = 4 }) => {
  return (
    <div
      style={{
        position: "absolute",
        top: 28,
        right: 32,
        background: "rgba(15, 20, 30, 0.52)",
        backdropFilter: "blur(16px) saturate(180%)",
        border: "1px solid rgba(255, 255, 255, 0.12)",
        borderRadius: 9999,
        padding: "4px 12px",
        display: "flex",
        alignItems: "center",
        color: "rgba(255, 255, 255, 0.92)",
        fontSize: 13,
        fontWeight: 600,
        fontFamily: "'Google Sans', -apple-system, sans-serif",
        letterSpacing: "0.04em",
        zIndex: 40,
        boxShadow: "0 2px 10px rgba(0, 0, 0, 0.25)",
      }}
    >
      <span>{Number(factor).toFixed(1)}×</span>
    </div>
  );
};
