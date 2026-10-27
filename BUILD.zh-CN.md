# Aincrad UI SC · v0.3 · WAO 界面符号版

当前交付：**wao-symbols**。在思源汉字全量版上补齐 WAO 需求中的 **24 个符号**，包括六个制表线符号。现有 **30,186 个汉字**保持，非汉字增至 **251 个**，最终共 **30,437 个字符**。

Regular／Display 沿用现有窄长比例、字重基础、圆角／切角和已有精修。本批保护原有 **30,413 个字符**的轮廓、完整水平度量与行距，不再逐字重排汉字部件。已归档结构试验继续留在工作目录 `archives/structure14-trial/ARCHIVE.md`，不嵌套进入分发包。

本批详细说明见 `WAO-SYMBOLS.md`，完整分发包为 `Aincrad-UI-SC-v0.3-wao-symbols.zip`，应用替换包为 `Aincrad-UI-SC-v0.3-wao-handoff.zip`。家庭名、正式字体路径和内部版本 0.300 保持，以本批包名与哈希区分交付。上一批汉字扩展的范围和历史验证见 `SOURCEHAN-HAN.md`。

```text
◆◇●■□▲▼▶◀‹«»─│┌┐└┘‥⟨⟩※†‖
```

## 字集

| 范围 | 字符数 |
| --- | ---: |
| 基本区汉字 | 20,945 |
| 扩展 A | 6,582 |
| 扩展 B／C／D／E | 2,051／46／33／108 |
| 基本兼容汉字／补充兼容汉字 | 366／55 |
| 全部汉字 | **30,186** |
| 其中补充平面汉字 | 2,293 |
| 非汉字字符（含本批 24 个符号） | 251 |
| 全部字符 | **30,437** |

GB2312 两级 6,763 汉字、此前四个集外字、两批应用增量及 64 卦全部保留。30 类、1,730 条界面语料保持。`data/charset.json` 和同源生成的 `data/font-catalog.js` 是字表与字样页统计依据。

汉字范围输入为 `data/sourcehan-han-extension.json`，本批符号输入为 `data/wao-symbol-extension.json` 和 `data/wao-symbols-v030.json`。不将本地 v1.004 说成最新版思源或完整 Unicode 汉字覆盖。兼容汉字保留原码位，不做 NFKC 归一化；同源 glyph 的兼容别名继续复用原 glyph 已有处理，“更”继承“更”的现有计划。

## 使用与查看

- `fonts/AincradUISc-Regular.ttf`：界面正文。
- `fonts/AincradUISc-Display.ttf`：标题。
- 同名 `.otf`／`.woff2`：相应安装或网页格式。
- `specimen.html`：分类词句、搜索、试字与字表统计。
- `wao-symbols-study.html`、`wao-symbols-study.png`：本批 24 个符号、既有对照符号、HUD 文案与制表线连接，主验 Display TTF 的 14px／DPR 1。
- `wao-symbols-study-dpr2.png`、`wao-symbols-zoom-dpr1.png`：DPR 2 回归和 DPR 1 像素整数放大。
- `sourcehan-samples.html`：扩展区、补充平面及兼容字的代表样张。
- `coverage-sheet-{Regular,Display}.png` 及 `-02` 至 `-30`：两档各 30 页全量汉字覆盖图。
- `small-size-study.html`：既有 11–14px 样张，实际浏览器 DPR 1／2。
- `ttf14-comparison.html`、`dense-14px-comparison.html`：使用固定旧字体副本的历史对照。

安装时同档选择 TTF 或 OTF 一种。已经安装旧版时按系统提示替换，并重开使用字体的应用。字号与样张不构成所有新字的逐字光学精修验收。

## 来源与构建输入

本地思源 v1.004 的每个 SC face 含 65,535 个 glyph、44,683 个 Unicode 码位、30,186 个汉字码位，后者映射到 30,091 个不同 glyph。字形数包含地区写法、替代形及其他文字。统计与原 TTC SHA 见 `data/source-font-coverage.json`。

