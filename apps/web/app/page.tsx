'use client';

import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const ADMIN = process.env.NEXT_PUBLIC_ADMIN_ID || '';

export default function Home() {
  const [data, setData] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(`${API}/api/v1/admin/overview`, { headers: { 'X-Discord-Id': ADMIN } })
      .then(async r => { if (!r.ok) throw new Error('Admin API unavailable'); return r.json(); })
      .then(setData).catch(e => setError(e.message));
  }, []);

  const cards = [
    ['Users', data?.users ?? 0], ['Servers', data?.servers ?? 0],
    ['Active Plans', data?.plans ?? 0], ['Deployments', data?.active_deployments ?? 0],
  ];

  return <main className="shell">
    <aside><div className="brand">ARVEX<span>CONTROL</span></div><nav>
      <a className="active">Overview</a><a>Users</a><a>Invite Plans</a><a>VPS Nodes</a><a>Pterodactyl</a><a>Servers</a><a>Deployments</a><a>AI</a><a>Audit Logs</a><a>Settings</a>
    </nav></aside>
    <section className="content">
      <header><div><p className="eyebrow">HOSTING AUTOMATION SAAS</p><h1>Control Center</h1></div><div className="status">● System Online</div></header>
      {error && <div className="alert">{error}. Configure NEXT_PUBLIC_API_URL and an admin Discord ID.</div>}
      <div className="grid">{cards.map(([label, value]) => <div className="card" key={label as string}><small>{label}</small><strong>{value}</strong><span>Live metric</span></div>)}</div>
      <div className="panel"><div><h2>Deployment pipeline</h2><p>Discord → API → Queue → Docker / Pterodactyl → DM</p></div><div className="pipeline"><i>Discord</i><b>→</b><i>API</i><b>→</b><i>Worker</i><b>→</b><i>Provider</i><b>→</b><i>Ready</i></div></div>
      <div className="two"><div className="panel"><h2>Invite system</h2><p>Create, edit, disable and reorder plans without changing bot code.</p><button>Manage Plans</button></div><div className="panel"><h2>AI Copilot</h2><p>Groq-powered support with allow-listed infrastructure tools.</p><button>Configure AI</button></div></div>
    </section>
  </main>;
}
