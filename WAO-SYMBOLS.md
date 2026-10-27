状态：已完成

# Aincrad UI SC · WAO 24 界面符号补齐

日期：2026-10-27（America/Los_Angeles）。对应根目录 `wao-font-request-20261027.md`，24 个符号全部纳入，包括原需求允许最后处理的六个制表线符号。

```text
◆◇●■□▲▼▶◀‹«»─│┌┐└┘‥⟨⟩※†‖
```

## 范围与字形

| 项目 | 补字前 | 本次新增 | 补字后 |
| --- | ---: | ---: | ---: |
| 汉字 | 30,186 | 0 | 30,186 |
| 非汉字字符 | 227 | 24 | 251 |
| 总字符 | 30,413 | 24 | **30,437** |
| 每档真实源字符 | 30,335 | 16 | 30,351 |
| 独立几何字符 | 78 | 8 | 86 |

Regular、Display 两档均提供 OTF、TTF、WOFF2。保留旧 30,413 字符的轮廓、完整水平度量、TTF 点位与行度量；原汉字精修、数字等宽及 64 卦保持。

16 个新符号保留本地 Source Han Sans SC v1.004 的来源链，按现有风格形成最终轮廓。六个制表线和两个数学角括号“⟨⟩”使用独立几何轮廓：制表线明确延伸到字符左右边界以及现有行单元的上下边界，支持样张中的连接；角括号使用自己的 Unicode 码位。新增“‹”与原“›”配对，“‥”与原“…”配套。字形方案位于 `data/wao-symbols-v030.json`，全部使用最终字体坐标，不重复压缩或切角。

新源为 `sources/AincradSeed-wao-{Regular,Medium}.otf`；旧 sourcehan、GB2312 和 v0.3 审阅源保留原字节。持久字符输入为 `data/wao-symbol-extension.json`。原字参照仅排除明确声明的 86 个独立几何字符，保留 16 个真实源符号，覆盖 30,351 字符。

## 查看与交付

- 当前字表：`data/charset.json`，其中 `character_count` 更新为 30,437。
- 正文 TTF：`fonts/AincradUISc-Regular.ttf`。
- 标题 TTF：`fonts/AincradUISc-Display.ttf`。
- 同目录 `.otf`、`.woff2` 为对应安装／网页格式。
- 14px TTF 样张：`wao-symbols-study.html`、`wao-symbols-study.png`。
- DPR 2 样张：`wao-symbols-study-dpr2.png`；DPR 1 整数放大：`wao-symbols-zoom-dpr1.png`。
- 完整包：`Aincrad-UI-SC-v0.3-wao-symbols.zip`。
- WAO 替换包：`Aincrad-UI-SC-v0.3-wao-handoff.zip`，包含两档 TTF、`aincrad-ui-sc-charset.json`、许可证及替换说明。

WAO 工程替换其 `assets/fonts/` 当前引用的 TTF 与 `aincrad-ui-sc-charset.json`，保持工程自己的文件名和字体声明一致，再运行其 `test/font_coverage_test.dart`。本仓库的字体验证与浏览器样张不等同于 WAO Flutter 应用端实测；交付记录将明确实际完成的范围。

## 验证范围

主验 Display TTF 的 14 CSS px／DPR 1，配合 Regular 同字号对照及 DPR 2。检查新 24 字符的实际加载、非空字形、空心轮廓、导航配对、视觉重心及制表线连接。一般验证与本批独立检查负责全六格式覆盖、旧字几何和度量保护、原字参照范围与数字等宽。

验证记录：`data/verification.json`、`data/wao-symbol-verification.json`、`data/wao-symbol-browser-verification.json`、`data/wao-source-preparation.json`、`data/wao-package-rebuild.json` 及 `data/package-verification.json`。

本批通用检查与独立检查均通过。六格式各 30,437 字，旧 30,413 字符的完整水平度量、行度量与轮廓保持；TTF 点位、点标志、轮廓终点和指令保持。数字仍为 Regular 450／Display 434 UPM。三个左右配对的几何镜像误差为零，六个制表线连接边界误差为零。

浏览器完成 256 次单字符字体归属检查、40 条 HUD 文案检查、32 个辅助字号行检查和 8 个制表框检查，字体响应与成品哈希一致，没有 fallback。已目视原生 DPR 1／2 样张及六倍整数放大图：实心与空心形有区分，导航方向正常，制表框没有背景断口；DPR 1 接点存在抗锯齿淡缝和彩色边缘，未隐藏或用放大重采样抹平。11–14px 辅助行只代表所列样本，不构成全字集小字号光学验收。

独立副本从缺少七个生成字体和字表的状态完成重建，再运行通用验证；全部 15 个字体文件（七个生成、八个历史）及字表与本次产出逐字节一致，28 项核心输入保持。构建不需要外部 TTC、历史 ZIP 或浏览器。完整包保留十个源子集和十四个构建／检查／预览脚本；历史包保留原字节。

字体仍按随包 OFL 1.1 和原来源说明提供，保留独立主名。内部版本继续为 0.300，以本批包名和哈希区分交付。此前结构试验保持归档，本批没有重新调整汉字部件；像素对齐可受新增映射及渲染环境影响，不承诺所有旧字在所有字号逐像素相同。
