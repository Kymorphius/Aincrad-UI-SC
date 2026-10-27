状态：已完成

完成记录（UTC）：2026-10-27T13:17:20.703382+00:00

# Aincrad UI SC · 本地思源汉字全量补齐

日期：2026-10-27（America/Los_Angeles）。按用户要求，将本地 Source Han Sans SC v1.004 实际包含的剩余汉字全部并入现有 Aincrad UI 风格；新增字批量应用既有规则，不增加逐字精修计划。

## 交付范围

| 项目 | 补字前 | 本批新增 | 补字后 |
| --- | ---: | ---: | ---: |
| 汉字码位 | 6,767 | 23,419 | **30,186** |
| 英文、数字、标点及其他符号 | 227 | 0 | 227 |
| 总字符 | 6,994 | 23,419 | **30,413** |
| 每档真实源字符 | 6,916 | 23,419 | **30,335** |

汉字范围取自实际来源字体的 Unicode cmap，按统一汉字及兼容汉字区块分类。基本区 20,945、扩展 A 区 6,582、扩展 B 至 E 区 2,238、基本兼容区 366、补充兼容区 55，合计 30,186，其中 2,293 位于补充平面。GB2312 两级 6,763 汉字及之前四个集外字继续保留。

本统计描述本地 v1.004 的实际覆盖，不等同于所有 Unicode 汉字或最新版思源覆盖，也不将 65,535 字形理解为独立汉字数。来源文件与统计详见 `data/source-font-coverage.json`。

## 风格与旧字保护

Regular／Display 保留现有窄长比例、字重基础、圆角／切角、字宽和行距。原 161 字计划、四字密集处理和 TTF14 两字处理保持原字节。新汉字全部沿用现有统一规则；已归档结构试验不恢复。

旧字保护检查涵盖轮廓、完整水平度量、TTF 点位／标志／轮廓端点及行度量，不能扩大解释为每种渲染器在每个字号逐像素相同。额外 FreeType 灰度诊断发现少量差异：14px 控制样本中 Regular 的“备、螣”有灰度边缘变化，Display 的控制样本相同；12px Regular 的“角”墨迹顶部相差 1 像素，行距和字宽仍相同。正式字体不为该现象增加轮廓或全局 hint 修改。

纯内存隔离试验确认，删除新增 BMP 汉字映射可恢复相关旧像素，恢复 head／hhea／OS2 全局字段则无效；这是渲染器依据可用字集重新校准像素对齐的影响。详细范围、差值及因果试验见 `data/sourcehan-raster-diagnostics.json`。FreeType 的 [CJK 自动对齐实现](https://raw.githubusercontent.com/freetype/freetype/master/src/autofit/afcjk.c) 与 [参考字符配置说明](https://raw.githubusercontent.com/freetype/freetype/master/src/autofit/afblue.dat) 解释了基于字体可用参考字符计算全局对齐区的机制。像素一致性作为明确报告的诊断项，覆盖／旧几何／度量／源保持等作为硬性验收项。

新增源为 `sources/AincradSeed-sourcehan-{Regular,Medium}.otf`，每档 30,335 字符。旧 v0.3 原审阅源及上批 GB2312 源继续保留。构建逐一核对全部 3,963 个原源字符和 6,916 个上批源字符的轮廓及水平度量，满足完全一致才复用原精修源锚；实际新源路径及哈希独立记入 `data/provenance.json`。

两份思源中有 94 组共用源 glyph 的汉字映射。兼容字保留其 Unicode 码位，不做 NFKC 归一化。新增兼容字“更”（U+F901）与“更”（U+66F4）共用源 glyph，因此复用“更”已存在的精修计划以保持同形，没有新建或修改手工计划。该继承另记入每档 provenance，不计为新增手工精修。

原有 78 个原创符号（早期 14 个符号及 64 卦）继续使用独立轮廓。原字参照 `SourceHanSansSC-Baseline.woff2` 覆盖 30,335 个真实源字符，正式成品覆盖全部 30,413 字符。

## 产出路径

- 字表：`D:\333.开发\SAO\design\aincrad-ui-sc\data\charset.json`
- Regular TTF：`D:\333.开发\SAO\design\aincrad-ui-sc\fonts\AincradUISc-Regular.ttf`
- Display TTF：`D:\333.开发\SAO\design\aincrad-ui-sc\fonts\AincradUISc-Display.ttf`
- 两档 OTF／WOFF2：同目录相应后缀。
- 字样页：`D:\333.开发\SAO\design\aincrad-ui-sc\specimen.html`
- 新字代表样张：`D:\333.开发\SAO\design\aincrad-ui-sc\sourcehan-samples.html`
- 全量输入：`D:\333.开发\SAO\design\aincrad-ui-sc\data\sourcehan-han-extension.json`
- 分发包：`D:\333.开发\SAO\design\aincrad-ui-sc\Aincrad-UI-SC-v0.3-sourcehan-han.zip`

内部版本继续为 0.300，家庭名与正式字体路径保持，按分发包名和哈希识别本次交付。安装时同档选择 TTF 或 OTF 一种，并重开使用字体的应用刷新缓存。

## 验证与重建

已通过综合字体验证、全量来源字集独立核对、旧 6,994 字符六格式逐字回归、补充平面 format 12 映射及兼容字形关系验证。全量栅格检查证明字形能实际显示；已有 11–14px 样张和新字代表样张用于检查实际加载，不代表 23,419 个新字逐一通过小字号人工精修验收。

验证与重建记录保存在 `data/verification.json`、`data/sourcehan-verification.json`、`data/sourcehan-raster-diagnostics.json`、`data/sourcehan-source-preparation.json`、`data/browser-verification.json`、`data/small-size-verification.json`、`data/sourcehan-sample-verification.json`、`data/sourcehan-package-rebuild.json` 和 `data/package-verification.json`。

解压后可运行：

```powershell
python -m pip install -r requirements.txt
python scripts/build_aincrad_font.py
python scripts/verify_aincrad_font.py --report data/verification.json
```

随包带有全部所需源子集和构建输入，常规重建不依赖完整 TTC 或历史 ZIP。完整来源独立回归使用本地原 TTC；旧字差异回归使用上批 `Aincrad-UI-SC-v0.3-gb2312-han.zip`。独立验证会明确区分缺少外部历史证据与实际通过，旧包不嵌入新包。字体继续按随包 OFL 1.1 和原来源说明提供。

最终独立检查实际返回 `ok=true`、`mandatory_requirements_passed=true`、`status=passed-with-raster-differences`，`failures=[]`。新增 23,419 字在六格式中共 140,514 次 32px 栅格检查均非空且不越行；旧 6,994 字的六格式几何与度量全保持。FreeType 逐像素相等不是本批结论，诊断中的 false 与相邻字号差异原样保留。独立目录完整重建与综合验证均成功，15 个字体及字表逐字节一致。
