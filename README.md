# 桌面助手（360 桌面助手风格套件）

一个基于 **Python + PySide6** 的 Windows 桌面助手，模块化复刻 360 桌面助手的主要能力。

## 功能总览

| 模块 | 说明 |
|---|---|
| **桌面整理** | 按类型把桌面文件自动归类到分类文件夹；规则自定义、整理预览、一键整理、撤销、桌面监听自动整理 |
| **秒级文件搜索** | Everything 式：SQLite **FTS5(trigram)** 全盘索引，中文任意子串毫秒级返回；后台并行重建、原子换表；本机装有 Everything 时可优先走其 HTTP 接口 |
| **电脑加速** | 一键清理临时文件（跳过占用文件）+ 释放可回收内存 + 可选清空回收站，如实统计释放量 |
| **回收站** | 查询回收站占用、一键清空（Shell API，不可恢复，需二次确认） |
| **软件管理** | 枚举系统已安装软件（注册表 Uninstall 项）、调用官方卸载程序、打开安装目录 |
| **壁纸** | 本地壁纸目录扫描预览、一键应用（Windows SystemParametersInfoW 持久化）、定时轮播（后台线程自动切换，可随时启停） |
| **定时关机** | 倒计时 / 指定时间，支持关机、重启、注销、睡眠；倒计时实时显示、一键取消排定任务 |
| **桌面小组件** | 悬浮球（CPU 环形进度、单击快捷菜单）、**时钟（农历+节日提醒，可右键切换大字体）**、天气（联网实时，离线自动重试）、系统监控（CPU/内存/磁盘/网速）、**收纳盒（拖入文件自动归类）**、**事项清单（待办事项，勾选/增删，自动持久化）** |
| **系统托盘** | 关闭窗口进托盘，托盘菜单一键整理/加速/显示主界面 |
| **开机自启** | 一键注册到当前用户启动项（注册表 Run） |

## 安装与运行（Windows）

```bash
pip install -r requirements.txt
python main.py
```

- 首次运行在 `C:\Users\<你>\.desktop_assistant\` 生成 `config.json`、`rules.json`、`todo.json`（待办）与 `file_index.db`（搜索索引）。
- **首次启动会在后台自动建立全盘文件索引**（数分钟，不影响使用）；建好后「全局搜索」输入关键字即秒级返回。也可在搜索页点「重建索引」。
- 天气默认城市为石家庄，可在「设置」页修改。

## 使用建议

- 桌面整理首次使用先保持「预览模式」，确认分类结果再执行真实整理。
- 「自动整理新文件」开启后，新放到桌面的文件会在数秒内自动归类。
- **收纳盒**：直接把桌面文件拖入收纳盒，自动按规则归入对应分类文件夹。
- **事项清单**：在桌面小组件中输入回车即添加，勾选即完成，重启不丢失。
- 时钟小组件右键可切换「大字体」；农历行同时显示干支纪年、生肖与节日（春节/中秋/除夕等）。
- **定时关机**：在「定时关机」页选择操作（关机/重启/注销/睡眠）与模式（倒计时分钟 / 指定 HH:MM），点「开始计时」后桌面保持显示剩余时间，倒计时结束自动执行；想取消点「取消已排定」。仅 Windows 生效。
- 软件管理、回收站、开机自启、内存清理、Everything 对接、定时关机为 **Windows 专属**；其他平台会提示不可用或跳过。

## 开源与下载

- 项目以 **MIT 协议**开源（见 LICENSE）。
- **Windows 一键包（免安装 exe）**：直接下载 Releases 中的 `DesktopAssistant.exe`（单文件，无需安装 Python），双击运行即可。
- 每次推送代码，GitHub Actions 会自动在 Windows 环境重新打包并上传构建产物（Actions 页 → 最新一次运行 → Artifacts）。
- 打 `v*` 标签（如 `v1.0.0`）推送时，会自动生成一个 Release 并附带 exe。

### 本地打包 exe（Windows）

```bat
双击 build.bat
```

或手动执行：

```bat
pip install -r requirements.txt pyinstaller
python build_icon.py
pyinstaller --noconfirm --clean --onefile --windowed --name DesktopAssistant --icon assets\app.ico main.py
```

产物在 `dist\DesktopAssistant.exe`。

## 项目结构

```
desktop_assistant/
├── main.py                        # 入口：托盘 + 小组件管理 + 悬浮球联动
├── requirements.txt               # PySide6, psutil
├── build.bat                      # Windows 一键打包 exe
├── build_icon.py                  # 生成应用图标 assets/app.ico
├── LICENSE                        # MIT 开源协议
├── README.md
├── .github/workflows/build.yml    # GitHub Actions：自动打包 exe + 发布 Release
└── assistant/
    ├── config.py                  # 全局配置持久化
    ├── rules.py                   # 分类规则
    ├── organizer.py               # 桌面整理执行器（扫描/移动/撤销）
    ├── lunar.py                   # 农历转换（1900–2100，含干支/生肖/节日）
    ├── fast_search.py             # FTS5 全盘索引 + Everything 可选对接
    ├── monitor.py                 # CPU/内存/磁盘/网速（psutil）
    ├── weather.py                 # 天气获取（wttr.in，离线降级）
    ├── accelerate.py              # 一键加速（清临时文件+内存+回收站）
    ├── recycle.py                 # 回收站查询与清空（Shell API）
    ├── apps.py                    # 已装软件 / 启动项 / 开机自启
    ├── wallpaper.py               # 壁纸（本地目录扫描 + Windows 设置 + 定时轮播）
    ├── shutdown_timer.py          # 定时关机/重启/注销/睡眠 + 倒计时
    ├── search.py                  # 目录树直搜（索引未就绪时降级用）
    ├── widgets/
    │   ├── base_widget.py         # 小组件基类（置顶/半透明/可拖动）
    │   ├── clock_widget.py        # 时钟（农历 · 大字体）
    │   ├── weather_widget.py      # 天气
    │   ├── monitor_widget.py      # 系统监控
    │   ├── floating_ball.py       # 悬浮球
    │   ├── shelf_widget.py        # 收纳盒（拖入文件自动归类）
    │   └── todo_widget.py         # 事项清单（待办持久化）
    └── ui/
        ├── main_window.py         # 主控制台（8 个功能页签）
        └── rule_dialog.py         # 分类规则编辑
```

## 说明与限制

- **壁纸**：壁纸页签选择本地图片目录后扫描预览（JPG/PNG/BMP/WebP）；Windows 下「应用选中壁纸」通过系统 API 立即生效并持久化，可开启定时轮播由后台线程自动切换；非 Windows 平台仅预览不修改桌面。
- **内存清理**：通过 Windows API 让系统回收可释放内存页，不会凭空增加物理内存，属于“整理型”加速。
- **临时文件清理**：跳过正在被占用的文件，释放量如实统计。
- **索引与 Everything**：内置索引搜索 >=3 字走 FTS trigram（任意子串），<3 字回退 LIKE；勾选“优先 Everything”后若检测到本机 Everything HTTP 服务（默认 127.0.0.1:80）则实时走 Everything。
- 桌面整理只整理普通文件，不移动文件夹、隐藏文件及 `desktop.ini` 等系统文件；同名文件自动加序号，绝不覆盖。
