import { createServer } from 'node:http';
import { timingSafeEqual } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { loadConfig } from './config.js';
import { Ledger } from './ledger.js';
import { createService } from './service.js';
export function httpServer(service, token) {
  let active = 0;
  const expected = Buffer.from('Bearer ' + token);
  return createServer(async (req, res) => {
    const send = (status, body) => { res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' }); res.end(JSON.stringify(body)); };
    if (req.method === 'GET' && req.url === '/health') return send(200, { ok: true });
    if (req.method === 'GET' && req.url === '/supported') return send(200, service.supported());
    if (req.method !== 'POST' || !['/verify', '/settle'].includes(req.url)) return send(404, { error: 'not_found' });
    const got = Buffer.from(req.headers.authorization || '');
    if (got.length !== expected.length || !timingSafeEqual(got, expected)) return send(401, { error: 'unauthorized' });
    if (active >= 8) return send(429, { error: 'busy' });
    if (!req.headers['content-type']?.startsWith('application/json')) return send(415, { error: 'json_required' });
    active++;
    try {
      const chunks = []; let bytes = 0;
      for await (const chunk of req) { bytes += chunk.length; if (bytes > 16384) { send(413, { error: 'body_too_large' }); req.destroy(); return; } chunks.push(chunk); }
      let body;
      try { body = JSON.parse(Buffer.concat(chunks).toString()); } catch { return send(400, { error: 'invalid_json' }); }
      return send(200, await service.handle(req.url.slice(1), body));
    } catch { if (!res.headersSent) send(503, { error: 'temporarily_unavailable' }); }
    finally { active--; }
  });
}
if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  try {
    process.umask(0o077);
    const config = loadConfig(), ledger = new Ledger(config.dbPath);
    const service = await createService(config, ledger), server = httpServer(service, config.token);
    server.requestTimeout = 15000; server.headersTimeout = 10000;
    server.listen(config.port, '127.0.0.1', () => console.log(JSON.stringify({ ready: true, port: config.port, networks: config.networks, settlementEnabled: config.settlementEnabled })));
    const stop = () => server.close(() => { ledger.close(); process.exit(0); });
    process.on('SIGTERM', stop); process.on('SIGINT', stop);
  } catch { console.error('Facilitator startup failed: check configuration, RPC chain/USDC probe and state permissions. No secrets logged.'); process.exitCode = 1; }
}
