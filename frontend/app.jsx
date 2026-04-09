<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Blackjack Optimizer</title>

  <script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/prop-types@15/prop-types.min.js" crossorigin></script>
  <script src="https://unpkg.com/recharts@2.12.7/umd/Recharts.js" crossorigin></script>
  <script src="https://unpkg.com/@babel/standalone@7.23.9/babel.min.js"></script>

  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:         #07111e;
      --surf:       #0c1a2e;
      --surf2:      #111f30;
      --surf3:      #162742;
      --bdr:        #162742;
      --bdr2:       #1e3350;
      --bdr3:       #274666;
      --dim:        #344e66;
      --muted:      #5a7a96;
      --text:       #8dafc8;
      --text2:      #adc8de;
      --hi:         #cfe3f2;
      --accent:     #00a8e4;
      --accent-bg:  rgba(0,168,228,.14);
      --accent-glo: rgba(0,168,228,.30);
      --green:      #00d46e;
      --green-bg:   rgba(0,212,110,.12);
      --red:        #ff3c3c;
      --red-bg:     rgba(255,60,60,.12);
      --orange:     #ff9b00;
      --yellow:     #f0cc00;
      --purple:     #b088ff;
      --purple-bg:  rgba(176,136,255,.12);
      --mono:       'Consolas','Courier New',monospace;
    }

    html, body {
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
      font-size: 13px;
      line-height: 1.4;
      height: 100%;
    }

    #root {
      display: flex;
      flex-direction: column;
      min-height: 100vh;
      max-width: 1380px;
      margin: 0 auto;
      padding: 10px 12px;
      gap: 8px;
    }

    /* ── Scrollbar ──────────────────────────────────── */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: var(--bg); }
    ::-webkit-scrollbar-thumb { background: var(--bdr2); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--accent); }

    /* ── Header ─────────────────────────────────────── */
    .hdr {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 9px 16px;
      background: var(--surf);
      border: 1px solid var(--bdr);
      border-top: 2px solid var(--accent);
      border-radius: 5px;
    }
    .hdr-left { display: flex; flex-direction: column; gap: 2px; }
    .hdr-title {
      font-family: var(--mono);
      font-size: 15px;
      font-weight: bold;
      letter-spacing: 3px;
      color: var(--accent);
      text-shadow: 0 0 16px var(--accent-glo);
    }
    .hdr-sub {
      font-family: var(--mono);
      font-size: 9px;
      letter-spacing: 2px;
      color: var(--dim);
    }
    .hdr-right { display: flex; align-items: center; gap: 10px; }
    .status-pill {
      display: flex;
      align-items: center;
      gap: 7px;
      padding: 4px 10px;
      background: var(--surf2);
      border: 1px solid var(--bdr2);
      border-radius: 20px;
      font-family: var(--mono);
      font-size: 10px;
      color: var(--muted);
      letter-spacing: 1px;
    }
    .dot {
      width: 7px; height: 7px;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 6px var(--green);
      flex-shrink: 0;
    }
    .dot.loading { background: var(--orange); box-shadow: 0 0 6px var(--orange); animation: blink .7s infinite; }
    .dot.error   { background: var(--red);    box-shadow: 0 0 6px var(--red); }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }

    /* ── Grid ───────────────────────────────────────── */
    .grid {
      display: grid;
      grid-template-columns: 270px 1fr;
      gap: 8px;
      flex: 1;
      min-height: 0;
    }

    /* ── Panel ──────────────────────────────────────── */
    .panel {
      background: var(--surf);
      border: 1px solid var(--bdr);
      border-radius: 5px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .phead {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 7px 14px;
      background: var(--surf2);
      border-bottom: 1px solid var(--bdr);
      font-family: var(--mono);
      font-size: 9px;
      letter-spacing: 2.5px;
      color: var(--muted);
      flex-shrink: 0;
    }
    .phead .bar {
      width: 3px; height: 12px;
      background: var(--accent);
      border-radius: 2px;
      box-shadow: 0 0 6px var(--accent);
    }
    .pbody { padding: 12px 14px; overflow-y: auto; flex: 1; }

    /* ── Field rows ─────────────────────────────────── */
    .field {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 7px 0;
      border-bottom: 1px solid var(--bdr);
    }
    .field:last-child { border-bottom: none; }
    .flabel {
      font-size: 12px;
      color: var(--text);
      flex: 1;
      min-width: 0;
    }
    .flabel small {
      display: block;
      font-size: 9px;
      color: var(--dim);
      margin-top: 1px;
      letter-spacing: .5px;
    }

    .sec {
      font-family: var(--mono);
      font-size: 8px;
      letter-spacing: 2px;
      color: var(--dim);
      padding: 10px 0 3px;
      border-bottom: 1px solid var(--bdr);
      margin-bottom: 0;
    }

    /* ── Select ─────────────────────────────────────── */
    select.sel {
      background: var(--surf2);
      border: 1px solid var(--bdr2);
      color: var(--hi);
      font-family: var(--mono);
      font-size: 11px;
      padding: 4px 22px 4px 8px;
      border-radius: 3px;
      cursor: pointer;
      appearance: none;
      -webkit-appearance: none;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath fill='%235a7a96' d='M0 0l4 5 4-5z'/%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: right 7px center;
      min-width: 88px;
      flex-shrink: 0;
    }
    select.sel:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-bg); }
    select.sel option { background: #111f30; }

    /* ── Toggle ─────────────────────────────────────── */
    .tog { position: relative; width: 36px; height: 19px; flex-shrink: 0; }
    .tog input { opacity: 0; width: 0; height: 0; position: absolute; }
    .track {
      position: absolute; inset: 0;
      background: var(--surf3);
      border: 1px solid var(--bdr2);
      border-radius: 19px;
      cursor: pointer;
      transition: background .2s, border-color .2s;
    }
    .track::after {
      content: '';
      position: absolute;
      left: 2px; top: 50%;
      transform: translateY(-50%);
      width: 13px; height: 13px;
      background: var(--dim);
      border-radius: 50%;
      transition: left .2s, background .2s;
    }
    .tog input:checked + .track { background: var(--accent); border-color: var(--accent); }
    .tog input:checked + .track::after { left: calc(100% - 15px); background: #fff; }

    /* ── Slider ─────────────────────────────────────── */
    .slwrap { display: flex; align-items: center; gap: 8px; }
    .slval {
      font-family: var(--mono);
      font-size: 11px;
      color: var(--hi);
      min-width: 36px;
      text-align: right;
    }
    input[type=range] {
      -webkit-appearance: none;
      width: 110px; height: 3px;
      background: var(--bdr2);
      border-radius: 2px;
      outline: none;
      cursor: pointer;
    }
    input[type=range]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 13px; height: 13px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 8px var(--accent-bg);
      cursor: pointer;
    }
    input[type=range]::-moz-range-thumb {
      width: 13px; height: 13px;
      border-radius: 50%;
      background: var(--accent);
      border: none;
    }

    /* ── Bet table ──────────────────────────────────── */
    .btbl { width: 100%; border-collapse: collapse; font-family: var(--mono); }
    .btbl th {
      padding: 5px 8px;
      text-align: left;
      font-size: 9px;
      letter-spacing: 1.5px;
      color: var(--dim);
      font-weight: normal;
      border-bottom: 1px solid var(--bdr2);
    }
    .btbl td { padding: 3px 8px; border-bottom: 1px solid var(--bdr); }
    .btbl tbody tr:last-child td { border-bottom: none; }
    .btbl tbody tr:hover td { background: rgba(0,168,228,.03); }

    .tc-lbl { font-size: 12px; color: var(--text2); }
    .tc-lbl.pos { color: var(--green); }
    .tc-lbl.neu { color: var(--dim); }
    .tc-lbl.neg { color: var(--red); }
    .wong-tag {
      font-size: 8px;
      color: var(--dim);
      letter-spacing: 1px;
      margin-left: 5px;
    }

    .bet-inp {
      background: var(--surf2);
      border: 1px solid var(--bdr2);
      color: var(--hi);
      font-family: var(--mono);
      font-size: 12px;
      padding: 3px 6px;
      border-radius: 3px;
      width: 68px;
      text-align: right;
    }
    .bet-inp:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-bg); }
    .bet-inp.zero { color: var(--dim); border-color: var(--bdr); }
    .eff-bet { font-size: 9px; color: var(--accent); margin-left: 5px; }

    .twox {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 30px; height: 19px;
      background: var(--surf2);
      border: 1px solid var(--bdr2);
      border-radius: 3px;
      color: var(--dim);
      font-family: var(--mono);
      font-size: 9px;
      cursor: pointer;
      transition: all .2s;
      user-select: none;
    }
    .twox:disabled { opacity: .4; cursor: default; }
    .twox.on { background: var(--accent-bg); border-color: var(--accent); color: var(--accent); box-shadow: 0 0 6px var(--accent-bg); }

    .rm-btn {
      background: none; border: none;
      color: var(--dim);
      cursor: pointer;
      padding: 2px 5px;
      font-size: 14px;
      border-radius: 3px;
      line-height: 1;
      transition: color .2s;
    }
    .rm-btn:hover { color: var(--red); }
    .rm-btn:disabled { opacity: .2; cursor: default; }

    .add-btn {
      display: flex;
      align-items: center;
      gap: 6px;
      background: none;
      border: 1px dashed var(--bdr2);
      color: var(--dim);
      cursor: pointer;
      padding: 6px 12px;
      border-radius: 3px;
      font-family: var(--mono);
      font-size: 9px;
      letter-spacing: 1px;
      margin-top: 8px;
      width: 100%;
      transition: all .2s;
    }
    .add-btn:hover { border-color: var(--green); color: var(--green); }

    .bet-hint {
      font-family: var(--mono);
      font-size: 9px;
      color: var(--dim);
      margin-top: 10px;
      line-height: 1.6;
    }

    /* ── Controls bar ───────────────────────────────── */
    .cbar {
      display: flex;
      align-items: center;
      gap: 18px;
      padding: 9px 16px;
      background: var(--surf);
      border: 1px solid var(--bdr);
      border-radius: 5px;
      flex-wrap: wrap;
    }
    .cgrp { display: flex; align-items: center; gap: 7px; }
    .clbl { font-size: 11px; color: var(--text); white-space: nowrap; }
    .cinp {
      background: var(--surf2);
      border: 1px solid var(--bdr2);
      color: var(--hi);
      font-family: var(--mono);
      font-size: 12px;
      padding: 5px 9px;
      border-radius: 3px;
      width: 96px;
      text-align: right;
    }
    .cinp:focus { outline: none; border-color: var(--accent); }
    .sep { width: 1px; height: 24px; background: var(--bdr2); flex-shrink: 0; }

    .run-btn {
      display: flex;
      align-items: center;
      gap: 7px;
      padding: 6px 16px;
      background: var(--accent-bg);
      border: 1px solid var(--accent);
      color: var(--accent);
      font-family: var(--mono);
      font-size: 10px;
      letter-spacing: 1px;
      border-radius: 4px;
      cursor: pointer;
      transition: all .2s;
      margin-left: auto;
      flex-shrink: 0;
    }
    .run-btn:hover:not(:disabled) { background: rgba(0,168,228,.22); box-shadow: 0 0 12px var(--accent-bg); }
    .run-btn:disabled { opacity: .5; cursor: not-allowed; }

    .spin {
      width: 10px; height: 10px;
      border: 2px solid transparent;
      border-top-color: currentColor;
      border-radius: 50%;
      animation: spin .6s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    .err-tag {
      font-family: var(--mono);
      font-size: 10px;
      color: var(--red);
      background: var(--red-bg);
      border: 1px solid rgba(255,60,60,.3);
      border-radius: 3px;
      padding: 4px 10px;
    }

    /* ── Results bar ────────────────────────────────── */
    .rbar {
      display: grid;
      grid-template-columns: repeat(4, 1fr) 130px;
      gap: 8px;
      padding: 0;
    }
    .mc {
      background: var(--surf);
      border: 1px solid var(--bdr);
      border-radius: 5px;
      padding: 10px 14px;
      position: relative;
      overflow: hidden;
    }
    .mc::after {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 2px;
      background: var(--bdr2);
      transition: background .3s;
    }
    .mc.pos::after { background: var(--green); }
    .mc.neg::after { background: var(--red); }
    .mc.warn::after { background: var(--orange); }
    .mc.info::after { background: var(--accent); }

    .mc-lbl {
      font-family: var(--mono);
      font-size: 8px;
      letter-spacing: 2px;
      color: var(--dim);
      margin-bottom: 5px;
    }
    .mc-val {
      font-family: var(--mono);
      font-size: 21px;
      font-weight: bold;
      color: var(--hi);
      line-height: 1;
      white-space: nowrap;
    }
    .mc-val.pos { color: var(--green); text-shadow: 0 0 12px var(--green-bg); }
    .mc-val.neg { color: var(--red); }
    .mc-val.warn { color: var(--orange); }
    .mc-val.placeholder { color: var(--dim); font-size: 16px; }
    .mc-sub {
      font-family: var(--mono);
      font-size: 9px;
      color: var(--dim);
      margin-top: 3px;
    }

    .vbtn {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 5px;
      background: var(--surf);
      border: 1px solid var(--bdr);
      border-radius: 5px;
      color: var(--muted);
      font-family: var(--mono);
      font-size: 9px;
      letter-spacing: 1px;
      cursor: pointer;
      padding: 8px;
      transition: all .25s;
    }
    .vbtn:hover:not(:disabled) {
      border-color: var(--purple);
      color: var(--purple);
      background: var(--purple-bg);
      box-shadow: 0 0 14px var(--purple-bg);
    }
    .vbtn:disabled { opacity: .35; cursor: not-allowed; }
    .vbtn .vi { font-size: 22px; }

    /* ── Stats strip ─────────────────────────────────── */
    .strip {
      display: flex;
      align-items: center;
      gap: 20px;
      padding: 7px 14px;
      background: var(--surf);
      border: 1px solid var(--bdr);
      border-radius: 5px;
      font-family: var(--mono);
      font-size: 10px;
      color: var(--muted);
      flex-wrap: wrap;
    }
    .strip span { white-space: nowrap; }
    .strip .sv { color: var(--text2); }
    .strip .sp { color: var(--green); }
    .strip .sn { color: var(--red); }
    .strip .sa { color: var(--accent); }

    /* ── Modal ──────────────────────────────────────── */
    .mbd {
      position: fixed; inset: 0;
      background: rgba(4,8,18,.87);
      backdrop-filter: blur(4px);
      z-index: 200;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .modal {
      background: var(--surf);
      border: 1px solid var(--bdr2);
      border-radius: 7px;
      width: 100%;
      max-width: 920px;
      max-height: 92vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .mhdr {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 18px;
      background: var(--surf2);
      border-bottom: 1px solid var(--bdr);
      flex-shrink: 0;
    }
    .mtitle {
      font-family: var(--mono);
      font-size: 11px;
      letter-spacing: 2px;
      color: var(--purple);
    }
    .mclose {
      background: none;
      border: 1px solid var(--bdr2);
      color: var(--muted);
      width: 26px; height: 26px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all .2s;
    }
    .mclose:hover { border-color: var(--red); color: var(--red); }

    .mbody {
      padding: 16px 18px;
      overflow-y: auto;
      flex: 1;
    }

    .mfoot {
      display: flex;
      gap: 24px;
      padding: 10px 18px;
      background: var(--surf2);
      border-top: 1px solid var(--bdr);
      flex-shrink: 0;
      flex-wrap: wrap;
    }
    .mstat { display: flex; flex-direction: column; gap: 2px; }
    .mslbl { font-family: var(--mono); font-size: 8px; letter-spacing: 1.5px; color: var(--dim); }
    .msval { font-family: var(--mono); font-size: 14px; color: var(--hi); }
    .msval.danger { color: var(--red); }
    .msval.good   { color: var(--green); }

    .chart-legend-note {
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 10px;
      font-family: var(--mono);
      font-size: 9px;
      color: var(--dim);
    }
    .lni { display: flex; align-items: center; gap: 5px; }
    .lnb { display: inline-block; width: 18px; height: 2px; border-radius: 1px; }

    .loading-state {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      padding: 70px 40px;
      color: var(--muted);
      font-family: var(--mono);
      font-size: 11px;
    }
    .lspin {
      width: 22px; height: 22px;
      border: 2px solid var(--bdr2);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin .8s linear infinite;
    }

    /* ── Recharts theme overrides ───────────────────── */
    .recharts-cartesian-grid line { stroke: #162742 !important; }
    .recharts-tooltip-wrapper * { font-family: 'Consolas','Courier New',monospace !important; }
  </style>
</head>
<body>
<div id="root"></div>

<script type="text/babel">
const { useState, useEffect, useRef, useCallback, useMemo } = React;
const {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine, ResponsiveContainer
} = Recharts;

const API = typeof window !== 'undefined' && window.location.hostname !== 'localhost'
  ? ''   // production: use relative /api/... path (same origin via Vercel routing)
  : 'http://localhost:8000';

/* ─── Formatters ─────────────────────────────────────────────────────────── */
const fmtDollar  = (v, d=0) => v == null ? '—' : '$' + Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d });
const fmtSigned  = (v, d=0) => v == null ? '—' : (v >= 0 ? '+' : '−') + fmtDollar(v, d);
const fmtPct     = (v, d=2) => v == null ? '—' : (v * 100).toFixed(d) + '%';

/* ─── Toggle ─────────────────────────────────────────────────────────────── */
const Toggle = ({ checked, onChange }) => (
  <label className="tog">
    <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
    <span className="track" />
  </label>
);

/* ─── Custom Chart Tooltip ───────────────────────────────────────────────── */
const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload || !payload.length) return null;
  const meta = {
    p5:  { label: '5th %ile',  color: '#ef4444' },
    p25: { label: '25th %ile', color: '#fb923c' },
    p50: { label: 'Median',    color: '#38bdf8' },
    p75: { label: '75th %ile', color: '#34d399' },
    p95: { label: '95th %ile', color: '#b088ff' },
    ev:  { label: 'EV line',   color: '#00d46e' },
  };
  return (
    <div style={{ background:'#0c1a2e', border:'1px solid #1e3350', borderRadius:4, padding:'8px 12px' }}>
      <div style={{ fontFamily:'var(--mono)', fontSize:10, color:'#8dafc8', marginBottom:6 }}>
        Hour {Math.round(label)}
      </div>
      {payload
        .filter(p => meta[p.dataKey])
        .map(p => (
          <div key={p.dataKey} style={{ display:'flex', justifyContent:'space-between', gap:20, fontFamily:'var(--mono)', fontSize:10, color: meta[p.dataKey].color }}>
            <span>{meta[p.dataKey].label}</span>
            <span>${Math.round(p.value).toLocaleString()}</span>
          </div>
        ))
      }
    </div>
  );
};

