状态：已完成

完成时间：2026-10-27T02:27:32.809526+00:00

# Regular TTF · 14 px / DPR 1 · 攥、螣第二轮优化

本轮需求：继续改善 Regular TTF 中“攥、螣”在 14 CSS px、DPR 1 的粘连和字内留白，保持字宽和行距，并提供同字号前后对照。当前版内版本号保持 0.300，交付标识为 `ttf14-round2`。

## 实际调整与结论

**攥**：将目部外框纵向空间增加约 30 源字体单位，三处内白高度各增加 10 单位，保留内部细横原厚度；竹头只作小幅位移与尾部收短，避免目部扩展后上下过挤。实际 TTF 的 DPR 1 样本中，中部不再像旧版那样均匀糊成一块灰面，层次更容易观察；原字号下仍密，不能宣称三层内白在任何像素位置都清晰可辨。

**螣**：将右下末点及其对应内侧斜边向右移 16 源字体单位，保持点与下横的厚度，打开邻近通道。没有采用削薄下横、削弱末点或整体收窄笔画的方案。实际改善较轻，DPR 1 的中下部仍拥挤；DPR 2 未观察到明显结构变形或破损。

本轮先比较了多个局部参数方案，再用正式重建字体复核。只扩大向量内白不足以保证小字号每个像素都更白，因此以真实 TTF 浏览器对照为主要选择依据，灰度采样保留局部变好与变差的全部结果。

## 字宽与行距

两字 advance 均保持 900／1000 UPM，LSB 保持攥 46、螣 41。所有字符的完整 `hmtx`、`hhea` 与 OS/2 行度量保留：Regular ascent 1160、descent −320、lineGap 0。浏览器中的两版自然宽度均为 12.609375 CSS px（14 × 0.9 的布局取整值），对照行高同为 28 CSS px，没有通过字距或宽度补偿制造差异。

Regular 仅这两字轮廓发生变化，另外 4,039 个字符保持；Display 的 OTF／TTF／WOFF2 保持上轮原文件。六十四卦、原 161 字配置和上轮的“羁、黛”均保留。默认数字 0–9 继续等宽，Regular 为 450、Display 为 434 字体单位。本轮不改字符集：3,814 汉字、4,041 总字符。

## 同字号对照条件与产出

`ttf14-comparison.html` 的前后两列直接加载 `.ttf`，检查浏览器实际采用的自定义字体和返回的文件字节哈希。对照保持 14 CSS px、字距 0、行高 28 CSS px、相同颜色与背景、同一 y 坐标和物理像素采样相位，没有滤镜或字体缩放。DPR 1 为主要样本，DPR 2 为回归；各有亮暗背景、单字、短语和未改控制文字。

| DPR／主题 | 攥的改变像素数 | 螣的改变像素数 | 控制文字 |
| --- | ---: | ---: | --- |
| 1／浅色 | 99 | 11 | 像素差 0 |
| 1／深色 | 105 | 10 | 像素差 0 |
| 2／浅色 | 305 | 25 | 像素差 0 |
| 2／深色 | 311 | 27 | 像素差 0 |

改变像素数用于证明实际样张发生变化，不能当成改善分数。控制文字为“羁黛”和“命宫2026”，所有组保持相同像素；目标字和短语没有字体回退或裁切。

- 原始 DPR 1：`D:\333.开发\SAO\design\aincrad-ui-sc\ttf14-comparison.png`
- 原始 DPR 2：`D:\333.开发\SAO\design\aincrad-ui-sc\ttf14-comparison-dpr2.png`
- 紧凑放大图：`D:\333.开发\SAO\design\aincrad-ui-sc\ttf14-comparison-compact.png`
- 可打开页面：`D:\333.开发\SAO\design\aincrad-ui-sc\ttf14-comparison.html`
- 浏览器证据：`D:\333.开发\SAO\design\aincrad-ui-sc\data\ttf14-comparison.json`

紧凑图左前右后，DPR 1 的物理像素最近邻放大 8 倍，DPR 2 放大 4 倍；没有插值增加细节。判断实际阅读效果仍应回到原图或 HTML 原字号。

