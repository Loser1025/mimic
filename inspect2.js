const https = require('https');
const crypto = require('crypto');
const SA = require('./automation-visitor-shindan/ageless-impulse-488713-m6-03014b3cddad.json');
const SSID = '1_xQzjPICr-m7VTcXh9R4AkDsFSCfqOcITKDausm5fuc';

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
      res.on('end', () => { try { ok(JSON.parse(body)); } catch (e) { console.log('PARSE ERROR:', body); err(e); } });
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
      res.on('end', () => { try { ok(JSON.parse(body)); } catch (e) { console.log('PARSE ERROR:', body); err(e); } });
    }).on('error', err);
  });
}

(async () => {
  const tok = (await post('https://oauth2.googleapis.com/token', { grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer', assertion: jwt })).access_token;
  
  // Get rows 1-5, all columns up to Z
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${encodeURIComponent('\u7372\u5f97\u4f01\u696d\u4e00\u89a7')}!A1:Z5`;
  const data = await get(url, tok);
  
  if (!data.values) {
    console.log('No data. Response:', JSON.stringify(data));
    return;
  }
  
  console.log('=== Row size by row ===');
  data.values.forEach((row, i) => {
    console.log(`Row ${i + 1}: ${row.length} columns`);
  });
  
  console.log('\n=== HEADERS (Row 1) ===');
  data.values[0].forEach((h, i) => {
    const colLetter = i < 26 ? String.fromCharCode(65 + i) : String.fromCharCode(64 + Math.floor(i / 26)) + String.fromCharCode(65 + (i % 26));
    console.log(`  ${colLetter} (${i}): ${h}`);
  });

  console.log('\n=== Row 2 (first data row) ===');
  if (data.values[1]) {
    data.values[1].forEach((v, i) => {
      const colLetter = i < 26 ? String.fromCharCode(65 + i) : String.fromCharCode(64 + Math.floor(i / 26)) + String.fromCharCode(65 + (i % 26));
      console.log(`  ${colLetter}: ${v}`);
    });
  }

  console.log('\n=== Row 3 (second data row) ===');
  if (data.values[2]) {
    data.values[2].forEach((v, i) => {
      const colLetter = i < 26 ? String.fromCharCode(65 + i) : String.fromCharCode(64 + Math.floor(i / 26)) + String.fromCharCode(65 + (i % 26));
      console.log(`  ${colLetter}: ${v}`);
    });
  }
})().catch(e => console.error('ERROR:', e));
