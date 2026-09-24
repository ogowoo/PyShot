# -*- coding: utf-8 -*-
"""生成 i18n_data.py 的词表（开发工具，不参与运行时）。

- 以**简体原文为 key**（gettext 风格），所以源码里写 tr("区域截图")
- 繁体：短语映射 + 字符映射自动转换（再人工核对台湾用词）
- 英文：手写在下面的 EN 字典里

用法：python _gen_i18n.py
"""
import ast
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
FILES = ["main.py", "snipper.py", "editor.py", "border.py", "watermark.py",
         "scroller.py", "pinboard.py", "bootstrap.py",
         "version.py",       # 版本主题等也在这里，别漏（否则英文界面会蹦中文）
         "help_text.py", "helpwin.py"]      # 帮助正文/帮助窗口
CJK = re.compile(r"[\u4e00-\u9fff]")

# ---------------------------------------------------------------- 繁化：短语优先
S2T_WORDS = [
    # 台湾用词（不只是字形）
    ("注册", "註冊"), ("依赖", "依賴"), ("注释", "註釋"), ("内存", "記憶體"),
    ("托盘", "托盤"), ("图标", "圖示"), ("滑块", "滑桿"), ("双击", "雙擊"),
    ("锚点", "錨點"), ("快速键", "快速鍵"), ("帧", "幀"),
    ("屏幕", "螢幕"), ("鼠标", "滑鼠"), ("键盘", "鍵盤"), ("剪贴板", "剪貼簿"),
    ("光标", "游標"), ("默认", "預設"), ("打开", "開啟"), ("关闭", "關閉"),
    ("界面", "介面"), ("视频", "影片"), ("滚动", "捲動"), ("设置", "設定"),
    ("软件", "軟體"), ("硬件", "硬體"), ("内存", "記憶體"), ("网络", "網路"),
    ("文件", "檔案"), ("复制", "複製"), ("粘贴", "貼上"), ("打印", "列印"),
    ("信息", "資訊"), ("支持", "支援"), ("回退", "退回"), ("预览", "預覽"),
    ("重启", "重啟"), ("崩溃", "當機"), ("保存", "儲存"), ("确定", "確定"),
    ("取消", "取消"), ("应用", "套用"), ("适应", "符合"), ("缩小", "縮小"),
    ("放大", "放大"), ("撤销", "復原"), ("重做", "重做"), ("贴图", "釘圖"),
    ("取色", "取色"), ("裁剪", "裁剪"), ("马赛克", "馬賽克"), ("高亮", "標示"),
    ("序号", "序號"), ("画笔", "畫筆"), ("箭头", "箭頭"), ("椭圆", "橢圓"),
    ("矩形", "矩形"), ("文字", "文字"), ("颜色", "顏色"), ("线宽", "線寬"),
    ("字号", "字號"), ("边框", "邊框"), ("阴影", "陰影"), ("圆角", "圓角"),
    ("虚线", "虛線"), ("双线", "雙線"), ("单线", "單線"), ("立体", "立體"),
    ("浮雕", "浮雕"), ("渐隐", "漸隱"), ("拍立得", "拍立得"), ("手撕纸", "手撕紙"),
    ("撕边", "撕邊"), ("浓度", "濃度"), ("透明度", "透明度"), ("纸张", "紙張"),
    ("不透明", "不透明"), ("粗细", "粗細"), ("描边", "描邊"), ("平铺", "平鋪"),
    ("整张", "整張"), ("旋转", "旋轉"), ("边距", "邊距"), ("间距", "間距"),
    ("字体", "字體"), ("粗体", "粗體"), ("斜体", "斜體"), ("图片", "圖片"),
    ("浏览", "瀏覽"), ("清除", "清除"), ("选择", "選擇"), ("显示器", "顯示器"),
    ("全屏", "全螢幕"), ("区域", "區域"), ("截图", "截圖"), ("编辑器", "編輯器"),
    ("标签", "標籤"), ("工具", "工具"), ("自动", "自動"), ("手动", "手動"),
    ("拖拽", "拖曳"), ("按键", "按鍵"), ("翻页", "翻頁"), ("拼接", "拼接"),
    ("抓帧", "擷取畫面"), ("帧", "幀"), ("像素", "像素"), ("适应窗口", "符合視窗"),
    ("实际像素", "實際像素"), ("对话框", "對話框"), ("提示", "提示"),
    ("失败", "失敗"), ("成功", "成功"), ("完成", "完成"), ("停止", "停止"),
    ("退出", "結束"), ("热键", "快速鍵"), ("占用", "佔用"), ("环境变量", "環境變數"),
    ("远程桌面", "遠端桌面"), ("虚拟", "虛擬"), ("内容保护", "內容保護"),
    ("硬件加速", "硬體加速"), ("空白", "空白"), ("纯色", "純色"),
    ("独立", "獨立"), ("明细", "明細"), ("面板", "面板"), ("工具栏", "工具列"),
    ("遮挡", "遮擋"), ("尺寸", "尺寸"), ("未检测到", "未偵測到"),
]

