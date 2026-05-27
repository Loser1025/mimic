const https = require('https');
const crypto = require('crypto');
const SA = require('./automation-visitor-shindan/ageless-impulse-488713-m6-03014b3cddad.json');

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
    }, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => {
        try { ok(JSON.parse(body)); }
        catch (e) { console.log('RAW:', body.substring(0, 500)); err(e); }
      });
    });
    r.on('error', err);
    r.write(d);
    r.end();
  });
}

function get(u, t) {
  return new Promise((ok, err) => {
    https.get(u, { headers: { Authorization: 'Bearer ' + t } }, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => {
        try { ok(JSON.parse(body)); }
        catch (e) { console.log('RAW:', body.substring(0, 500)); err(e); }
      });
    }).on('error', err);
  });
}

(async () => {
  const tok = (await post('https://oauth2.googleapis.com/token', {
    grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
    assertion: jwt
  })).access_token;

  // Test both spreadsheets
  const ids = [
    { id: '1gNEl14RKlx-14i87FHpmHG0fSaX6zwmW2YZNVWlTKko', sheet: '\u30b7\u30fc\u30c81' },  // RA SEARCH Sheet1
    { id: '1_xQzjPICr-m7VTcXh9R4AkDsFSCfqOcITKDausm5fuc', sheet: '\u7372\u5f97\u4f01\u696d\u4e00\u89a7' }  // Acquired companies
  ];

  for (const { id, sheet } of ids) {
    console.log(`\n========== ${sheet} (SSID: ${id}) ==========`);
    const url = `https://sheets.googleapis.com/v4/spreadsheets/${id}/values/${encodeURIComponent(sheet)}!A1:H3`;
    const data = await get(url, tok);

    if (data.error) {
      console.log('ERROR:', JSON.stringify(data.error));
    } else if (!data.values || data.values.length === 0) {
      console.log('No values (empty sheet or no permission)');
      console.log('Full response:', JSON.stringify(data).substring(0, 300));
    } else {
      data.values.forEach((row, ri) => {
        console.log(`Row ${ri + 1}:`);
        row.forEach((v, ci) => {
          console.log(`  ${String.fromCharCode(65 + ci)}: ${v}`);
        });
      });
    }
  }
})().catch(e => console.error('ERROR:', e));
