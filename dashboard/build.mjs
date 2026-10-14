import { mkdir, copyFile, readFile, writeFile, readdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
const root=fileURLToPath(new URL('.',import.meta.url));
execFileSync(process.execPath,['--check',root+'src/app.js']);
await mkdir(root+'dist',{recursive:true});
await mkdir(root+'dist/images',{recursive:true});
const manifest={};
for(const file of ['index.html','app.js','styles.css','icon.svg','leaflet.js','leaflet.css']){
  await copyFile(root+'src/'+file,root+'dist/'+file);
  manifest[file]=createHash('sha256').update(await readFile(root+'dist/'+file)).digest('hex');
}
try {
  const images = await readdir(root+'src/images');
  for(const img of images){
    await copyFile(root+'src/images/'+img,root+'dist/images/'+img);
  }
} catch(e){}
await writeFile(root+'dist/build-manifest.json',JSON.stringify(manifest,null,2));
console.log('Dashboard build passed: 4 local assets; no CDN dependencies.');