# ---------------------------------------------------------------- 繁化：字符映射
S2T_CHARS = {
    "图": "圖", "编": "編", "辑": "輯", "设": "設", "颜": "顏", "线": "線",
    "宽": "寬", "号": "號", "关": "關", "闭": "閉", "开": "開", "启": "啟",
    "撤": "撤", "销": "銷", "复": "複", "制": "製", "贴": "貼", "应": "應",
    "选": "選", "择": "擇", "滚": "滾", "动": "動", "长": "長", "显": "顯",
    "检": "檢", "测": "測", "无": "無", "试": "試", "实": "實", "际": "際",
    "适": "適", "缩": "縮", "标": "標", "签": "籤", "页": "頁", "盖": "蓋",
    "渐": "漸", "隐": "隱", "纸": "紙", "边": "邊", "阴": "陰", "圆": "圓",
    "虚": "虛", "双": "雙", "单": "單", "体": "體", "浓": "濃", "细": "細",
    "节": "節", "预": "預", "览": "覽", "换": "換", "个": "個", "随": "隨",
    "机": "機", "种": "種", "张": "張", "铺": "鋪", "转": "轉", "间": "間",
    "浏": "瀏", "频": "頻", "视": "視", "缓": "緩", "冲": "衝", "内": "內",
    "网": "網", "络": "路", "远": "遠", "键": "鍵", "盘": "盤", "输": "輸",
    "块": "塊", "区": "區", "独": "獨", "帧": "幀", "护": "護", "拟": "擬",
    "认": "認", "为": "為", "读": "讀", "写": "寫", "败": "敗", "环": "環",
    "境": "境", "变": "變", "运": "運", "对": "對", "齐": "齊", "画": "畫",
    "组": "組", "总": "總", "结": "結", "统": "統", "过": "過", "还": "還",
    "这": "這", "么": "麼", "后": "後", "里": "裡", "将": "將", "来": "來",
    "会": "會", "赖": "賴", "录": "錄", "当": "當", "匀": "勻", "栏": "欄",
    "侧": "側", "锁": "鎖", "钮": "鈕", "绘": "繪", "递": "遞", "骤": "驟",
    "涂": "塗", "仅": "僅", "们": "們", "备": "備", "准": "準", "尝": "嘗",
    "静": "靜", "轨": "軌", "径": "徑", "释": "釋", "约": "約", "钟": "鐘",
    "导": "導", "逻": "邏", "规": "規", "则": "則", "稳": "穩", "宫": "宮",
    "洁": "潔", "参": "參", "浅": "淺", "见": "見", "于": "於", "严": "嚴",
    "强": "強", "壮": "壯", "构": "構", "妇": "婦", "岗": "崗", "屿": "嶼",
    "难": "難", "摊": "攤", "瘫": "癱", "叹": "嘆", "艰": "艱", "悬": "懸",
    "为": "為", "乐": "樂", "书": "書", "买": "買", "乱": "亂", "争": "爭",
    "亲": "親", "众": "眾", "优": "優", "传": "傳", "伤": "傷", "价": "價",
    "华": "華", "单": "單", "卖": "賣", "卫": "衛", "厂": "廠", "历": "歷",
    "压": "壓", "县": "縣", "号": "號", "听": "聽", "员": "員", "响": "響",
    "团": "團", "园": "園", "围": "圍", "国": "國", "场": "場", "坏": "壞",
    "块": "塊", "坚": "堅", "处": "處", "头": "頭", "夹": "夾", "学": "學",
    "实": "實", "宝": "寶", "对": "對", "寻": "尋", "层": "層", "属": "屬",
    "岁": "歲", "师": "師", "带": "帶", "库": "庫", "应": "應", "开": "開",
    "异": "異", "弃": "棄", "张": "張", "归": "歸", "彻": "徹", "态": "態",
    "总": "總", "户": "戶", "报": "報", "拟": "擬", "换": "換", "据": "據",
    "数": "數", "断": "斷", "无": "無", "旧": "舊", "时": "時", "显": "顯",
    "术": "術", "条": "條", "来": "來", "极": "極", "构": "構", "标": "標",
    "样": "樣", "检": "檢", "楼": "樓", "欢": "歡", "气": "氣", "汉": "漢",
    "没": "沒", "测": "測", "满": "滿", "灵": "靈", "点": "點", "爱": "愛",
    "状": "狀", "独": "獨", "环": "環", "现": "現", "画": "畫", "盘": "盤",
    "码": "碼", "确": "確", "离": "離", "种": "種", "积": "積", "称": "稱",
    "笔": "筆", "简": "簡", "签": "簽", "类": "類", "练": "練", "组": "組",
    "经": "經", "给": "給", "统": "統", "续": "續", "维": "維", "缩": "縮",
    "罗": "羅", "职": "職", "联": "聯", "脑": "腦", "节": "節", "获": "獲",
    "营": "營", "蓝": "藍", "虑": "慮", "补": "補", "装": "裝", "览": "覽",
    "觉": "覺", "触": "觸", "认": "認", "让": "讓", "训": "訓", "议": "議",
    "记": "記", "访": "訪", "证": "證", "评": "評", "识": "識", "诉": "訴",
    "词": "詞", "译": "譯", "试": "試", "询": "詢", "该": "該", "语": "語",
    "误": "誤", "说": "說", "请": "請", "读": "讀", "课": "課", "调": "調",
    "谈": "談", "谢": "謝", "贝": "貝", "负": "負", "责": "責", "货": "貨",
    "质": "質", "费": "費", "资": "資", "赛": "賽", "赞": "讚", "赢": "贏",
    "赶": "趕", "趋": "趨", "转": "轉", "轮": "輪", "软": "軟", "轻": "輕",
    "辆": "輛", "较": "較", "辅": "輔", "输": "輸", "辖": "轄", "达": "達",
    "迁": "遷", "过": "過", "运": "運", "进": "進", "远": "遠", "违": "違",
    "连": "連", "迟": "遲", "响": "響", "页": "頁", "项": "項", "顺": "順",
    "须": "須", "预": "預", "领": "領", "频": "頻", "颗": "顆", "题": "題",
    "颜": "顏", "额": "額", "风": "風", "飞": "飛", "饮": "飲", "馆": "館",
    "马": "馬", "驾": "駕", "验": "驗", "鱼": "魚", "鸟": "鳥", "鸣": "鳴",
    "齐": "齊", "龄": "齡", "龙": "龍",
    "time": "time", "点": "點", "击": "擊", "双": "雙", "单": "單",
    "删": "刪", "除": "除", "颜": "顏", "续": "續", "实": "實", "现": "現",
    "义": "義", "尽": "盡", "两": "兩", "样": "樣", "与": "與", "专": "專",
    "业": "業", "务": "務", "员": "員", "层": "層", "属": "屬", "岁": "歲",
    "帮": "幫", "带": "帶", "库": "庫", "应": "應", "态": "態", "戏": "戲",
    "户": "戶", "执": "執", "扩": "擴", "扫": "掃", "扬": "揚", "拟": "擬",
    "换": "換", "据": "據", "损": "損", "摄": "攝", "摆": "擺", "数": "數",
    "断": "斷", "旧": "舊", "时": "時", "显": "顯", "术": "術", "条": "條",
    "查": "查", "标": "標", "检": "檢", "楼": "樓", "欢": "歡", "毕": "畢",
    "气": "氣", "汉": "漢", "没": "沒", "测": "測", "涨": "漲", "温": "溫",
    "满": "滿", "灭": "滅", "灯": "燈", "灵": "靈", "热": "熱", "爱": "愛",
    "状": "狀", "独": "獨", "环": "環", "现": "現", "画": "畫", "疗": "療",
    "盘": "盤", "码": "碼", "码": "碼", "确": "確", "离": "離", "种": "種",
    "积": "積", "称": "稱", "笔": "筆", "简": "簡", "签": "簽", "类": "類",
    "线": "線", "练": "練", "组": "組", "经": "經", "给": "給", "统": "統",
    "续": "續", "维": "維", "缩": "縮", "罗": "羅", "职": "職", "联": "聯",
    "胁": "脅", "背": "背", "能": "能", "脑": "腦", "腾": "騰", "举": "舉",
    "节": "節", "获": "獲", "营": "營", "蓝": "藍", "虑": "慮", "补": "補",
    "装": "裝", "览": "覽", "觉": "覺", "触": "觸", "认": "認", "讨": "討",
    "让": "讓", "训": "訓", "议": "議", "记": "記", "设": "設", "访": "訪",
    "证": "證", "评": "評", "识": "識", "诉": "訴", "词": "詞", "译": "譯",
    "试": "試", "询": "詢", "该": "該", "语": "語", "误": "誤", "说": "說",
    "请": "請", "读": "讀", "课": "課", "调": "調", "谈": "談", "谓": "謂",
    "谢": "謝", "贝": "貝", "负": "負", "责": "責", "货": "貨", "质": "質",
    "费": "費", "资": "資", "赛": "賽", "赞": "讚", "赢": "贏", "赶": "趕",
    "趋": "趨", "转": "轉", "轮": "輪", "软": "軟", "轻": "輕", "辆": "輛",
    "较": "較", "辅": "輔", "输": "輸", "辖": "轄", "达": "達", "迁": "遷",
    "过": "過", "运": "運", "进": "進", "远": "遠", "违": "違", "连": "連",
    "迟": "遲", "响": "響", "页": "頁", "项": "項", "顺": "順", "须": "須",
    "预": "預", "领": "領", "频": "頻", "颗": "顆", "题": "題", "颜": "顏",
    "额": "額", "风": "風", "飞": "飛", "饮": "飲", "馆": "館", "马": "馬",
    "驾": "駕", "验": "驗", "骨": "骨", "高": "高", "鱼": "魚", "鸟": "鳥",
    "鸣": "鳴", "鼓": "鼓", "齐": "齊", "龄": "齡",
}


def to_traditional(text: str) -> str:
    out = text
    for simp, trad in S2T_WORDS:
        out = out.replace(simp, trad)
    out = "".join(S2T_CHARS.get(ch, ch) for ch in out)
    return out


# ---------------------------------------------------------------- 英文
# 只翻译用户看得见的文案；诊断日志（下面这些函数收到的字符串）不进词表。
DIAG_FUNCS = {"_dlog", "log", "timed", "exc", "dump_env", "_cap_log",
              "_dtimed", "print"}


def _diag_literal_ids(tree) -> set:
    """收集"诊断日志函数实参"里字符串常量对象的 id，用于排除。"""
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = getattr(f, "id", None) or getattr(f, "attr", None)
        if name not in DIAG_FUNCS:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.add(id(arg))       # 注意：存的是 **AST 结点** 的 id
    return out


