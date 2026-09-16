import React from "react";
import ReactECharts from "echarts-for-react";

interface KinematicSpeedChartProps {
  vesselName?: string;
  speedKnots?: number;
}

export const KinematicSpeedChart: React.FC<KinematicSpeedChartProps> = ({
  vesselName = "PACIFIC VOYAGER",
  speedKnots = 12.2,
}) => {
  const times = [
    "00:15",
    "00:30",
    "00:45",
    "01:00 (Origin)",
    "01:15",
    "01:30",
    "01:45",
  ];

  // Steady transit with subtle speed fluctuation
  const speedSeries = [12.4, 12.3, 12.1, speedKnots, 12.2, 12.3, 12.5];
  const distanceSeries = [7.2, 4.8, 2.1, 0.572, 2.4, 5.1, 7.9]; // Distance to origin in km

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      backgroundColor: "#0f172a",
      borderColor: "#334155",
      textStyle: { color: "#f8fafc", fontSize: 11 },
    },
    legend: {
      bottom: 0,
      textStyle: { color: "#94a3b8", fontSize: 11 },
    },
    grid: {
      top: "15%",
      left: "8%",
      right: "8%",
      bottom: "22%",
    },
    xAxis: {
      type: "category",
      data: times,
      axisLine: { lineStyle: { color: "#334155" } },
      axisLabel: { color: "#94a3b8", fontSize: 10 },
    },
    yAxis: [
      {
        type: "value",
        name: "Speed (kn)",
        min: 10,
        max: 16,
        axisLine: { lineStyle: { color: "#334155" } },
        splitLine: { lineStyle: { color: "#1e293b" } },
        axisLabel: { color: "#94a3b8", fontSize: 10 },
      },
      {
        type: "value",
        name: "Distance to Origin (km)",
        min: 0,
        max: 10,
        axisLine: { lineStyle: { color: "#334155" } },
        splitLine: { show: false },
        axisLabel: { color: "#94a3b8", fontSize: 10 },
      },
    ],
    series: [
      {
        name: "Transit Speed (knots)",
        type: "line",
        smooth: true,
        data: speedSeries,
        itemStyle: { color: "#38bdf8" },
        lineStyle: { width: 2.5 },
      },
      {
        name: "Proximity to Origin (km)",
        type: "line",
        yAxisIndex: 1,
        smooth: true,
        data: distanceSeries,
        itemStyle: { color: "#f43f5e" },
        lineStyle: { width: 2, type: "dashed" },
        markPoint: {
          data: [
            {
              type: "min",
              name: "Closest Point of Approach",
              label: {
                formatter: "CPA: 0.57 km",
                color: "#ffffff",
                fontSize: 10,
              },
              itemStyle: { color: "#f43f5e" },
            },
          ],
        },
      },
    ],
  };

  return (
    <div className="w-full h-64">
      <ReactECharts option={option} style={{ height: "100%", width: "100%" }} />
    </div>
  );
};
