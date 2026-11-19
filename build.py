#!/usr/bin/env python3
"""把《深入理解 AI Infra》书稿 + 小龙虾解读，打包成网页。

用法:
  python3 build.py <ai-infra-book 仓库路径> <输出目录> [章节文件名 ...] [--strict]
      多网页版：首页 + 每章一个网页，图片单独放、看到才加载，公式提前排好。
      GitHub Pages 用这个，输出目录写 . （仓库根目录）。需要 Node.js。
  python3 build.py <ai-infra-book 仓库路径> <输出.html> [章节文件名 ...] [--strict]
      单文件版：图片、公式字体全塞进一个 HTML，没网也能双击打开（约 34 MB）。

不给章节就打包全书（00-前言 到 12）。每章的解读和重点句放在 notes/chNN.py，
NN 是章节文件名开头的两位数字。--strict：有对不上的标题或重点句就报错退出。
"""
import base64
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).parent
TPL = HERE / "templates"
REPO_URL = "https://github.com/bojieli/ai-infra-book/blob/main"
MIMES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def esc(s: str) -> str:
    """标题文字转义一次（目录里的标题可能已经转义过）。"""
    return html.escape(html.unescape(s))


def load_notes(num: str):
    """读 notes/chNN.py，返回 (COMMENTARY, HIGHLIGHTS)；没有文件就返回空。"""
    f = HERE / "notes" / f"ch{num}.py"
    if not f.exists():
        return {}, []
    spec = importlib.util.spec_from_file_location(f"notes_ch{num}", f)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "COMMENTARY", {}), getattr(mod, "HIGHLIGHTS", [])


def protect_math(text: str):
    """把 $$..$$ 和 $..$ 换成占位符，防止 Markdown 改坏公式。"""
    store = []

    def keep(kind):
        def _f(m):
            store.append((kind, m.group(1).strip()))
            return f"KXMATH{len(store) - 1:05d}X"
        return _f

    text = re.sub(r"\$\$(.+?)\$\$", keep("display"), text, flags=re.S)
    text = re.sub(r"(?<![\\$])\$(?!\$)([^$\n]+?)\$", keep("inline"), text)
    return text, store


def math_plain(text: str, store) -> str:
    """占位符换回公式原文，去掉反斜杠命令和花括号（用在标题 id、目录、属性里）。"""
    return re.sub(r"KXMATH(\d{5})X",
                  lambda m: re.sub(r"\\[a-zA-Z]+|[{}]", "", store[int(m.group(1))][1]), text)


def restore_math(html_text: str, store) -> str:
    def _f(m):
        kind, tex = store[int(m.group(1))]
        tag = "div" if kind == "display" else "span"
        return f'<{tag} class="math {kind}">{html.escape(tex)}</{tag}>'
    # 标签属性里（如图片 alt）的公式只能放纯文字，放 HTML 会把标签弄坏
    html_text = re.sub(r"<[^<>]*KXMATH\d{5}X[^<>]*>",
                       lambda m: re.sub(r"KXMATH(\d{5})X",
                                        lambda k: html.escape(math_plain(k.group(0), store)), m.group(0)),
                       html_text)
    # 独占一段的公式块会被包进 <p>，去掉它
    html_text = re.sub(r"<p>\s*(KXMATH\d{5}X)\s*</p>", r"\1", html_text)
    return re.sub(r"KXMATH(\d{5})X", _f, html_text)


MATH_RE = re.compile(r'<(span|div) class="math (inline|display)">(.*?)</\1>', re.S)


def prerender_math(body: str, katex_js: Path) -> str:
    """多网页版：用 Node 跑 KaTeX，把公式提前排成 HTML，手机上不用再排。"""
    items = [(html.unescape(re.sub(r"<[^>]+>", "", m.group(3))), m.group(2) == "display")
             for m in MATH_RE.finditer(body)]
    if not items:
        return body
    res = subprocess.run(["node", str(HERE / "katex_render.cjs"), str(katex_js)],
                         input=json.dumps(items), capture_output=True, text=True, check=True)
    rendered = iter(json.loads(res.stdout))
    return MATH_RE.sub(lambda m: f'<{m.group(1)} class="math {m.group(2)}">{next(rendered)}</{m.group(1)}>', body)


