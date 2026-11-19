# 深入理解 AI Infra · 原文 + 解读 学习版

把李博杰《深入理解 AI Infra：量化分析与系统设计》的原文，和逐节的大白话解读放在一个网页里。解读可以一键打开或关闭，原文里的重点句加了下划线。

> **这不是官方版本。** 本项目由读者自制，未经原作者审阅，与原作者无关。
> 原文一字未改；解读和下划线是另加的，由 AI 辅助生成，**可能有错，数字和结论以原书为准**。
> 发现解读有误，欢迎提 Issue。原文本身的勘误请提到 [原书仓库](https://github.com/bojieli/ai-infra-book)。

## 在线阅读

👉 **[打开网页](https://hanqingaws.github.io/ai-infra-book-reader/)**

每章一个网页，手机也能顺畅看：最大的一章压缩后约 100 KB，公式已经提前排好，配图滚到附近才加载。

电脑上想没网也能看：下载 [`offline.html`](offline.html)，双击打开（整本书一个文件，约 34 MB，第一次打开要等几秒，不适合手机）。

## 网页功能

| 功能 | 说明 |
|---|---|
| 解读开关 | 右上角开关或按 `N`，打开/关闭全部解读 |
| 单段收起 | 点橙色框标题，只收起这一段 |
| 重点句 | 原文重要句子加橘黄色下划线 |
| 颜色 | 浅色 / 护眼绿 / 深色，三种循环切换 |
| 字号 | `A-` / `A+` |
| 目录与续读 | 左侧目录高亮当前位置；每章记住读到哪里，首页有"继续阅读" |
| 翻页 | 章末有上一章 / 下一章；手机上点左上角 ☰ 打开目录 |

## 内容

- 前言 + 第 1–12 章全部原文、配图和公式
- 346 段解读：每段含"一句话 / 大白话 / 游戏里怎么想"，部分对照 AWS 实例举例
- 344 句重点下划线

解读面向有编程经验、想入门 AI Infra 的读者，类比偏游戏开发。

## 自己重新生成

原书还在持续更新。原书更新后，可以重新打包：

需要 Python 3 和 Node.js（用原书自带的 KaTeX 提前排公式）。

```bash
pip install markdown
git clone --depth 1 https://github.com/bojieli/ai-infra-book.git
python3 build.py ai-infra-book offline.html --strict   # 先生成离线版，首页会显示它的大小
python3 build.py ai-infra-book . --strict              # 再生成在线版：index.html、chNN.html、assets/、img/
```

输出写 `.html` 文件名就生成单文件离线版，写目录就生成多网页在线版。生成在线版时会先清空输出目录里的 `assets/` 和 `img/`。

- `notes/chNN.py`：第 NN 章的解读（`COMMENTARY`，按小节标题对应）和重点句（`HIGHLIGHTS`，必须和原文一字不差）。
- `templates/`：页面骨架（`home.html` 首页、`chapter.html` 章节页、`single.html` 离线版）和共用的 `reader.css`、`reader.js`。
- `build.py`：读取原书 Markdown，加上解读和重点句，输出网页。
- `katex_render.cjs`：`build.py` 调用它在生成时排好公式。
- `--strict`：标题或重点句对不上原文时报错，原书改动后用它找出要更新的解读。

## 许可与致谢

- **原文、配图**：© 2026 Bojie Li（李博杰），[Apache License 2.0](LICENSE)。来源：[bojieli/ai-infra-book](https://github.com/bojieli/ai-infra-book)。
- **本项目的改动**（解读、下划线、页面和构建脚本）同样以 Apache License 2.0 发布。改动说明见 [NOTICE](NOTICE)。
- **KaTeX**（公式显示，含字体）：MIT 许可，见 [THIRD_PARTY_LICENSES/KaTeX-LICENSE](THIRD_PARTY_LICENSES/KaTeX-LICENSE)。

感谢原作者把全书开源。想支持作者，请去 [原书仓库](https://github.com/bojieli/ai-infra-book) 点 Star。
