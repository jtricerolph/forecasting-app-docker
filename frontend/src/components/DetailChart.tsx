import React from 'react'
import Plot from 'react-plotly.js'
import Plotly from 'plotly.js'
import { colors, typography } from '../utils/theme'

// Theme-aware layout defaults
const baseLayout: Partial<Plotly.Layout> = {
  paper_bgcolor: 'transparent',
  plot_bgcolor: colors.surface,
  font: {
    family: typography.fontFamily,
    color: colors.text,
    size: 12,
  },
  margin: { l: 50, r: 20, t: 40, b: 50 },
  xaxis: {
    gridcolor: colors.borderLight,
    linecolor: colors.border,
    tickfont: { color: colors.textSecondary },
  },
  yaxis: {
    gridcolor: colors.borderLight,
    linecolor: colors.border,
    tickfont: { color: colors.textSecondary },
  },
  legend: {
    orientation: 'h',
    yanchor: 'bottom',
    y: 1.02,
    xanchor: 'right',
    x: 1,
  },
  hovermode: 'x unified',
}

// Chart color palette
export const plotlyColors = {
  primary: colors.accent,
  secondary: colors.info,
  tertiary: colors.success,
  quaternary: '#8b5cf6',
  quinary: '#06b6d4',
}

export const plotlyColorArray = [
  plotlyColors.primary,
  plotlyColors.secondary,
  plotlyColors.tertiary,
  plotlyColors.quaternary,
  plotlyColors.quinary,
]

// Interactive config
const baseConfig: Partial<Plotly.Config> = {
  displayModeBar: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
  scrollZoom: true,
  responsive: true,
}

interface TimeSeriesData {
  x: (string | Date)[]
  y: number[]
  name: string
  color?: string
  mode?: 'lines' | 'markers' | 'lines+markers'
  fill?: 'tozeroy' | 'tonexty' | 'none'
}

interface DetailLineChartProps {
  data: TimeSeriesData[]
  title?: string
  xAxisTitle?: string
  yAxisTitle?: string
  height?: number
  showRangeSlider?: boolean
}

export const DetailLineChart: React.FC<DetailLineChartProps> = ({
  data,
  title,
  xAxisTitle,
  yAxisTitle,
  height = 400,
  showRangeSlider = true,
}) => {
  const traces: Plotly.Data[] = data.map((series, i) => ({
    x: series.x,
    y: series.y,
    name: series.name,
    type: 'scatter',
    mode: series.mode || 'lines',
    line: {
      color: series.color || plotlyColorArray[i % plotlyColorArray.length],
      width: 2,
    },
    fill: series.fill || 'none',
    fillcolor: series.fill
      ? `${series.color || plotlyColorArray[i % plotlyColorArray.length]}20`
      : undefined,
    hovertemplate: `%{y:.1f}<extra>${series.name}</extra>`,
  }))

  const layout: Partial<Plotly.Layout> = {
    ...baseLayout,
    title: title ? { text: title, font: { size: 16 } } : undefined,
    height,
    xaxis: {
      ...baseLayout.xaxis,
      title: xAxisTitle ? { text: xAxisTitle } : undefined,
      rangeslider: showRangeSlider ? { visible: true } : undefined,
      rangeselector: showRangeSlider
        ? {
            buttons: [
              { count: 7, label: '1w', step: 'day', stepmode: 'backward' },
              { count: 1, label: '1m', step: 'month', stepmode: 'backward' },
              { count: 3, label: '3m', step: 'month', stepmode: 'backward' },
              { count: 6, label: '6m', step: 'month', stepmode: 'backward' },
              { step: 'all', label: 'All' },
            ],
          }
        : undefined,
    },
    yaxis: {
      ...baseLayout.yaxis,
      title: yAxisTitle ? { text: yAxisTitle } : undefined,
    },
  }

  return <Plot data={traces} layout={layout} config={baseConfig} style={{ width: '100%' }} />
}

interface DetailBarChartProps {
  x: string[]
  datasets: {
    y: number[]
    name: string
    color?: string
  }[]
  title?: string
  xAxisTitle?: string
  yAxisTitle?: string
  height?: number
  barMode?: 'group' | 'stack'
}