/* ─── Variance Modal ─────────────────────────────────────────────────────── */
const VIZ_HOURS    = 1000;   // time horizon sent to the API
const VIZ_PATHS    = 300;    // number of random-walk paths
const VIZ_SHOES    = 10_000; // base simulation shoes for EV/SD

const VarianceModal = ({ data, bankroll, loading, error, elapsed, onClose }) => {
  const chartData = useMemo(() => {
    if (!data) return [];
    return data.hours.map((h, i) => ({
      hour: Math.round(h * 10) / 10,
      p5:   Math.max(0, Math.round(data.percentile_curves['5'][i])),
      p25:  Math.max(0, Math.round(data.percentile_curves['25'][i])),
      p50:  Math.max(0, Math.round(data.percentile_curves['50'][i])),
      p75:  Math.max(0, Math.round(data.percentile_curves['75'][i])),
      p95:  Math.max(0, Math.round(data.percentile_curves['95'][i])),
      ev:   Math.max(0, Math.round(data.ev_curve[i])),
    }));
  }, [data]);

  const yDomain = useMemo(() => {
    if (!data) return ['auto', 'auto'];
    const flat = [
      ...data.percentile_curves['5'],
      ...data.percentile_curves['95'],
    ].filter(v => v > 0);
    if (!flat.length) return [0, bankroll * 2];
    const lo = Math.floor(Math.min(...flat) / 5000) * 5000;
    const hi = Math.ceil(Math.max(...flat) / 5000) * 5000;
    return [Math.max(0, lo), hi];
  }, [data, bankroll]);

  const endMedian = chartData.length > 0 ? chartData[chartData.length - 1].p50 : null;
  const rorPct = data ? (data.ruin_probability * 100).toFixed(1) + '%' : '—';

  return (
    <div className="mbd" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal">

        <div className="mhdr">
          <span className="mtitle">◈ VARIANCE VISUALIZER</span>
          <button className="mclose" onClick={onClose}>✕</button>
        </div>

        <div className="mbody">
          {loading && (
            <div className="loading-state">
              <div className="lspin" />
              <span>
                Simulating {VIZ_SHOES.toLocaleString()} shoes + {VIZ_PATHS} random walks…
                {elapsed > 0 && <span style={{ color:'var(--accent)', marginLeft:8 }}>{elapsed}s</span>}
              </span>
            </div>
          )}
          {error && (
            <div className="loading-state" style={{ color:'var(--red)' }}>
              ⚠ {error}
            </div>
          )}
          {!loading && !error && data && (
            <>
              <ResponsiveContainer width="100%" height={360}>
                <LineChart data={chartData} margin={{ top: 8, right: 16, left: 8, bottom: 16 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#162742" />
                  <XAxis
                    dataKey="hour"
                    stroke="#344e66"
                    tick={{ fill:'#5a7a96', fontSize:10, fontFamily:'Consolas,monospace' }}
                    label={{ value:'Hours of play', position:'insideBottom', offset:-8, fill:'#344e66', fontSize:10, fontFamily:'Consolas,monospace' }}
                  />
                  <YAxis
                    domain={yDomain}
                    stroke="#344e66"
                    tickFormatter={v => '$' + (v >= 1000 ? (v/1000).toFixed(0)+'k' : v)}
                    tick={{ fill:'#5a7a96', fontSize:10, fontFamily:'Consolas,monospace' }}
                    width={58}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Legend
                    wrapperStyle={{ paddingTop:8, fontSize:10, fontFamily:'Consolas,monospace' }}
                    formatter={(value, entry) => (
                      <span style={{ color: entry.color }}>{value}</span>
                    )}
                  />

                  {/* Starting bankroll reference */}
                  <ReferenceLine
                    y={bankroll}
                    stroke="#1e3350"
                    strokeDasharray="6 3"
                    label={{ value:'Start', position:'right', fill:'#344e66', fontSize:9, fontFamily:'Consolas,monospace' }}
                  />

                  {/* Outer percentiles — dashed */}
                  <Line type="monotone" dataKey="p5"  name="5th %ile"  stroke="#ef4444" strokeWidth={1}   dot={false} strokeDasharray="5 3" />
                  <Line type="monotone" dataKey="p95" name="95th %ile" stroke="#b088ff" strokeWidth={1}   dot={false} strokeDasharray="5 3" />

                  {/* Inner percentiles */}
                  <Line type="monotone" dataKey="p25" name="25th %ile" stroke="#fb923c" strokeWidth={1.5} dot={false} />
                  <Line type="monotone" dataKey="p75" name="75th %ile" stroke="#34d399" strokeWidth={1.5} dot={false} />

                  {/* Median — bold */}
                  <Line type="monotone" dataKey="p50" name="Median"    stroke="#38bdf8" strokeWidth={3}   dot={false} />

                  {/* EV line — dotted */}
                  <Line type="monotone" dataKey="ev"  name="EV line"   stroke="#00d46e" strokeWidth={1.5} dot={false} strokeDasharray="3 6" />
                </LineChart>
              </ResponsiveContainer>

              <div className="chart-legend-note">
                <span className="lni"><span className="lnb" style={{background:'#38bdf8',height:3}}/>Median: half of sessions finish above this line</span>
                <span className="lni"><span className="lnb" style={{background:'#34d399'}}/>75th %ile: 75% of sessions finish above this</span>
                <span className="lni"><span className="lnb" style={{background:'#ef4444'}}/>5th %ile: worst-case floor (5% of sessions)</span>
                <span className="lni"><span className="lnb" style={{background:'#00d46e',borderTop:'1px dashed #00d46e',height:1}}/>EV: theoretical expected value</span>
              </div>
            </>
          )}
        </div>

        {(data || loading) && (
          <div className="mfoot">
            <div className="mstat">
              <span className="mslbl">RUIN PROBABILITY</span>
              <span className={`msval ${data && data.ruin_probability > 0.1 ? 'danger' : 'good'}`}>{rorPct}</span>
            </div>
            <div className="mstat">
              <span className="mslbl">PATHS SIMULATED</span>
              <span className="msval">{data ? VIZ_PATHS.toLocaleString() : '…'}</span>
            </div>
            <div className="mstat">
              <span className="mslbl">HORIZON</span>
              <span className="msval">{VIZ_HOURS.toLocaleString()} hrs</span>
            </div>
            <div className="mstat">
              <span className="mslbl">SHOES SIMULATED</span>
              <span className="msval">{data ? VIZ_SHOES.toLocaleString() : '…'}</span>
            </div>
            {endMedian != null && (
              <div className="mstat" style={{ marginLeft:'auto' }}>
                <span className="mslbl">MEDIAN OUTCOME (END)</span>
                <span className="msval good">${endMedian.toLocaleString()}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

/* ─── Main App ───────────────────────────────────────────────────────────── */
const App = () => {
  /* ── state ── */
  const [rules, setRules] = useState({
    decks: 6, penetration: 0.75,
    h17: true, das: true, surrender: true, rsa: false,
    maxSplits: 3, bjPayout: 1.5,
  });

  const [betRows, setBetRows] = useState([
    { tc: 0,  bet: 0,   twoX: false },
    { tc: 1,  bet: 25,  twoX: false },
    { tc: 2,  bet: 50,  twoX: false },
    { tc: 3,  bet: 100, twoX: false },
    { tc: 4,  bet: 150, twoX: true  },
    { tc: 5,  bet: 200, twoX: true  },
    { tc: 6,  bet: 200, twoX: true  },
  ]);

  const [bankroll,   setBankroll]   = useState(25000);
  const [rph,        setRph]        = useState(100);
  const [numShoes,   setNumShoes]   = useState(3000);
  const [results,    setResults]    = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState(null);
  const [showViz,    setShowViz]    = useState(false);
  const [vizData,    setVizData]    = useState(null);
  const [vizLoading, setVizLoading] = useState(false);
  const [vizError,   setVizError]   = useState(null);
  const [vizElapsed, setVizElapsed] = useState(0);
  const debounce  = useRef(null);
  const simAbort  = useRef(null);   // AbortController for /simulate
  const vizAbort  = useRef(null);   // AbortController for /variance-visual
  const vizTimer  = useRef(null);   // setInterval for elapsed counter

  /* ── helpers ── */
  const buildSpread = useCallback(() => {
    const spread = {};
    let hasPos = false;
    betRows.forEach(row => {
      const eff = row.twoX && row.bet > 0 ? row.bet * 2 : row.bet;
      spread[String(row.tc)] = eff;
      if (eff > 0) hasPos = true;
    });
    return hasPos ? spread : null;
  }, [betRows]);

  const buildBody = useCallback((extraShoes) => ({
    rules: {
      decks: rules.decks,
      penetration: rules.penetration,
      h17: rules.h17,
      das: rules.das,
      rsa: rules.rsa,
      max_splits: rules.maxSplits,
      surrender: rules.surrender,
      bj_payout: rules.bjPayout,
    },
    bet_spread: buildSpread(),
    bankroll,
    rounds_per_hour: rph,
    num_shoes: extraShoes || numShoes,
    seed: null,
  }), [rules, buildSpread, bankroll, rph, numShoes]);

  /* ── fetch with timeout helper ── */
  const fetchWithTimeout = useCallback(async (url, options, timeoutMs, abortRef) => {
    // Cancel any in-flight request for this slot.
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const resp = await fetch(url, { ...options, signal: controller.signal });
      clearTimeout(timer);
      return resp;
    } catch (e) {
      clearTimeout(timer);
      if (e.name === 'AbortError') throw new Error('Request timed out — try fewer shoes or a smaller bankroll.');
      throw e;
    }
  }, []);

  /* ── simulation ── */
  const runSim = useCallback(async () => {
    const spread = buildSpread();
    if (!spread) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetchWithTimeout(
        `${API}/simulate`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildBody()) },
        120_000,   // 2-minute hard limit
        simAbort,
      );
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      setResults(await resp.json());
    } catch (e) {
      if (e.name === 'AbortError') return;   // cancelled by a newer request — silently ignore
      const msg = e.message;
      setError(
        msg.toLowerCase().includes('fetch') || msg.toLowerCase().includes('networkerror')
          ? 'Cannot reach backend — is it running on :8000?'
          : msg,
      );
    } finally {
      setLoading(false);
    }
  }, [buildBody, buildSpread, fetchWithTimeout]);

  /* ── debounced auto-run ── */
  useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(runSim, 750);
    return () => clearTimeout(debounce.current);
  }, [runSim]);

  /* ── variance visualizer ── */
  const openViz = async () => {
    if (!results) return;
    setShowViz(true);
    setVizData(null);
    setVizError(null);
    setVizElapsed(0);
    setVizLoading(true);

    // Start elapsed-seconds ticker.
    const startTs = Date.now();
    clearInterval(vizTimer.current);
    vizTimer.current = setInterval(() => {
      setVizElapsed(Math.floor((Date.now() - startTs) / 1000));
    }, 1000);

    try {
      const body = {
        ...buildBody(VIZ_SHOES),
        seed: 42,
        hours: VIZ_HOURS,
        num_paths: VIZ_PATHS,
        percentiles: [5, 25, 50, 75, 95],
      };
      const resp = await fetchWithTimeout(
        `${API}/variance-visual`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
        240_000,   // 4-minute hard limit for 10k-shoe + 1000-hr walk
        vizAbort,
      );
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      setVizData(await resp.json());
    } catch (e) {
      setVizError(e.message.toLowerCase().includes('fetch') || e.message.toLowerCase().includes('networkerror')
        ? 'Cannot reach backend — is it running on :8000?'
        : e.message);
    } finally {
      clearInterval(vizTimer.current);
      setVizLoading(false);
    }
  };

  /* ── clean up on unmount ── */
  useEffect(() => {
    return () => {
      clearInterval(vizTimer.current);
      if (simAbort.current) simAbort.current.abort();
      if (vizAbort.current) vizAbort.current.abort();
    };
  }, []);

  /* ── rule / row mutators ── */
  const setRule   = (k, v) => setRules(r => ({ ...r, [k]: v }));
  const setRow    = (i, k, v) => setBetRows(rows => rows.map((r, j) => j === i ? { ...r, [k]: v } : r));
  const removeRow = (i) => setBetRows(rows => rows.filter((_, j) => j !== i));
  const addRow    = () => {
    const maxTc  = Math.max(...betRows.map(r => r.tc));
    const lastBet = betRows[betRows.length - 1]?.bet ?? 200;
    setBetRows(rows => [...rows, { tc: maxTc + 1, bet: lastBet, twoX: true }]);
  };

  /* ── derived display values ── */
  const ev   = results?.ev_per_hour;
  const sd   = results?.std_dev_per_hour;
  const ror  = results?.risk_of_ruin;
  const n0   = results?.hours_to_n0;

  const evCls  = ev  == null ? ''     : ev  > 0       ? 'pos' : 'neg';
  const rorCls = ror == null ? 'info' : ror > 0.15    ? 'neg' : ror > 0.05 ? 'warn' : 'pos';
  const dotCls = loading ? 'loading' : error ? 'error' : '';

  const edgeEntries = results
    ? Object.entries(results.edge_by_tc)
        .map(([k, v]) => [Number(k), v])
        .filter(([tc]) => tc >= 1 && tc <= 7)
        .sort(([a], [b]) => a - b)
    : [];

  return (
    <>
      {/* ── Header ─────────────────────────────────────── */}
      <div className="hdr">
        <div className="hdr-left">
          <div className="hdr-title">BLACKJACK OPTIMIZER</div>
          <div className="hdr-sub">HI-LO COUNTING SIMULATOR · CVCX-STYLE METRICS · ILLUSTRIOUS 18 + FAB 4</div>
        </div>
        <div className="hdr-right">
          <div className="status-pill">
            <span className={`dot ${dotCls}`} />
            {loading ? 'SIMULATING' : error ? 'ERROR' : results ? 'READY' : 'WAITING'}
          </div>
        </div>
      </div>

      {/* ── Main two-column grid ────────────────────────── */}
      <div className="grid">

        {/* LEFT — Game Rules */}
        <div className="panel">
          <div className="phead">
            <span className="bar" />
            GAME RULES
          </div>
          <div className="pbody">

            <div className="field">
              <span className="flabel">Decks</span>
              <select className="sel" value={rules.decks} onChange={e => setRule('decks', Number(e.target.value))}>
                {[1, 2, 4, 6, 8].map(d => <option key={d} value={d}>{d} Deck{d > 1 ? 's' : ''}</option>)}
              </select>
            </div>

            <div className="field">
              <span className="flabel">
                Penetration
                <small>shoe depth dealt before reshuffle</small>
              </span>
              <div className="slwrap">
                <input type="range" min={50} max={92} step={1}
                  value={Math.round(rules.penetration * 100)}
                  onChange={e => setRule('penetration', Number(e.target.value) / 100)}
                />
                <span className="slval">{Math.round(rules.penetration * 100)}%</span>
              </div>
            </div>

            <div className="sec">DEALER RULES</div>

            <div className="field">
              <span className="flabel">
                Hits Soft 17
                <small>H17 costs player ~0.20%</small>
              </span>
              <Toggle checked={rules.h17} onChange={v => setRule('h17', v)} />
            </div>

            <div className="sec">PLAYER OPTIONS</div>

            <div className="field">
              <span className="flabel">
                Double After Split
                <small>DAS saves player ~0.14%</small>
              </span>
              <Toggle checked={rules.das} onChange={v => setRule('das', v)} />
            </div>

            <div className="field">
              <span className="flabel">
                Late Surrender
                <small>saves ~0.08%</small>
              </span>
              <Toggle checked={rules.surrender} onChange={v => setRule('surrender', v)} />
            </div>

            <div className="field">
              <span className="flabel">
                Re-split Aces
                <small>saves ~0.06%</small>
              </span>
              <Toggle checked={rules.rsa} onChange={v => setRule('rsa', v)} />
            </div>

            <div className="sec">PAYOUTS &amp; LIMITS</div>

            <div className="field">
              <span className="flabel">
                Blackjack Payout
                <small>6:5 costs ~1.39% vs 3:2</small>
              </span>
              <select className="sel" value={rules.bjPayout} onChange={e => setRule('bjPayout', Number(e.target.value))}>
                <option value={1.5}>3 : 2</option>
                <option value={1.2}>6 : 5</option>
              </select>
            </div>

            <div className="field">
              <span className="flabel">Max Splits</span>
              <select className="sel" value={rules.maxSplits} onChange={e => setRule('maxSplits', Number(e.target.value))}>
                {[1,2,3,4].map(n => <option key={n} value={n}>{n + 1} Hands</option>)}
              </select>
            </div>

          </div>
        </div>

        {/* RIGHT — Bet Spread */}
        <div className="panel">
          <div className="phead">
            <span className="bar" style={{ background:'var(--green)', boxShadow:'0 0 6px var(--green-bg)' }} />
            BET SPREAD
          </div>
          <div className="pbody">
            <table className="btbl">
              <thead>
                <tr>
                  <th>TRUE COUNT</th>
                  <th>BET SIZE</th>
                  <th title="Play two simultaneous spots — doubles effective bet">2X HANDS</th>
                  <th style={{ width: 28 }} />
                </tr>
              </thead>
              <tbody>
                {betRows.map((row, i) => {
                  const tcClass = row.tc > 0 ? 'pos' : row.tc === 0 ? 'neu' : 'neg';
                  const tcLabel = row.tc === 0 ? 'TC ≤ 0' : `TC ${row.tc > 0 ? '+' : ''}${row.tc}`;
                  return (
                    <tr key={i}>
                      <td>
                        <span className={`tc-lbl ${tcClass}`}>{tcLabel}</span>
                        {row.bet === 0 && <span className="wong-tag">WONG OUT</span>}
                      </td>
                      <td>
                        <span style={{ color:'var(--dim)', fontFamily:'var(--mono)', marginRight:2 }}>$</span>
                        <input
                          type="number" min={0} step={5}
                          className={`bet-inp${row.bet === 0 ? ' zero' : ''}`}
                          value={row.bet}
                          onChange={e => setRow(i, 'bet', Math.max(0, Math.round(Number(e.target.value) / 5) * 5))}
                        />
                        {row.twoX && row.bet > 0 && (
                          <span className="eff-bet">= ${(row.bet * 2).toLocaleString()} eff.</span>
                        )}
                      </td>
                      <td>
                        <button
                          className={`twox${row.twoX ? ' on' : ''}`}
                          onClick={() => setRow(i, 'twoX', !row.twoX)}
                          disabled={row.bet === 0}
                          title="Play two spots (doubles effective bet)"
                        >2X</button>
                      </td>
                      <td>
                        <button
                          className="rm-btn"
                          onClick={() => removeRow(i)}
                          disabled={betRows.length <= 2}
                          title="Remove this count level"
                        >×</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            <button className="add-btn" onClick={addRow}>
              <span style={{ fontSize:14, lineHeight:1 }}>+</span> ADD COUNT LEVEL
            </button>

            <div className="bet-hint">
              Bet = $0 at a count → wong out (skip round, keep counting).<br />
              2X plays two hands simultaneously, doubling effective exposure.<br />
              Deviations: Illustrious 18 + Fab 4 applied automatically.
            </div>
          </div>
        </div>
      </div>

      {/* ── Controls bar ─────────────────────────────────── */}
      <div className="cbar">
        <div className="cgrp">
          <span className="clbl">Bankroll</span>
          <input type="number" className="cinp" step={1000} min={100}
            value={bankroll}
            onChange={e => setBankroll(Math.max(100, Number(e.target.value)))} />
        </div>

        <div className="sep" />

        <div className="cgrp">
          <span className="clbl">Rounds / hr</span>
          <input type="number" className="cinp" style={{ width:72 }} step={10} min={10} max={400}
            value={rph}
            onChange={e => setRph(Math.max(10, Number(e.target.value)))} />
          <span style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--dim)' }}>
            {rph >= 180 ? '1 player' : rph >= 115 ? '2 players' : rph >= 80 ? '3 players' : rph >= 60 ? '4 players' : '5+ players'}
          </span>
        </div>

        <div className="sep" />

        <div className="cgrp">
          <span className="clbl">Accuracy</span>
          <select className="sel" value={numShoes} onChange={e => setNumShoes(Number(e.target.value))}>
            <option value={500}>Quick  (500 shoes)</option>
            <option value={3000}>Standard (3k)</option>
            <option value={10000}>Detailed (10k)</option>
          </select>
        </div>

        {error && <span className="err-tag">⚠ {error}</span>}

        <button className="run-btn" onClick={runSim} disabled={loading}>
          {loading
            ? <><span className="spin" />&nbsp;Simulating…</>
            : '▶  RUN SIMULATION'
          }
        </button>
      </div>

      {/* ── Results bar ──────────────────────────────────── */}
      <div className="rbar">

        {/* EV / hr */}
        <div className={`mc ${evCls}`}>
          <div className="mc-lbl">EV / HOUR</div>
          <div className={`mc-val ${loading ? 'placeholder' : evCls}`}>
            {loading ? '…' : ev == null ? '—' : fmtSigned(ev)}
          </div>
          {results && (
            <div className="mc-sub">
              {fmtSigned(results.ev_per_hand, 2)} / hand
            </div>
          )}
        </div>

        {/* 1 SD / hr */}
        <div className="mc info">
          <div className="mc-lbl">1 STD DEVIATION / HR</div>
          <div className={`mc-val ${loading ? 'placeholder' : ''}`}>
            {loading ? '…' : sd == null ? '—' : '±' + fmtDollar(sd)}
          </div>
          {results && (
            <div className="mc-sub">
              ±{fmtDollar(results.std_dev_per_hand, 2)} / hand
            </div>
          )}
        </div>

        {/* Risk of Ruin */}
        <div className={`mc ${rorCls}`}>
          <div className="mc-lbl">RISK OF RUIN</div>
          <div className={`mc-val ${loading ? 'placeholder' : rorCls}`}>
            {loading ? '…' : ror == null ? '—' : ror * 100 < 0.01 ? '<0.01%' : fmtPct(ror, 2)}
          </div>
          {results && (
            <div className="mc-sub">{fmtDollar(bankroll)} bankroll</div>
          )}
        </div>

        {/* N-0 */}
        <div className="mc">
          <div className="mc-lbl">HOURS TO N-0</div>
          <div className={`mc-val ${loading ? 'placeholder' : ''}`} style={{ color: loading ? undefined : 'var(--yellow)' }}>
            {loading
              ? '…'
              : n0 == null ? '—'
              : n0 === -1 || n0 > 50000 ? '∞'
              : Math.round(n0) + ' hrs'
            }
          </div>
          {results && n0 != null && n0 !== -1 && n0 <= 50000 && (
            <div className="mc-sub">
              {Math.round(n0 * rph).toLocaleString()} hands
            </div>
          )}
        </div>

        {/* Variance Visualizer button */}
        <button className="vbtn" onClick={openViz} disabled={!results || loading}>
          <span className="vi">📈</span>
          VARIANCE<br />VISUALIZER
        </button>
      </div>

      {/* ── Stats strip ──────────────────────────────────── */}
      {results && (
        <div className="strip">
          <span>
            SCORE: <span className="sa">{results.score.toFixed(4)}</span>
          </span>
          <span>
            Hands: <span className="sv">{results.total_hands.toLocaleString()}</span>
          </span>
          <span>
            Wagered: <span className="sv">{fmtDollar(results.total_wagered)}</span>
          </span>
          <span>
            Net P&amp;L: <span className={results.total_won >= 0 ? 'sp' : 'sn'}>
              {fmtSigned(results.total_won)}
            </span>
          </span>
          {edgeEntries.length > 0 && (
            <span style={{ marginLeft:'auto' }}>
              EDGE BY TC:
              {edgeEntries.map(([tc, edge]) => (
                <span key={tc} className={edge > 0 ? 'sp' : 'sn'} style={{ marginLeft:10 }}>
                  TC+{tc} {(edge * 100).toFixed(1)}%
                </span>
              ))}
            </span>
          )}
        </div>
      )}

      {/* ── Variance Modal ────────────────────────────────── */}
      {showViz && (
        <VarianceModal
          data={vizData}
          bankroll={bankroll}
          loading={vizLoading}
          error={vizError}
          elapsed={vizElapsed}
          onClose={() => { setShowViz(false); clearInterval(vizTimer.current); }}
        />
      )}
    </>
  );
};

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
</script>
</body>
</html>