def svg_min(p: Path) -> str:
    """SVG 去掉 metadata 和多余空白。"""
    s = p.read_text(encoding="utf-8")
    s = re.sub(r"<metadata>.*?</metadata>", "", s, flags=re.S)
    return re.sub(r">\s+<", "><", s)


def svg_data(p: Path) -> str:
    return "data:image/svg+xml;base64," + b64(svg_min(p).encode())


def svg_size(s: str):
    """读 SVG 的宽高（换成像素），给 <img> 先占好位置，图片晚加载也不跳。"""
    m = re.search(r"<svg\b[^>]*>", s)
    tag = m.group(0) if m else ""
    def attr(name):
        a = re.search(rf'\b{name}="([\d.]+)(pt|px)?"', tag)
        return float(a.group(1)) * (4 / 3 if a.group(2) == "pt" else 1) if a else None
    w, h = attr("width"), attr("height")
    if not (w and h):
        vb = re.search(r'viewBox="[\d.\-]+[ ,]+[\d.\-]+[ ,]+([\d.]+)[ ,]+([\d.]+)"', tag)
        if not vb:
            return None
        w, h = float(vb.group(1)), float(vb.group(2))
    return round(w), round(h)


def fix_paths(text: str, mdir: Path, missing_imgs: list, images=None) -> str:
    """图片：单文件版内嵌成 data URI；多网页版记下来，改成 img/ 下的路径。相对链接改成 GitHub 链接。"""
    def img(m):
        alt, src = m.group(1), m.group(2)
        p = mdir / src
        if not p.exists():
            missing_imgs.append(src)
            return m.group(0)
        suffix = p.suffix.lower()
        if suffix != ".svg" and suffix not in MIMES:
            return m.group(0)
        if images is None:
            data = svg_data(p) if suffix == ".svg" else f"data:{MIMES[suffix]};base64,{b64(p.read_bytes())}"
            return f"![{alt}]({data})"
        try:
            rel = p.resolve().relative_to(mdir.resolve()).as_posix()
        except ValueError:
            rel = "_ext/" + p.name
        images["img/" + rel] = p
        return f"![{alt}](img/{rel})"

    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", img, text)
    text = re.sub(r"\]\(\.\./", f"]({REPO_URL}/", text)
    text = re.sub(r"\]\((ch\d\d/)", rf"]({REPO_URL}/manuscripts/\1", text)
    return text


def note_html(md_text: str, idx: str) -> str:
    body = markdown.markdown(md_text, extensions=["tables"])
    return (
        f'<aside class="note" data-note="{idx}">'
        f'<button class="note-head" type="button" aria-expanded="true">'
        f'<span class="note-tag">🦞 小龙虾解读</span><span class="note-arrow">收起</span></button>'
        f'<div class="note-body">{body}</div></aside>'
    )


def add_highlights(body: str, phrases: list, found: set) -> str:
    """给重点句加 <mark class="key">，每句只标第一次出现。"""
    for phrase in phrases:
        if phrase in found:
            continue
        i = body.find(phrase)
        if i >= 0:
            body = body[:i] + f'<mark class="key">{phrase}</mark>' + body[i + len(phrase):]
            found.add(phrase)
    return body


