import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, RadialBarChart, RadialBar } from 'recharts';
import NavBar from '../components/NavBar';
import { api } from '../api/client';

const AC = { good:'var(--green)', warning:'var(--amber)', critical:'var(--red)' };

const ChartTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:'var(--bg2)', border:'1px solid var(--borderB)', padding:'10px 14px', borderRadius:4 }}>
      <div className="label" style={{ marginBottom:4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.name} style={{ fontFamily:'var(--ff-mono)', fontSize:11, color: p.fill || 'var(--cyan)' }}>
          {p.value > 0 ? '+' : ''}{p.value?.toFixed(1)}%
        </div>
      ))}
    </div>
  );
};

export default function AuthorityDashboard({ session, onLogout }) {
  const navigate = useNavigate();
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.insights()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <>
      <NavBar session={session} onLogout={onLogout} />
      <div style={{ minHeight:'100vh', display:'flex', alignItems:'center', justifyContent:'center' }}>
        <div className="spinner" />
      </div>
    </>
  );

  if (!data) return (
    <>
      <NavBar session={session} onLogout={onLogout} />
      <div className="page"><p style={{ color:'var(--red)' }}>Failed to load network data. Is the API running?</p></div>
    </>
  );

  const { network_health, system_summary: ss, network_anomalies, top_priority_routes, client_insights } = data;

  const healthColor = network_health?.color === 'green' ? 'var(--green)'
    : network_health?.color === 'amber' ? 'var(--amber)' : 'var(--red)';

  const trendBar = (client_insights || []).map(c => ({
    name:  c.name.split(' ')[0],
    trend: c.trend_pct,
    fill:  c.trend_pct > 0 ? 'var(--green)' : c.trend_pct < -10 ? 'var(--red)' : 'var(--amber)',
  }));

  return (
    <>
      <NavBar session={session} onLogout={onLogout} />
      <div className="page fade-in">

        {/* Header */}
        <div style={{ marginBottom:28 }}>
          <div className="label" style={{ marginBottom:6 }}>Network Overview</div>
          <h1 style={{ fontFamily:'var(--ff-head)', fontSize:30, fontWeight:700, color:'var(--t0)' }}>
            Authority <span style={{ color:'var(--amber)' }}>Dashboard</span>
          </h1>
          <p style={{ color:'var(--t1)', marginTop:6, fontSize:13 }}>
            Real-time network intelligence — demand trends, anomaly detection, and route-level recommendations.
          </p>
        </div>

        {/* Top row */}
        <div style={{ display:'grid', gridTemplateColumns:'200px 1fr', gap:20, marginBottom:24 }}>

          {/* Health gauge */}
          <div className="card" style={{ padding:24, display:'flex', flexDirection:'column', alignItems:'center' }}>
            <div className="label" style={{ marginBottom:14, textAlign:'center' }}>Network Health</div>
            <div style={{ position:'relative', width:140, height:140 }}>
              <RadialBarChart width={140} height={140} cx={70} cy={70} innerRadius={46} outerRadius={64}
                data={[{ value: network_health?.score }]} startAngle={90} endAngle={-270}>
                <RadialBar dataKey="value" cornerRadius={4} fill={healthColor} background={{ fill:'var(--bg3)' }} />
              </RadialBarChart>
              <div style={{
                position:'absolute', inset:0, display:'flex', flexDirection:'column',
                alignItems:'center', justifyContent:'center',
              }}>
                <div style={{ fontFamily:'var(--ff-head)', fontSize:30, fontWeight:700, color:healthColor, lineHeight:1 }}>
                  {network_health?.score}
                </div>
                <div className="label">/100</div>
              </div>
            </div>
            <div style={{ fontFamily:'var(--ff-head)', fontSize:14, fontWeight:700, color:healthColor, letterSpacing:'0.1em', marginTop:10 }}>
              {network_health?.label?.toUpperCase()}
            </div>
            <div className="divider" style={{ width:'100%' }} />
            <div className="label" style={{ textAlign:'center', marginBottom:4 }}>Next Month Forecast</div>
            <div style={{ fontFamily:'var(--ff-head)', fontSize:18, fontWeight:700, color:'var(--cyan)' }}>
              {ss ? (ss.total_next_month_forecast / 1e6).toFixed(1) + 'M' : '—'}
            </div>
          </div>

          {/* Summary stats */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(130px,1fr))', gap:12 }}>
            {[
              { label:'Total Operators',    val: ss?.total_operators,          color:'var(--cyan)'  },
              { label:'Stable',             val: ss?.operators_stable,         color:'var(--green)' },
              { label:'Declining',          val: ss?.operators_declining,      color:'var(--red)'   },
              { label:'With Anomalies',     val: ss?.operators_with_anomalies, color:'var(--amber)' },
              { label:'Network Trend',      val: ss ? `${ss.avg_trend_pct > 0 ? '+' : ''}${ss.avg_trend_pct?.toFixed(1)}%` : '—',
                                            color: ss?.avg_trend_pct >= 0 ? 'var(--green)' : 'var(--red)' },
            ].map(item => (
              <div key={item.label} className="stat">
                <div className="label">{item.label}</div>
                <div className="val" style={{ color: item.color }}>{item.val}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Trend chart + anomalies */}
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20, marginBottom:24 }}>

          <div className="card" style={{ padding:24 }}>
            <div className="label" style={{ marginBottom:16 }}>Operator Demand Trend (YoY %)</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={trendBar} margin={{ top:0, right:0, left:0, bottom:24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="name" tick={{ fontFamily:'var(--ff-mono)', fontSize:9, fill:'var(--t2)' }} angle={-30} textAnchor="end" interval={0} />
                <YAxis tick={{ fontFamily:'var(--ff-mono)', fontSize:9, fill:'var(--t2)' }} tickFormatter={v => `${v}%`} />
                <Tooltip content={<ChartTip />} />
                <Bar dataKey="trend" radius={[2,2,0,0]}>
                  {trendBar.map((d,i) => <Cell key={i} fill={d.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card" style={{ padding:24 }}>
            <div className="label" style={{ marginBottom:14 }}>
              ⚠ Anomaly Alerts ({network_anomalies?.length || 0})
            </div>
            {network_anomalies?.length > 0 ? (
              <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                {network_anomalies.map(a => (
                  <div key={a.route_id} style={{
                    padding:'12px 14px',
                    background:'rgba(255,179,0,0.06)',
                    border:'1px solid rgba(255,179,0,0.22)',
                    borderRadius:'var(--r)', borderLeft:'3px solid var(--amber)',
                  }}>
                    <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                      <span style={{ fontFamily:'var(--ff-head)', fontSize:13, fontWeight:700, color:'var(--amber)' }}>
                        Route {a.route_id} — {a.routename}
                      </span>
                      <span style={{ fontFamily:'var(--ff-mono)', fontSize:11, color:'var(--red)' }}>
                        Z={a.zscore?.toFixed(2)}
                      </span>
                    </div>
                    <div style={{ fontFamily:'var(--ff-mono)', fontSize:10, color:'var(--t1)' }}>
                      {a.pct_change?.toFixed(1)}% · Hist avg: {a.historical_avg?.toLocaleString()} · Recent: {a.recent_demand?.toLocaleString()}
                    </div>
                    <button className="btn btn-amber" style={{ marginTop:8, padding:'4px 12px', fontSize:10 }}
                      onClick={() => navigate(`/operator/${a.client_id}`)}>
                      Investigate →
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontFamily:'var(--ff-mono)', fontSize:12, color:'var(--green)', padding:8 }}>
                ✓ No anomalies detected across the network.
              </div>
            )}
          </div>
        </div>

        {/* Priority routes */}
        <div className="card" style={{ padding:24, marginBottom:24 }}>
          <div className="label" style={{ marginBottom:16 }}>Top Priority Routes — Network Wide</div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(300px,1fr))', gap:10 }}>
            {(top_priority_routes || []).slice(0, 12).map(r => (
              <div key={`${r.client_id}-${r.route_id}`}
                onClick={() => navigate(`/operator/${r.client_id}`)}
                style={{
                  padding:'12px 14px', borderRadius:'var(--r)', cursor:'pointer',
                  background: r.alert_level==='critical' ? 'var(--red-lo)' : 'var(--bg3)',
                  border:`1px solid ${r.alert_level==='critical' ? 'rgba(255,68,68,0.22)' : 'var(--border)'}`,
                  borderLeft:`3px solid ${AC[r.alert_level]}`,
                  transition:'var(--tr)',
                }}
                onMouseEnter={e => e.currentTarget.style.opacity='0.8'}
                onMouseLeave={e => e.currentTarget.style.opacity='1'}
              >
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                  <div>
                    <span style={{ fontFamily:'var(--ff-mono)', fontSize:10, color:'var(--t2)', marginRight:6 }}>{r.route_id}</span>
                    <span style={{ fontFamily:'var(--ff-head)', fontSize:13, fontWeight:600, color:'var(--t0)' }}>{r.routename}</span>
                  </div>
                  <span style={{ fontFamily:'var(--ff-head)', fontSize:15, fontWeight:700, color: r.trend_direction==='growing' ? 'var(--green)' : 'var(--red)' }}>
                    {r.trend_pct > 0 ? '+' : ''}{r.trend_pct?.toFixed(1)}%
                  </span>
                </div>
                <div className="label" style={{ marginBottom:4, color: AC[r.alert_level] }}>{r.status_label}</div>
                <div style={{ fontFamily:'var(--ff-mono)', fontSize:10, color:'var(--t2)', lineHeight:1.4 }}>{r.recommendation}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Operator cards */}
        <div>
          <div className="label" style={{ marginBottom:14 }}>All Operators</div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(260px,1fr))', gap:12 }}>
            {(client_insights || []).map(c => (
              <div key={c.client_id} onClick={() => navigate(`/operator/${c.client_id}`)}
                style={{
                  background:'var(--bg2)', border:'1px solid var(--border)',
                  borderLeft:`3px solid ${AC[c.alert_level]}`,
                  borderRadius:'var(--r)', padding:16, cursor:'pointer', transition:'var(--tr)',
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = AC[c.alert_level]}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
              >
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:8 }}>
                  <div>
                    <div style={{ fontFamily:'var(--ff-head)', fontSize:14, fontWeight:700, color:'var(--t0)', letterSpacing:'0.05em' }}>{c.name}</div>
                    <div className="label" style={{ marginTop:2 }}>{c.n_routes} routes</div>
                  </div>
                  <div style={{ fontFamily:'var(--ff-head)', fontSize:18, fontWeight:700, color: c.trend_pct > 0 ? 'var(--green)' : c.trend_pct < -5 ? 'var(--red)' : 'var(--cyan)' }}>
                    {c.trend_pct > 0 ? '+' : ''}{c.trend_pct?.toFixed(1)}%
                  </div>
                </div>
                <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                  <span className={`badge badge-${c.alert_level}`}>{c.trend_direction}</span>
                  {c.has_anomalies && <span className="badge badge-warning">⚠ anomaly</span>}
                  <span className="badge badge-info">{c.service_pattern?.dominant_pattern?.replace('_',' ')}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </>
  );
}
