import React from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { Line, Bar, Doughnut } from 'react-chartjs-2'
import { colors, typography } from '../utils/theme'

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

// Theme-aware defaults
ChartJS.defaults.font.family = typography.fontFamily
ChartJS.defaults.color = colors.textSecondary
ChartJS.defaults.borderColor = colors.borderLight

// Chart color palette
export const chartColors = {
  primary: colors.accent,
  secondary: colors.info,
  tertiary: colors.success,
  quaternary: '#8b5cf6', // purple
  quinary: '#06b6d4',    // cyan
}

export const chartColorArray = [
  chartColors.primary,
  chartColors.secondary,
  chartColors.tertiary,
  chartColors.quaternary,
  chartColors.quinary,
]

interface SimpleLineChartProps {
  labels: string[]
  datasets: {
    label: string
    data: number[]
    color?: string
    fill?: boolean
  }[]
  height?: number
  showLegend?: boolean
}

export const SimpleLineChart: React.FC<SimpleLineChartProps> = ({
  labels,
  datasets,
  height = 200,
  showLegend = false,
}) => {
  const data = {
    labels,
    datasets: datasets.map((ds, i) => ({
      label: ds.label,
      data: ds.data,
      borderColor: ds.color || chartColorArray[i % chartColorArray.length],
      backgroundColor: ds.fill
        ? `${ds.color || chartColorArray[i % chartColorArray.length]}20`
        : 'transparent',
      fill: ds.fill || false,
      tension: 0.3,
      pointRadius: 2,
      pointHoverRadius: 5,
    })),
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: showLegend,
        position: 'top' as const,
      },
    },
    scales: {
      x: {
        grid: { display: false },
      },
      y: {
        grid: { color: colors.borderLight },
      },
    },
  }

  return (
    <div style={{ height }}>
      <Line data={data} options={options} />
    </div>
  )
}

interface SimpleBarChartProps {
  labels: string[]
  datasets: {
    label: string
    data: number[]
    color?: string
  }[]
  height?: number
  showLegend?: boolean
  horizontal?: boolean
}

export const SimpleBarChart: React.FC<SimpleBarChartProps> = ({
  labels,
  datasets,
  height = 200,
  showLegend = false,
  horizontal = false,
}) => {
  const data = {
    labels,
    datasets: datasets.map((ds, i) => ({
      label: ds.label,
      data: ds.data,
      backgroundColor: ds.color || chartColorArray[i % chartColorArray.length],
      borderRadius: 4,
    })),
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: horizontal ? ('y' as const) : ('x' as const),
    plugins: {
      legend: {
        display: showLegend,
        position: 'top' as const,
      },
    },
    scales: {
      x: {
        grid: { display: horizontal },
      },
      y: {
        grid: { display: !horizontal, color: colors.borderLight },
      },
    },
  }

  return (
    <div style={{ height }}>
      <Bar data={data} options={options} />
    </div>
  )
}

interface SimpleDoughnutChartProps {
  labels: string[]
  data: number[]
  colors?: string[]
  height?: number
  showLegend?: boolean
}

export const SimpleDoughnutChart: React.FC<SimpleDoughnutChartProps> = ({
  labels,
  data,
  colors: customColors,
  height = 200,
  showLegend = true,
}) => {
  const chartData = {
    labels,
    datasets: [
      {
        data,
        backgroundColor: customColors || chartColorArray,
        borderWidth: 0,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: showLegend,
        position: 'right' as const,
      },
    },
    cutout: '60%',
  }

  return (
    <div style={{ height }}>
      <Doughnut data={chartData} options={options} />
    </div>
  )
}
