const fs = require('fs');
const path = require('path');
const pkg = require('@antv/g2/package.json');
const main = path.join(process.cwd(), 'node_modules/@antv/g2', pkg.module || pkg.main);
const dir = path.dirname(main);
console.log('g2 esm dir:', dir);

// 找事件相关源码
const files = [];
function walk(d) {
  for (const f of fs.readdirSync(d)) {
    const p = path.join(d, f);
    const st = fs.statSync(p);
    if (st.isDirectory()) walk(p);
    else if (f.endsWith('.js') || f.endsWith('.d.ts')) files.push(p);
  }
}
walk(dir);
console.log('files:', files.length);

// 找 click 事件定义
const hits = files.filter((f) => {
  try {
    const s = fs.readFileSync(f, 'utf8');
    return /element:click|interval:click/.test(s);
  } catch { return false; }
});
console.log('click event files:', hits.slice(0, 8));

// 找 label overflow / 重叠处理
const overflow = files.filter((f) => {
  try { return /overflow.*hide|overlapDodge|labelOverflow/.test(fs.readFileSync(f, 'utf8')); } catch { return false; }
});
console.log('label overflow files:', overflow.slice(0, 8));
