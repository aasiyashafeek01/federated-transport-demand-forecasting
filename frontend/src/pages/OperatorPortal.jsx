import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts';
import NavBar from '../components/NavBar';
import { api } from '../api/client';

const PC = { commuter_dominant:'var(--cyan)', leisure_mixed:'var(--amber)', balanced:'var(--green)' };
const AC = { good:'var(--green)', warning:'var(--amber)', critical:'var(--red)' };

const ChartTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:'var(--bg2)', border:'1px solid var(--borderB)', padding:'10px 14px', borderRadius:4 }}>
      <div className="label" style={{ marginBottom:6 }}>{label}</div>
      {payload.map(p => (
        <div key={p.name} style={{ fontFamily:'var(--ff-mono)', fontSize:11, color:p.color, marginBottom:2 }}>
          {p.name}: {Math.round(p.value)?.toLocaleString()}
        </div>
      ))}
    </div>
  );
};

const ALL = [
  {id:0,name:'South Side Transit'},{id:1,name:'West Loop Authority'},{id:2,name:'Far South Depot'},
  {id:3,name:'Southwest Transit'},{id:4,name:'Central Loop Operator'},{id:5,name:'North Chicago Transit'},
  {id:6,name:'Northwest Corridor'},{id:7,name:'Mid-South Authority'},
];

