# -*- coding: utf-8 -*-
"""桌面助手套件：核心逻辑离屏自测（非 Windows 可运行部分）。"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0

def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK  {msg}")
    else:
        FAIL += 1
        print(f"  FAIL  {msg}")

def main():
    tmp = tempfile.mkdtemp(prefix="da_test_")

    print("== 1. 配置 ==")
    from assistant.config import AppConfig
    c = AppConfig(os.path.join(tmp, "config.json"))
    check(c.get("dry_run") is True, "默认 dry_run=True")
    c.set("dry_run", False)
    c2 = AppConfig(os.path.join(tmp, "config.json"))
    check(c2.get("dry_run") is False, "配置保存并重载")

    print("== 2. 桌面整理 ==")
    from assistant.rules import RuleManager
    from assistant.organizer import DesktopOrganizer
    rm = RuleManager(os.path.join(tmp, "rules.json"))
    check(rm.classify("x.png") == "图片", "png -> 图片")
    check(rm.classify("a.docx") == "文档", "docx -> 文档")
    desk = os.path.join(tmp, "Desktop")
    os.makedirs(desk)
    for f in ("a.jpg", "b.jpg", "doc.pdf", "z.zip", "desktop.ini"):
        open(os.path.join(desk, f), "w").close()
    org = DesktopOrganizer(desk, rm)
    items = org.scan()
    check(len(items) == 4, f"跳过 desktop.ini，扫描到 4 个(实得 {len(items)})")
    ok, fail = org.run(dry_run=False)
    check(ok == 4 and fail == 0, f"整理 4 成功(ok={ok} fail={fail})")
    check(os.path.exists(os.path.join(desk, "图片", "a.jpg")), "a.jpg 归入 图片/")
    check(os.path.exists(os.path.join(desk, "压缩包", "z.zip")), "z.zip 归入 压缩包/")
    ok, fail = org.undo()
    check(ok == 4 and fail == 0, "撤销 4 成功")

    print("== 3. 系统监控 ==")
    from assistant.monitor import SystemMonitor
    m = SystemMonitor()
    s = m.snapshot()
    check(m.available and s.mem_total_gb > 0, "psutil 监控可用且内存总量>0")

    print("== 4. 加速（非 Windows 只测临时文件清理） ==")
    from assistant.accelerate import clean_temp_files
    tdir = os.path.join(tmp, "tmpdir")
    os.makedirs(tdir)
    open(os.path.join(tdir, "x.tmp"), "w").write("hello")
    open(os.path.join(tdir, "y.tmp"), "w").write("world")
    from unittest.mock import patch
    with patch("assistant.accelerate._temp_dirs", return_value=[tdir]):
        cnt, freed, skipped = clean_temp_files()
    check(cnt == 2, f"清理到 2 个临时文件(实得 {cnt})")
    check(freed > 0, f"释放量>0 ({freed:.2f} MB)")

    print("== 5. 回收站信息（非 Windows 返回 0） ==")
    from assistant.recycle import recycle_info, human_bytes
    info = recycle_info()
    check(info["item_count"] == 0 and info["bytes"] == 0, "非 Windows 回收站返回 0")
    check(human_bytes(1536) == "1.5 KB", "human_bytes 换算正确")

    print("== 6. 全局搜索 ==")
    from assistant.search import search_files
    make = os.path.join(tmp, "files")
    os.makedirs(os.path.join(make, "sub"))
    open(os.path.join(make, "annual_report_2026.pdf"), "w").close()
    open(os.path.join(make, "年度报告_2026.pdf"), "w").close()
    open(os.path.join(make, "sub", "notes.txt"), "w").close()
    open(os.path.join(make, "random.dat"), "w").close()
    res = search_files("annual", [make])
    check(len(res) == 1 and "annual_report_2026.pdf" in res[0], "文件名子串搜索命中")
    res2 = search_files("", [make])
    check(res2 == [], "空关键字返回空")

    print("== 7. 软件管理（非 Windows 返回空/跳过） ==")
    from assistant.apps import list_installed_apps, set_auto_start
    check(list_installed_apps() == [], "非 Windows 无软件列表")
    set_auto_start(True)
    check(True, "set_auto_start 非 Windows 不抛异常")

    print("== 8. 天气（离线/失败降级） ==")
    from assistant.weather import get_weather
    r = get_weather("____not_a_city____", timeout=3)
    check(r is None or r.get("temp"), "天气函数不崩溃")

    print("== 9. 农历转换 ==")
    from assistant.lunar import solar_to_lunar
    for y, m, d in ((2024, 2, 10), (2025, 1, 29), (2026, 2, 17), (2000, 2, 5), (2023, 1, 22)):
        lunar = solar_to_lunar(y, m, d)
        check(lunar and lunar.month == 1 and lunar.day == 1 and not lunar.is_leap,
              f"{y}-{m:02d}-{d:02d} 应为正月初一(实得 {lunar.month_name}{lunar.day_name})")
    mid = solar_to_lunar(2026, 9, 25)
    check(mid and mid.month == 8 and mid.day == 15 and mid.festival == "中秋节",
          f"2026-09-25 应为中秋节(实得 {mid.display() if mid else None})")
    today = solar_to_lunar(2026, 10, 21)
    check(today and today.day_name and today.ganzhi_year, f"2026-10-21 农历显示: {today.display()}")
    leap = solar_to_lunar(2020, 5, 23)
    check(leap and leap.is_leap and leap.month == 4 and leap.day == 1,
          f"2020-05-23 应为闰四月初一(实得 {leap.month_name}{leap.day_name} {leap.day})")
    check(solar_to_lunar(1800, 1, 1) is None, "超范围返回 None")

    print("== 10. FTS5 秒级索引 ==")
    from assistant.fast_search import FastIndex
    idx_db = os.path.join(tmp, "file_index.db")
    fi = FastIndex(db_path=idx_db, roots=[make])
    n = fi.rebuild()
    check(n >= 4, f"索引建立 {n} 个文件(≥4)")
    st = fi.stats()
    check(st["count"] >= 4 and st["fts"], f"索引统计正确 count={st['count']} fts={st['fts']}")
    hits = fi.search("annual")
    check(len(hits) >= 1 and any("annual_report_2026.pdf" in h["path"] for h in hits),
          "FTS 子串搜索命中 annual")
    hits2 = fi.search("报告")
    check(len(hits2) >= 1 and any("年度报告_2026.pdf" in h["path"] for h in hits2),
          f"中文子串搜索命中 {len(hits2)}")
    hits3 = fi.search("annual_report_2026")
    check(len(hits3) >= 1, "长文件名精确子串命中")
    check(fi.search("") == [], "空关键字返回空")

    print("== 11. 收纳盒归类 ==")
    from assistant.organizer import FileItem
    from assistant.organizer import DesktopOrganizer as _Org
    desk3 = os.path.join(tmp, "Desktop3")
    os.makedirs(desk3)
    open(os.path.join(desk3, "photo1.png"), "w").close()
    rm3 = RuleManager(os.path.join(tmp, "rules3.json"))
    o3 = _Org(desk3, rm3)
    items3 = [FileItem(src=os.path.join(desk3, "photo1.png"), name="photo1.png",
                       category=rm3.classify("photo1.png"))]
    ok3, fail3 = o3.run(items3, dry_run=False)
    check(ok3 == 1 and fail3 == 0 and os.path.exists(os.path.join(desk3, "图片", "photo1.png")),
          "拖入收纳盒 → 自动归类成功")

    print("== 12. 事项清单持久化 ==")
    import json as _json
    todo_f = os.path.join(tmp, "todo.json")
    with open(todo_f, "w", encoding="utf-8") as f:
        _json.dump([{"text": "整理桌面", "done": False}, {"text": "写周报", "done": True}], f, ensure_ascii=False)
    check(os.path.exists(todo_f), "todo.json 写入")

    print("== 13. 壁纸模块 ==")
    from assistant.wallpaper import WallpaperManager
    wpdir = os.path.join(tmp, "wallpapers")
    os.makedirs(wpdir)
    for n in ("a.jpg", "b.png", "c.webp", "readme.txt"):
        open(os.path.join(wpdir, n), "w").close()
    wm = WallpaperManager(wpdir)
    imgs = wm.list_images()
    check(len(imgs) == 3, f"壁纸扫描 3 张(实得 {len(imgs)})")
    ok = wm.apply(imgs[0])
    check(ok is False and wm._current == imgs[0], "非 Windows 仅记录不设置(apply 返回 False)")
    nxt = wm.next()
    check(nxt in imgs and nxt != imgs[0], "轮播切换到下一张")
    wm.start_rotation(5.0)
    check(wm.rotating, "轮播线程已启动")
    wm.stop_rotation()
    check(not wm.rotating, "轮播线程安全停止")
    wm.shutdown()

    print("== 14. 定时关机 ==")
    from assistant.shutdown_timer import build_command, cancel as sd_cancel, execute as sd_execute, Countdown
    check(build_command("shutdown", 60) == ["shutdown", "/s", "/t", "60"], "关机命令构造正确")
    check(build_command("restart", 30) == ["shutdown", "/r", "/t", "30"], "重启命令构造正确")
    check(build_command("logout", 99) == ["shutdown", "/l"], "注销命令立即执行")
    check(build_command("sleep", 10) is None, "睡眠走 API 不走 shutdown")
    check(sd_cancel() is False and sd_execute("shutdown", 60) is False, "非 Windows 取消/执行返回 False")
    cd = Countdown(3)
    check(not cd.tick() and cd.remaining == 2, "倒计时递减")
    check(cd.tick(2) and cd.finished and cd.remaining == 0, "倒计时归零触发")
    cd.reset(3661)
    check(cd.format_remaining() == "01:01:01", f"剩余时间格式化 {cd.format_remaining()}")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n结果: 通过 {PASS} 项, 失败 {FAIL} 项")
    return 1 if FAIL else 0

if __name__ == "__main__":
    sys.exit(main())
