import React, { useState, useEffect, useMemo, useRef } from 'react';
import htm from 'htm';
import * as d3 from 'd3';
import { AlertOctagon, TrendingUp, Info, HelpCircle, Activity, Battery, Moon } from 'lucide-react';

const html = htm.bind(React.createElement);

const MOOD_LABELS = { 1: 'Awful', 2: 'Bad', 3: 'Okay', 4: 'Good', 5: 'Rad' };

export default function AnalyticsCharts({ logs }) {
  const [timeframe, setTimeframe] = useState('monthly');
  const [hoveredDay, setHoveredDay] = useState(null);
  const lineChartRef = useRef(null);
  const barChartRef = useRef(null);

  const filteredLogs = useMemo(() => {
    const sorted = [...logs].sort((a, b) => new Date(a.date) - new Date(b.date));
    const now = new Date();
    let daysToKeep = 30;
    if (timeframe === 'weekly') daysToKeep = 7;
    if (timeframe === 'semester') daysToKeep = 90;
    const cutoffDate = new Date();
    cutoffDate.setDate(now.getDate() - daysToKeep);
    return sorted.filter(log => new Date(log.date) >= cutoffDate);
  }, [logs, timeframe]);

  const burnoutAlert = useMemo(() => {
    const sortedLogs = [...logs].sort((a, b) => new Date(a.date) - new Date(b.date));
    if (sortedLogs.length < 3) return null;
    for (let i = 0; i <= sortedLogs.length - 3; i++) {
      const day1 = sortedLogs[i];
      const day2 = sortedLogs[i + 1];
      const day3 = sortedLogs[i + 2];
      if (
        day1.stress >= 4 && day1.sleepHours < 5.0 &&
        day2.stress >= 4 && day2.sleepHours < 5.0 &&
        day3.stress >= 4 && day3.sleepHours < 5.0
      ) {
        return { startDate: day1.date, endDate: day3.date, days: [day1, day2, day3] };
      }
    }
    return null;
  }, [logs]);

  const sleepEnergyStats = useMemo(() => {
    const stats = {
      Poor: { energySum: 0, count: 0 },
      Fair: { energySum: 0, count: 0 },
      Good: { energySum: 0, count: 0 }
    };
    filteredLogs.forEach(log => {
      const q = log.sleepQuality || 'Good';
      if (stats[q]) {
        stats[q].energySum += log.energy;
        stats[q].count += 1;
      }
    });
    return Object.keys(stats).map(quality => ({
      quality,
      avgEnergy: stats[quality].count > 0
        ? parseFloat((stats[quality].energySum / stats[quality].count).toFixed(1))
        : 0,
      count: stats[quality].count
    }));
  }, [filteredLogs]);

  // d3.js line chart — Mood vs Stress
  useEffect(() => {
    const container = lineChartRef.current;
    if (!container) return;
    container.innerHTML = '';
    if (filteredLogs.length === 0) return;

    const width = 500;
    const height = 220;
    const margin = { top: 30, right: 40, bottom: 30, left: 40 };

    const svg = d3.select(container)
      .append('svg')
      .attr('width', '100%')
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'none')
      .style('cursor', 'crosshair');

    const x = d3.scalePoint()
      .domain(filteredLogs.map(d => d.date))
      .range([margin.left, width - margin.right]);

    const y = d3.scaleLinear()
      .domain([1, 5])
      .range([height - margin.bottom, margin.top]);

    svg.append('g')
      .attr('class', 'grid')
      .selectAll('line')
      .data(y.ticks(4))
      .join('line')
      .attr('x1', margin.left)
      .attr('x2', width - margin.right)
      .attr('y1', d => y(d))
      .attr('y2', d => y(d))
      .attr('stroke', '#94a3b8')
      .attr('stroke-width', 0.5)
      .attr('stroke-dasharray', '4 4')
      .attr('opacity', 0.4);

    svg.append('g')
      .attr('transform', `translate(${margin.left - 10},0)`)
      .selectAll('text')
      .data(y.ticks(4))
      .join('text')
      .attr('y', d => y(d) + 4)
      .attr('text-anchor', 'end')
      .attr('fill', '#94a3b8')
      .attr('font-size', '10px')
      .attr('font-weight', 'bold')
      .text(d => d);

    const lineMood = d3.line()
      .x(d => x(d.date))
      .y(d => y(d.mood))
      .curve(d3.curveMonotoneX);

    const lineStress = d3.line()
      .x(d => x(d.date))
      .y(d => y(d.stress))
      .curve(d3.curveMonotoneX);

    svg.append('path')
      .datum(filteredLogs)
      .attr('fill', 'none')
      .attr('stroke', '#10b981')
      .attr('stroke-width', 2.5)
      .attr('d', lineMood);

    svg.append('path')
      .datum(filteredLogs)
      .attr('fill', 'none')
      .attr('stroke', '#f43f5e')
      .attr('stroke-width', 2.5)
      .attr('d', lineStress);

    const formatShortDate = (dateStr) => {
      const d = new Date(dateStr + 'T00:00:00');
      return `${d.getMonth() + 1}/${d.getDate()}`;
    };

    filteredLogs.forEach((log, idx) => {
      let showLabel = timeframe === 'weekly' || idx === filteredLogs.length - 1;
      if (timeframe === 'monthly' && idx % 5 === 0) showLabel = true;
      if (timeframe === 'semester' && idx % 14 === 0) showLabel = true;
      if (!showLabel) return;
      svg.append('text')
        .attr('x', x(log.date))
        .attr('y', height - 8)
        .attr('text-anchor', 'middle')
        .attr('fill', '#94a3b8')
        .attr('font-size', '10px')
        .attr('font-weight', 'bold')
        .text(formatShortDate(log.date));
    });

    const overlay = svg.append('rect')
      .attr('x', margin.left)
      .attr('y', margin.top)
      .attr('width', width - margin.left - margin.right)
      .attr('height', height - margin.top - margin.bottom)
      .attr('fill', 'transparent');

    const focusLine = svg.append('line')
      .attr('stroke', '#94a3b8')
      .attr('stroke-width', 1)
      .attr('stroke-dasharray', '2 2')
      .attr('opacity', 0)
      .attr('y1', margin.top)
      .attr('y2', height - margin.bottom);

    const moodDot = svg.append('circle').attr('r', 5).attr('fill', '#10b981').attr('stroke', '#fff').attr('opacity', 0);
    const stressDot = svg.append('circle').attr('r', 5).attr('fill', '#f43f5e').attr('stroke', '#fff').attr('opacity', 0);

    overlay.on('mousemove', function (event) {
      const [mx] = d3.pointer(event);
      let nearest = 0;
      let minDist = Infinity;
      filteredLogs.forEach((log, i) => {
        const dist = Math.abs(x(log.date) - mx);
        if (dist < minDist) { minDist = dist; nearest = i; }
      });
      const log = filteredLogs[nearest];
      focusLine.attr('x1', x(log.date)).attr('x2', x(log.date)).attr('opacity', 0.7);
      moodDot.attr('cx', x(log.date)).attr('cy', y(log.mood)).attr('opacity', 1);
      stressDot.attr('cx', x(log.date)).attr('cy', y(log.stress)).attr('opacity', 1);
      setHoveredDay(nearest);
    }).on('mouseleave', () => {
      focusLine.attr('opacity', 0);
      moodDot.attr('opacity', 0);
      stressDot.attr('opacity', 0);
      setHoveredDay(null);
    });
  }, [filteredLogs, timeframe]);

  // d3.js bar chart — Sleep quality vs energy
  useEffect(() => {
    const container = barChartRef.current;
    if (!container) return;
    container.innerHTML = '';
    if (filteredLogs.length === 0) return;

    const width = 400;
    const height = 160;
    const margin = { top: 10, right: 10, bottom: 30, left: 10 };

    const svg = d3.select(container)
      .append('svg')
      .attr('width', '100%')
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`);

    const x = d3.scaleBand()
      .domain(sleepEnergyStats.map(d => d.quality))
      .range([margin.left, width - margin.right])
      .padding(0.3);

    const y = d3.scaleLinear()
      .domain([0, 5])
      .range([height - margin.bottom, margin.top]);

    const colors = { Poor: '#f43f5e', Fair: '#f59e0b', Good: '#10b981' };

    svg.selectAll('rect')
      .data(sleepEnergyStats)
      .join('rect')
      .attr('x', d => x(d.quality))
      .attr('y', d => y(d.avgEnergy))
      .attr('width', x.bandwidth())
      .attr('height', d => y(0) - y(d.avgEnergy))
      .attr('fill', d => colors[d.quality])
      .attr('rx', 6)
      .transition()
      .duration(800)
      .attr('y', d => y(d.avgEnergy))
      .attr('height', d => y(0) - y(d.avgEnergy));

    svg.selectAll('.label')
      .data(sleepEnergyStats)
      .join('text')
      .attr('class', 'label')
      .attr('x', d => x(d.quality) + x.bandwidth() / 2)
      .attr('y', height - 8)
      .attr('text-anchor', 'middle')
      .attr('fill', '#64748b')
      .attr('font-size', '11px')
      .attr('font-weight', 'bold')
      .text(d => d.quality);
  }, [sleepEnergyStats, filteredLogs.length]);

  const formatShortDate = (dateStr) => {
    const d = new Date(dateStr + 'T00:00:00');
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  const formatTooltipDate = (dateStr) => {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  };

  const hoveredLog = hoveredDay !== null ? filteredLogs[hoveredDay] : null;

  return html`
    <div className="space-y-6">
      ${burnoutAlert && html`
        <div className="bg-gradient-to-r from-rose-50 to-red-100/50 dark:from-red-950/20 dark:to-rose-950/10 border border-red-200 dark:border-red-900/50 rounded-2xl p-4.5 shadow-sm animate-pulse-subtle flex items-start gap-4">
          <div className="w-10 h-10 rounded-xl bg-red-100 dark:bg-red-900/40 text-red-500 dark:text-red-400 flex items-center justify-center shrink-0">
            <${AlertOctagon} className="w-6 h-6 animate-bounce-slow" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-red-800 dark:text-red-300">Burnout Warning Signal Detected</h3>
            <p className="text-xs text-red-700/90 dark:text-red-400/90 leading-relaxed">
              Our analysis shows <strong>3 consecutive days</strong> of high stress combined with low sleep around
              <span className="font-semibold text-red-800 dark:text-red-200"> ${formatShortDate(burnoutAlert.startDate)} - ${formatShortDate(burnoutAlert.endDate)}</span>.
            </p>
          </div>
        </div>
      `}

      <div className="bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800/80 rounded-2xl p-4 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-2">
          <${TrendingUp} className="w-5 h-5 text-emerald-500" />
          <h2 className="text-sm font-bold text-slate-800 dark:text-white">Trends Analytics <span className="text-xxs text-slate-400 font-medium">(d3.js)</span></h2>
        </div>
        <div className="flex bg-slate-100 dark:bg-slate-800 p-0.75 rounded-xl gap-0.5">
          ${[
            { id: 'weekly', label: '7D' },
            { id: 'monthly', label: '30D' },
            { id: 'semester', label: '90D' }
          ].map(opt => html`
            <button
              key=${opt.id}
              onClick=${() => { setTimeframe(opt.id); setHoveredDay(null); }}
              className="px-3.5 py-1.5 rounded-lg text-xxs font-bold tracking-wider transition-all ${
                timeframe === opt.id
                  ? 'bg-white dark:bg-slate-700 text-emerald-600 dark:text-emerald-400 shadow-sm'
                  : 'text-slate-500 dark:text-slate-400'
              }"
            >
              ${opt.label}
            </button>
          `)}
        </div>
      </div>

      ${filteredLogs.length === 0 ? html`
        <div className="bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800/80 rounded-2xl p-10 shadow-sm text-center flex flex-col items-center gap-3">
          <${Info} className="w-8 h-8 text-slate-300" />
          <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">No check-in logs found for the selected timeframe.</p>
        </div>
      ` : html`
        <div className="bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800/80 rounded-2xl p-5 shadow-sm space-y-4">
          <h3 className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <${Activity} className="w-4 h-4 text-emerald-500" />
            <span>Mood vs. Stress Level</span>
          </h3>
          <div ref=${lineChartRef} id="d3-mood-stress-chart" />
          <div className="bg-slate-50 dark:bg-slate-900/60 rounded-xl p-3 border border-slate-100/50 dark:border-slate-800/40 min-h-12">
            ${hoveredLog ? html`
              <div className="flex flex-col sm:flex-row justify-between gap-2">
                <span className="text-xxs font-bold text-slate-500 uppercase">${formatTooltipDate(hoveredLog.date)}</span>
                <div className="flex flex-wrap gap-3 text-xs font-semibold">
                  <span>Mood: <span className="text-emerald-500">${MOOD_LABELS[hoveredLog.mood]}</span></span>
                  <span>Stress: <span className="text-rose-500">${hoveredLog.stress}/5</span></span>
                  <span>Sleep: <span className="text-indigo-500">${hoveredLog.sleepHours}h</span></span>
                </div>
              </div>
            ` : html`
              <p className="text-xxs text-slate-400 text-center flex items-center justify-center gap-1">
                <${HelpCircle} className="w-3.5 h-3.5" />
                <span>Hover the d3 chart to inspect daily details.</span>
              </p>
            `}
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800/80 rounded-2xl p-5 shadow-sm space-y-4">
          <h3 className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <${Battery} className="w-4 h-4 text-amber-500" />
            <span>Sleep Quality Impact on Energy</span>
          </h3>
          <div ref=${barChartRef} id="d3-sleep-energy-chart" />
          <div className="bg-slate-50 dark:bg-slate-900/60 rounded-xl p-3 border border-slate-100/50 dark:border-slate-800/40 text-xxs text-slate-500 flex items-start gap-2">
            <${Moon} className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
            <p><strong>Data Insight:</strong> Bars show average energy (1–5) grouped by sleep quality, rendered with d3 scales and transitions.</p>
          </div>
        </div>
      `}
    </div>
  `;
}