export const DetailBarChart: React.FC<DetailBarChartProps> = ({
  x,
  datasets,
  title,
  xAxisTitle,
  yAxisTitle,
  height = 400,
  barMode = 'group',
}) => {
  const traces: Plotly.Data[] = datasets.map((ds, i) => ({
    x,
    y: ds.y,
    name: ds.name,
    type: 'bar',
    marker: {
      color: ds.color || plotlyColorArray[i % plotlyColorArray.length],
    },
    hovertemplate: `%{y:.1f}<extra>${ds.name}</extra>`,
  }))

  const layout: Partial<Plotly.Layout> = {
    ...baseLayout,
    title: title ? { text: title, font: { size: 16 } } : undefined,
    height,
    barmode: barMode,
    xaxis: {
      ...baseLayout.xaxis,
      title: xAxisTitle ? { text: xAxisTitle } : undefined,
    },
    yaxis: {
      ...baseLayout.yaxis,
      title: yAxisTitle ? { text: yAxisTitle } : undefined,
    },
  }

  return <Plot data={traces} layout={layout} config={baseConfig} style={{ width: '100%' }} />
}

interface HeatmapData {
  z: number[][]
  x: string[]
  y: string[]
}

interface DetailHeatmapProps {
  data: HeatmapData
  title?: string
  height?: number
  colorScale?: string
}

export const DetailHeatmap: React.FC<DetailHeatmapProps> = ({
  data,
  title,
  height = 400,
  colorScale = 'RdYlGn',
}) => {
  const trace: Plotly.Data = {
    z: data.z,
    x: data.x,
    y: data.y,
    type: 'heatmap',
    colorscale: colorScale,
    hovertemplate: 'x: %{x}<br>y: %{y}<br>value: %{z:.1f}<extra></extra>',
  }

  const layout: Partial<Plotly.Layout> = {
    ...baseLayout,
    title: title ? { text: title, font: { size: 16 } } : undefined,
    height,
  }

  return <Plot data={[trace]} layout={layout} config={baseConfig} style={{ width: '100%' }} />
}

interface Detail3DScatterProps {
  data: {
    x: number[]
    y: number[]
    z: number[]
    name: string
    color?: string
  }[]
  title?: string
  xAxisTitle?: string
  yAxisTitle?: string
  zAxisTitle?: string
  height?: number
}

export const Detail3DScatter: React.FC<Detail3DScatterProps> = ({
  data,
  title,
  xAxisTitle,
  yAxisTitle,
  zAxisTitle,
  height = 500,
}) => {
  const traces: Plotly.Data[] = data.map((series, i) => ({
    x: series.x,
    y: series.y,
    z: series.z,
    name: series.name,
    type: 'scatter3d',
    mode: 'markers',
    marker: {
      size: 4,
      color: series.color || plotlyColorArray[i % plotlyColorArray.length],
      opacity: 0.8,
    },
  }))

  const layout: Partial<Plotly.Layout> = {
    ...baseLayout,
    title: title ? { text: title, font: { size: 16 } } : undefined,
    height,
    scene: {
      xaxis: { title: xAxisTitle ? { text: xAxisTitle } : undefined, gridcolor: colors.borderLight },
      yaxis: { title: yAxisTitle ? { text: yAxisTitle } : undefined, gridcolor: colors.borderLight },
      zaxis: { title: zAxisTitle ? { text: zAxisTitle } : undefined, gridcolor: colors.borderLight },
    },
  }

  return <Plot data={traces} layout={layout} config={baseConfig} style={{ width: '100%' }} />
}

interface DetailSurfaceProps {
  z: number[][]
  x?: number[]
  y?: number[]
  title?: string
  height?: number
  colorScale?: string
}

export const DetailSurface: React.FC<DetailSurfaceProps> = ({
  z,
  x,
  y,
  title,
  height = 500,
  colorScale = 'Viridis',
}) => {
  const trace: Plotly.Data = {
    z,
    x,
    y,
    type: 'surface',
    colorscale: colorScale,
  }

  const layout: Partial<Plotly.Layout> = {
    ...baseLayout,
    title: title ? { text: title, font: { size: 16 } } : undefined,
    height,
  }

  return <Plot data={[trace]} layout={layout} config={baseConfig} style={{ width: '100%' }} />
}

// Export the raw Plot component for custom charts
export { Plot, baseLayout, baseConfig, Plotly }
