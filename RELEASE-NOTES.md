# Aincrad UI SC · v0.3.0 · wao-symbols

[English introduction](https://github.com/kymorphius/Aincrad-UI-SC/blob/main/README.en.md) · [中文介绍](https://github.com/kymorphius/Aincrad-UI-SC/blob/main/README.zh-CN.md)

## 中文

**补齐 WAO 全部 24 个界面符号：30,437 个总字符，包含 30,186 个汉字。**

```text
◆◇●■□▲▼▶◀‹«»─│┌┐└┘‥⟨⟩※†‖
```

Regular／Display 均提供 OTF、TTF、WOFF2。现有汉字范围、窄长风格、既有精修、数字等宽和 64 卦保持；本次没有新增汉字或汉字手工精修计划。24 个新符号中，16 个保留本地思源 v1.004 来源链，六个制表线和两个数学角括号采用原创几何；全库独立几何符号共 86 个。

通用与独立符号检查通过。旧 **30,413 个字符**的矢量轮廓、完整水平与行度量、TTF 点位／标志／轮廓端点／指令保持。全部 24 个新符号在六格式的 14px／28px 栅格中均能实际显示且未越行。桌面 Chromium 主验 **Display TTF 14 CSS px／DPR 1**，配合 Regular、深浅主题及 DPR 2 回归；256 次单字符字体归属检查没有回退。独立完整重建后，全部 **15 个字体文件及字表逐字节一致**。

制表线按原始字宽和行高连接，DPR 1 的抗锯齿淡接缝和彩色边缘保留在真实样张中。11–14px 代表样张不构成全字集光学验收；本字体仓库没有运行 WAO Flutter／Android 应用测试，接入方替换资源后仍需运行自己的字体覆盖测试。此前 SourceHan 汉字扩展的像素差异作为历史记录保留，本次独立符号检查状态为 **`passed`**，不宣称全字号逐像素一致。

下载附件：

- **`Aincrad-UI-SC-v0.3-wao-symbols.zip`**：完整发行包，**158,164,747 字节**（约 158 MB），含字体、十个源子集、字表、样张、验证记录和十四个脚本。
- **`Aincrad-UI-SC-v0.3-wao-handoff.zip`**：WAO 替换包，**14,424,628 字节**（约 14 MB），含两档 TTF、`aincrad-ui-sc-charset.json`、OFL 和替换说明。
- 两个 ZIP 各自的 **`.zip.sha256`** 校验文件。
- `AincradUISc-Regular.otf`、`.ttf`、`.woff2` 和 `AincradUISc-Display.otf`、`.ttf`、`.woff2`：六个正式字体。
- **`OFL.txt`**：随附字体许可证；**`SHA256SUMS`**：发行附件校验值。

每档安装 TTF 或 OTF 一种，网页使用 WOFF2。发行标签 **`v0.3.0`**、版别 **`wao-symbols`** 和哈希标识本次交付；字体内部版本保持 **0.300**。

## English

**All 24 requested WAO interface symbols: 30,437 encoded characters, including 30,186 Han codepoints.**

Regular and Display each ship as OTF, TTF and WOFF2. The existing Han coverage, condensed style, refinements, tabular digits and all 64 hexagrams remain intact. No Han characters or new manual Han refinement plans were added. Sixteen new symbols retain the local Source Han v1.004 provenance chain; six box-drawing glyphs and two mathematical angle brackets use original geometry, bringing the total to 86 independently drawn symbols.

General and independent symbol checks pass. The **30,413 previous characters** retain their vector outlines, full horizontal and line metrics, and TrueType coordinates, flags, contour endpoints and instructions. All 24 new symbols show visible ink within the line cell at 14px and 28px across all six fonts. Desktop Chromium primarily tested **Display TTF at 14 CSS px / DPR 1**, with Regular, light/dark themes and DPR 2 regression; 256 single-character font-attribution checks confirmed no fallback. An independent complete rebuild produced byte-identical copies of **all 15 font files and the charset**.

Box-drawing glyphs connect at the original advances and line height. Actual DPR 1 specimens retain faint antialiasing seams and colored edge pixels. The 11–14px samples are not an all-character optical acceptance test, and the WAO Flutter/Android application tests were not run in this font workspace; integrating applications should run their own coverage tests. Earlier Source Han expansion raster differences remain historical records. This edition's independent symbol status is **`passed`**, without an all-size pixel-identity claim.

Download assets:

- **`Aincrad-UI-SC-v0.3-wao-symbols.zip`**: complete distribution, **158,164,747 bytes** (about 158 MB), including fonts, ten source subsets, charset, specimens, verification records and fourteen scripts.
- **`Aincrad-UI-SC-v0.3-wao-handoff.zip`**: WAO handoff, **14,424,628 bytes** (about 14 MB), with both TTFs, `aincrad-ui-sc-charset.json`, OFL and replacement instructions.
- The separate **`.zip.sha256`** file for each ZIP.
- `AincradUISc-Regular.otf`, `.ttf`, `.woff2` and `AincradUISc-Display.otf`, `.ttf`, `.woff2`: all six production fonts.
- **`OFL.txt`**: the accompanying font license; **`SHA256SUMS`**: checksums for the release assets.

Install either TTF or OTF for each style, or use WOFF2 on the web. The release tag **`v0.3.0`**, edition **`wao-symbols`** and hashes identify this delivery; the internal font version remains **0.300**.

## SHA-256

```text
48ae619762d7e41c2ec6dfff2c9dd7227b4cc09523a7505a1b6100c7e48cc181  Aincrad-UI-SC-v0.3-wao-symbols.zip
5f60a003997279e1611b8c67412d5e2b0880327753451c2203ce37bb230bc027  Aincrad-UI-SC-v0.3-wao-handoff.zip
```

字体派生自 Adobe Source Han Sans，按 **SIL Open Font License 1.1** 提供，版权和完整条款见 `OFL.txt`。“全部汉字”限于项目本地 Source Han Sans SC v1.004 实际映射的 30,186 个汉字，不等同于全部 Unicode 汉字或最新版思源覆盖。本项目与《刀剑神域》官方无关，不含 `SAOUI` 字体轮廓。

The fonts derive from Adobe Source Han Sans and are supplied under the **SIL Open Font License 1.1**; see `OFL.txt` for copyright and complete terms. “All Han” refers to the 30,186 Han codepoints mapped by the project's local Source Han Sans SC v1.004 inputs, not every Unicode Han character or the latest Source Han release. This independent project is not affiliated with or endorsed by *Sword Art Online* and contains no `SAOUI` font outlines.
