import {build} from 'esbuild';
import {mkdir,writeFile,readFile,cp,stat} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';
const here=path.dirname(fileURLToPath(import.meta.url));
const out=path.resolve(process.env.QUANTUM_TRAVEL_OUT||path.join(here,'.build/TravelSpace'));
await mkdir(out,{recursive:true});
await build({absWorkingDir:here,entryPoints:['src/main.jsx'],bundle:true,minify:true,format:'iife',
  outfile:path.join(out,'app.js'),assetNames:'assets/[name]-[hash]',
  loader:{'.png':'file','.jpg':'file','.jpeg':'file','.webp':'file'},
  define:{'process.env.NODE_ENV':'"production"'},target:['safari17'],metafile:true});
const catalogSource=await readFile(path.join(here,'src/magazine-photos.js'),'utf8');
const catalog=JSON.parse(catalogSource.match(/export const photoPool=(\[[\s\S]*?\]);/)[1].replace(/,\s*\]/g,']'));
await writeFile(path.join(out,'catalog.json'),JSON.stringify(catalog));
await cp(path.join(here,'src/assets/magazine1000'),path.join(out,'magazine'),{recursive:true,filter:async(src,dst)=>{if((await stat(src)).isDirectory())return true;try{return createHash('sha256').update(await readFile(src)).digest('hex')!==createHash('sha256').update(await readFile(dst)).digest('hex');}catch{return true;}}});
await writeFile(path.join(out,'index.html'),`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' quantum-media: data: blob: https:; font-src 'self'; connect-src 'none'; media-src 'self' quantum-media: blob:; base-uri 'none'; form-action 'none'"><title>Quantum 旅行空间</title><link rel="stylesheet" href="app.css"></head><body><div id="root"></div><script src="app.js"></script></body></html>`);
console.log('Built native TravelSpace renderer with lazy local photography.');
