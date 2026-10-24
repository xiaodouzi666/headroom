
import puppeteer from '/home/xiaodouzi/workspace/headroom/.tools/lighthouse/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js';
import lighthouse, {generateReport} from '/home/xiaodouzi/workspace/headroom/.tools/lighthouse/node_modules/lighthouse/core/index.js';
import {readFile, writeFile, readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import os from 'node:os';
import path from 'node:path';

const root='/home/xiaodouzi/workspace/headroom';
const output=process.argv[2], profile=process.argv[3];
const url='http://127.0.0.1:8765/';
const requests=[],blocked=[],pageErrors=[],assets=[];
const viewport={width:390,height:844,deviceScaleFactor:2,isMobile:true,hasTouch:true};
let browser, chromePID, browserVersion, result, mobile, failure;
const started=new Date().toISOString();
async function manifest(dir) {
 const result={};
 for(const entry of await readdir(dir,{withFileTypes:true})) {
  const file=path.join(dir,entry.name);
  if(entry.isDirectory()) Object.assign(result,await manifest(file));
  else if(entry.isFile()) result[path.relative(root,file)]=createHash('sha256').update(await readFile(file)).digest('hex');
 }
 return result;
}
const before=await manifest(path.join(root,'web/dist'));
async function guard(page,phase) {
 await page.setRequestInterception(true);
 page.on('request',request=>{
  const target=request.url(),method=request.method();
  const item={phase,url:target,method};requests.push(item);
  if ((target.startsWith(url) && ['GET','HEAD'].includes(method)) ||
      target.startsWith('data:') || target.startsWith('blob:') || target==='about:blank') {
   request.continue();
  } else {blocked.push(item);request.abort();}
 });
 page.on('pageerror',error=>pageErrors.push({phase,error:String(error)}));
 page.on('response',response=>{
  const target=response.url();
  if(target.startsWith(url)) assets.push({phase,url:target,status:response.status()});
 });
}
try {
 const env={...process.env,TMPDIR:profile,XDG_CONFIG_HOME:path.join(profile,'xdg-config'),XDG_CACHE_HOME:path.join(profile,'xdg-cache')};
 delete env.NEBIUS_API_KEY;delete env.TAVILY_API_KEY;
 browser=await puppeteer.launch({
  executablePath:'/usr/bin/google-chrome',headless:true,userDataDir:path.join(profile,'browser'),
  args:['--disable-gpu','--disable-extensions','--disable-background-networking','--disable-component-update',
        '--disable-sync','--disable-default-apps','--no-first-run','--no-default-browser-check',
        '--metrics-recording-only','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1'],
  env
 });
 chromePID=browser.process().pid;browserVersion=await browser.version();
 await writeFile(path.join(output,'owned-browser.json'),JSON.stringify({pid:chromePID,profile,started,browserVersion},null,2)+'\n',{flag:'wx'});
 console.log(JSON.stringify({stage:'browser_ready',pid:chromePID,browserVersion,output}));
 const page=await browser.newPage();
 await guard(page,'lighthouse');
 result=await lighthouse(url,{
  onlyCategories:['performance'],logLevel:'error',output:'json',
  formFactor:'mobile',screenEmulation:{mobile:true,width:390,height:844,deviceScaleFactor:2,disabled:false},
  throttlingMethod:'simulate',maxWaitForLoad:45000,enableErrorReporting:false
 },undefined,page);
 if(!result)throw new Error('Lighthouse returned no result');
 await writeFile(path.join(output,'home.report.json'),JSON.stringify(result.lhr,null,2)+'\n',{flag:'wx'});
 await writeFile(path.join(output,'home.report.html'),generateReport(result.lhr,'html'),{flag:'wx'});
 console.log(JSON.stringify({stage:'lighthouse_complete',score:result.lhr.categories.performance.score,runtimeError:result.lhr.runtimeError}));
 await page.close();
 const phone=await browser.newPage();
 await phone.setViewport(viewport);
 await phone.setCacheEnabled(false);
 await guard(phone,'mobile_layout');
 const response=await phone.goto(url,{waitUntil:'networkidle2',timeout:45000});
 await phone.evaluate(()=>document.fonts.ready);
 await new Promise(resolve=>setTimeout(resolve,500));
 const observed=await phone.evaluate(()=>({
  url:location.href,title:document.title,headings:[...document.querySelectorAll('h1,h2')].map(e=>e.textContent),
  innerWidth:innerWidth,documentClientWidth:document.documentElement.clientWidth,
  documentScrollWidth:document.documentElement.scrollWidth,bodyScrollWidth:document.body.scrollWidth,
  scrollHeight:document.documentElement.scrollHeight,
  overflowingElements:[...document.querySelectorAll('body *')].map(e=>({element:e.tagName,className:String(e.className).slice(0,140),rect:e.getBoundingClientRect()}))
   .filter(item=>item.rect.width>0 && (item.rect.right>innerWidth+1 || item.rect.left< -1))
   .slice(0,30).map(({element,className,rect})=>({element,className,left:rect.left,right:rect.right,width:rect.width}))
 }));
 await phone.screenshot({path:path.join(output,'home-390px.png'),fullPage:true});
 mobile={viewport,status:response.status(),observed,horizontal_overflow:Math.max(observed.documentScrollWidth,observed.bodyScrollWidth)>observed.innerWidth};
 await phone.close();
} catch(error) {
 failure={name:error.name,message:error.message,stack:String(error.stack).slice(0,4000)};
} finally {
 if(browser) await browser.close();
}
const after=await manifest(path.join(root,'web/dist'));
const lhr=result?.lhr;
const performanceScore=lhr?.categories?.performance?.score;
const receipt={
 started_at:started,finished_at:new Date().toISOString(),scope:'One Home Lighthouse and 390px layout observation; no live repair UI/CLI acceptance',
 requested_url:url,preview_pid:3842066,chrome_pid:chromePID,browser_version:browserVersion,lighthouse_version:lhr?.lighthouseVersion,
 cpu_background_load_note:'Root full guarded backend suite was running during preparation (PID 3876358); this was not exclusive machine use.',
 load_average_after:os.loadavg(),chrome_default_sandbox:true,gpu_disabled:true,chrome_profile:profile,browser_close_completed:true,
 source_mutation:false,real_model_calls:0,live_run_submissions:0,
 lighthouse:{performance_score:performanceScore==null?null:Math.round(performanceScore*100),
  gate_70:performanceScore!=null&&performanceScore>=.70&&!lhr.runtimeError,
  runtime_error:lhr?.runtimeError??null,warnings:lhr?.runWarnings??[],
  final_url:lhr?.finalDisplayedUrl??lhr?.finalUrl,
  config_settings:lhr?.configSettings,metrics:lhr?Object.fromEntries(
   ['first-contentful-paint','largest-contentful-paint','total-blocking-time','cumulative-layout-shift','speed-index'].map(k=>[k,{
    value:lhr.audits[k].numericValue,unit:lhr.audits[k].numericUnit,display:lhr.audits[k].displayValue}])):null},
 mobile,requests,blocked_requests:blocked,page_errors:pageErrors,responses:assets,
 dist_before:before,dist_after:after,dist_unchanged:JSON.stringify(before)===JSON.stringify(after),
 failure:failure??null,process_cleanup_requires_independent_proc_check:true
};
await writeFile(path.join(output,'measurement.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({stage:'complete',score:receipt.lighthouse.performance_score,gate:receipt.lighthouse.gate_70,
 overflow:mobile?.horizontal_overflow,blocked:blocked.length,errors:pageErrors.length,failure:failure??null}));
process.exitCode=failure||!receipt.lighthouse.gate_70||mobile?.horizontal_overflow||blocked.length||pageErrors.length?1:0;
