# Aincrad UI SC

**保留 SAO 窄长气质的中文界面字体。**

[English](README.en.md) · 简体中文 · [下载 v0.3.0](https://github.com/kymorphius/Aincrad-UI-SC/releases/tag/v0.3.0)

![Aincrad UI SC 界面字样](media/preview.png)

Aincrad UI SC 派生自 **Source Han Sans SC v1.004**，沿用窄长比例、克制的圆角与切角，提供适合正文的 **Regular** 和适合标题的 **Display** 两档。当前收录 **30,437 个字符**：本地思源来源实际映射的全部 **30,186 个汉字码位**，以及 **251 个英文、数字、标点及其他符号**。

本次 **`wao-symbols`** 版补齐 WAO 界面需求中的全部 24 个符号，包括六个制表线符号：

```text
◆◇●■□▲▼▶◀‹«»─│┌┐└┘‥⟨⟩※†‖
```

## 下载

从 [GitHub Release v0.3.0](https://github.com/kymorphius/Aincrad-UI-SC/releases/tag/v0.3.0) 下载字体。

| 用途 | 下载或文件 |
| --- | --- |
| 完整发行包：字体、源子集、字表、样张与重建工具 | [Aincrad-UI-SC-v0.3-wao-symbols.zip](https://github.com/kymorphius/Aincrad-UI-SC/releases/download/v0.3.0/Aincrad-UI-SC-v0.3-wao-symbols.zip) |
| WAO 接入：两档 TTF、应用字表、许可证和替换说明 | [Aincrad-UI-SC-v0.3-wao-handoff.zip](https://github.com/kymorphius/Aincrad-UI-SC/releases/download/v0.3.0/Aincrad-UI-SC-v0.3-wao-handoff.zip) |
| 界面正文 | `AincradUISc-Regular.ttf` 或 `.otf` |
| 标题 | `AincradUISc-Display.ttf` 或 `.otf` |
| 网页嵌入 | 两档对应的 `.woff2` |
| 完整字符列表 | [`data/charset.json`](data/charset.json) |

完整发行包为 **158,164,747 字节**（约 158 MB），WAO 替换包为 **14,424,628 字节**（约 14 MB）。两个 ZIP 分别附有 `.zip.sha256` 文件，[`SHA256SUMS`](https://github.com/kymorphius/Aincrad-UI-SC/releases/download/v0.3.0/SHA256SUMS) 覆盖发行附件。发行标签为 **`v0.3.0`**，交付版别为 **`wao-symbols`**，字体内部版本保持 **0.300**。

单独下载字体时，请同时保留随附的 [OFL.txt](https://github.com/kymorphius/Aincrad-UI-SC/releases/download/v0.3.0/OFL.txt)。

## 安装与使用

1. 每档选择 **TTF 或 OTF 其中一种**，通过系统字体管理器安装；网页项目使用 WOFF2。
2. 在应用中选择 `Aincrad UI SC` 或 `Aincrad UI SC Display`。
3. 替换旧版后，重新打开使用字体的应用以刷新缓存。

Regular 优先用于界面正文、列表与控件文字，Display 用于标题。两档数字在各自字体内默认等宽。

WAO 接入时，替换 TTF 资源及 `assets/fonts/aincrad-ui-sc-charset.json`，保持文件名与 Flutter 字体声明一致，再运行应用自己的 `test/font_coverage_test.dart` 并检查界面。字体工作区**没有代跑 WAO Flutter／Android 应用测试**。

## 网页使用

将 WOFF2 文件放入站点的 `fonts` 目录：

```css
@font-face {
  font-family: "Aincrad UI SC";
  src: url("./fonts/AincradUISc-Regular.woff2") format("woff2");
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}

@font-face {
  font-family: "Aincrad UI SC Display";
  src: url("./fonts/AincradUISc-Display.woff2") format("woff2");
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}

body {
  font-family: "Aincrad UI SC", "Microsoft YaHei", sans-serif;
}

h1, h2, .display-text {
  font-family: "Aincrad UI SC Display", "Microsoft YaHei", sans-serif;
  font-weight: 400;
}
```

## 字符范围

| 范围 | 数量 |
| --- | ---: |
| 汉字码位 | **30,186** |
| 英文、数字、标点及其他符号 | **251** |
| 总字符 | **30,437** |
| 汉字中的兼容汉字 | 421 |
| 汉字中的补充平面字符 | 2,293 |
| 本次新增界面符号 | 24 |

GB2312 两级汉字、此前应用增量和全部 **64 卦**均保留，兼容汉字保持原始 Unicode 码位。本次**没有新增汉字或汉字手工精修计划**。

“全部汉字”指本地 **Source Han Sans SC v1.004** 实际映射的统一汉字与兼容汉字，不等同于最新思源版本、所有 Unicode 汉字或全部思源字符的覆盖。精确范围见 [`data/source-font-coverage.json`](data/source-font-coverage.json)。

## 样张与验证

![14 CSS px、DPR 1 下的实际 TTF 符号样张](media/wao-symbols-study.png)

符号样张主验 **Display TTF 的 14 CSS px／DPR 1**，提供 Regular 同字号参照、深浅主题及 DPR 2 回归。[六倍整数放大图](media/wao-symbols-zoom-dpr1.png) 保留原生 DPR 1 像素供查看。汉字代表样张仍可在 [14px 汉字样张](media/sourcehan-samples.png) 中查看。

本次通用检查与独立符号检查均通过：

- 六份正式字体均覆盖 **30,437 个字符**。旧 **30,413 个字符**的矢量轮廓、完整水平度量与行度量保持；TTF 原有点位、点标志、轮廓端点及指令保持。
- 全部 24 个新符号在六格式的 14px／28px 栅格中均有实际墨迹且未越出行框；三组导航／括号的几何镜像误差为零，六个制表线符号均到达规定连接边界。
- 桌面 Chromium 在 DPR 1／2 下确认实际 TTF 加载、无字体回退，完成 **256 次单字符字体归属检查**，并检查 HUD 文案和制表框。既有 11–14px 样张和汉字代表样张均已使用当前字体刷新。
- 独立目录完整重建后，**全部 15 个字体文件及字表**与正式产出逐字节一致，其中包括七个生成文件和八个历史对照字体。

制表框按字体原始字宽和行高连接。**DPR 1 抗锯齿仍会产生轻淡的格间接缝和彩色边缘**，真实效果保留在样张中；自定义字距或行高会改变连接。密集汉字在小字号下仍可能拥挤，样张不构成全字集光学验收，也不代替 Flutter／Android 应用测试。

报告：[`data/verification.json`](data/verification.json)、[`data/wao-symbol-verification.json`](data/wao-symbol-verification.json)、[`data/wao-symbol-browser-verification.json`](data/wao-symbol-browser-verification.json) 和 [`data/wao-package-rebuild.json`](data/wao-package-rebuild.json)。此前思源汉字扩展的像素差异另存于 [`data/sourcehan-raster-diagnostics.json`](data/sourcehan-raster-diagnostics.json)，属于历史记录，不作为本次符号版的验证状态。本项目不宣称所有字号逐像素一致。

打开 `specimen.html` 可搜索和试字，打开 `wao-symbols-study.html` 查看符号样张。完整发行包另含两档各 30 页全量汉字覆盖图和 11–14px 样张。本次交付记录见 [`WAO-SYMBOLS.md`](WAO-SYMBOLS.md)。

## 重建

完整发行包包含十个源子集及十四个构建、验证与预览脚本。在解压后的目录中运行：

```powershell
python -m pip install -r requirements.txt
python scripts/build_aincrad_font.py
python scripts/verify_aincrad_font.py --report data/verification.json
```

普通重建与通用验证不需要外部 TTC、历史 ZIP 或浏览器。完整独立来源／回归检查还会使用原 TTC 和上批发行包；浏览器预览需要 Playwright／Chromium。详细构建说明见 [`BUILD.zh-CN.md`](BUILD.zh-CN.md)。验证记录保留本地和临时路径作为出处，正常重建不依赖这些目录。

## 来源与许可

原字体项目：[Adobe Source Han Sans](https://github.com/adobe-fonts/source-han-sans)。本项目使用本地 Regular／Medium TTC 的 SC face 2，保留来源版本、文件哈希和原始版权记录。派生字体采用独立名称 `Aincrad UI SC` 和 `Aincrad UI SC Display`。

字体及相应字体修改按 **SIL Open Font License 1.1** 提供。使用、嵌入、修改和再分发时，请保留相应版权与许可；完整条款见 [`OFL.txt`](OFL.txt)。以该字体排版生成的文档或图片不会因此自动采用 OFL。

本次 16 个符号保留思源来源链，六个制表线与两个角括号采用原创几何，使独立绘制符号总数达到 **86 个**：此前 14 个符号、64 个卦符和本次八个新增符号。这些轮廓及字体修改随派生字体按 OFL 1.1 提供，详细记录见 [`data/provenance.json`](data/provenance.json)。

这是独立的 SAO 风格字体项目，与《刀剑神域》官方无关，不代表官方授权或背书，也没有合并或重新发布 `SAOUI` 字体轮廓。
