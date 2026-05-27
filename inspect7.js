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
  
  // The sheet has 51 cols (AY). Let's read A1:AY3
  const range = SHEET + '!A1:AY5';
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${encodeURIComponent(range)}`;
  const d = await get(url, tok);
  
  if(d.error){console.log('ERR:',JSON.stringify(d.error));return;}
  console.log('Response keys:', Object.keys(d));
  if(d.range) console.log('Range:', d.range);
  
  if(!d.values){
    console.log('No values. Full response:', JSON.stringify(d).substring(0,500));
    
    // Try WITHOUT encoding the sheet name
    const url2 = `https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/'${SHEET}'!A1:AY3`;
    console.log('\nRetrying with different format...');
    const d2 = await get(url2, tok);
    if(d2.values){
      console.log('SUCCESS without encodeURIComponent!');
      d2.values.forEach((row,ri)=>{
        console.log('Row'+(ri+1)+'('+row.length+'cols):');
        row.forEach((v,i)=>{
          const l=i<26?String.fromCharCode(65+i):String.fromCharCode(64+Math.floor(i/26))+String.fromCharCode(65+i%26);
          if(v && v.trim()!=='') console.log('  '+l+'['+i+']: '+v);
        });
      });
    } else {
      console.log('Still no values:', JSON.stringify(d2).substring(0,300));
    }
    return;
  }
  
  console.log('Rows:', d.values.length, '| Cols in row1:', d.values[0].length);
  d.values.forEach((row,ri)=>{
    console.log('\n=== ROW '+(ri+1)+' ===');
    row.forEach((v,i)=>{
      const l=i<26?String.fromCharCode(65+i):String.fromCharCode(64+Math.floor(i/26))+String.fromCharCode(65+i%26);
      console.log('  '+l+'['+i+']: '+v);
    });
  });
})().catch(e=>console.error('ERR:',e));
