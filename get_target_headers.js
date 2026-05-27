const https = require('https');
const crypto = require('crypto');
const fs = require('fs');

const SA = JSON.parse(fs.readFileSync('./automation-visitor-shindan/ageless-impulse-488713-m6-03014b3cddad.json', 'utf8'));
const SSID = '1gNEl14RKlx-14i87FHpmHG0fSaX6zwmW2YZNVWlTKko';

function b64url(b) {
  return b.toString('base64').replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'');
}

const now = Math.floor(Date.now()/1000);
const h = b64url(Buffer.from(JSON.stringify({alg:'RS256',typ:'JWT'})));
const p = b64url(Buffer.from(JSON.stringify({iss:SA.client_email,scope:'https://www.googleapis.com/auth/spreadsheets.readonly',aud:'https://oauth2.googleapis.com/token',iat:now,exp:now+3600})));
const s = crypto.createSign('RSA-SHA256');
s.update(h+'.'+p);
const jwt = h+'.'+p+'.'+b64url(s.sign(SA.private_key));

function post(u,b){return new Promise((ok,err)=>{const d=new URLSearchParams(b).toString();const U=new URL(u);const r=https.request({hostname:U.hostname,path:U.pathname,method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','Content-Length':Buffer.byteLength(d)}},res=>{let body='';res.on('data',c=>body+=c);res.on('end',()=>ok(JSON.parse(body)));});r.on('error',err);r.write(d);r.end();});}
function get(u,t){return new Promise((ok,err)=>{https.get(u,{headers:{Authorization:'Bearer '+t}},res=>{let body='';res.on('data',c=>body+=c);res.on('end',()=>ok(JSON.parse(body)));}).on('error',err);});}

(async()=>{
  const tok = (await post('https://oauth2.googleapis.com/token',{grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion:jwt})).access_token;
  
  // Get rows 1-3, columns A to Z (シート1)
  const url = 'https://sheets.googleapis.com/v4/spreadsheets/'+SSID+'/values/'+encodeURIComponent('\u30b7\u30fc\u30c81')+'!A1:Z3';
  const data = await get(url, tok);
  
  if(!data.values){ console.log('No data'); return; }
  
  console.log('=== Row 1 (categories) ===');
  data.values[0].forEach((v,i)=>{if(v!=='')console.log('  '+String.fromCharCode(65+i)+'['+i+']: '+v);});
  
  console.log('\n=== Row 2 (headers) ===');
  data.values[1].forEach((v,i)=>{if(v!=='')console.log('  '+String.fromCharCode(65+i)+'['+i+']: '+v);});
  
  console.log('\n=== Row 3 (sample data) ===');
  data.values[2].forEach((v,i)=>{if(v!=='')console.log('  '+String.fromCharCode(65+i)+'['+i+']: '+v);});
  
  // Also get wider range to see all columns
  const url2 = 'https://sheets.googleapis.com/v4/spreadsheets/'+SSID+'/values/'+encodeURIComponent('\u30b7\u30fc\u30c81')+'!A1:AH3';
  const data2 = await get(url2, tok);
  console.log('\n=== Row 2 headers (AH range - all columns) ===');
  if(data2.values && data2.values[1]){
    data2.values[1].forEach((v,i)=>{
      const label = i<26 ? String.fromCharCode(65+i) : String.fromCharCode(64+Math.floor(i/26))+String.fromCharCode(65+(i%26));
      console.log('  '+label+'['+i+']: '+(v||'(empty)'));
    });
    console.log('Total cols: '+data2.values[1].length);
  }
  
  // Get last No. to know what to assign
  const url3 = 'https://sheets.googleapis.com/v4/spreadsheets/'+SSID+'/values/'+encodeURIComponent('\u30b7\u30fc\u30c81')+'!A:A';
  const data3 = await get(url3, tok);
  if(data3.values){
    const allNumbers = data3.values.slice(2).map(r=>r[0]).filter(v=>v!==''&&!isNaN(Number(v)));
    const maxNo = allNumbers.length > 0 ? Math.max(...allNumbers.map(Number)) : 0;
    console.log('\nTotal data rows: '+allNumbers.length);
    console.log('Max No.: '+maxNo);
    console.log('Last 5 Nos: '+allNumbers.slice(-5).join(', '));
  }
})().catch(e=>console.error('ERROR:',e));