## 构建与验证记录

两字配置为 `data/ttf14-refinements-v030.json`，在原 `data/dense-refinements-v030.json` 后应用。它锁定前置计划 SHA、源子集 SHA、轮廓拓扑与节点锚点，构建时不满足即停止。三种 Regular 输出格式使用同一份源局部调整，以 TTF 为主要验收格式；没有加入全局 hint 程序或修改全库渲染表。

正式 Regular TTF SHA-256：

```text
b5c0733fdb47c077768966a54b4e6c7d27b6484263230af461b562a07759a03e
```

不可变基线：`Aincrad-UI-SC-v0.3-dense14-hexagrams.zip`，SHA-256：

```text
fbb334a39f97a16426198bda98242e5cde04a237b415184c7be15569cfe5fd1d
```

其中旧 Regular TTF SHA 为 `a5a0bcb9ff7f8fa9cc3a8085c1bb64fd74cbeab075d83ad7bde62494b441320b`，另存为 `fonts/AincradUISc-v030-before-ttf14-Regular.ttf`。上轮四字 WOFF2 对照的“后版”也另存为历史文件，旧 HTML 只改该资源 URL，不重写旧截图或假称它是本轮证据。

综合检查 `data/verification.json` 已运行。独立两字检查与便携重建结果分别见 `data/ttf14-verification.json`、`data/ttf14-package-rebuild.json`；最终分发清单见 `data/package-verification.json`。主预览 19 项与 WOFF2 小字号 32 面板／8 手机样张已按本轮字体重新生成并复核。小字号页面实际使用 WOFF2，其 TTF 哈希仅是文件身份记录；TTF 渲染结论来自专用对照。

## 固定区域灰度诊断

独立 Pillow／FreeType 默认 TTF 栅格在 **14 物理像素** 下，以同一基线、固定旧区域计算连续灰度白量（1−alpha/255 的面积加权均值），不移动采样框，也不二值化。它与浏览器截图是两类证据：

| 固定旧区域 | 修改前白量 | 修改后白量 | 增加百分点 |
| --- | ---: | ---: | ---: |
| 攥／原目框 | 37.1065% | 46.3624% | +9.2559 |
| 螣／原下部内白 | 41.5454% | 47.2172% | +5.6718 |
| 螣／原末点根部 | 30.5325% | 32.3544% | +1.8219 |

13、14、15、28 物理像素共 48 项固定区域比较中，25 项白量增加、9 项下降、14 项不变；包括“攥”旧中部内白窗口和“螣”中央冒头窗口的局部负值，均在报告保留。指定区域更白不代表整字减重，三格式总墨面积有小幅重分配；方向与严格交叉检查保持，非空／裁切和控制文字检查通过。所有度量与其余字符保持检查通过。

## 当前成品路径

- 字表：`D:\333.开发\SAO\design\aincrad-ui-sc\data\charset.json`
- 主要成品 TTF：`D:\333.开发\SAO\design\aincrad-ui-sc\fonts\AincradUISc-Regular.ttf`
- Regular OTF：`D:\333.开发\SAO\design\aincrad-ui-sc\fonts\AincradUISc-Regular.otf`
- Regular WOFF2：`D:\333.开发\SAO\design\aincrad-ui-sc\fonts\AincradUISc-Regular.woff2`
- Display：同目录 `AincradUISc-Display.otf`／`.ttf`／`.woff2`，本轮文件不变。
- 独立分发包：`D:\333.开发\SAO\design\aincrad-ui-sc\Aincrad-UI-SC-v0.3-ttf14-round2.zip`

新包含源子集、可重建配置、字体、对照与验证脚本，不包含旧 ZIP 或原始 TTC；历史包均保留。普通构建不需要外部 TTC。重新跑完整旧字差异检查或提取基线，需要另给上轮 ZIP；打开现有对照页不需要。

本次结果只覆盖指定桌面 Chromium 的 TTF 样本及独立栅格诊断；不是识字率盲测，也未完成 Flutter／Android 真实星盘页面验收。固定区域留白增加不能证明所有局部细节、所有像素相位和所有平台都更清晰。
