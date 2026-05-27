const https = require('https');
const crypto = require('crypto');
const SA = require('./automation-visitor-shindan/ageless-impulse-488713-m6-03014b3cddad.json');
const SSID = '1_xQzjPICr-m7VTcXh9R4AkDsFSCfqOcITKDausm5fuc';
const SHEET = '\u7372\u5f97\u4f01\u696d\u4e00\u89a7';

function b64url(b){return b.toString('base64').replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'');}
const now=Math.floor(Date.now()/1000);
const h=b64url(Buffer.from(JSON.stringify({alg:'RS256',typ:'JWT'})));
const p=b64url(Buffer.from(JSON.stringify({iss:SA.client_email,scope:'https://www.googleapis.com/auth/spreadsheets.readonly',aud:'https://oauth2.googleapis.com/token',iat:now,exp:now+3600})));
const s=crypto.createSign('RSA-SHA256');
s.update(h+'.'+p);
const jwt=h+'.'+p+'.'+b64url(s.sign(SA.private_key));

function post(u,b){return new Promise((ok,err)=>{const d=new URLSearchParams(b).toString();const U=new URL(u);const r=https.request({hostname:U.hostname,path:U.pathname,method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','Content-Length':Buffer.byteLength(d)}},res=>{let body='';res.on('data',c=>body+=c);res.on('end',()=>ok(JSON.parse(body)));});r.on('error',err);r.write(d);r.end();});}
function get(u,t){return new Promise((ok,err)=>{https.get(u,{headers:{Authorization:'Bearer '+t}},res=>{let body='';res.on('data',c=>body+=c);res.on('end',()=>ok(JSON.parse(body)));}).on('error',err);});}

(async()=>{
  const tok=(await post('https://oauth2.googleapis.com/token',{grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion:jwt})).access_token;
  
  // 1) Get all headers (A to Z) + rows 1-3
  const d1=await get(`https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${encodeURIComponent(SHEET)}!A1:Z3`,tok);
  if(d1.error){console.log('ERR:',JSON.stringify(d1.error));return;}
  if(!d1.values){console.log('No values. Full:',JSON.stringify(d1).substring(0,400));return;}

  console.log('Row1 cols:',d1.values[0].length,'| Rows:',d1.values.length);

  console.log('\n=== HEADERS ROW 1 ===');
  d1.values[0].forEach((v,i)=>{
    const l=i<26?String.fromCharCode(65+i):String.fromCharCode(64+Math.floor(i/26))+String.fromCharCode(65+i%26);
    console.log('  '+l+'['+i+']: '+v);
  });

  console.log('\n=== ROW 2 ===');
  if(d1.values[1])d1.values[1].forEach((v,i)=>{
    const l=i<26?String.fromCharCode(65+i):String.fromCharCode(64+Math.floor(i/26))+String.fromCharCode(65+i%26);
    console.log('  '+l+': '+v);
  });

  console.log('\n=== ROW 3 ===');
  if(d1.values[2])d1.values[2].forEach((v,i)=>{
    const l=i<26?String.fromCharCode(65+i):String.fromCharCode(64+Math.floor(i/26))+String.fromCharCode(65+i%26);
    console.log('  '+l+': '+v);
  });

  // 2) If row 1 has category labels on merged cells, also read row 2 as sub-headers if needed
  // 3) Find all rows with V(col21) == '締結済' and count
  const dAll=await get(`https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${encodeURIComponent(SHEET)}!A1:Z200`,tok);
  if(dAll.values&&dAll.values.length>1){
    const rows=dAll.values.slice(1);
    const matched=[],unmatched=[];
    rows.forEach((row,idx)=>{
      const rowNum=idx+2;
      if(row[21]==='\u7d04\u7d04\u6e08') matched.push(rowNum);
      else if(row[0]||row[1]) unmatched.push({row:rowNum,v:row[21]});
    });
    console.log('\n=== V=="\u7d04\u7d04\u6e08" rows: '+matched.length+' ===');
    console.log('Row #s:',matched.join(', '));
    console.log('\n=== Non-empty other rows (V values): ===');
    unmatched.forEach(r=>console.log('  Row '+r.row+': V="'+r.v+'"'));
  }
})().catch(e=>console.error('ERR:',e));
