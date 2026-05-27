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
    }, res => { let body = ''; res.on('data', c => body += c); res.on('end', () => ok(JSON.parse(body))); });
    r.on('error', err); r.write(d); r.end();
  });
}

function get(u, t) {
  return new Promise((ok, err) => {
    https.get(u, { headers: { Authorization: 'Bearer ' + t } }, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => ok(JSON.parse(body)));
    }).on('error', err);
  });
}

(async () => {
  const tok = (await post('https://oauth2.googleapis.com/token', {
    grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
    assertion: jwt
  })).access_token;

  // Read rows 1 to 10, columns A to Z to find where the actual data starts
  const range = encodeURIComponent(SHEET_NAME + '!A1:Z10');
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${range}`;
  const data = await get(url, tok);

  if (!data.values) { console.log('No data'); return; }

  console.log('=== FULL PREVIEW (Rows 1-10, showing only non-empty cells) ===');
  data.values.forEach((row, ri) => {
    const nonEmpty = [];
    row.forEach((v, ci) => {
      if (v !== '' && v !== undefined && v !== null) {
        const colLabel = ci < 26 ? String.fromCharCode(65 + ci) : String.fromCharCode(64 + Math.floor(ci / 26)) + String.fromCharCode(65 + (ci % 26));
        nonEmpty.push(`${colLabel}=${v}`);
      }
    });
    if (nonEmpty.length > 0 || ri < 3) {
      console.log(`Row ${ri + 1}: ${nonEmpty.join(' | ') || '(empty)'}`);
    }
  });

  // Now get ALL rows for a thorough scan
  const rangeAll = encodeURIComponent(SHEET_NAME + '!A1:Z200');
  const urlAll = `https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${rangeAll}`;
  const all = await get(urlAll, tok);

  if (!all.values) { console.log('No all data'); return; }

  // Find the header row - look for rows containing typical headers
  console.log('\n=== SCANNING FOR HEADER ROW ===');
  all.values.forEach((row, ri) => {
    const hasTypicalHeader = ['企業名', 'No.', '業種', '職種', '都道府県', '市区町村'].some(h => row.some(v => String(v).trim() === h));
    if (hasTypicalHeader) {
      console.log(`\n>>> FOUND header-like row at Row ${ri + 1}:`);
      row.forEach((v, ci) => {
        if (v !== '') {
          const colLabel = ci < 26 ? String.fromCharCode(65 + ci) : String.fromCharCode(64 + Math.floor(ci / 26)) + String.fromCharCode(65 + (ci % 26));
          console.log(`  ${colLabel} [${ci}]: ${v}`);
        }
      });
    }
  });

  // Check V column for "締結済"
  console.log('\n=== V COLUMN SCAN ===');
  all.values.forEach((row, ri) => {
    const vVal = row[21];
    if (vVal === '締結済' || vVal === '締結済み') {
      console.log(`Row ${ri + 1}: V="${vVal}" | A="${row[0]}" | B="${row[1]}" | C="${row[2]}" | D="${row[3]}"`);
    }
  });

  // Also check all columns for "契約書締結"
  console.log('\n=== SEARCHING for "契約書締結" in all cells ===');
  all.values.forEach((row, ri) => {
    row.forEach((v, ci) => {
      if (String(v).includes('契約書') || String(v).includes('締結済')) {
        const colLabel = ci < 26 ? String.fromCharCode(65 + ci) : String.fromCharCode(64 + Math.floor(ci / 26)) + String.fromCharCode(65 + (ci % 26));
        console.log(`  Row ${ri + 1}, ${colLabel}: ${v}`);
      }
    });
  });

  // Check AR and beyond - seems there are stats in row 2
  console.log('\n=== Extended columns (AA+) for row 1 ===');
  all.values[0]?.forEach((v, ci) => {
    if (v !== '' && ci >= 26) {
      const colLabel = String.fromCharCode(64 + Math.floor(ci / 26)) + String.fromCharCode(65 + (ci % 26));
      console.log(`  ${colLabel} [${ci}]: ${v}`);
    }
  });
})().catch(e => console.error('ERROR:', e));
