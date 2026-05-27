const https = require('https');
const crypto = require('crypto');
const fs = require('fs');

const SA = JSON.parse(fs.readFileSync('./automation-visitor-shindan/ageless-impulse-488713-m6-03014b3cddad.json', 'utf8'));
const SSID = '1_xQzjPICr-m7VTcXh9R4AkDsFSCfqOcITKDausm5fuc';
const SHEET_NAME = '\u7372\u5f97\u4f01\u696d\u4e00\u89a7';

function b64url(b) {
  return b.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

const now = Math.floor(Date.now() / 1000);
const h = b64url(Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })));
const p = b64url(Buffer.from(JSON.stringify({
  iss: SA.client_email,
  scope: 'https://www.googleapis.com/auth/spreadsheets.readonly',
  aud: 'https://oauth2.googleapis.com/token',
  iat: now,
  exp: now + 3600
})));
const s = crypto.createSign('RSA-SHA256');
s.update(h + '.' + p);
const jwt = h + '.' + p + '.' + b64url(s.sign(SA.private_key));

function post(u, b) {
  return new Promise((ok, err) => {
    const d = new URLSearchParams(b).toString();
    const U = new URL(u);
    const r = https.request({
      hostname: U.hostname, path: U.pathname, method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': Buffer.byteLength(d) }
    }, res => { let body = ''; res.on('data', c => body += c); res.on('end', () => ok(JSON.parse(body))); });
    r.on('error', err); r.write(d); r.end();
  });
}

function get(u, t) {
  return new Promise((resolve, reject) => {
    https.get(u, { headers: { Authorization: 'Bearer ' + t } }, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => {
        console.log('[HTTP status]', res.statusCode);
        try { resolve(JSON.parse(body)); }
        catch (e) { console.log('PARSE ERROR, raw:', body.substring(0, 500)); reject(e); }
      });
    }).on('error', reject);
  });
}

(async () => {
  const tok = (await post('https://oauth2.googleapis.com/token', {
    grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
    assertion: jwt
  })).access_token;
  console.log('Token OK');

  // Small range first: A1:E10
  const url = 'https://sheets.googleapis.com/v4/spreadsheets/' + SSID + '/values/' + encodeURIComponent(SHEET_NAME + '!A1:E10');
  console.log('\nURL:', url);
  const data = await get(url, tok);
  console.log('Response:', JSON.stringify(data).substring(0, 2000));

  if (data.values) {
    console.log('\nRow 1:', data.values[0]);
    console.log('Row 2:', data.values[1]);
    console.log('Row 3:', data.values[2]);
  }
})().catch(e => console.error('ERROR:', e));
