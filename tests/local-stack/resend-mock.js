// Local stand-in for the Resend API: POST /emails records the message; GET /emails lists them; DELETE clears.
// Set FAIL=1 in a request's subject to simulate a provider error.
const http = require('http'); let mails = [];
http.createServer((req, res) => {
  let b = ''; req.on('data', c => b += c); req.on('end', () => {
    if (req.method === 'GET') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify(mails)); }
    if (req.method === 'DELETE') { mails = []; res.writeHead(204); return res.end(); }
    let m; try { m = JSON.parse(b) } catch { res.writeHead(400); return res.end('bad json') }
    if (!/^Bearer re_/.test(req.headers.authorization || '')) { res.writeHead(401); return res.end('{"message":"bad key"}') }
    if (process.env.FAIL_ALL === '1') { res.writeHead(500); return res.end('{"message":"mock failure"}') }
    mails.push({ ...m, at: Date.now() }); res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ id: 'mock_' + mails.length }));
  });
}).listen(54330, '127.0.0.1');
