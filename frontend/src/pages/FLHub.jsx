import React, { useEffect, useState, useCallback } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useNavigate } from 'react-router-dom';
import NavBar from '../components/NavBar';
import { api } from '../api/client';

const CLIENT_NAMES = {
  0:'South Side Transit', 1:'West Loop Authority', 2:'Far South Depot',
  3:'Southwest Transit',  4:'Central Loop Operator', 5:'North Chicago Transit',
  6:'Northwest Corridor', 7:'Mid-South Authority',
  8:'North Shore Transit Co.', 9:'Lakefront Express Auth.',
};

const maeColor = m => m < 3500 ? 'var(--green)' : m < 5500 ? 'var(--cyan)' : 'var(--amber)';

const ChartTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:'var(--bg2)', border:'1px solid var(--borderB)', padding:'10px 14px', borderRadius:4 }}>
      <div className="label" style={{ marginBottom:6 }}>Round {label}</div>
      {payload.map(p => (
        <div key={p.name} style={{ fontFamily:'var(--ff-mono)', fontSize:11, color:p.color, marginBottom:2 }}>
          {p.name}: {p.value?.toLocaleString()}
        </div>
      ))}
    </div>
  );
};

export default function FLHub({ session, onLogout }) {
  const navigate = useNavigate();
  const [regions,   setRegions]   = useState([]);
  const [clients,   setClients]   = useState({ active:[], pending:[] });
  const [results,   setResults]   = useState(null);
  const [compare,   setCompare]   = useState(null);
  const [training,  setTraining]  = useState(false);
  const [algo,      setAlgo]      = useState('fedavg');
  const [nRounds,   setNRounds]   = useState(5);
  const [log,       setLog]       = useState([]);
  const [loading,   setLoading]   = useState(true);
  // Live chart data — updated immediately after each training run
  const [liveChart, setLiveChart] = useState(null);

  // Selective participation — which active clients are checked for next training run
  const [selectedClients, setSelectedClients] = useState(new Set());

  const load = useCallback(async () => {
    try {
      const [r, c, res, cmp] = await Promise.all([
        api.regions(), api.clients(), api.federatedResults(), api.federatedCompare(5),
      ]);
      setRegions(r.regions || []);
      setClients(c);
      setResults(res);
      setCompare(cmp);
      // Default: all active clients selected
      const activeIds = new Set((c.active || []).map(cl => cl.client_id));
      setSelectedClients(prev => {
        // Keep existing selections if they are still active, else reset to all
        if (prev.size === 0) return activeIds;
        return activeIds;
      });
    } catch(e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleClient = (id) => {
    setSelectedClients(prev => {
      const next = new Set(prev);
      if (next.has(id)) { if (next.size > 1) next.delete(id); } // keep at least 1
      else next.add(id);
      return next;
    });
  };

  const runTrain = async () => {
    setTraining(true);
    const clientList = [...selectedClients].sort();
    setLog([
      `Initiating ${algo.toUpperCase()} — ${nRounds} rounds`,
      `Participating clients: ${clientList.map(id => `C${id}`).join(', ')}`,
    ]);
    try {
      // Send selected client IDs — backend will only train those clients
      const clientIdList = [...selectedClients].sort((a,b) => a-b);
      const res = await api.trainFederated(algo, nRounds, clientIdList);
      if (res.rounds) {
        res.rounds.forEach(r => {
          setLog(l => [...l, `  Round ${r.round}  |  MAE: ${Math.round(r.global_mae).toLocaleString()}  |  Clients: ${r.n_clients}`]);
        });
        // Update chart immediately with this run's convergence
        setLiveChart(res.rounds.map(r => ({
          round: r.round,
          [algo === 'fedavg' ? 'FedAvg' : 'FedProx']: Math.round(r.global_mae),
        })));
      }
      setLog(l => [...l, `✓ Complete. Final MAE: ${Math.round(res.final_mae || 0).toLocaleString()}`]);
      await load();
    } catch { setLog(l => [...l, '✗ Error: could not reach API']); }
    setTraining(false);
  };

  // Chart data priority:
  // 1. liveChart — set immediately after a training run (most up to date)
  // 2. compare endpoint — shows both FedAvg and FedProx from startup
  // 3. results — startup FedAvg only (always available)
  const chartData = (() => {
    if (liveChart?.length > 0) return liveChart;
    if (compare?.convergence_comparison?.length > 0) {
      return compare.convergence_comparison.map(r => ({
        round: r.round,
        'FedAvg':  Math.round(r.fedavg_mae),
        'FedProx': Math.round(r.fedprox_mae),
      }));
    }
    if (results?.rounds?.length > 0) {
      return results.rounds.map(r => ({
        round: r.round,
        'FedAvg': Math.round(r.global_mae),
      }));
    }
    return [];
  })();

  if (loading) return (
    <>
      <NavBar session={session} onLogout={onLogout} />
      <div style={{ minHeight:'100vh', display:'flex', alignItems:'center', justifyContent:'center' }}>
        <div className="spinner" />
      </div>
    </>
  );

  return (
    <>
      <NavBar session={session} onLogout={onLogout} />
      <div className="page fade-in">

        {/* Header */}
        <div style={{ marginBottom:28 }}>
          <div className="label" style={{ marginBottom:6 }}>Federated Learning</div>
          <h1 style={{ fontFamily:'var(--ff-head)', fontSize:30, fontWeight:700, color:'var(--t0)' }}>
            Global <span style={{ color:'var(--cyan)' }}>Coordinator Hub</span>
          </h1>
          <p style={{ color:'var(--t1)', marginTop:6, fontSize:13 }}>
            Train and monitor the federated model. Raw data never leaves individual operator premises — only model parameters are shared.
          </p>
        </div>

        {/* KPI row */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(150px,1fr))', gap:12, marginBottom:28 }}>
          {[
            { label:'Active Clients',  val: clients.active?.length ?? 0,                                            color:'var(--cyan)'  },
            { label:'Pending',         val: clients.pending?.length ?? 0,                                           color:'var(--amber)' },
            { label:'Final MAE',       val: results?.final_mae ? Math.round(results.final_mae).toLocaleString() : '—', color:'var(--green)' },
            { label:'Algorithm',       val: (results?.algorithm || 'FEDAVG').toUpperCase(),                        color:'var(--cyan)'  },
            { label:'Rounds Trained',  val: results?.total_rounds ?? 0,                                            color:'var(--cyan)'  },
          ].map(item => (
            <div key={item.label} className="stat">
              <div className="label">{item.label}</div>
              <div className="val" style={{ color: item.color }}>{item.val}</div>
            </div>
          ))}
        </div>

        {/* Main grid */}
        <div style={{ display:'grid', gridTemplateColumns:'1fr 380px', gap:20, marginBottom:20 }}>

          {/* Convergence chart */}
          <div className="card" style={{ padding:24 }}>
            <div className="label" style={{ marginBottom:16 }}>Algorithm Convergence — FedAvg vs FedProx (MAE per Round)</div>
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={chartData} margin={{ top:5, right:20, left:0, bottom:5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="round" tick={{ fontFamily:'var(--ff-mono)', fontSize:10, fill:'var(--t2)' }} />
                  <YAxis tick={{ fontFamily:'var(--ff-mono)', fontSize:10, fill:'var(--t2)' }} tickFormatter={v => v.toLocaleString()} />
                  <Tooltip content={<ChartTip />} />
                  <Legend wrapperStyle={{ fontFamily:'var(--ff-mono)', fontSize:11, color:'var(--t1)' }} />
                  <Line type="monotone" dataKey="FedAvg"  stroke="var(--cyan)"  strokeWidth={2} dot={{ fill:'var(--cyan)',  r:4 }} />
                  <Line type="monotone" dataKey="FedProx" stroke="var(--amber)" strokeWidth={2} strokeDasharray="5 3" dot={{ fill:'var(--amber)', r:4 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height:240, display:'flex', alignItems:'center', justifyContent:'center', color:'var(--t2)', fontFamily:'var(--ff-mono)', fontSize:12 }}>
                Loading convergence data...
              </div>
            )}
            {compare && (
              <div style={{ marginTop:14, fontFamily:'var(--ff-mono)', fontSize:11, color:'var(--t2)', lineHeight:1.7, background:'var(--bg3)', padding:'10px 14px', borderRadius:3 }}>
                FedProx starts higher due to proximal regularisation but converges to the same final MAE as FedAvg —
                expected behaviour on linear models with convex loss surfaces.
              </div>
            )}
          </div>

          {/* Right panel: training + per-client performance */}
          <div style={{ display:'flex', flexDirection:'column', gap:16 }}>

            {/* Training controls */}
            <div className="card" style={{ padding:20 }}>
              <div className="label" style={{ marginBottom:14 }}>Training Controls</div>

              {/* Algorithm selector */}
              <div style={{ marginBottom:12 }}>
                <div className="label" style={{ marginBottom:6 }}>Algorithm</div>
                <div style={{ display:'flex', gap:8 }}>
                  {['fedavg','fedprox'].map(a => (
                    <button key={a} onClick={() => setAlgo(a)} style={{
                      flex:1, padding:'8px 0',
                      background: algo===a ? 'var(--cyan-lo)' : 'transparent',
                      border:`1px solid ${algo===a ? 'var(--borderB)' : 'var(--border)'}`,
                      color: algo===a ? 'var(--cyan)' : 'var(--t2)',
                      fontFamily:'var(--ff-head)', fontSize:12, fontWeight:600,
                      letterSpacing:'0.1em', textTransform:'uppercase',
                      borderRadius:'var(--r)', transition:'var(--tr)',
                    }}>{a.toUpperCase()}</button>
                  ))}
                </div>
              </div>

              {/* Rounds slider */}
              <div style={{ marginBottom:14 }}>
                <div className="label" style={{ marginBottom:6 }}>Rounds: {nRounds}</div>
                <input type="range" min={1} max={10} value={nRounds}
                  onChange={e => setNRounds(+e.target.value)}
                  style={{ width:'100%', accentColor:'var(--cyan)' }} />
              </div>

              {/* Client participation checkboxes */}
              <div style={{ marginBottom:14 }}>
                <div className="label" style={{ marginBottom:8 }}>
                  Participating Clients ({selectedClients.size} / {clients.active?.length || 0})
                </div>
                <div style={{ display:'flex', flexDirection:'column', gap:4, maxHeight:160, overflowY:'auto' }}>
                  {(clients.active || []).map(c => (
                    <label key={c.client_id} style={{
                      display:'flex', alignItems:'center', gap:8,
                      padding:'5px 8px', borderRadius:3,
                      background: selectedClients.has(c.client_id) ? 'var(--cyan-lo)' : 'var(--bg3)',
                      border:`1px solid ${selectedClients.has(c.client_id) ? 'var(--borderB)' : 'var(--border)'}`,
                      cursor:'pointer', transition:'var(--tr)',
                    }}>
                      <input
                        type="checkbox"
                        checked={selectedClients.has(c.client_id)}
                        onChange={() => toggleClient(c.client_id)}
                        style={{ accentColor:'var(--cyan)', cursor:'pointer' }}
                      />
                      <span style={{ fontFamily:'var(--ff-mono)', fontSize:10, color: selectedClients.has(c.client_id) ? 'var(--cyan)' : 'var(--t2)' }}>
                        C{c.client_id} — {c.name}
                      </span>
                    </label>
                  ))}
                </div>
                {selectedClients.size < (clients.active?.length || 0) && (
                  <div style={{ marginTop:6, fontFamily:'var(--ff-mono)', fontSize:10, color:'var(--amber)' }}>
                    ⚠ Partial participation — {(clients.active?.length || 0) - selectedClients.size} client(s) excluded
                  </div>
                )}
              </div>

              <button className="btn btn-primary" style={{ width:'100%' }} onClick={runTrain} disabled={training}>
                {training
                  ? <><div className="spinner" style={{ width:14, height:14 }} />Training...</>
                  : `▶ Run ${algo.toUpperCase()} (${selectedClients.size} clients)`
                }
              </button>

              {/* Training log */}
              {log.length > 0 && (
                <div style={{
                  marginTop:12, background:'var(--bg0)', border:'1px solid var(--border)',
                  borderRadius:3, padding:10, fontFamily:'var(--ff-mono)', fontSize:10,
                  color:'var(--t2)', lineHeight:1.8, maxHeight:140, overflowY:'auto',
                }}>
                  {log.map((l, i) => (
                    <div key={i} style={{
                      color: l.startsWith('✓') ? 'var(--green)'
                           : l.startsWith('✗') ? 'var(--red)'
                           : l.startsWith('Initiating') ? 'var(--cyan)' : 'var(--t2)',
                    }}>{l}</div>
                  ))}
                </div>
              )}
            </div>

            {/* Per-client MAE bars */}
            <div className="card" style={{ padding:20, flex:1 }}>
              <div className="label" style={{ marginBottom:12 }}>Client Performance (MAE)</div>
              <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                {regions.map(r => (
                  <div key={r.client_id}
                    onClick={() => navigate(`/operator/${r.client_id}`)}
                    style={{ display:'flex', alignItems:'center', gap:8, cursor:'pointer' }}
                  >
                    <div style={{ fontFamily:'var(--ff-mono)', fontSize:10, color:'var(--t2)', width:20 }}>C{r.client_id}</div>
                    <div style={{ flex:1, height:5, background:'var(--bg3)', borderRadius:3, overflow:'hidden' }}>
                      <div style={{
                        height:'100%', borderRadius:3,
                        width:`${Math.min((r.performance?.mae / 8000) * 100, 100)}%`,
                        background: maeColor(r.performance?.mae),
                      }} />
                    </div>
                    <div style={{ fontFamily:'var(--ff-mono)', fontSize:11, color: maeColor(r.performance?.mae), width:52, textAlign:'right' }}>
                      {Math.round(r.performance?.mae || 0).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop:10, fontFamily:'var(--ff-mono)', fontSize:10, color:'var(--t2)' }}>
                Click any bar to view operator portal →
              </div>
            </div>
          </div>
        </div>

        {/* Active client management */}
        <div className="card" style={{ padding:24, marginBottom:20 }}>
          <div className="label" style={{ marginBottom:16 }}>Active Operator Management</div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(240px,1fr))', gap:10 }}>
            {(clients.active || []).map(c => (
              <div key={c.client_id} style={{
                padding:'12px 14px', background:'var(--bg3)',
                border:'1px solid var(--border)', borderRadius:'var(--r)',
                display:'flex', justifyContent:'space-between', alignItems:'center',
              }}>
                <div>
                  <div style={{ fontFamily:'var(--ff-head)', fontSize:13, fontWeight:600, color:'var(--t0)', marginBottom:3 }}>
                    {c.name}
                  </div>
                  <div className="label">{c.n_routes} routes · {c.n_samples?.toLocaleString()} samples</div>
                </div>
                <div style={{ display:'flex', flexDirection:'column', alignItems:'flex-end', gap:6 }}>
                  <span className="badge badge-good" style={{ fontSize:9 }}>● Active</span>
                  <button className="btn btn-red" style={{ padding:'3px 10px', fontSize:10 }}
                    onClick={() => api.deactivateClient(c.client_id).then(load)}>
                    Deactivate
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Dynamic onboarding */}
        <div className="card" style={{ padding:24 }}>
          <div className="label" style={{ marginBottom:14 }}>Pending Operator Onboarding</div>
          <p style={{ color:'var(--t2)', fontSize:12, marginBottom:16, lineHeight:1.6 }}>
            New operators awaiting federation approval. Once approved their local model gradients will be included in the next aggregation round — no raw data is shared.
          </p>
          {(clients.pending || []).length > 0 ? (
            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(280px,1fr))', gap:12 }}>
              {clients.pending.map(c => (
                <div key={c.client_id} style={{
                  padding:16, background:'var(--amber-lo)',
                  border:'1px solid rgba(255,179,0,0.25)', borderRadius:'var(--r)',
                }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:8 }}>
                    <div>
                      <div style={{ fontFamily:'var(--ff-head)', fontSize:14, fontWeight:700, color:'var(--amber)' }}>{c.name}</div>
                      <div className="label" style={{ marginTop:3 }}>{c.n_routes} routes · {c.n_samples?.toLocaleString()} samples</div>
                    </div>
                    <span className="badge badge-warning">Pending</span>
                  </div>
                  <div style={{ fontFamily:'var(--ff-mono)', fontSize:11, color:'var(--t1)', marginBottom:12 }}>
                    Avg demand: {Math.round(c.avg_monthly_demand || 0).toLocaleString()} / month
                  </div>
                  <button className="btn btn-green" style={{ width:'100%' }}
                    onClick={() => api.approveClient(c.client_id).then(load)}>
                    ✓ Approve &amp; Onboard
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontFamily:'var(--ff-mono)', fontSize:12, color:'var(--t2)', padding:8 }}>
              No pending operators. All registered operators are currently active.
            </div>
          )}
        </div>

      </div>
    </>
  );
}