def build_chapter(path: Path, report: dict, images=None, katex_js=None) -> tuple[str, list]:
    num = path.name[:2]
    cid = f"c{num}"
    commentary, phrases = load_notes(num)
    lines = path.read_text(encoding="utf-8").split("\n")
    out, notes, used, current = [], {}, set(), None

    def flush():
        if current and current in commentary:
            n = f"{cid}-{len(notes)}"
            notes[n] = commentary[current]
            used.add(current)
            out.extend(["", f"KXNOTE{n}X", ""])

    in_code = False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
        m = None if in_code else re.match(r"^(#{1,3}) (.+)$", line)
        if m:
            flush()
            current = m.group(2).strip()
        out.append(line)
    flush()

    missing_imgs = []
    text = fix_paths("\n".join(out), path.parent, missing_imgs, images)
    text, store = protect_math(text)
    md = markdown.Markdown(
        extensions=["tables", "footnotes", "toc", "fenced_code", "attr_list"],
        # 标题里有公式时，id 用公式原文，不留占位符
        extension_configs={"toc": {"slugify": lambda v, s: cid + "-" + re.sub(r"\W+", "-", math_plain(v, store)).strip("-")}},
    )
    body = md.convert(text)
    # 脚注 id 加章节前缀，避免多章重名
    body = re.sub(r'(id="|href="#)(fn(?:ref)?\d*:)', rf"\1{cid}-\2", body)
    body = restore_math(body, store)
    found = set()
    body = add_highlights(body, phrases, found)
    body = re.sub(r"<p>\s*KXNOTE([\w-]+)X\s*</p>", lambda m: note_html(notes[m.group(1)], m.group(1)), body)
    body = body.replace('<a href="http', '<a target="_blank" rel="noopener" href="http')
    if katex_js:
        body = prerender_math(body, katex_js)
    if images is not None:
        body = lazy_images(body, images)

    report[path.name] = {
        "notes": len(used),
        "highlights": len(found),
        "unmatched_notes": sorted(set(commentary) - used),
        "unmatched_highlights": [p for p in phrases if p not in found],
        "missing_images": missing_imgs,
    }
    # 目录里的标题若含公式，换回公式原文（去掉反斜杠命令）
    def fix_toc(tokens):
        for t in tokens:
            t["name"] = math_plain(t["name"], store)
            fix_toc(t.get("children", []))

    fix_toc(md.toc_tokens)
    return body, md.toc_tokens


def lazy_images(body: str, images: dict) -> str:
    """图片标上宽高，滚到附近才加载。"""
    def _f(m):
        src = m.group(2)
        p = images.get(src)
        size = svg_size(svg_min(p)) if p is not None and p.suffix.lower() == ".svg" else None
        wh = f' width="{size[0]}" height="{size[1]}"' if size else ""
        return f'<img{m.group(1)}src="{src}"{wh} loading="lazy" decoding="async"{m.group(3)}>'
    return re.sub(r'<img([^>]*?)src="(img/[^"]+)"([^>]*?)\s*/?>', _f, body)


def toc_items(tokens, depth=1) -> str:
    if not tokens or depth > 3:
        return ""
    items = []
    for t in tokens:
        sub = toc_html(t.get("children", []), depth + 1)
        items.append(f'<li><a href="#{t["id"]}" data-level="{t["level"]}">{esc(t["name"])}</a>{sub}</li>')
    return "".join(items)


def toc_html(tokens, depth=1) -> str:
    s = toc_items(tokens, depth)
    return f"<ul>{s}</ul>" if s else ""


def katex_dir(repo: Path) -> Path:
    return repo / "manuscripts/ch01/vendor/katex"


def katex_css(repo: Path, inline_fonts: bool) -> str:
    """KaTeX 样式只留 woff2 字体；单文件版把字体内嵌进去。"""
    kdir = katex_dir(repo)
    css = (kdir / "katex.min.css").read_text()
    if inline_fonts:
        css = re.sub(
            r"url\(fonts/([^)]+?\.woff2)\)",
            lambda m: f"url(data:font/woff2;base64,{b64((kdir / 'fonts' / m.group(1)).read_bytes())})",
            css,
        )
    return re.sub(r',url\(fonts/[^)]+?\.(?:woff|ttf)\) format\("[^"]+"\)', "", css)


def source_version(repo: Path) -> str:
    """原书仓库的 commit，写进页面，方便对照原文版本。"""
    try:
        h, d = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%h %cs"],
                              capture_output=True, text=True, check=True).stdout.split()
        return (f'<a href="https://github.com/bojieli/ai-infra-book/tree/{h}" target="_blank" '
                f'rel="noopener">{h}</a>（{d}）')
    except Exception:
        return "未知"


def print_report(report: dict) -> bool:
    bad = False
    for name, r in report.items():
        print(f"{name}: 解读 {r['notes']} 段，重点句 {r['highlights']} 句")
        for k, label in [("unmatched_notes", "解读没对上标题"), ("unmatched_highlights", "重点句在原文里没找到"),
                         ("missing_images", "图片文件不存在")]:
            if r[k]:
                bad = True
                print(f"  警告：{label}: {r[k]}", file=sys.stderr)
    return bad


