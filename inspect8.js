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

  // Sheet has 1490 rows. Read all to find header row and data rows.
  // Read A1:AY1500 with VALUE_RENDER_OPTION=UNFORMATTED
  const url=`https://sheets.googleapis.com/v4/spreadsheets/${SSID}/values/${encodeURIComponent(SHEET+'!A1:AY1500')}?valueRenderOption=FORMATTED_VALUE`;
  const d=await get(url,tok);
  if(d.error){console.log('ERR:',JSON.stringify(d.error));return;}
  if(!d.values){console.log('No values');return;}
  
  console.log('Total rows:', d.values.length);

  // Find header row: look for row that has 'No' or '\u4f01\u696d\u540d' or or 'No.' in first few cols
  let headerRowIdx = -1;
  for(let i=0;i<Math.min(30,d.values.length);i++){
    const row = d.values[i];
    const rowStr = row.join('|');
    if((row[0]==='No' || row[0]==='No.' || row[0]==='\u756a\u53f7') && 
       (row[1]==='\u4f01\u696d\u540d' || row[1]==='\u4f1a\u793e\u540d' || row[1]==='\u4f01\u696d\u540d\uff08\u30ab\u30ca\uff09')){
      headerRowIdx = i;
      console.log('Header found at row', i+1);
      break;
    }
    // Also try finding just '\u4f01\u696d\u540d' anywhere in first 30 rows
    if(rowStr.includes('\u4f01\u696d\u540d') && rowStr.includes('\u696d\u7a2e')){
      headerRowIdx = i;
      console.log('Header found at row', i+1, '(by content match)');
      break;
    }
  }

  if(headerRowIdx >= 0){
    // Print header row
    console.log('\n=== HEADER ROW (row '+(headerRowIdx+1)+') ===');
    d.values[headerRowIdx].forEach((v,i)=>{
      const l=i<26?String.fromCharCode(65+i):String.fromCharCode(64+Math.floor(i/26))+String.fromCharCode(65+i%26);
      console.log('  '+l+'['+i+']: '+v);
    });
    
    // Print next 2 data rows
    for(let r=headerRowIdx+1;r<=Math.min(headerRowIdx+3, d.values.length-1);r++){
      console.log('\n=== DATA ROW '+(r+1)+' ===');
      d.values[r].forEach((v,i)=>{
        const l=i<26?String.fromCharCode(65+i):String.fromCharCode(64+Math.floor(i/26))+String.fromCharCode(65+i%26);
        if(v && v.trim()!=='') console.log('  '+l+'['+i+']: '+v);
      });
    }

    // Find rows where V(col 21) == '\u7d04\u7d04\u6e08'
    const dataStart = headerRowIdx + 1;
    const matched = [], unmatchedSample = [];
    for(let r=dataStart;r<d.values.length;r++){
      const row = d.values[r];
      if(!row[0] && !row[1]) continue; // skip empty rows
      if(row[21] === '\u7d04\u7d04\u6e08') {
        matched.push(r+1);
      } else if(row[1] || row[0]) {
        if(unmatchedSample.length < 10) unmatchedSample.push({row:r+1, v:row[21]});
      }
    }
    console.log('\n=== Rows where V="\u7d04\u7d04\u6e08": '+matched.length+' rows ===');
    console.log('Row numbers:', matched.slice(0,20).join(', ')+(matched.length>20?'...':''));
    console.log('\n=== Sample unmatched rows V values ===');
    unmatchedSample.forEach(r=>console.log('  Row '+r.row+': V="'+r.v+'"'));
  } else {
    console.log('Header row not found in first 30 rows. Showing rows 1-10:');
    for(let i=0;i<Math.min(10,d.values.length);i++){
      const row = d.values[i];
      const nonEmpty = [];
      row.forEach((v,ci)=>{if(v && v.trim()!=='') nonEmpty.push(String.fromCharCode(65+Math.floor(ci/26))+(ci<26?'':String.fromCharCode(65+ci%26))+'['+ci+']='+v);});
      console.log('Row '+(i+1)+': '+nonEmpty.join(' | '));
    }
  }
})().catch(e=>console.error('ERR:',e));
