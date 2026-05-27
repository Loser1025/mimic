const https = require('https');
const crypto = require('crypto');
const fs = require('fs');

const SA = JSON.parse(fs.readFileSync('./automation-visitor-shindan/ageless-impulse-488713-m6-03014b3cddad.json', 'utf8'));
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
  iat: now, exp: now + 3600
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
      res.on('end', () => resolve(JSON.parse(body)));
    }).on('error', reject);
  });
}

function colLabel(i) {
  if (i < 26) return String.fromCharCode(65 + i);
  return String.fromCharCode(64 + Math.floor(i / 26)) + String.fromCharCode(65 + (i % 26));
}

(async () => {
  const tok = (await post('https://oauth2.googleapis.com/token', {
    grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer', assertion: jwt
  })).access_token;
  console.log('Token OK\n');

  // Row 1: A to L (non-empty check)
  for (let startCol = 0; startCol < 30; startCol += 12) {
    const startL = colLabel(startCol);
    const endL = colLabel(Math.min(startCol + 11, 40));
    const range = encodeURIComponent('\u7372\u5f97\u4f01\u696d\u4e00\u89a7' + '!' + startL + '1:' + endL + '3');
    const url = 'https://sheets.googleapis.com/v4/spreadsheets/' + SSID + '/values/' + range;
    const data = await get(url, tok);
    if (data.values && data.values.length > 0 && data.values[0].length > 0) {
      console.log(`--- Range ${startL}1:${endL}3 ---`);
      data.values.forEach((row, ri) => {
        row.forEach((v, ci) => {
          if (v !== '' && v != null) {
            console.log(`  Row${ri + 1} ${colLabel(startCol + ci)}[${startCol + ci}]: ${v}`);
          }
        });
      });
    }
  }

  // Now find where actual data table is - scan every 5 rows
  console.log('\n=== Scanning row 1-50 for first non-empty row in A column ===');
  for (let r = 1; r <= 50; r += 5) {
    const endR = r + 4;
    const range = encodeURIComponent('\u7372\u5f97\u4f01\u696d\u4e00\u89a7' + '!A' + r + ':Z' + endR);
    const url = 'https://sheets.googleapis.com/v4/spreadsheets/' + SSID + '/values/' + range;
    const data = await get(url, tok);
    if (data.values && data.values.length > 0) {
      const nonEmptyRows = [];
      data.values.forEach((row, ri) => {
        const actualRow = r + ri;
        const nonEmpty = row.filter(v => v !== '' && v != null);
        if (nonEmpty.length > 0) {
          nonEmptyRows.push(`Row${actualRow}(${nonEmpty.length}cells)`);
        }
      });
      if (nonEmptyRows.length > 0) {
        console.log(`  Rows ${r}-${endR}: ${nonEmptyRows.join(', ')}`);

        // Show detail for first non-empty row
        for (let ri2 = 0; ri2 < data.values.length; ri2++) {
          const row = data.values[ri2];
          const isNonEmpty = row.filter(v => v !== '' && v != null).length > 0;
          if (isNonEmpty) {
            const actualRow = r + ri2;
            row.forEach((v, ci) => {
              if (v !== '' && v != null) {
                console.log(`    Row${actualRow} ${colLabel(ci)}[${ci}]: ${v}`);
              }
            });
            break;
          }
        }
      }
    }
  }

  // Find "契約書締結" or "締結済" anywhere
  console.log('\n=== Searching all rows for contract-related keywords ===');
  const allRange = encodeURIComponent('\u7372\u5f97\u4f01\u696d\u4e00\u89a7' + '!A1:Z200');
  const allUrl = 'https://sheets.googleapis.com/v4/spreadsheets/' + SSID + '/values/' + allRange;
  const allData = await get(allUrl, tok);
  if (allData.values) {
    allData.values.forEach((row, ri) => {
      row.forEach((v, ci) => {
        const s = String(v || '');
        if (s.includes('\u5951\u7d04\u66f8') || s.includes('\u7d04\u7d04\u6e08') || s.includes('\u30b0\u30ea\u30a2\u7d04\u7d04')) {
          console.log(`  Row${ri + 1} ${colLabel(ci)}[${ci}]: "${s}"`);
        }
      });
    });
  }
})().catch(e => console.error('ERROR:', e));
