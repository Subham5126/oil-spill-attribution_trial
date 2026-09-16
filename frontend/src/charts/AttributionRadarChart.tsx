import React from "react";
import ReactECharts from "echarts-for-react";
import { CandidateVessel } from "../types";

interface AttributionRadarChartProps {
  candidates: CandidateVessel[];
  selectedVessel?: CandidateVessel | null;
}

export const AttributionRadarChart: React.FC<AttributionRadarChartProps> = ({
  candidates,
  selectedVessel,
}) => {
  const primary = candidates[0];
  const secondary = candidates[1];

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      backgroundColor: "#0f172a",
      borderColor: "#334155",
      textStyle: { color: "#f8fafc", fontSize: 12 },
    },
    legend: {
      bottom: 0,
      textStyle: { color: "#94a3b8", fontSize: 11 },
      itemGap: 14,
    },
    radar: {
      indicator: [
        { name: "Spatial (40%)", max: 1.0 },
        { name: "Temporal (35%)", max: 1.0 },
        { name: "Trajectory (15%)", max: 1.0 },
        { name: "Behaviour (10%)", max: 1.0 },
      ],
      radius: "56%",
      center: ["50%", "44%"],
      splitNumber: 4,
      axisName: {
        color: "#cbd5e1",
        fontSize: 11,
      },
      splitLine: {
        lineStyle: { color: "#334155" },
      },
      splitArea: {
        show: true,
        areaStyle: {
          color: ["rgba(15, 23, 42, 0.4)", "rgba(30, 41, 59, 0.4)"],
        },
      },
      axisLine: {
        lineStyle: { color: "#475569" },
      },
    },
    series: [
      {
        name: "Attribution Breakdown",
        type: "radar",
        data: [
          primary
            ? {
                value: [
                  primary.scores.spatial,
                  primary.scores.temporal,
                  primary.scores.trajectory,
                  primary.scores.behaviour,
                ],
                name: `${primary.vessel_name} (Rank #1 - ${(primary.scores.overall * 100).toFixed(1)}%)`,
                itemStyle: { color: "#f43f5e" },
                areaStyle: { color: "rgba(244, 63, 94, 0.25)" },
                lineStyle: { width: 2 },
              }
            : null,
          secondary
            ? {
                value: [
                  secondary.scores.spatial,
                  secondary.scores.temporal,
                  secondary.scores.trajectory,
                  secondary.scores.behaviour,
                ],
                name: `${secondary.vessel_name} (Rank #2 - ${(secondary.scores.overall * 100).toFixed(1)}%)`,
                itemStyle: { color: "#0ea5e9" },
                areaStyle: { color: "rgba(14, 165, 233, 0.2)" },
                lineStyle: { width: 2 },
              }
            : null,
        ].filter(Boolean),
      },
    ],
  };

  return (
    <div className="w-full h-52">
      <ReactECharts option={option} style={{ height: "100%", width: "100%" }} />
    </div>
  );
};
