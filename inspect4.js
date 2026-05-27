const https = require('https');
const crypto = require('crypto');
const SA = require('./automation-visitor-shindan/ageless-impulse-488713-m6-03014b3cddad.json');
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
  return new Promise((ok, err) => {
    https.get(u, { headers: { Authorization: 'Bearer ' + t } }, res => { let body = ''; res.on('data', c => body += c); res.on('end', () => ok(JSON.parse(body))); }).on('error', err);
  });
}

(async () => {
  const tok = (await post('https://oauth2.googleapis.com/token', { grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer', assertion: jwt })).access_token;

  // Read all columns (A to Z = 26 cols) for rows 1-3
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${encodeURIComponent(SHEET_NAME)}!A1:Z3`;
  const data = await get(url, tok);

  if (data.error) { console.log('ERROR:', JSON.stringify(data.error)); return; }
  if (!data.values || data.values.length === 0) { { console.log('EMPTY or no permission'); console.log(JSON.stringify(data).substring(0,300)); } return; }

  console.log('Total rows returned:', data.values.length);
  console.log('Total cols in row 1:', data.values[0].length);

  // Also extended to check cols beyond Z
  const url2 = `https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${encodeURIComponent(SHEET_NAME)}!A1:AZ5`;
  const data2 = await get(url2, tok);
  console.log('\nTotal cols in row 1 (AZ range):', data2.values[0].length);
  console.log('Total rows (AZ range):', data2.values.length);

  console.log('\n=== HEADERS (Row 1, ALL columns) ===');
  data2.values[0].forEach((cell, i) => {
    let colLabel = '';
    if (i < 26) colLabel = String.fromCharCode(65 + i);
    else colLabel = String.fromCharCode(64 + Math.floor(i / 26)) + String.fromCharCode(65 + (i % 26));
    console.log(`  ${colLabel} [${i}]: ${cell}`);
  });

  console.log('\n=== Row 2 (first data) ===');
  if (data2.values[1]) {
    data2.values[1].forEach((v, i) => {
      let colLabel = '';
      if (i < 26) colLabel = String.fromCharCode(65 + i);
      else colLabel = String.fromCharCode(64 + Math.floor(i / 26)) + String.fromCharCode(65 + (i % 26));
      console.log(`  ${colLabel}: ${v}`);
    });
  }

  console.log('\n=== Row 3 (second data) ===');
  if (data2.values[2]) {
    data2.values[2].forEach((v, i) => {
      let colLabel = '';
      if (i < 26) colLabel = String.fromCharCode(65 + i);
      else colLabel = String.fromCharCode(64 + Math.floor(i / 26)) + String.fromCharCode(65 + (i % 26));
      console.log(`  ${colLabel}: ${v}`);
    });
  }

  // Find rows where V (index 21) === '締結済'
  const urlAll = `https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${encodeURIComponent(SHEET_NAME)}!A1:Z200`;
  const allData = await get(urlAll, tok);
  if (allData.values && allData.values.length > 1) {
    const dataRows = allData.values.slice(1);
    const keiyakuRowIndices = [];
    dataRows.forEach((row, idx) => {
      if (row[21] === '\u7d04\u7d04\u6e08') keiyakuRowIndices.push(idx + 2); // +2 because header is row 1, and idx is 0-based
    });
    console.log(`\n=== Rows where V == "締結済": ${keiyakuRowIndices.length} rows ===`);
    console.log('Row numbers:', keiyakuRowIndices.join(', '));
  }
})().catch(e => console.error('ERROR:', e));
