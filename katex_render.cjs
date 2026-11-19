// 给 build.py 用：生成网页时提前排好公式，手机打开就不用再跑 KaTeX。
// 用法: node katex_render.cjs <katex.min.js 路径>
// 标准输入: JSON [[公式, 是否独占一行], ...]；标准输出: JSON [排好的 HTML, ...]
const path = require('path');
const katex = require(path.resolve(process.argv[2]));
let buf = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', d => { buf += d; });
process.stdin.on('end', () => {
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const out = JSON.parse(buf).map(([tex, display]) => {
    try {
      return katex.renderToString(tex, { displayMode: display, throwOnError: false, strict: false, output: 'html' });
    } catch (e) {
      return '<code>' + esc(tex) + '</code>';
    }
  });
  process.stdout.write(JSON.stringify(out));
});