EN = {
    # ---- 托盘菜单 ----
    "区域截图": "Capture Region",
    "框选一块区域截图": "Drag to capture a region",
    "全屏截图": "Capture Full Screen",
    "截取鼠标所在的那块显示器": "Capture the monitor the mouse is on",
    "选择显示器截图": "Capture a Specific Monitor",
    "滚动长截图": "Scrolling Capture",
    "滚动长截图（实验性）": "Scrolling Capture (experimental)",
    "说明：实验性功能，长图可能重复、错位或拼不上":
        "Note: experimental — the long image may repeat, misalign, or fail to "
        "stitch",
    "启用滚动长截图（不稳定）": "Enable Scrolling Capture (unstable)",
    "默认关闭：这个功能还在实验阶段，长图可能重复、错位或拼不上":
        "Off by default: this feature is still experimental — the long image "
        "may repeat, misalign, or fail to stitch",
    "滚动长截图（实验性功能）": "Scrolling Capture (experimental)",
    "滚动长截图还是实验性功能，默认关闭。":
        "Scrolling capture is still experimental and is off by default.",
    "它靠「逐帧拼接」实现：程序自己滚动画面，再把每一帧接起来。遇到下面这些情况很容易出问题：\n· 只对普通网页/文档比较可靠；Citrix、远程桌面、Java、虚拟机里的画面经常拼不上\n· 可能拼出重复内容或错位，也可能滚到一半就停住\n· 滚动期间不要动鼠标键盘，窗口也不要移动或缩放\n\n只要一张普通截图的话，用「区域截图 / 全屏截图」就够了。确实需要长图再启用。":
        "It works by stitching frame after frame: PyShot scrolls the view and "
        "joins the frames back together. It goes wrong easily when:\n"
        "· Only plain web pages/documents are fairly reliable; Citrix, Remote "
        "Desktop, Java apps and virtual machines often fail to stitch\n"
        "· The result may repeat content or misalign, or stop halfway\n"
        "· Do not touch the mouse or keyboard while it scrolls, and do not move "
        "or resize the window\n\n"
        "If you only need a normal screenshot, Capture Region / Capture Full "
        "Screen is enough. Enable this only when you really need a long image.",
    "不再提示": "Don't show again",
    "仍然启用": "Enable anyway",
    "滚动长截图未启用": "Scrolling capture is not enabled",
    "这是实验性功能，默认关闭。请在托盘菜单「滚动长截图（实验性）」里勾选「启用滚动长截图（不稳定）」后再用。":
        "This is an experimental feature and is off by default. In the tray "
        "menu, open “Scrolling Capture (experimental)” and tick “Enable "
        "Scrolling Capture (unstable)” first.",
    "屏幕取色": "Screen Color Picker",
    "单击屏幕任意位置，把色值复制到剪贴板":
        "Click anywhere to copy its color to the clipboard",
    "贴出剪贴板图片": "Pin Clipboard Image",
    "把剪贴板里的图片钉在屏幕最上层":
        "Pin the clipboard image on top of the screen",
    "打开图片编辑…": "Open Image for Editing…",
    "打开一张已有图片进行标注": "Open an existing image to annotate",
    "打开编辑器": "Show Editor",
    "把编辑器窗口恢复到前台（取消截图后找不到编辑器时点这里）":
        "Bring the editor back to the front (use this if you lost it)",
    "退出 PyShot": "Exit PyShot",
    "取消截图": "Cancel Capture",
    "收起正在显示的截图遮罩（Esc / 再按一次热键也可以）":
        "Dismiss the capture overlay (Esc or pressing the hotkey again also works)",
    "所有显示器拼成一张": "All Monitors as One Image",
    "把每块显示器按逻辑位置拼成一张长图":
        "Stitch every monitor into a single image",
    "主屏": "Primary",
    "显示器": "Monitor",
    "（未检测到显示器）": "(no monitor detected)",
    "自动滚轮": "Auto Wheel",
    "框选可滚动区域，程序自己发滚轮逐屏拼接（普通网页/文档）":
        "Select a scrollable area; PyShot sends wheel events and stitches "
        "(web pages, documents)",
    "拖拽滚动条": "Drag Scrollbar",
    "框选区域后点一下滚动条滑块，程序按住滑块匀速拖拽。\\n远程桌面 / Citrix 里最稳：步长会实测标定":
        "Select an area, then click the scrollbar thumb; PyShot drags it "
        "steadily.\\nMost reliable in Remote Desktop / Citrix "
        "(step size is calibrated automatically)",
    "按键翻页": "Page Down",
    "框选区域后程序发送 PageDown 翻页（适合没有滚动条的应用）":
        "Select an area; PyShot sends Page Down (for apps without a scrollbar)",
    "手动滚动": "Manual Scroll",
    "自己用滚轮滚动，程序只负责逐帧拼接":
        "You scroll; PyShot only stitches the frames",
    "全屏截图（当前显示器）": "Capture Full Screen (current monitor)",
    "语言": "Language",
    # ---- 通知 / 提示 ----
    "PyShot 已启动": "PyShot started",
    "PyShot 截图工具": "PyShot Screen Capture",
    "双击图标截图": "Double-click the icon to capture",
    "单击不截图：双击托盘图标开始截图（也可以按 {}）":
        "A single click does not capture — double-click the tray icon to start "
        "(or press {})",
    "单击不截图：双击托盘图标开始截图":
        "A single click does not capture — double-click the tray icon to start",
    "全屏截图完成": "Full-screen capture done",
    "滚动截图完成": "Scrolling capture done",
    "滚动截图失败": "Scrolling capture failed",
    "打开编辑器失败": "Could not open the editor",
    "全屏截图失败": "Full-screen capture failed",
    "已记录滚动条位置": "Scrollbar position recorded",
    "已复制": "Copied",
    "滚动截图": "Scrolling capture",
    "区域太小，请框选更高的可滚动区域":
        "Area too small — select a taller scrollable region",
    "剪贴板里没有图片": "No image in the clipboard",
    "PyShot 热键不可用": "PyShot hotkeys unavailable",
    "打开图片": "Open Image",
    "保存截图": "Save Capture",
    # ---- 覆盖层提示 ----
    "屏幕取色：单击复制色值    ·    Esc / 右键 取消":
        "Color picker: click to copy the value    ·    Esc / right-click to cancel",
    "拖拽选择要滚动截图的区域    ·    Esc / 右键 取消":
        "Drag to select the area to scroll-capture    ·    Esc / right-click to cancel",
    "蓝框内可直接点击滚动条【滑块】→ 自动开始滚动    ·    Esc 取消":
        "Click the scrollbar thumb inside the frame to start    ·    Esc to cancel",
    "拖拽选择截图区域    ·    Esc / 右键 取消":
        "Drag to select a region    ·    Esc / right-click to cancel",
    # ---- 工具 ----
    "选择": "Select",
    "选择并移动已有标注（Delete 删除）":
        "Select and move annotations (Delete to remove)",
    "矩形": "Rectangle",
    "拖拽画矩形，Shift 画正方形": "Drag for a rectangle, Shift for a square",
    "椭圆": "Ellipse",
    "拖拽画椭圆，Shift 画正圆": "Drag for an ellipse, Shift for a circle",
    "直线": "Line",
    "拖拽画直线，Shift 锁定水平/垂直/45°":
        "Drag for a line, Shift locks to 0/45/90°",
    "箭头": "Arrow",
    "拖拽画箭头，指引方向": "Drag for an arrow",
    "画笔": "Pen",
    "自由手绘": "Freehand drawing",
    "序号": "Step Number",
    "单击放置递增序号，做步骤指引":
        "Click to place an incrementing step number",
    "文字": "Text",
    "单击后输入文字，Enter 确认": "Click and type, Enter to confirm",
    "高亮": "Highlight",
    "拖拽涂抹半透明高亮": "Drag to paint a translucent highlight",
    "马赛克": "Mosaic",
    "拖拽对区域打码": "Drag to pixelate an area",
    "取色": "Pick Color",
    "单击吸取图上颜色作为当前标注颜色":
        "Click to pick a color from the image",
    "裁剪": "Crop",
    "拖拽选择保留区域，Enter 应用": "Drag to select what to keep, Enter to apply",
    "输入文字，Enter 确认 / Esc 取消": "Type text, Enter to confirm / Esc to cancel",
    "工具：": "Tool: ",
    "工具": "Tool",
    "已取色": "Picked",
    "，切回": ", back to ",
    # ---- 编辑器 ----
    "PyShot 编辑器": "PyShot Editor",
    "关闭此标签 (Ctrl+W)": "Close this tab (Ctrl+W)",
    "截图": "Capture",
    "截取新区域\\n会自动最小化编辑器，截完回到这里新增标签":
        "Capture a new region\\nThe editor is minimized and new captures "
        "are added as tabs",
    "颜色": "Color",
    "自定义颜色": "Custom color…",
    "线宽": "Width",
    "字号": "Size",
    "序号圆的大小\\n选中已有序号时可直接调整它的大小":
        "Step-circle size\\nAdjusts the selected step number directly",
    "撤销": "Undo",
    "撤销 (Ctrl+Z)": "Undo (Ctrl+Z)",
    "重做": "Redo",
    "重做 (Ctrl+Y)": "Redo (Ctrl+Y)",
    "应用裁剪": "Apply Crop",
    "应用裁剪框 (Enter)": "Apply the crop (Enter)",
    "复制": "Copy",
    "复制到剪贴板 (Ctrl+C)": "Copy to clipboard (Ctrl+C)",
    "贴图": "Pin",
    "把当前结果钉在屏幕最上层（Snipaste 风格）":
        "Pin the result on top of the screen (Snipaste style)",
    "水印": "Watermark",
    "边框": "Border",
    "保存": "Save",
    "保存为文件 (Ctrl+S)": "Save to a file (Ctrl+S)",
    "关闭": "Close",
    "关闭编辑器 (Esc)": "Close the editor (Esc)",
    "缩小 (Ctrl+滚轮)": "Zoom out (Ctrl+wheel)",
    "放大 (Ctrl+滚轮)": "Zoom in (Ctrl+wheel)",
    "选择颜色": "Choose a color",
    "已复制到剪贴板": "Copied to the clipboard",
    "实际像素 (1:1)": "Actual pixels (1:1)",
    "适应": "Fit",
    "缩放以适应窗口": "Scale to fit the window",
    "已保存：": "Saved: ",
    "已加边框：": "Border added: ",
    "边框宽度为 0，未做改动": "Border width is 0 — nothing changed",
    "已设为默认水印，之后每次新截图会自动添加":
        "Saved as the default watermark; it will be added automatically",
    "已设为默认水印（本次运行有效，配置写入失败）":
        "Saved as the default watermark for this session (config write failed)",
    "已设为默认边框，之后每次新截图会自动加":
        "Saved as the default border; it will be added automatically",
    "已设为默认边框（本次运行有效，配置写入失败）":
        "Saved as the default border for this session (config write failed)",
    "px\\n滚轮/Ctrl+滚轮 缩放 · 中键拖动滚动":
        "px\\nWheel / Ctrl+wheel to zoom · middle-drag to scroll",
    "滚轮/Ctrl+滚轮 缩放 · 中键或空格拖动查看":
        "Wheel / Ctrl+wheel to zoom · middle-drag or Space to pan",
    # ---- 边框对话框 ----
    "单线边框": "Solid Line",
    "纯色边框，最简洁": "A simple solid border",
    "双线边框": "Double Line",
    "外粗内细的双线": "A thick outer and thin inner line",
    "虚线边框": "Dashed",
    "虚线描边": "Dashed outline",
    "圆角边框": "Rounded",
    "图片切圆角 + 描边": "Rounded corners with an outline",
    "投影阴影": "Drop Shadow",
    "四周柔和阴影（背景透明，适合贴到文档里）":
        "Soft shadow, transparent background (great for documents)",
    "立体浮雕": "Bevel",
    "左上亮、右下暗，做出凹凸感":
        "Light from the top-left, dark bottom-right",
    "边缘渐隐": "Fade Edges",
    "图片四边渐隐到边框色": "The image fades into the border color",
    "拍立得白边": "Polaroid",
    "下方留宽白边，像拍立得": "Wide white margin at the bottom",
    "手撕纸": "Torn Paper",
    "图片贴在一张撕下来的纸上，边缘不规则 + 投影":
        "The image sits on a torn piece of paper with an irregular edge "
        "and a shadow",
    "边框 / 边缘效果": "Border / Edge Effect",
    "样式": "Style",
    "宽度": "Width",
    "圆角": "Corner radius",
    "撕边": "Tear",
    "撕口的起伏幅度；不能超过纸边宽度":
        "Depth of the torn edge; cannot exceed the paper margin",
    "换一个撕法": "Re-roll",
    "重新随机撕口（同一个种子预览和成品一致）":
        "Pick a new random tear (the preview always matches the result)",
    "阴影浓度": "Shadow",
    "投影浓度": "Shadow",
    "细节": "Details",
    "预览": "Preview",
    "应用": "Apply",
    "应用并设为默认": "Apply and Set as Default",
    "取消": "Cancel",
    "边框颜色": "Border color",
    # ---- 水印对话框 ----
    "仅供参考": "For reference only",
    "左上": "Top-left",
    "上中": "Top-center",
    "右上": "Top-right",
    "左中": "Middle-left",
    "居中": "Center",
    "右中": "Middle-right",
    "左下": "Bottom-left",
    "下中": "Bottom-center",
    "右下": "Bottom-right",
    "未启用": "Disabled",
    "平铺": "Tiled",
    "文字水印": "Text watermark",
    "要加在水印上的文字（可多行）": "Watermark text (multiple lines allowed)",
    "文字颜色": "Text color",
    "描边（深浅背景都清晰）": "Outline (readable on any background)",
    "选择水印字体": "Choose the watermark font",
    "水印颜色": "Watermark color",
    "图片水印": "Image watermark",
    "选择一张图片（建议用透明底的 PNG）":
        "Choose an image (a transparent PNG works best)",
    "浏览…": "Browse…",
    "清除": "Clear",
    "% 图宽": "% of width",
    "选择水印图片": "Choose a watermark image",
    "位置与排布": "Position & Layout",
    "平铺整张图": "Tile across the image",
    "文字「": "Text “",
    "图片": "Image",
    "字体": "Font",
    "不透明度": "Opacity",
    "粗体": "Bold",
    "斜体": "Italic",
    "大小": "Size",
    "间距": "Spacing",
    "旋转": "Rotate",
    "边距": "Margin",
    "（未选择）": "(none)",
    "（无图片）": "(no image)",
    # ---- 滚动截图 ----
    "滚动截图准备中…": "Preparing scrolling capture…",
    "截图中…": "Capturing…",
    "帧 /": "Frames ",
    "完成 (Enter)": "Done (Enter)",
    "停止 (Esc)": "Stop (Esc)",
    "请用鼠标滚轮或 Page Down 自己滚动页面，滚到底后点「完成」":
        "Scroll with the wheel or Page Down, then click Done",
    "抓帧失败：区域过小或被遮挡": "Capture failed: the region is too small or hidden",
    "抓帧失败：": "Capture failed: ",
    "首帧": "first frame",
    "没有抓到任何内容": "Nothing was captured",
    "滚轮": "Wheel",
    "按键": "Key",
    "手动": "Manual",
    "滚动": "Scroll",
    "拖拽没生效，改用滚轮重试": "Dragging had no effect — retrying with the wheel",
    "抓帧尺寸发生变化，已停止（请确保窗口未移动/缩放）":
        "The captured area changed size; stopped (keep the window fixed)",
    "画面内容变化过快，无法对齐拼接。":
        "The content changed too fast to align and stitch.",
    "（请关闭动画/视频后重试）": "(close animations/videos and retry)",
    "拖拽滚动条模式下最常见的原因：点在了滚动条的**轨道**上而不是**滑块**上——那样会一次翻整页，无法拼接。请重新框选并点中滑块本身。":
        "Most common cause: you clicked the scrollbar *track* instead of the "
        "*thumb*, which jumps a whole page. Select again and click the thumb "
        "itself.",
    "此模式下最常见的原因：点在了滚动条的**轨道**上而不是**滑块**上——那样会一次翻整页，无法拼接。请重新框选并点中滑块本身。":
        "Most common cause: you clicked the scrollbar *track* instead of the "
        "*thumb*, which jumps a whole page. Select again and click the thumb "
        "itself.",
    "选区里似乎包含多块独立滚动的区域（例如上方列表 + 下方明细面板），它们滚动量不同，拼不到一起。\\n请只框选其中一个面板（不含固定的明细面板/工具栏）后重试。\\n（排查用：设环境变量 PYSHOT_SCROLL_DEBUG=1 会把每帧存到 ~/.pyshot/scroll_debug）":
        "The selection seems to contain several independently scrolling "
        "areas, which cannot be stitched.\\nPlease select only one panel "
        "(without fixed toolbars/panels) and retry.\\n(Diagnostics: set "
        "PYSHOT_SCROLL_DEBUG=1 to dump every frame to ~/.pyshot/scroll_debug)",
    "拖拽和滚轮都没能让页面滚动。\\n可能原因：点击位置不在滚动区域，或该窗口不响应注入的输入。\\n建议改用「滚动长截图（PageDown 自动滚动）」或「手动滚动」。":
        "Neither dragging nor the wheel scrolled the page.\\nThe click may be "
        "outside the scrollable area, or the window ignores injected "
        "input.\\nTry Page Down mode or Manual scroll instead.",
    # ---- 贴图 ----
    "复制图片": "Copy image",
    "重置大小 / 透明度": "Reset size / opacity",
    "关闭 (Esc)": "Close (Esc)",
    # ---- 依赖自举 ----
    "PyShot 依赖检查：": "PyShot dependency check:",
    "PyShot 依赖安装失败": "PyShot dependency installation failed",
    "PyShot 依赖仍不可用": "PyShot dependencies are still unavailable",
    "内嵌依赖目录: 无（将使用系统环境或自动安装）":
        "Bundled deps: none (using the system environment or auto-install)",
    "内嵌依赖目录:": "Bundled deps:",
    "解释器:": "Interpreter:",
    "，正在自动安装（首次约需 1-3 分钟）…":
        ", installing automatically (1–3 minutes the first time)…",
    "请手动执行以下命令后重新运行：":
        "Please run the following command manually and start again:",
    "以下库导入失败：": "These libraries failed to import:",
    "[缺失]": "[missing]",
    # ---- 语言 ----
    "语言": "Language",
    "跟随系统": "Follow system",
    "按系统语言自动选择": "Choose automatically from the system language",
    "界面语言已切换": "Interface language changed",
    # ---- 文件对话框过滤 / 杂项 ----
    "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)":
        "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
    "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)":
        "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All files (*.*)",
    "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;BMP 图片 (*.bmp)":
        "PNG image (*.png);;JPEG image (*.jpg);;BMP image (*.bmp)",
    "拖拽滚动条自动滚动": "Drag the scrollbar to scroll automatically",
    "截图 1": "Capture 1",
    "截图 {}": "Capture {}",
    "截取新区域{}\n会自动最小化编辑器，截完回到这里新增标签":
        "Capture a new region{}\nThe editor is minimized; new captures are "
        "added as tabs",
    "（本帧 +{}）": "(+{} this frame)",
    "{}截图中… {} 帧 / {} px": "{}capturing… {} frames / {} px",
    "滑块锚点 ({}, {})，开始自动拖拽滚动。\n":
        "Thumb anchor ({}, {}) — starting to drag.\n",
    "热键（{}）都被占用，请双击托盘图标截图。\n":
        "Hotkeys ({}) are all taken — double-click the tray icon to capture.\n",
    "按 {} 框选截图，或双击托盘图标。\n":
        "Press {} to capture a region, or double-click the tray icon.\n",
    "{} 区域截图": "{} Capture Region",
    "{} 全屏截图": "{} Capture Full Screen",
    "PyShot 截图工具\n{}\n双击图标截图":
        "PyShot Screen Capture\n{}\nDouble-click the icon to capture",
    "显示器 {}": "Monitor {}",
    "水印：文字与图片可各自开关（也可同时用）\n九宫格位置或平铺、各自调不透明度、可旋转与设边距\n还能「应用并设为默认」，之后新截图自动加":
        "Watermark: text and image can be used together\n9-grid position or tiling, separate opacity, rotation and margin\nApply and set as default to add it to new captures",
    "加边框（对应 FSCapture 的「特效 → 边缘」）\n单线/双线/虚线/圆角/投影阴影/立体浮雕/边缘渐隐/拍立得白边\n边框加在图片外面，图会变大；可 Ctrl+Z 撤销":
        "Border (FSCapture's Effects -> Edge)\nSolid / double / dashed / rounded / drop shadow / bevel / fade / polaroid / torn paper\nThe border goes outside the image, so the result gets bigger; Ctrl+Z to undo",
    "序号圆的大小\n选中已有序号时可直接调整它的大小":
        "Step-circle size\nAdjusts the selected step number directly",
    "截取新区域\n会自动最小化编辑器，截完回到这里新增标签":
        "Capture a new region\nThe editor is minimized and the capture is added as a tab",
    "工具：选择": "Tool: Select",
    " px\n滚轮/Ctrl+滚轮 缩放 · 中键拖动滚动":
        "px\nWheel / Ctrl+wheel to zoom · middle-drag to scroll",
    " % 图宽": "% of width",
    "PyShot 截图工具\n双击图标截图 · 右键菜单":
        "PyShot Screen Capture\nDouble-click to capture · right-click for the menu",
    "右键托盘图标：滚动长截图 / 屏幕取色 / 贴图 / 退出。\n找不到图标时点任务栏右侧的 ∧ 展开。":
        "Right-click the tray icon: scrolling capture / color picker / pin / exit.\nIf the icon is hidden, click the ∧ arrow near the clock.",
    "可用环境变量 PYSHOT_HOTKEY 指定其他组合，例如 PYSHOT_HOTKEY=ctrl+alt+j":
        "Set PYSHOT_HOTKEY to pick another combination, e.g. PYSHOT_HOTKEY=ctrl+alt+j",
    "已拼接 ": "Stitched ",
    " px 长图": " px",
    " 工具": " Tool",
    "图片 ": "Image ",
    "滚到底会自动结束；想中途停止点控制条上的按钮。":
        "It stops automatically at the bottom; click the button on the bar to stop early.",
    "框选区域后点一下滚动条滑块，程序按住滑块匀速拖拽。\n远程桌面 / Citrix 里最稳：步长会实测标定":
        "Select an area, then click the scrollbar thumb; PyShot drags it steadily.\nMost reliable in Remote Desktop / Citrix (the step size is calibrated automatically)",
    "画面内容变化过快，无法对齐拼接。\n":
        "The content changed too fast to align and stitch.\n",
    "拖拽滚动条模式下最常见的原因：点在了滚动条的**轨道**上而不是**滑块**上——那样会一次翻整页，无法拼接。请重新框选并点中滑块本身。\n":
        "Most common cause: you clicked the scrollbar *track* instead of the *thumb*, which jumps a whole page. Select again and click the thumb itself.\n",
    "（请关闭动画/视频后重试）\n": "(close animations/videos and retry)\n",
    "选区里似乎包含多块独立滚动的区域（例如上方列表 + 下方明细面板），它们滚动量不同，拼不到一起。\n请只框选其中一个面板（不含固定的明细面板/工具栏）后重试。\n（排查用：设环境变量 PYSHOT_SCROLL_DEBUG=1 会把每帧存到 ~/.pyshot/scroll_debug）":
        "The selection seems to contain several independently scrolling areas, which cannot be stitched.\nPlease select only one panel (without fixed toolbars) and retry.\n(Diagnostics: set PYSHOT_SCROLL_DEBUG=1 to dump frames to ~/.pyshot/scroll_debug)",
    "抓到的画面是空白/纯色，无法拼接。\n目标窗口（Citrix / 远程桌面 / Java 应用）多半在用硬件加速或内容保护，GDI 抓屏拿不到内容。按顺序试：\n① Citrix Workspace：关掉「使用硬件加速进行图形处理」；服务端策略把「视频编解码压缩」设为不使用\n② Java 应用：启动参数加 -Dsun.java2d.d3d=false -Dsun.java2d.opengl=false -Dsun.java2d.noddraw=true（强制走 GDI 绘制）\n③ 托盘菜单用「滚动长截图（手动滚动）」：你自己滚，程序只拼帧\n④ 把窗口最大化或调整大小后重试":
        "The captured frames are blank/solid and cannot be stitched.\n"
        "The target window (Citrix / Remote Desktop / a Java app) is probably using "
        "hardware acceleration or content protection, which blocks GDI screen capture. "
        "Try, in order:\n"
        "(1) Citrix Workspace: turn off 'Use hardware acceleration for graphics'; on the "
        "server set video-codec compression to 'Do not use video codec'\n"
        "(2) Java apps: add -Dsun.java2d.d3d=false -Dsun.java2d.opengl=false "
        "-Dsun.java2d.noddraw=true to force GDI rendering\n"
        "(3) Tray menu -> Manual scrolling capture: you scroll, PyShot just stitches\n"
        "(4) Maximize or resize the window and retry",
    "拖拽和滚轮都没能让页面滚动。\n可能原因：点击位置不在滚动区域，或该窗口不响应注入的输入。\n建议改用「滚动长截图（PageDown 自动滚动）」或「手动滚动」。":
        "Neither dragging nor the wheel scrolled the page.\nThe click may be outside the scrollable area, or the window ignores injected input.\nTry Page Down mode or Manual scroll instead.",
    # ---- 编辑器菜单栏 / 空状态 ----
    "文件": "File", "编辑": "Edit", "视图": "View", "特效": "Effects",
    "选项": "Options", "帮助": "Help",
    "打开图片…": "Open Image…", "打开剪贴板图片": "Open Clipboard Image",
    "关闭当前标签": "Close Tab", "退出": "Exit",
    "复制到剪贴板": "Copy to Clipboard", "贴图到屏幕": "Pin to Screen",
    "打开剪贴板图片": "Open Clipboard Image",
    "把剪贴板里的图片作为**新标签**打开":
        "Open the clipboard image as a **new tab**",
    "粘贴到当前图（浮动）": "Paste onto This Image (floating)",
    "把剪贴板里的截图贴到当前图上：拖动摆位置、Ctrl+滚轮缩放，Enter 固定、Esc 取消":
        "Paste the clipboard screenshot onto this image: drag to place it, "
        "Ctrl+wheel to scale, Enter to apply, Esc to discard",
    "固定粘贴的图": "Apply Pasted Image",
    "把正在摆放的粘贴图合成进当前图（Enter）":
        "Merge the pasted image into this one (Enter)",
    "取消粘贴": "Discard Paste",
    "丢掉正在摆放的粘贴图（Esc）": "Throw away the pasted image (Esc)",
    "已粘贴到当前图：拖动摆位置 · Ctrl+滚轮缩放 · Enter 固定 · Esc 取消":
        "Pasted onto this image: drag to place · Ctrl+wheel to scale · "
        "Enter to apply · Esc to discard",
    "已粘贴到当前图：拖动摆位置 · 拖手柄缩放、拖上方圆点旋转 · Enter 固定 · Esc 取消":
        "Pasted onto this image: drag to place · drag the handles to scale, "
        "the dot above to rotate · Enter to apply · Esc to discard",
    "已固定粘贴的图（Ctrl+Z 可撤销）":
        "Pasted image applied (Ctrl+Z to undo)",
    "已取消粘贴": "Paste discarded",
    "置于顶层": "Bring to Front",
    "置于底层": "Send to Back",
    "上移一层": "Bring Forward",
    "下移一层": "Send Backward",
    "再制一个": "Duplicate",
    "复制选中的图形/文字，向右下错开一点":
        "Copy the selected shape/text, offset slightly down-right",
    "旋转 15°": "Rotate 15°",
    "把选中图形转 15°（拖它上面的圆形手柄可以任意角度）":
        "Rotate the selection by 15° (drag the round handle above it for any angle)",
    "摆正（0°）": "Straighten (0°)",
    "先选一个图形（用「选择」工具点一下）":
        "Select a shape first (click it with the Select tool)",
    "已再制一个（Ctrl+Z 可撤销）": "Duplicated (Ctrl+Z to undo)",
    "旋转 {:.0f}°（Ctrl+Z 可撤销）": "Rotated {:.0f}° (Ctrl+Z to undo)",
    "删除": "Delete",
    "粘贴图外观": "Pasted Image Style",
    "加阴影": "Add shadow",
    "加白色描边": "Add white outline",
    "直角": "Square corners",
    "小圆角": "Slightly rounded",
    "大圆角": "Very rounded",
    "修改文字…": "Edit Text…",
    "改选中文字的内容（也可以直接双击文字）":
        "Change the selected text (or just double-click the text)",
    "字体…": "Font…",
    "选字体/字号/粗体：选中文字就改它，否则改之后新写的文字":
        "Pick family/size/bold: applies to the selected text, otherwise to text you write next",
    "选择字体": "Choose Font",
    "先选一段文字（用「选择」工具点一下，或直接双击文字）":
        "Select a text object first (click it with Select, or double-click the text)",
    "已改字体（Ctrl+Z 可撤销）": "Font changed (Ctrl+Z to undo)",
    "之后的文字用这个字体": "New text will use this font",
    "水平翻转": "Flip Horizontally",
    "垂直翻转": "Flip Vertically",
    "左右镜像（标注也跟着翻，可 Ctrl+Z 撤销）":
        "Mirror left-right (annotations flip too; Ctrl+Z to undo)",
    "上下镜像（标注也跟着翻，可 Ctrl+Z 撤销）":
        "Mirror top-bottom (annotations flip too; Ctrl+Z to undo)",
    "顺时针 90°": "Rotate 90° CW",
    "逆时针 90°": "Rotate 90° CCW",
    "调整尺寸…": "Resize…",
    "按像素重设整张图（含标注），可 Ctrl+Z 撤销":
        "Resize the whole image in pixels (annotations scale with it); Ctrl+Z to undo",
    "已水平翻转（Ctrl+Z 可撤销）": "Flipped horizontally (Ctrl+Z to undo)",
    "已垂直翻转（Ctrl+Z 可撤销）": "Flipped vertically (Ctrl+Z to undo)",
    "已旋转 90°（Ctrl+Z 可撤销）": "Rotated 90° (Ctrl+Z to undo)",
    "已逆时针旋转 90°（Ctrl+Z 可撤销）":
        "Rotated 90° counter-clockwise (Ctrl+Z to undo)",
    "调整尺寸": "Resize",
    "宽度（像素，当前 {}）": "Width in pixels (currently {})",
    "高度（像素，当前 {}）": "Height in pixels (currently {})",
    "已调整为 {} × {}（Ctrl+Z 可撤销）":
        "Resized to {} × {} (Ctrl+Z to undo)",
    "放大": "Zoom In", "缩小": "Zoom Out", "适应窗口": "Fit to Window",
    "显示左侧工具条": "Show Tool Rail",
    "工具条可以滚动；嫌占地方就整条收起（工具快捷键依然可用）":
        "The tool rail scrolls; turn it off entirely if you need the space "
        "(tool shortcuts still work)",
    "已收起左侧工具条（工具快捷键仍可用；想恢复：视图菜单）":
        "Tool rail hidden (shortcuts still work; bring it back from the View menu)",
    "已显示左侧工具条": "Tool rail shown",
    "水印…": "Watermark…", "边框…": "Border…",
    "编辑默认水印…": "Edit Default Watermark…",
    "编辑默认边框…": "Edit Default Border…",
    "关于 PyShot": "About PyShot",
    "还没有图片": "No image yet",
    "从「文件」菜单打开图片，或直接截图 / 从剪贴板粘贴":
        "Open an image from the File menu, capture the screen, or paste from the clipboard",
    "直接打开编辑器窗口（空白也能用，从它的「文件」菜单打开图片）":
        "Open the editor window directly (works even when empty; use its File menu to open an image)",
    "显示编辑器": "Show Editor",
    "PyShot {}\n仿 FastStone Capture 的截图与标注工具\n\n托盘右键：区域截图 / 全屏截图 / 滚动长截图 / 屏幕取色 / 贴图\n编辑器：多标签标注 · 水印 · 加边框（含手撕纸）· 三语界面":
        "PyShot {}\nA FastStone Capture style screenshot and annotation tool\n\n"
        "Tray menu: region / full-screen capture, scrolling capture, color picker, pin\n"
        "Editor: multi-tab annotation · watermark · borders (incl. torn paper) · 3 languages",
    "PyShot {} — {}\n仿 FastStone Capture 的截图与标注工具\n\n托盘右键：区域截图 / 全屏截图 / 滚动长截图 / 屏幕取色 / 贴图\n编辑器：多标签标注 · 粘贴拼图 · 水印 · 加边框（含手撕纸）· 三语界面\n\n作者：{} <{}>":
        "PyShot {} — {}\nA FastStone Capture style screenshot and annotation tool\n\n"
        "Tray menu: region / full-screen capture, scrolling capture, color picker, pin\n"
        "Editor: multi-tab annotation · paste & compose · watermark · borders (incl. torn paper) · 3 languages\n\n"
        "Author: {} <{}>",
    "浮动粘贴 + 编辑增强 + 启动提速":
        "floating paste + editing power-ups + faster startup",
    "工具条可滚动可收起": "scrollable / collapsible tool rail",
    "三语帮助系统": "trilingual help system",
    "截图后自动进剪贴板": "captures go straight to the clipboard",
    "标注作者信息": "author info in About",
    "抓手": "Hand",
    "拖拽移动画面（图放大后看不同位置）；任何工具下按住中键或空格也能拖":
        "Drag to move the view (look around once zoomed in); middle-drag or hold Space works with any tool",
    "px\n滚轮/Ctrl+滚轮 缩放 · 中键或空格拖动查看":
        "px\nWheel / Ctrl+wheel to zoom · middle-drag or Space to pan",
    "启动时恢复上次的截图": "Restore last captures on startup",
    "截图时不最小化编辑器": "Keep the editor visible while capturing",
    "截图后自动复制到剪贴板": "Copy to clipboard after capturing",
    "截图完成后立刻把这张图放进剪贴板（标注后的版本仍可用 Ctrl+C 复制）":
        "Put the captured image on the clipboard right away (annotate it and use "
        "Ctrl+C later if you want the annotated version instead)",
    "已开启：截图完成后自动复制到剪贴板":
        "On: captures go to the clipboard automatically",
    "已关闭：截图后不再自动复制（需要时按 Ctrl+C）":
        "Off: captures no longer go to the clipboard (press Ctrl+C when you need it)",
    "已复制到剪贴板（选项里可关）":
        "Copied to the clipboard (can be turned off in Options)",
    "打开后截图时编辑器留在原地，方便截编辑器自己；平时关着（截图时自动让位，免得被拍进图里）":
        "When on, the editor stays where it is while you capture — handy for "
        "capturing the editor itself. Keep it off normally, so the editor gets "
        "out of the way instead of appearing in your screenshot",
    "已开启：截图时编辑器留在原地（方便截编辑器自己）":
        "On: the editor stays visible while capturing (good for capturing the editor)",
    "已关闭：截图时编辑器自动最小化让位":
        "Off: the editor minimizes itself while capturing",
    "重启后自动把上次编辑的截图放回来（存在缓存里，不需要你保存）":
        "Bring back your last captures automatically after a restart (kept in a cache — no need to save)",
    "清除上次的截图缓存": "Clear last-capture cache",
    "已清除上次的截图缓存": "Last-capture cache cleared",
    "PyShot 已启动（恢复了 {} 张上次的截图）":
        "PyShot started (restored {} capture(s))",
    "当前颜色": "Current color",
    "更多颜色…（系统拾色盘风格）": "More colors… (system palette)",
    "自定义…": "Custom…",
    "基本颜色": "Basic colors",
    "自定义颜色": "Custom colors",
    "点这里定义一个自定义颜色…": "Click to define a custom color…",
    "打开系统拾色器": "Open the system color picker",
    # ---- 帮助（内容见 help_text.py / helpwin.py）----
    "使用帮助": "Help",
    "打开帮助窗口（三语，可按关键字搜索）":
        "Open the help window (in 3 languages, searchable)",
    "打开帮助窗口（F1；三语，可按关键字搜索）":
        "Open the help window (F1; 3 languages, searchable)",
    "区域截图（全局热键）": "Capture Region (global hotkey)",
    "全屏截图（全局热键）": "Capture Full Screen (global hotkey)",
    "PyShot 使用帮助": "PyShot Help",
    "截图 + 标注工具，专为做操作指引/步骤说明优化。":
        "Screenshot and annotation tool, built for step-by-step guides.",
    "搜索帮助内容…（例如：拼图、滚动、快捷键）":
        "Search the help… (e.g. compose, scrolling, shortcuts)",
    "快捷键一览": "Shortcuts",
    "下面这些是当前生效的快捷键（菜单里改不了的就写在这里）。":
        "These are the shortcuts that are active right now.",
    "快速开始": "Quick Start",
    "截图方式": "Capture Modes",
    "编辑器工具": "Editor Tools",
    "把多张截图拼到一张图上": "Compose Several Screenshots into One",
    "编辑效率": "Editing Power-Ups",
    "水印与边框": "Watermark & Border",
    "保存、复制与贴图": "Save, Copy, Pin",
    "疑难解答": "Troubleshooting",
    "关于与依赖": "About & Dependencies",
    "按 {hotkey} 框选截图，或双击托盘图标。":
        "Press {hotkey} to capture a region, or double-click the tray icon.",
    "- 截完自动进编辑器：左边选工具，图上直接标。":
        "- The capture opens in the editor: pick a tool on the left and annotate right on the image.",
    "- 编辑器里 Ctrl+S 保存、Ctrl+C 复制、Ctrl+Z 撤销。":
        "- In the editor: Ctrl+S saves, Ctrl+C copies, Ctrl+Z undoes.",
    "- 托盘图标找不到时，点任务栏右侧的 ∧ 展开。":
        "- Can't find the tray icon? Click the ∧ arrow near the clock to expand it.",
    "- 区域截图：拖拽框选，Esc 或右键取消。":
        "- Region capture: drag to select; Esc or right-click cancels.",
    "- 全屏截图 {fullhotkey}：截鼠标所在的那块显示器。":
        "- Full screen {fullhotkey}: captures the monitor the mouse is on.",
    "- 选择显示器截图：多屏时指定某一块，或「所有显示器拼成一张」。":
        "- Capture a specific monitor: pick one, or stitch every monitor into a single image.",
    "- 滚动长截图（实验性，默认关闭）：先在托盘菜单里勾选启用；框选可滚动区域后程序自己滚轮逐屏拼接。":
        "- Scrolling capture (experimental, off by default): enable it in the tray menu first; "
        "select a scrollable area and PyShot scrolls and stitches frame by frame.",
    "- 手动滚动：你自己滚，程序只负责拼帧，兼容性最好。":
        "- Manual scroll: you scroll, PyShot only stitches — the most compatible mode.",
    "- 选择：点选/拖动已有标注；方向键微调 1px（按住 Shift 是 10px）；Delete 删除。":
        "- Select: click or drag existing annotations; arrow keys nudge by 1px (Shift: 10px); Delete removes.",
    "- 矩形 / 椭圆 / 直线 / 箭头 / 画笔：拖拽绘制；按住 Shift 可画正方形、正圆或锁定方向。":
        "- Rectangle / ellipse / line / arrow / pen: drag to draw; hold Shift for a square, a circle, or a locked direction.",
    "- 序号：单击放置递增序号，做步骤指引。":
        "- Step number: click to place an incrementing number for step-by-step guides.",
    "- 文字：单击后输入，Enter 确认；双击已有文字可以直接改内容。":
        "- Text: click and type, Enter to confirm; double-click existing text to edit it.",
    "- 高亮 / 马赛克：拖拽涂抹。":
        "- Highlight / mosaic: drag to paint.",
    "- 取色：单击吸取图上颜色（取完自动切回上一个工具）。":
        "- Pick color: click to pick a color from the image (it switches back to your previous tool).",
    "- 裁剪：拖拽选出要保留的区域，Enter 应用。":
        "- Crop: drag the area to keep, Enter applies it.",
    "- 抓手：放大后拖动查看；任何工具下按住空格或鼠标中键也能拖。":
        "- Hand: drag to pan once zoomed in; middle-drag or hold Space works with any tool.",
    "Ctrl+V 会把剪贴板里的截图贴到**当前这张图**上（想新开标签用 Ctrl+Shift+V）。":
        "Ctrl+V pastes the clipboard screenshot onto **this** image (Ctrl+Shift+V opens it as a new tab).",
    "- 贴上去是浮动层：拖动摆位置、拖 8 个手柄改大小（Shift 等比）、拖上方圆点旋转。":
        "- It arrives as a floating layer: drag to place, drag the 8 handles to resize (Shift keeps the ratio), drag the dot above to rotate.",
    "- 外观可调：编辑菜单 →「粘贴图外观」可加阴影、白色描边、圆角。":
        "- Style it from Edit → Pasted Image Style: shadow, white outline, rounded corners.",
    "- Enter 或双击固定进图（Ctrl+Z 撤销），Esc 丢弃；连按两次 Ctrl+V 会先把上一张固定。":
        "- Enter or double-click applies it (Ctrl+Z undoes), Esc discards; pasting twice applies the first one before starting the next.",
    "- 固定后它就是底图的一部分，可以继续在上面标注。":
        "- Once applied it is part of the image, and you can keep annotating on top.",
    "- 图层顺序：右键菜单或编辑菜单里的置于顶层 / 底层、上移 / 下移一层。":
        "- Layer order: right-click menu or Edit → Bring to Front / Send to Back / Bring Forward / Send Backward.",
    "- Ctrl+D 再制一个；旋转 15° / 摆正也在编辑菜单。":
        "- Ctrl+D duplicates; Rotate 15° / Straighten are in the Edit menu too.",
    "- 画布变换（特效菜单）：水平/垂直翻转、顺/逆时针 90°、调整尺寸 —— 标注会跟着一起变换，之后还能继续编辑。":
        "- Canvas transforms (Effects menu): flip horizontally/vertically, rotate 90° either way, resize — annotations transform with it and stay editable.",
    "- 撤销 / 重做：Ctrl+Z / Ctrl+Y（Ctrl+Shift+Z 也可以）。":
        "- Undo / redo: Ctrl+Z / Ctrl+Y (Ctrl+Shift+Z also works).",
    "- 特效 → 水印：文字或图片、九宫格位置或平铺、各自调透明度、可旋转与设边距。":
        "- Effects → Watermark: text or image, 9-grid position or tiling, separate opacity, rotation and margin.",
    "- 特效 → 边框：单线 / 双线 / 虚线 / 圆角 / 投影 / 立体浮雕 / 边缘渐隐 / 拍立得 / 手撕纸。":
        "- Effects → Border: solid / double / dashed / rounded / drop shadow / bevel / fade edges / polaroid / torn paper.",
    "- 两个对话框里都能「应用并设为默认」，之后每次新截图自动加上。":
        "- Both dialogs offer Apply and Set as Default, so new captures get it automatically.",
    "- Ctrl+S 保存成 PNG / JPG / BMP；Ctrl+C 复制到剪贴板。":
        "- Ctrl+S saves as PNG / JPG / BMP; Ctrl+C copies to the clipboard.",
    "- 截图完成后会**自动复制到剪贴板**（默认开，选项里可关），截完直接粘到聊天/文档里。":
        "- Every capture is **copied to the clipboard automatically** (on by default; "
        "turn it off in Options), so you can paste it straight away.",
    "- 编辑 → 贴图到屏幕：把结果钉在屏幕最上层，方便照着做。":
        "- Edit → Pin to Screen: keeps the result on top of everything while you follow it.",
    "- 关掉编辑器也不怕：默认会记住上次的截图（选项 → 启动时恢复上次的截图）。":
        "- Closing the editor is safe: your last captures are remembered (Options → Restore last captures on startup).",
    "- 多标签：一次会话里的多张截图各占一个标签，Ctrl+W 关掉当前标签。":
        "- Multiple tabs: each capture of a session gets a tab; Ctrl+W closes the current one.",
    "滚动长截图拼不上：Citrix、远程桌面、Java、虚拟机里的画面经常拼不出来 —— 关掉目标软件的硬件加速，或改用「手动滚动」；另外选区只框住会滚的那块（别带上工具栏/侧栏）成功率更高。":
        "Scrolling capture fails to stitch: Citrix, Remote Desktop, Java apps and virtual machines often "
        "cannot be stitched — turn off hardware acceleration in the target app, or switch to Manual scroll; "
        "selecting only the part that actually scrolls (without toolbars/sidebars) works much better.",
    "截出来是黑的 / 花的：目标窗口在用硬件加速或内容保护，常见于 Citrix、视频播放器。可尝试改用手动滚动，或把窗口调整大小后重试。":
        "The capture comes out black or garbled: the target window uses hardware acceleration or content "
        "protection (common with Citrix and video players). Try Manual scroll, or resize the window and retry.",
    "按快捷键没反应：先确认托盘图标还在（可能在任务栏右侧的 ∧ 里）；热键被别的软件占用时程序会自动换一个，启动气泡里会写当前用的是哪个。":
        "The hotkey does nothing: first check the tray icon is still there (it may be behind the ∧ arrow). "
        "If another app owns the hotkey, PyShot automatically picks a different one — the startup balloon says which.",
    "启动有点慢：首次启动要付一次 Qt 的初始化开销（本机实测几秒），之后就好；想看得更细，设环境变量 PYSHOT_DEBUG=1，日志里每一步都有耗时。":
        "Startup feels slow: the first launch pays a one-time Qt initialization cost (a few seconds on the "
        "test machine) and is fine afterwards. Set PYSHOT_DEBUG=1 for a log with per-step timings.",
    "想截编辑器自己：选项 → 截图时不最小化编辑器。":
        "Want to capture the editor itself? Options → Keep the editor visible while capturing.",
    "- 版本号在 version.py；托盘或编辑器「帮助 → 关于」也能看到。":
        "- The version lives in version.py; Help → About shows it too.",
    "- 作者：{author} <{email}>。":
        "- Author: {author} <{email}>.",
    "- 检查依赖：python PyShot.py --check-deps（单文件版缺库会自动 pip 安装）。":
        "- Check dependencies: python PyShot.py --check-deps (the single-file build auto-installs what is missing).",
    "- 设置与缓存都在 ~/.pyshot/（settings.json、session/、debug.log）。":
        "- Settings and cache live in ~/.pyshot/ (settings.json, session/, debug.log).",
    "- 界面语言：选项 → 语言，简体中文 / 繁體中文 / English。":
        "- Language: Options → Language — Simplified Chinese / Traditional Chinese / English.",
    "更多颜色…（基本颜色 + 自定义颜色）":
        "More colors… (basic + custom)",
}