export default function OperatorPortal({ session, onLogout }) {
  const { id } = useParams();
  const cid = parseInt(id, 10);
  const navigate = useNavigate();

  const [ins,     setIns]     = useState(null);
  const [preds,   setPreds]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab,     setTab]     = useState('overview');

  useEffect(() => {
    setLoading(true); setIns(null); setPreds(null);
    Promise.all([api.clientInsights(cid), api.clientPredictions(cid)])
      .then(([i, p]) => { setIns(i); setPreds(p); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [cid]);

  if (loading) return (
    <>
      <NavBar session={session} onLogout={onLogout} />
      <div style={{ minHeight:'100vh', display:'flex', alignItems:'center', justifyContent:'center' }}>
        <div className="spinner" />
      </div>
    </>
  );

  if (!ins) return (
    <>
      <NavBar session={session} onLogout={onLogout} />
      <div className="page"><p style={{ color:'var(--red)' }}>Failed to load operator data. Is the API running?</p></div>
    </>
  );

  // chart_data is what the API actually returns
  const demandData = (preds?.chart_data || []).slice(-24).map(m => ({
    month:     m.month?.slice(0,7),
    Actual:    Math.round(m.actual),
    Predicted: Math.round(m.predicted),
  }));

  const ps = ins.service_pattern?.summary;
  const patternBars = ps ? [
    { name:'Commuter', value:ps.commuter_routes, fill:'var(--cyan)'  },
    { name:'Leisure',  value:ps.leisure_routes,  fill:'var(--amber)' },
    { name:'Balanced', value:ps.balanced_routes, fill:'var(--green)' },
  ] : [];

  const alertColor = AC[ins.alert_level] || 'var(--cyan)';
  const trendColor = ins.trend_pct > 0 ? 'var(--green)' : ins.trend_pct < -5 ? 'var(--red)' : 'var(--cyan)';

  // Only show selector if coordinator (authority view shows all operators)
  const showSelector = session?.role === 'coordinator' || session?.role === 'authority';

  return (
    <>
      <NavBar session={session} onLogout={onLogout} />
      <div className="page fade-in">

        {/* Operator selector */}
        {showSelector && (
          <div style={{ display:'flex', gap:6, marginBottom:20, flexWrap:'wrap' }}>
            {ALL.map(c => (
              <button key={c.id} onClick={() => navigate(`/operator/${c.id}`)} style={{
                padding:'5px 12px',
                background: c.id===cid ? 'var(--cyan-lo)' : 'transparent',
                border:`1px solid ${c.id===cid ? 'var(--borderB)' : 'var(--border)'}`,
                color: c.id===cid ? 'var(--cyan)' : 'var(--t2)',
                fontFamily:'var(--ff-head)', fontSize:11, fontWeight:600,
                letterSpacing:'0.08em', textTransform:'uppercase',
                borderRadius:'var(--r)', transition:'var(--tr)',
              }}>{c.name.split(' ')[0]}</button>
            ))}
          </div>
        )}

        {/* Header */}
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:20 }}>
          <div>
            <div className="label" style={{ marginBottom:6 }}>Operator Analytics</div>
            <h1 style={{ fontFamily:'var(--ff-head)', fontSize:28, fontWeight:700, color:'var(--cyan)' }}>{ins.name}</h1>
            <p style={{ color:'var(--t1)', fontSize:13, marginTop:4 }}>{ins.detail}</p>
          </div>
          <div style={{ display:'flex', gap:8, alignItems:'center' }}>
            <span className={`badge badge-${ins.alert_level}`}>
              {ins.trend_direction} · {ins.trend_pct > 0 ? '+' : ''}{ins.trend_pct?.toFixed(1)}%
            </span>
            {ins.has_anomalies && <span className="badge badge-warning">⚠ anomaly</span>}
          </div>
        </div>

        {/* KPI row */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(150px,1fr))', gap:12, marginBottom:24 }}>
          {[
            { label:'Recent Demand',      val: Math.round(ins.recent_monthly_demand)?.toLocaleString(),    color: alertColor },
            { label:'Baseline (YoY)',     val: Math.round(ins.baseline_monthly_demand)?.toLocaleString(),  color:'var(--t1)' },
            { label:'Next Month Forecast',val: Math.round(ins.next_month_forecast)?.toLocaleString(),      color:'var(--amber)' },
            { label:'Trend YoY',          val: `${ins.trend_pct > 0 ? '+' : ''}${ins.trend_pct?.toFixed(1)}%`, color: trendColor },
            { label:'Routes',             val: ins.n_routes,                                               color:'var(--cyan)' },
            { label:'Local MAE',          val: preds?.mae ? Math.round(preds.mae).toLocaleString() : '—', color:'var(--green)' },
          ].map(item => (
            <div key={item.label} className="stat">
              <div className="label">{item.label}</div>
              <div className="val" style={{ color: item.color }}>{item.val}</div>
            </div>
          ))}
        </div>

        {/* Tabs */}
        <div style={{ display:'flex', gap:0, borderBottom:'1px solid var(--border)', marginBottom:24 }}>
          {['overview','predictions','routes'].map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              background:'none', border:'none',
              borderBottom: tab===t ? '2px solid var(--cyan)' : '2px solid transparent',
              color: tab===t ? 'var(--cyan)' : 'var(--t2)',
              padding:'8px 20px', fontFamily:'var(--ff-head)', fontSize:12,
              fontWeight:600, letterSpacing:'0.1em', textTransform:'uppercase',
              transition:'var(--tr)',
            }}>{t}</button>
          ))}
        </div>

        {/* OVERVIEW */}
        {tab === 'overview' && (
          <div style={{ display:'grid', gridTemplateColumns:'2fr 1fr', gap:20 }}>
            <div style={{ display:'flex', flexDirection:'column', gap:20 }}>

              {/* Status */}
              <div className="card" style={{ padding:20 }}>
                <div style={{ fontFamily:'var(--ff-head)', fontSize:15, fontWeight:700, color: alertColor, marginBottom:8 }}>
                  {ins.status_label}
                </div>
                <p style={{ color:'var(--t1)', fontSize:13, lineHeight:1.6, marginBottom:12 }}>{ins.detail}</p>
                <div style={{ background:'var(--bg3)', borderRadius:3, padding:12, borderLeft:`3px solid var(--cyan)` }}>
                  <div className="label" style={{ marginBottom:4 }}>Recommendation</div>
                  <p style={{ fontSize:12, color:'var(--t1)' }}>{ins.recommendation}</p>
                </div>
              </div>

              {/* Anomalies */}
              {ins.anomalies?.length > 0 && (
                <div className="card" style={{ padding:20, border:'1px solid rgba(255,179,0,0.25)' }}>
                  <div className="label" style={{ marginBottom:12, color:'var(--amber)' }}>⚠ Anomalies Detected</div>
                  {ins.anomalies.map(a => (
                    <div key={a.route_id} style={{ marginBottom:10, paddingBottom:10, borderBottom:'1px solid var(--border)' }}>
                      <div style={{ fontFamily:'var(--ff-head)', fontSize:13, fontWeight:700, color:'var(--amber)', marginBottom:4 }}>
                        Route {a.route_id} — {a.routename}
                      </div>
                      <div style={{ fontFamily:'var(--ff-mono)', fontSize:11, color:'var(--t1)' }}>
                        Z-score: {a.zscore?.toFixed(2)} · Change: {a.pct_change?.toFixed(1)}%
                      </div>
                      <p style={{ fontSize:11, color:'var(--t2)', marginTop:4 }}>{a.message}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Priority routes */}
              {ins.top_routes?.length > 0 && (
                <div className="card" style={{ padding:20 }}>
                  <div className="label" style={{ marginBottom:12 }}>Priority Routes</div>
                  <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                    {ins.top_routes.slice(0,6).map(r => (
                      <div key={r.route_id} style={{
                        display:'flex', alignItems:'center', gap:10,
                        padding:'10px 12px', background:'var(--bg3)',
                        border:`1px solid ${r.alert_level==='critical' ? 'rgba(255,68,68,0.22)' : 'var(--border)'}`,
                        borderRadius:'var(--r)',
                      }}>
                        <div style={{
                          fontFamily:'var(--ff-mono)', fontSize:11,
                          color: AC[r.alert_level], background:`${AC[r.alert_level]}18`,
                          border:`1px solid ${AC[r.alert_level]}38`,
                          padding:'1px 6px', borderRadius:2, minWidth:36, textAlign:'center',
                        }}>{r.route_id}</div>
                        <div style={{ flex:1 }}>
                          <div style={{ fontSize:12, color:'var(--t0)', marginBottom:2 }}>{r.routename}</div>
                          <div className="label">{r.status_label}</div>
                        </div>
                        <div style={{ fontFamily:'var(--ff-head)', fontSize:15, fontWeight:700, color: r.trend_direction==='growing' ? 'var(--green)' : 'var(--red)' }}>
                          {r.trend_pct > 0 ? '+' : ''}{r.trend_pct?.toFixed(1)}%
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Right */}
            <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
              <div className="card" style={{ padding:20 }}>
                <div className="label" style={{ marginBottom:12 }}>Service Pattern</div>
                <div style={{ textAlign:'center', fontFamily:'var(--ff-head)', fontSize:15, fontWeight:700, color: PC[ins.service_pattern?.dominant_pattern], marginBottom:12, letterSpacing:'0.08em', textTransform:'uppercase' }}>
                  {ins.service_pattern?.dominant_pattern?.replace(/_/g,' ')}
                </div>
                {patternBars.length > 0 && (
                  <ResponsiveContainer width="100%" height={110}>
                    <BarChart data={patternBars} margin={{ top:0,right:0,left:-20,bottom:0 }}>
                      <XAxis dataKey="name" tick={{ fontFamily:'var(--ff-mono)', fontSize:10, fill:'var(--t2)' }} />
                      <YAxis tick={{ fontFamily:'var(--ff-mono)', fontSize:9, fill:'var(--t2)' }} />
                      <Tooltip content={<ChartTip />} />
                      <Bar dataKey="value" radius={[2,2,0,0]}>
                        {patternBars.map((d,i) => <Cell key={i} fill={d.fill} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
                <div className="divider" />
                <p style={{ fontSize:11, color:'var(--t2)', lineHeight:1.6 }}>
                  {ins.service_pattern?.client_schedule_recommendation}
                </p>
              </div>

              <div className="card" style={{ padding:20 }}>
                <div className="label" style={{ marginBottom:12 }}>Route Summary</div>
                {[
                  { label:'Total Routes',         val: ins.route_summary?.total_routes },
                  { label:'Needing Attention',     val: ins.route_summary?.routes_needing_attention, color:'var(--amber)' },
                  { label:'High Demand',           val: ins.route_summary?.high_demand_count,        color:'var(--red)' },
                  { label:'Declining',             val: ins.route_summary?.declining_count,          color:'var(--red)' },
                ].map(item => (
                  <div key={item.label} style={{ display:'flex', justifyContent:'space-between', padding:'8px 0', borderBottom:'1px solid var(--border)' }}>
                    <span style={{ fontSize:12, color:'var(--t1)' }}>{item.label}</span>
                    <span style={{ fontFamily:'var(--ff-mono)', fontSize:13, fontWeight:700, color: item.color || 'var(--cyan)' }}>{item.val}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* PREDICTIONS */}
        {tab === 'predictions' && (
          <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
            <div className="card" style={{ padding:24 }}>
              <div className="label" style={{ marginBottom:16 }}>Actual vs Federated Predicted — Last 24 Months</div>
              {demandData.length > 0 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart data={demandData} margin={{ top:5, right:20, left:10, bottom:5 }}>
                    <defs>
                      <linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#00e5ff" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#00e5ff" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="pg" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#ffb300" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#ffb300" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="month" tick={{ fontFamily:'var(--ff-mono)', fontSize:9, fill:'var(--t2)' }} interval={2} />
                    <YAxis tick={{ fontFamily:'var(--ff-mono)', fontSize:9, fill:'var(--t2)' }} tickFormatter={v => (v/1000).toFixed(0)+'k'} />
                    <Tooltip content={<ChartTip />} />
                    <Area type="monotone" dataKey="Actual"    stroke="var(--cyan)"  strokeWidth={2} fill="url(#ag)" />
                    <Area type="monotone" dataKey="Predicted" stroke="var(--amber)" strokeWidth={2} fill="url(#pg)" strokeDasharray="5 3" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height:280, display:'flex', alignItems:'center', justifyContent:'center', color:'var(--t2)', fontFamily:'var(--ff-mono)', fontSize:12 }}>
                  No prediction data available
                </div>
              )}
              <div style={{ marginTop:16, display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12 }}>
                {[
                  { label:'Model MAE',  val: preds?.mae  ? Math.round(preds.mae).toLocaleString()  : '—' },
                  { label:'Model RMSE', val: preds?.rmse ? Math.round(preds.rmse).toLocaleString() : '—' },
                  { label:'Data Points',val: preds?.chart_data?.length ?? '—' },
                ].map(item => (
                  <div key={item.label} className="stat">
                    <div className="label">{item.label}</div>
                    <div className="val" style={{ color:'var(--cyan)', fontSize:20 }}>{item.val}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ROUTES */}
        {tab === 'routes' && (
          <div className="card" style={{ padding:24 }}>
            <div className="label" style={{ marginBottom:14 }}>All Routes — Service Pattern Detail</div>
            <div style={{ overflowX:'auto' }}>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead>
                  <tr style={{ borderBottom:'1px solid var(--border)' }}>
                    {['Route','Name','Pattern','Weekday %','Weekday Avg','Sat Avg','Sun Avg'].map(h => (
                      <th key={h} style={{ fontFamily:'var(--ff-mono)', fontSize:10, color:'var(--t2)', letterSpacing:'0.1em', textAlign:'left', padding:'6px 10px', textTransform:'uppercase' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ins.service_pattern?.routes?.map((r, i) => (
                    <tr key={r.route_id} style={{ borderBottom:'1px solid var(--border)', background: i%2===0 ? 'rgba(0,0,0,0.12)' : 'transparent' }}>
                      <td style={{ fontFamily:'var(--ff-mono)', fontSize:11, color:'var(--cyan)', padding:'7px 10px' }}>{r.route_id}</td>
                      <td style={{ fontSize:12, color:'var(--t0)', padding:'7px 10px' }}>{r.routename}</td>
                      <td style={{ padding:'7px 10px' }}>
                        <span style={{
                          fontFamily:'var(--ff-mono)', fontSize:10,
                          color: PC[r.pattern], background:`${PC[r.pattern]}18`,
                          border:`1px solid ${PC[r.pattern]}38`,
                          padding:'2px 6px', borderRadius:2,
                        }}>{r.pattern_label}</span>
                      </td>
                      <td style={{ fontFamily:'var(--ff-mono)', fontSize:11, color:'var(--t1)', padding:'7px 10px' }}>{r.weekday_share_pct?.toFixed(1)}%</td>
                      <td style={{ fontFamily:'var(--ff-mono)', fontSize:11, color:'var(--t1)', padding:'7px 10px' }}>{r.avg_weekday_rides?.toLocaleString()}</td>
                      <td style={{ fontFamily:'var(--ff-mono)', fontSize:11, color:'var(--t1)', padding:'7px 10px' }}>{r.avg_saturday_rides?.toLocaleString()}</td>
                      <td style={{ fontFamily:'var(--ff-mono)', fontSize:11, color:'var(--t1)', padding:'7px 10px' }}>{r.avg_sunday_rides?.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>
    </>
  );
}