def build_single(repo: Path, chapters: list, out: Path, report: dict):
    bodies, tocs = [], []
    for name in chapters:
        body, toc = build_chapter(repo / "manuscripts" / name, report)
        bodies.append(f'<section class="chapter">{body}</section>')
        tocs.append(toc_html(toc))
    js = (katex_dir(repo) / "katex.min.js").read_text()
    total = sum(r["notes"] for r in report.values())
    page = (
        (TPL / "single.html").read_text(encoding="utf-8")
        .replace("/*KATEX_CSS*/", katex_css(repo, inline_fonts=True))
        .replace("/*READER_CSS*/", (TPL / "reader.css").read_text(encoding="utf-8"))
        .replace("/*KATEX_JS*/", js)
        .replace("/*READER_JS*/", (TPL / "reader.js").read_text(encoding="utf-8"))
        .replace("<!--TOC-->", "".join(tocs))
        .replace("<!--BODY-->", "".join(bodies))
        .replace("<!--NOTE_COUNT-->", str(total))
        .replace("<!--SRC_VERSION-->", source_version(repo))
    )
    out.write_text(page, encoding="utf-8")
    print(f"已生成 {out}  {out.stat().st_size / 1e6:.1f} MB，共 {len(chapters)} 章，解读 {total} 段，"
          f"重点句 {sum(r['highlights'] for r in report.values())} 句")


def split_title(title: str):
    """'第 3 章 推理与训练负载' → ('第 3 章', '推理与训练负载')；'前言' → ('', '前言')。"""
    m = re.match(r"^(第\s*\d+\s*章)\s+(.+)$", title)
    return (m.group(1), m.group(2)) if m else ("", title)


