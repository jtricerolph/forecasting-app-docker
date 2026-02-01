// Simple charts (Chart.js) - lightweight, for dashboard cards & summaries
export {
  SimpleLineChart,
  SimpleBarChart,
  SimpleDoughnutChart,
  chartColors,
  chartColorArray,
} from './SimpleChart'

// Detail charts (Plotly) - full featured with zoom/pan/3D
export {
  DetailLineChart,
  DetailBarChart,
  DetailHeatmap,
  Detail3DScatter,
  DetailSurface,
  Plot,
  baseLayout,
  baseConfig,
  plotlyColors,
  plotlyColorArray,
} from './DetailChart'
