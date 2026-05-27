const https = require('https');
const crypto = require('crypto');
const fs = require('fs');

const SA = JSON.parse(fs.readFileSync('./automation-visitor-shindan/ageless-impulse-488713-m6-03014b3cddad.json', 'utf8'));
const SSID = '1_xQzjPICr-m7VTcXh9R4AkDsFSCfqOcITKDausm5fuc';
const SHEET_NAME = '獲得企業一覧';

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
    r.on('error', err); r.write(d); r.end();
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

  console.log('Token OK');

  // Read all columns A to AZ for rows 1 to 5
  const range = encodeURIComponent(SHEET_NAME + '!A1:AZ5');
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${range}`;
  const data = await get(url, tok);

  if (data.error) {
    console.log('API ERROR:', JSON.stringify(data.error, null, 2));
    return;
  }

  if (!data.values || data.values.length === 0) {
    console.log('No data. Response:', JSON.stringify(data).substring(0, 500));
    return;
  }

  console.log('Rows returned:', data.values.length);
  console.log('Cols in row 1:', data.values[0].length);

  // Print ALL headers
  console.log('\n=== HEADERS (Row 1) ===');
  data.values[0].forEach((h, i) => {
    const colLabel = i < 26
      ? String.fromCharCode(65 + i)
      : String.fromCharCode(64 + Math.floor(i / 26)) + String.fromCharCode(65 + (i % 26));
    console.log(`  ${colLabel} [${i}]: ${h}`);
  });

  // Print rows 2 and 3 for comparison
  for (let r = 1; r < Math.min(data.values.length, 5); r++) {
    console.log(`\n=== Row ${r + 1} ===`);
    data.values[r].forEach((v, i) => {
      const colLabel = i < 26
        ? String.fromCharCode(65 + i)
        : String.fromCharCode(64 + Math.floor(i / 26)) + String.fromCharCode(65 + (i % 26));
      console.log(`  ${colLabel}: ${v}`);
    });
  }

  // Now count total rows and find V=締結済 rows
  const rangeAll = encodeURIComponent(SHEET_NAME + '!A1:AZ200');
  const urlAll = `https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${rangeAll}`;
  const all = await get(urlAll, tok);
  if (all.values && all.values.length > 1) {
    const dataRows = all.values.slice(1);
    const vRows = [];
    dataRows.forEach((row, idx) => {
      if (row[21] === '締結済') vRows.push(idx + 2);
    });
    console.log(`\n統計: 全${dataRows.length}件のうち V=締結済 は ${vRows.length}件`);
    if (vRows.length > 0 && vRows.length <= 30) {
      console.log('対象行番号:', vRows.join(', '));
    }
  }
})().catch(e => console.error('ERROR:', e));