def build_site(repo: Path, chapters: list, out: Path, report: dict):
    if not shutil.which("node"):
        sys.exit("多网页版要用 Node.js 提前排公式，请先安装 Node.js。")
    kdir = katex_dir(repo)
    images, infos = {}, []
    for name in chapters:
        body, toc = build_chapter(repo / "manuscripts" / name, report, images, kdir / "katex.min.js")
        title = html.unescape(toc[0]["name"]) if toc else Path(name).stem
        num, short = split_title(title)
        infos.append({"page": f"ch{name[:2]}", "file": name, "title": title, "num": num, "name": short,
                      "body": body, "toc": toc, "sections": len(toc[0].get("children", [])) if toc else 0,
                      **report[name]})

    # 页内跳转 #id 如果落在别的章，改成 chNN.html#id
    owner = {}
    for c in infos:
        for i in re.findall(r'\bid="([^"]+)"', c["body"]):
            owner.setdefault(i, c["page"])
    for c in infos:
        mine = set(re.findall(r'\bid="([^"]+)"', c["body"]))
        def fix(m, c=c, mine=mine):
            i = html.unescape(m.group(1))
            if m.group(1) in mine or i in mine:
                return m.group(0)
            if m.group(1) in owner:
                return f'href="{owner[m.group(1)]}.html#{m.group(1)}"'
            print(f"  警告：{c['file']} 里的链接 #{i} 找不到目标", file=sys.stderr)
            return m.group(0)
        c["body"] = re.sub(r'href="#([^"]+)"', fix, c["body"])

    # 生成的文件夹先清掉再写，免得留下旧图
    for d in ("assets", "img"):
        shutil.rmtree(out / d, ignore_errors=True)
    (out / "assets/katex/fonts").mkdir(parents=True)
    css = katex_css(repo, inline_fonts=False)
    (out / "assets/katex/katex.min.css").write_text(css, encoding="utf-8")
    for font in sorted(set(re.findall(r"url\(fonts/([^)]+?\.woff2)\)", css))):
        shutil.copyfile(kdir / "fonts" / font, out / "assets/katex/fonts" / font)
    shutil.copyfile(kdir / "LICENSE", out / "assets/katex/LICENSE")
    for f in ("reader.css", "reader.js"):
        shutil.copyfile(TPL / f, out / "assets" / f)
    for rel, src in sorted(images.items()):
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() == ".svg":
            dst.write_text(svg_min(src), encoding="utf-8")
        else:
            shutil.copyfile(src, dst)

    version = source_version(repo)
    tpl = (TPL / "chapter.html").read_text(encoding="utf-8")
    for i, c in enumerate(infos):
        side = []
        for o in infos:
            if o is c:
                side.append(toc_items(c["toc"]).replace("<li>", '<li class="current">', 1))
            else:
                side.append(f'<li class="other"><a href="{o["page"]}.html" data-level="1">{esc(o["title"])}</a></li>')
        prev, nxt = (infos[i - 1] if i > 0 else None), (infos[i + 1] if i + 1 < len(infos) else None)
        pager = (
            (f'<a class="prev" href="{prev["page"]}.html"><small>← 上一章</small>{esc(prev["title"])}</a>'
             if prev else '<span class="pad"></span>')
            + '<a class="toc" href="index.html">全书目录</a>'
            + (f'<a class="next" href="{nxt["page"]}.html"><small>下一章 →</small>{esc(nxt["title"])}</a>'
               if nxt else '<span class="pad"></span>')
        )
        page = (tpl.replace("<!--TITLE-->", esc(c["title"])).replace("<!--PAGE-->", c["page"])
                .replace("<!--CHAPTERS-->", "".join(side)).replace("<!--BODY-->", c["body"])
                .replace("<!--PAGER-->", pager).replace("<!--SRC_VERSION-->", version))
        (out / f'{c["page"]}.html').write_text(page, encoding="utf-8")

    items = "".join(
        f'<li><a href="{c["page"]}.html" data-page="{c["page"]}">'
        + (f'<span class="num">{esc(c["num"])}</span>' if c["num"] else "") +
        f'<span class="name">{esc(c["name"])}</span>'
        f'<span class="meta">{c["sections"]} 节 · 解读 {c["notes"]} 段</span></a></li>'
        for c in infos)
    offline = out / "offline.html"
    offline_line = (f'      电脑上想离线看：<a href="offline.html" download>下载单文件版</a>'
                    f'（约 {offline.stat().st_size / 1e6:.0f} MB，不适合手机）。<br>') if offline.exists() else ""
    total = sum(c["notes"] for c in infos)
    home = ((TPL / "home.html").read_text(encoding="utf-8")
            .replace("<!--CHAPTERS-->", items).replace("<!--OFFLINE-->", offline_line)
            .replace("<!--CHAPTER_COUNT-->", str(len(infos))).replace("<!--NOTE_COUNT-->", str(total))
            .replace("<!--HL_COUNT-->", str(sum(c["highlights"] for c in infos)))
            .replace("<!--SRC_VERSION-->", version))
    (out / "index.html").write_text(home, encoding="utf-8")

    sizes = sorted(((out / f'{c["page"]}.html').stat().st_size, c["page"]) for c in infos)
    img_mb = sum((out / r).stat().st_size for r in images) / 1e6
    print(f"已生成 {out}/index.html + {len(infos)} 个章节网页，解读 {total} 段；"
          f"章节网页 {sizes[0][0] / 1e3:.0f}–{sizes[-1][0] / 1e3:.0f} KB，图片 {len(images)} 张共 {img_mb:.1f} MB（看到才加载）")


def main():
    args = [a for a in sys.argv[1:] if a != "--strict"]
    strict = "--strict" in sys.argv
    if len(args) < 2:
        sys.exit(__doc__)
    repo, out = Path(args[0]), Path(args[1])
    chapters = args[2:] or sorted(p.name for p in (repo / "manuscripts").glob("[01][0-9]-*.md"))
    if not chapters or not (katex_dir(repo) / "katex.min.css").exists():
        sys.exit(f"在 {repo} 里找不到原书章节或 KaTeX，第一个参数要写 ai-infra-book 仓库路径。")
    report = {}
    if out.suffix.lower() == ".html":
        build_single(repo, chapters, out, report)
    else:
        build_site(repo, chapters, out, report)
    if print_report(report) and strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
