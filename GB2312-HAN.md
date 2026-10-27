状态：已完成

完成记录（UTC）：2026-10-27T12:34:37.345083+00:00

# Aincrad UI SC · GB2312 两级汉字补齐

日期：2026-10-27（America/Los_Angeles）。用户选择先补齐 GB2312 一级与二级汉字，沿用当前正式字体风格，停止的逐字结构精修和已归档试验不恢复。

## 交付范围

| 项目 | 补字前 | 本批新增 | 补字后 |
| --- | ---: | ---: | ---: |
| GB2312 一级汉字 | 3,755 | 0 | 3,755 |
| GB2312 二级汉字 | 55 | 2,953 | 3,008 |
| 两级汉字合计 | 3,810 | 2,953 | 6,763 |
| 原有范围外汉字 | 4 | 0 | 4 |
| 全部汉字 | 3,814 | 2,953 | **6,767** |
| 全部字符 | 4,041 | 2,953 | **6,994** |

额外保留的四字为“夬、姤、螣、遯”。原 227 个非汉字字符、两批应用扩展和 64 卦全部保留。此处“GB2312 两级”仅指 6,763 个汉字，不宣称实现完整 GB2312 字符或编码标准。

Regular／Display 的六份 OTF、TTF、WOFF2 成品均补齐本批字符。新增汉字批量沿用原有窄长比例和转角处理，没有逐字部件重排，也不将这批称为 2,953 字手工精修。

## 思源本身能提供多少字

本地来源是 Source Han Sans SC v1.004，Regular／Medium 两份完整 TTC 的 SC face 2。逐实际字体统计，两款覆盖相同：

| 概念 | 每款数量 |
| --- | ---: |
| 字形 glyph | 65,535 |
| 有效 Unicode 字符码位 | 44,683 |
| 汉字码位（含统一及兼容汉字） | **30,186** |
| 其中不同汉字 glyph | 30,091 |

65,535 包含中日韩地区写法、竖排／替代形以及其他文字；不是 65,535 个独立汉字。30,186 中又有兼容汉字和中日韩共用文字，不能理解成现代中文常用字数量。详细分区、文件哈希与全部非空轮廓检查见 `data/source-font-coverage.json`；本统计仅描述本地 v1.004，不冒称最新版覆盖。

Adobe 官方关于思源的介绍也将 65,535 明确表述为每字重的字形数：[Introducing Source Han Sans](https://blog.adobe.com/en/publish/2014/07/15/introducing-source-han-sans-an-open-source-pan-cjk-typeface)。

## 持久输入与旧字保护

`data/gb2312-han-extension.json` 保存 Python `gb2312` 编码器解码得到的完整 6,763 字，按 Unicode 码位排序，并保存两级划分、2,953 新增字、保留字和新旧源文件关系。独立验证从 Unicode 汉字反向编码检查两级，避免直接信任同一份生成清单。

本批扩展源另存为：

- `sources/AincradSeed-gb2312-Regular.otf`
- `sources/AincradSeed-gb2312-Medium.otf`

原 `sources/AincradSeed-v030-{Regular,Medium}.otf` 及三份已审阅计划继续保持原字节。构建按扩展源真实 SHA 记录出处，同时逐一比较全部 3,963 个旧源字符的轮廓与字宽完全一致，满足条件才复用旧计划的源指纹和节点锚。本批不会重新生成或扩大原 161 字精修规则。

两份扩展源各有 **6,916 个源字符**。源字体不含的早期 14 个原创符号和 64 卦，共 78 个符号继续使用项目的独立轮廓。原字参照 `fonts/SourceHanSansSC-Baseline.woff2` 也只覆盖这 6,916 个真实源字符，正式成品覆盖全部 6,994 字符。

独立验证已确认保留所有 4,041 个旧字符在对应格式中的轮廓、字宽和行度量；原 161 字、四字密集调整、TTF14 两字处理及全部原创符号均保留。默认数字继续同档等宽，Regular 为 450、Display 为 434（1000 UPM）。

## 成品路径

- 字表：`D:\333.开发\SAO\design\aincrad-ui-sc\data\charset.json`
- Regular TTF：`D:\333.开发\SAO\design\aincrad-ui-sc\fonts\AincradUISc-Regular.ttf`
- Display TTF：`D:\333.开发\SAO\design\aincrad-ui-sc\fonts\AincradUISc-Display.ttf`
- 两档 OTF／WOFF2：同目录相应后缀文件。
- 字样页：`D:\333.开发\SAO\design\aincrad-ui-sc\specimen.html`
- 本批增量输入：`D:\333.开发\SAO\design\aincrad-ui-sc\data\gb2312-han-extension.json`
- 独立分发包：`D:\333.开发\SAO\design\aincrad-ui-sc\Aincrad-UI-SC-v0.3-gb2312-han.zip`

内部字体版本保持 0.300，以本批分发名与文件哈希识别。安装时同一风格选择 OTF 或 TTF 一种；已经安装旧版时需要按系统提示替换，并重新打开应用以刷新字体缓存。未收录的汉字仍需配置中文回退字体。

## 验证记录与范围

- `data/verification.json`：六份正式字体的覆盖、命名、两档区别、原精修回归、原字参照和数字等宽。
- `data/gb2312-verification.json`：独立核对两级 6,763 汉字、恰好新增 2,953、旧 4,041 字保持、源轮廓保持及新增字实际栅格非空。
- `data/gb2312-source-preparation.json`：扩展源子集的准备、来源与旧字保护。
- `data/provenance.json` 的 `source_expansion_review`：构建时的旧源逐字比对与实际新源哈希。
- `data/browser-verification.json`、`data/small-size-verification.json`：当前字样页与既有小字号样张的实际加载、布局与成品绑定。
- `data/gb2312-package-rebuild.json`、`data/package-verification.json`：便携重建与最终分发校验。

构建生成两档各 7 页的汉字覆盖图，检查所有 6,767 汉字实际渲染非空。已有 11–14px 样张用于延续原样本的显示检查，不意味着每个新增字都经过人工小字号辨识验收。

旧 `ttf14-comparison.html` 已将“后版”固定到原字体副本，保留原截图／时间／测量。密集四字历史对照也使用固定副本。已归档的结构试验和其 ZIP 保持原字节，需要继续时在完整归档包中恢复；本批未改用结构试验 C。

## 重建

在解压后的目录：

```powershell
python -m pip install -r requirements.txt
python scripts/build_aincrad_font.py
python scripts/verify_aincrad_font.py --report data/verification.json
```

随包带有全部所需新旧源子集、配置和脚本，普通重建不需要原始 TTC 或旧 ZIP，不必先运行 prepare。完整旧字差异回归另需上一正式版 `Aincrad-UI-SC-v0.3-ttf14-round2.zip`；旧包不嵌套进本批包。缺旧包时，专用增量检查应明确报告回归不可用，不能把当下覆盖检查混称为旧字保持通过。

字体与轮廓改造继续按随包 OFL 1.1 及原来源说明提供。本批不承诺 GB18030、完整 Unicode 汉字、所有繁体／姓名，也不宣称新增字完成专业逐字精修或跨平台阅读验收。
