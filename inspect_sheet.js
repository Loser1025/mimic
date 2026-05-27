const https = require('https');
const crypto = require('crypto');

const SERVICE_ACCOUNT = require('./automation-visitor-shindan/ageless-impulse-488713-m6-03014b3cddad.json');
const SPREADSHEET_ID = '1_xQzjPICr-m7VTcXh9R4AkDsFSCfqOcITKDausm5fuc';

// Step 1: Create JWT and get access token
function base64url(buf) {
  return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

function createJWT() {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: 'RS256', typ: 'JWT' };
  const payload = {
    iss: SERVICE_ACCOUNT.client_email,
    scope: 'https://www.googleapis.com/auth/spreadsheets.readonly',
    aud: 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3600
  };
  const headerB64 = base64url(Buffer.from(JSON.stringify(header)));
  const payloadB64 = base64url(Buffer.from(JSON.stringify(payload)));
  const sign = crypto.createSign('RSA-SHA256');
  sign.update(headerB64 + '.' + payloadB64);
  const signature = base64url(sign.sign(SERVICE_ACCOUNT.private_key));
  return headerB64 + '.' + payloadB64 + '.' + signature;
}

function post(url, body) {
  return new Promise((resolve, reject) => {
    const data = new URLSearchParams(body).toString();
    const u = new URL(url);
    const req = https.request({
      hostname: u.hostname,
      path: u.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(data)
      }
    }, res => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => resolve(JSON.parse(body)));
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

function get(url, token) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { Authorization: 'Bearer ' + token } }, res => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => resolve(JSON.parse(body)));
    }).on('error', reject);
  });
}

async function main() {
  const jwt = createJWT();
  const tokenResp = await post('https://oauth2.googleapis.com/token', {
    grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
    assertion: jwt
  });
  console.log('Token OK:', !!tokenResp.access_token);
  const token = tokenResp.access_token;

  // Step 2: Get sheet metadata to find sheet name
  const metaUrl = `https://sheets.googleapis.com/v4/spreadsheets/${SPREADSHEET_ID}`;
  const meta = await get(metaUrl, token);
  console.log('\n=== Sheets ===');
  meta.sheets.forEach(s => {
    console.log(`  "${s.properties.title}" (id=${s.properties.sheetId})`);
  });

  // Find the sheet with gid 870498158
  const targetSheet = meta.sheets.find(s => s.properties.sheetId == 870498158);
  const sheetName = targetSheet ? targetSheet.properties.title : meta.sheets[0].properties.title;
  console.log(`\nTarget sheet: "${sheetName}"`);

  // Step 3: Get first 3 rows to see headers and sample data
  const rangeUrl = `https://sheets.googleapis.com/v4/spreadsheets/${SPREADSHEET_ID}/values/${encodeURIComponent(sheetName)}!A1:Z3`;
  const rangeData = await get(rangeUrl, token);
  
  if (rangeData.values) {
    console.log('\n=== Headers (Row 1) ===');
    rangeData.values[0].forEach((h, i) => {
      console.log(`  ${String.fromCharCode(65 + i)} (${i}): ${h}`);
    });
    
    console.log('\n=== Sample Row 2 ===');
    if (rangeData.values[1]) {
      rangeData.values[1].forEach((v, i) => {
        console.log(`  ${String.fromCharCode(65 + i)}: ${v}`);
      });
    }
    
    console.log('\n=== Sample Row 3 ===');
    if (rangeData.values[2]) {
      rangeData.values[2].forEach((v, i) => {
        console.log(`  ${String.fromCharCode(65 + i)}: ${v}`);
      });
    }
  }

  // Step 4: Count total rows
  const allUrl = `https://sheets.googleapis.com/v4/spreadsheets/${SPREADSHEET_ID}/values/${encodeURIComponent(sheetName)}!A:A`;
  const allData = await get(allUrl, token);
  console.log(`\nTotal rows: ${allData.values ? allData.values.length : 0}`);
}

main().catch(e => console.error('Error:', e.message));