def collect_strings():
    """从源码里收集用户可见的简体文案。

    诊断日志的文案（_dlog / _cap_log / log / print 的实参）**不算界面文案**：
    它们是给开发者排查用的，英文界面下保持中文反而更好搜日志。
    不排除的话，"英文覆盖率"这条质量门槛会被几十条日志文案稀释掉。
    """
    out = []
    for name in FILES:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        skip = _diag_literal_ids(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                body = getattr(node, "body", None)
                if body and isinstance(body[0], ast.Expr) \
                        and isinstance(body[0].value, ast.Constant) \
                        and isinstance(body[0].value.value, str):
                    skip.add(id(body[0].value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in skip:
                s = node.value
                if len(s.strip()) >= 2 and CJK.search(s) and s not in out:
                    out.append(s)
    return out


def main():
    strings = collect_strings()
    missing_en, rows = [], []
    for s in strings:
        zh_tw = to_traditional(s)
        en = EN.get(s)
        if en is None:
            missing_en.append(s)
        rows.append((s, zh_tw, en or ""))

    lines = ['# -*- coding: utf-8 -*-',
             '"""i18n 词表（由 _gen_i18n.py 生成，请勿手改本文件）。',
             '',
             '键 = 简体原文；值 = (繁體, English)。tr() 查不到时回落原文。',
             '"""',
             '',
             '# key: 简体原文 -> (繁體, English)',
             'TABLE = {']
    for s, zh_tw, en in rows:
        key = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        tw = zh_tw.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        ev = en.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        lines.append(f'    "{key}": ("{tw}", "{ev}"),')
    lines.append('}')
    lines.append('')
    with open(os.path.join(HERE, "i18n_data.py"), "w", encoding="utf-8",
              newline="\n") as f:
        f.write("\n".join(lines))

    print(f"共收集 {len(strings)} 条，已生成 i18n_data.py")
    print(f"  英文已覆盖 {len(strings) - len(missing_en)} 条，"
          f"缺 {len(missing_en)} 条")
    if missing_en:
        print("  缺英文的条目（英文界面下会显示中文原文）：")
        for s in missing_en[:40]:
            print("   -", s.replace("\n", "\\n")[:60])


if __name__ == "__main__":
    main()
