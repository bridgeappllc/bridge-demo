// Minimal stand-in for Supabase's Kong API gateway: routes /auth/v1 -> GoTrue, /rest/v1 -> PostgREST.
const http = require('http');
const routes = { '/auth/v1': 9999, '/rest/v1': 3000 };
const CORS = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS', 'access-control-expose-headers': '*' };
http.createServer((req, res) => {
  if (req.method === 'OPTIONS') { res.writeHead(204, CORS); return res.end(); }
  const pre = Object.keys(routes).find(p => req.url.startsWith(p));
  if (!pre) { res.writeHead(404, CORS); return res.end('no route'); }
  const p = http.request({ host: '127.0.0.1', port: routes[pre], path: req.url.slice(pre.length) || '/', method: req.method, headers: { ...req.headers, host: '127.0.0.1' } }, r => {
    const h = { ...r.headers }; for (const k of Object.keys(h)) if (k.startsWith('access-control-')) delete h[k];
    res.writeHead(r.statusCode, { ...h, ...CORS }); r.pipe(res);
  });
  p.on('error', e => { res.writeHead(502, CORS); res.end(String(e)); });
  req.pipe(p);
}).listen(54321, '127.0.0.1', () => console.log('gateway on :54321'));
