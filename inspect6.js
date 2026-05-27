const https = require('https');
const crypto = require('crypto');
const SA = require('./automation-visitor-shindan/ageless-impulse-488713-m6-03014b3cddad.json');
const SSID = '1_xQzjPICr-m7VTcXh9R4AkDsFSCfqOcITKDausm5fuc';

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
  
  // Step 1: Get spreadsheet metadata to see all sheets
  const meta = await get(`https://sheets.googleapis.com/v4/spreadsheets/${SSID}`,tok);
  if(meta.error){console.log('META ERR:',JSON.stringify(meta.error));return;}
  
  console.log('=== All sheets ===');
  meta.sheets.forEach(s=>{
    const p=s.properties;
    console.log('  "'+p.title+'" sheetId='+p.sheetId+' index='+p.index);
    if(p.gridProperties){
      console.log('    rows='+p.gridProperties.rowCount+' cols='+p.gridProperties.columnCount);
    }
  });

  // Step 2: Try each sheet
  for(const s of meta.sheets){
    const name = s.properties.title;
    const url = `https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${encodeURIComponent(name)}!A1:E2`;
    const d = await get(url, tok);
    if(d.values && d.values.length > 0){
      console.log('\n=== "'+name+'" ROW1 ===');
      d.values[0].forEach((v,i)=>console.log('  '+String.fromCharCode(65+i)+': '+v));
      if(d.values[1]){
        console.log('  ROW2:');
        d.values[1].forEach((v,i)=>console.log('  '+String.fromCharCode(65+i)+': '+v));
      }
    } else {
      console.log('\n"'+name+'": empty or no data');
    }
  }
})().catch(e=>console.error('ERR:',e));
