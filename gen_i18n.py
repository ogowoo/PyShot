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

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["main.py", "snipper.py", "editor.py", "border.py", "watermark.py",
         "scroller.py", "pinboard.py", "bootstrap.py"]
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
EN = {
    # ---- 托盘菜单 ----
    "区域截图": "Capture Region",
    "框选一块区域截图": "Drag to capture a region",
    "全屏截图": "Capture Full Screen",
    "截取鼠标所在的那块显示器": "Capture the monitor the mouse is on",
    "选择显示器截图": "Capture a Specific Monitor",
    "滚动长截图": "Scrolling Capture",
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
    "抓到的画面是空白/纯色，无法拼接。\n目标窗口（如 Citrix 虚拟桌面里的应用）可能启用了硬件加速或内容保护，系统抓屏 API 拿不到内容。\n可尝试：① 在 Citrix/远程桌面里关闭硬件加速；② 用托盘菜单的「滚动长截图（手动滚动）」；③ 把该窗口最大化或调整大小后重试。":
        "The captured frames are blank/solid, so they cannot be stitched.\nThe target window (e.g. an app inside Citrix) may use hardware acceleration or content protection that blocks screen capture.\nTry: (1) disable hardware acceleration in Citrix, (2) use Manual scrolling capture from the tray menu, (3) maximize or resize the window and retry.",
    "拖拽和滚轮都没能让页面滚动。\n可能原因：点击位置不在滚动区域，或该窗口不响应注入的输入。\n建议改用「滚动长截图（PageDown 自动滚动）」或「手动滚动」。":
        "Neither dragging nor the wheel scrolled the page.\nThe click may be outside the scrollable area, or the window ignores injected input.\nTry Page Down mode or Manual scroll instead.",
    # ---- 编辑器菜单栏 / 空状态 ----
    "文件": "File", "编辑": "Edit", "视图": "View", "特效": "Effects",
    "选项": "Options", "帮助": "Help",
    "打开图片…": "Open Image…", "打开剪贴板图片": "Open Clipboard Image",
    "关闭当前标签": "Close Tab", "退出": "Exit",
    "复制到剪贴板": "Copy to Clipboard", "贴图到屏幕": "Pin to Screen",
    "放大": "Zoom In", "缩小": "Zoom Out", "适应窗口": "Fit to Window",
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
    "抓手": "Hand",
    "拖拽移动画面（图放大后看不同位置）；任何工具下按住中键或空格也能拖":
        "Drag to move the view (look around once zoomed in); middle-drag or hold Space works with any tool",
    "px\n滚轮/Ctrl+滚轮 缩放 · 中键或空格拖动查看":
        "px\nWheel / Ctrl+wheel to zoom · middle-drag or Space to pan",
    "启动时恢复上次的截图": "Restore last captures on startup",
    "重启后自动把上次编辑的截图放回来（存在缓存里，不需要你保存）":
        "Bring back your last captures automatically after a restart (kept in a cache — no need to save)",
    "清除上次的截图缓存": "Clear last-capture cache",
    "已清除上次的截图缓存": "Last-capture cache cleared",
    "PyShot 已启动（恢复了 {} 张上次的截图）":
        "PyShot started (restored {} capture(s))",
}


def collect_strings():
    """从源码里收集用户可见的简体文案。"""
    out = []
    for name in FILES:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        skip = set()
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