当前源子集为 `sources/AincradSeed-wao-{Regular,Medium}.otf`，每档 **30,351 个真实源字符**，包含本批 16 个有来源的符号。原字参照 `fonts/SourceHanSansSC-Baseline.woff2` 使用相同范围；正式成品另外包含 **86 个独立绘制符号**，其中本批新增六个制表线和两个数学角括号。旧 sourcehan、GB2312 和 v0.3 原审阅源分别保留，原三份精修计划不改字节。构建先比对全部旧源轮廓与水平度量，满足一致才复用已审阅源锚。

## 验证记录

- `data/verification.json`：通用六格式覆盖、命名、原精修、字宽、行度量与数字等宽检查。
- `data/wao-symbol-verification.json`：独立检查 24 符号、旧 30,413 字符在六格式的轮廓与水平／行度量保留，以及源范围和数字等宽。
- `data/wao-symbol-browser-verification.json`：当前两档 TTF 的 14px／DPR 1 主验与 DPR 2 回归，包含真实字体加载和制表框样张。
- `data/wao-source-preparation.json`、`data/provenance.json`：真实新源与全部旧源保留证明。
- `data/browser-verification.json`、`data/small-size-verification.json`、`data/sourcehan-sample-verification.json`：当前字体实际加载、页面及样张。
- `data/wao-package-rebuild.json`、`data/package-verification.json`：便携重建与最终分发校验。
- `data/sourcehan-raster-diagnostics.json`：上一批已记录的 FreeType 自动对齐变化证据；几何与度量保持不代表所有字号逐像素相同。

历史 sourcehan、GB2312、ttf14 和 dense 报告继续作为各自版本的证据保留，不把其旧日期与旧统计伪称为本批重跑结果。上一正式包 `Aincrad-UI-SC-v0.3-sourcehan-han.zip` 保留原字节供回归与恢复。WAO Flutter 工程不在本字体仓库，本批没有代替它运行 `test/font_coverage_test.dart`；替换包内提供接入说明。

## 重建

解压后的目录直接运行，不必先 prepare：

```powershell
python -m pip install -r requirements.txt
python scripts/build_aincrad_font.py
python scripts/verify_aincrad_font.py --report data/verification.json
```

分发包内包含所需源子集和配置，常规重建不依赖完整 TTC、旧 ZIP 或浏览器。本批完整来源／旧字独立回归另需原 TTC 和上批 sourcehan-han 包；缺少外部证据时必须明确标记检查范围，不能称为完整回归。浏览器预览需要 Playwright／Chromium。

## 许可与来源

本版字体派生自 Adobe 的 Source Han Sans，以 SIL Open Font License 1.1 发布。原始本地 TTC 的字体元数据保留了 Adobe 2014/2015 版权及保留字体名 `Source`。附带的 `OFL.txt` 同时保留这项原版说明，以及从 Adobe 官方仓库取得的完整 OFL 文本；官方当前许可头中的 2014–2025 年份不改变本地输入文件的版本或原始版权年份。

此前第二批中 18 个符号和本批 16 个符号沿用这条源字体许可链。此前 14 个符号、64 个卦符和本批八个几何符号，共 86 个由本项目独立绘制轮廓，连同参数化与局部字形改造一起随派生字体按 OFL 1.1 提供。来源及图形配置在 `data/symbols-v030.json`、`data/hexagrams.json`、`data/hexagram-outlines-v030.json` 和 `data/wao-symbols-v030.json` 中记录；Unicode 字符表仅作为字符身份参照，未提取或转用其字体数据。

派生字体使用独立主名 `Aincrad UI SC`、`Aincrad UI SC Display`，不沿用保留字体名。对照文件名保留来源提示，其内部字体主名也应使用独立名称。字体可按 OFL 条款使用、嵌入、修改和随软件分发，分发时应带上版权及许可证；不得将字体文件单独销售。以字体排版生成的文档或图片不因此必须使用 OFL 发布。完整条件见 `OFL.txt`。

此原型没有合并或重发已经收集的 `SAOUI` 字体轮廓。`SAO` 与《刀剑神域》的名称只用于说明界面风格研究方向，不表示官方授权或背书。

- 原字体项目：<https://github.com/adobe-fonts/source-han-sans>
- 官方许可文本：<https://raw.githubusercontent.com/adobe-fonts/source-han-sans/release/LICENSE.txt>
