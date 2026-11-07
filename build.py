#!/usr/bin/env python3
"""把《深入理解 AI Infra》书稿 + 小龙虾解读，打包成一个离线可读的 HTML 文件。

用法:
  python3 build.py <ai-infra-book 仓库路径> <输出.html> [章节文件名 ...] [--strict]

不给章节就打包全书（00-前言 到 12）。每章的解读和重点句放在 notes/chNN.py，
NN 是章节文件名开头的两位数字。--strict：有对不上的标题或重点句就报错退出。
"""
import base64
import html
import importlib.util
import re
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).parent
REPO_URL = "https://github.com/bojieli/ai-infra-book/blob/main"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


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


def restore_math(html_text: str, store) -> str:
    def _f(m):
        kind, tex = store[int(m.group(1))]
        tag = "div" if kind == "display" else "span"
        return f'<{tag} class="math {kind}">{html.escape(tex)}</{tag}>'
    # 独占一段的公式块会被包进 <p>，去掉它
    html_text = re.sub(r"<p>\s*(KXMATH\d{5}X)\s*</p>", r"\1", html_text)
    return re.sub(r"KXMATH(\d{5})X", _f, html_text)


def svg_data(p: Path) -> str:
    """SVG 去掉 metadata 和多余空白，再转 base64。"""
    s = p.read_text(encoding="utf-8")
    s = re.sub(r"<metadata>.*?</metadata>", "", s, flags=re.S)
    s = re.sub(r">\s+<", "><", s)
    return "data:image/svg+xml;base64," + b64(s.encode())


def fix_paths(text: str, mdir: Path, missing_imgs: list) -> str:
    """图片内嵌成 data URI；相对链接改成 GitHub 链接。"""
    mimes = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}

    def img(m):
        alt, src = m.group(1), m.group(2)
        p = mdir / src
        if not p.exists():
            missing_imgs.append(src)
            return m.group(0)
        if p.suffix == ".svg":
            return f"![{alt}]({svg_data(p)})"
        if p.suffix.lower() in mimes:
            return f"![{alt}](data:{mimes[p.suffix.lower()]};base64,{b64(p.read_bytes())})"
        return m.group(0)

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


def build_chapter(path: Path, report: dict) -> tuple[str, list]:
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
    text = fix_paths("\n".join(out), path.parent, missing_imgs)
    text, store = protect_math(text)
    md = markdown.Markdown(
        extensions=["tables", "footnotes", "toc", "fenced_code", "attr_list"],
        extension_configs={"toc": {"slugify": lambda v, s: cid + "-" + re.sub(r"\W+", "-", v).strip("-")}},
    )
    body = md.convert(text)
    # 脚注 id 加章节前缀，避免多章重名
    body = re.sub(r'(id="|href="#)(fn(?:ref)?\d*:)', rf"\1{cid}-\2", body)
    body = restore_math(body, store)
    found = set()
    body = add_highlights(body, phrases, found)
    body = re.sub(r"<p>\s*KXNOTE([\w-]+)X\s*</p>", lambda m: note_html(notes[m.group(1)], m.group(1)), body)
    body = body.replace('<a href="http', '<a target="_blank" rel="noopener" href="http')

    report[path.name] = {
        "notes": len(used),
        "highlights": len(found),
        "unmatched_notes": sorted(set(commentary) - used),
        "unmatched_highlights": [p for p in phrases if p not in found],
        "missing_images": missing_imgs,
    }
    # 目录里的标题若含公式，换回公式原文（去掉反斜杠命令）
    def plain(name):
        return re.sub(r"KXMATH(\d{5})X",
                      lambda m: re.sub(r"\\[a-zA-Z]+|[{}]", "", store[int(m.group(1))][1]), name)

    def fix_toc(tokens):
        for t in tokens:
            t["name"] = plain(t["name"])
            fix_toc(t.get("children", []))

    fix_toc(md.toc_tokens)
    return body, md.toc_tokens


def toc_html(tokens, depth=1) -> str:
    if not tokens or depth > 3:
        return ""
    items = []
    for t in tokens:
        sub = toc_html(t.get("children", []), depth + 1)
        items.append(f'<li><a href="#{t["id"]}" data-level="{t["level"]}">{html.escape(t["name"])}</a>{sub}</li>')
    return "<ul>" + "".join(items) + "</ul>"


def katex_assets(repo: Path) -> tuple[str, str]:
    kdir = repo / "manuscripts/ch01/vendor/katex"
    css = (kdir / "katex.min.css").read_text()
    css = re.sub(
        r"url\(fonts/([^)]+?\.woff2)\)",
        lambda m: f"url(data:font/woff2;base64,{b64((kdir / 'fonts' / m.group(1)).read_bytes())})",
        css,
    )
    css = re.sub(r',url\(fonts/[^)]+?\.(?:woff|ttf)\) format\("[^"]+"\)', "", css)
    js = (kdir / "katex.min.js").read_text()
    return css, js


def source_version(repo: Path) -> str:
    """原书仓库的 commit，写进页面，方便对照原文版本。"""
    import subprocess
    try:
        h, d = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%h %cs"],
                              capture_output=True, text=True, check=True).stdout.split()
        return (f'<a href="https://github.com/bojieli/ai-infra-book/tree/{h}" target="_blank" '
                f'rel="noopener">{h}</a>（{d}）')
    except Exception:
        return "未知"


def main():
    args = [a for a in sys.argv[1:] if a != "--strict"]
    strict = "--strict" in sys.argv
    repo, out = Path(args[0]), Path(args[1])
    mdir = repo / "manuscripts"
    chapters = args[2:] or sorted(p.name for p in mdir.glob("[01][0-9]-*.md"))

    report, bodies, tocs = {}, [], []
    for name in chapters:
        body, toc = build_chapter(mdir / name, report)
        bodies.append(f'<section class="chapter">{body}</section>')
        tocs.append(toc_html(toc))

    bad = False
    for name, r in report.items():
        print(f"{name}: 解读 {r['notes']} 段，重点句 {r['highlights']} 句")
        for k, label in [("unmatched_notes", "解读没对上标题"), ("unmatched_highlights", "重点句在原文里没找到"),
                         ("missing_images", "图片文件不存在")]:
            if r[k]:
                bad = True
                print(f"  警告：{label}: {r[k]}", file=sys.stderr)

    css, js = katex_assets(repo)
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    total = sum(r["notes"] for r in report.values())
    page = (
        tpl.replace("/*KATEX_CSS*/", css)
        .replace("/*KATEX_JS*/", js)
        .replace("<!--TOC-->", "".join(tocs))
        .replace("<!--BODY-->", "".join(bodies))
        .replace("<!--NOTE_COUNT-->", str(total))
        .replace("<!--SRC_VERSION-->", source_version(repo))
    )
    out.write_text(page, encoding="utf-8")
    print(f"已生成 {out}  {out.stat().st_size / 1e6:.1f} MB，共 {len(chapters)} 章，解读 {total} 段，"
          f"重点句 {sum(r['highlights'] for r in report.values())} 句")
    if strict and bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
