const BASE = 'http://localhost:5000/api';

const get  = (path)        => fetch(`${BASE}${path}`).then(r => r.json());
const post = (path, body)  => fetch(`${BASE}${path}`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
}).then(r => r.json());

export const api = {
  status:            ()                                    => get('/status'),
  clients:           ()                                    => get('/clients'),
  client:            (id)                                  => get(`/clients/${id}`),
  clientInsights:    (id)                                  => get(`/clients/${id}/insights`),
  clientPredictions: (id)                                  => get(`/clients/${id}/predictions`),
  regions:           ()                                    => get('/map/regions'),
  insights:          ()                                    => get('/insights'),
  federatedResults:  ()                                    => get('/federated/results'),
  federatedCompare:  (n = 5)                               => get(`/federated/compare?n_rounds=${n}`),

  // client_ids is optional — if provided only those clients participate
  trainFederated:    (algorithm, n_rounds, client_ids)     => post('/federated/train', {
    algorithm,
    n_rounds,
    ...(client_ids ? { client_ids } : {}),
  }),

  approveClient:     (id, round = 5)                       => post(`/clients/${id}/approve`, { current_round: round }),
  deactivateClient:  (id)                                  => post(`/clients/${id}/deactivate`, {}),
};