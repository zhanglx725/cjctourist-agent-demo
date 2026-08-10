from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(r"D:\nuo\agent项目\cjctourist_agent-main\cjctourist_agent-main")
FFMPEG = ROOT / "tools" / "_vendor_video" / "imageio_ffmpeg" / "binaries" / "ffmpeg-win-x86_64-v7.1.exe"
SEGMENT_DIR = ROOT / "output" / "video" / "segments"
OUT_DIR = ROOT / "output" / "video" / "review"
WORK_DIR = ROOT / "tmp" / "video_ab_review"

A_SOURCE = Path(r"D:\34267\Videos\屏幕录制\屏幕录制 2026-08-10 194107最终开头.mp4")
B_SOURCE = SEGMENT_DIR / "02_古风书生完整主线_无字幕版.mp4"

BASE = OUT_DIR / "AB_项目开场与古风书生主线_无字幕审阅版.mp4"
CAPTIONED = OUT_DIR / "AB_项目开场与古风书生主线_字幕审阅版.mp4"
ASS_FILE = OUT_DIR / "AB_项目开场与古风书生主线_审阅版.ass"
FILTER_FILE = WORK_DIR / "ab_filter.txt"

A_TITLE_DURATION = 6.0
A_SOURCE_END = 25.3
A_SOURCE_SPEED = 1.1
B_START = 19.0
B_END = 139.0
A_DURATION = A_TITLE_DURATION + A_SOURCE_END / A_SOURCE_SPEED
FINAL_DURATION = A_DURATION + (B_END - B_START)


def run(command: list[str]) -> None:
    print("RUN:", " ".join(command))
    subprocess.run(command, check=True)


def ass_time(seconds: float) -> str:
    total = int(round(seconds * 100))
    hours, total = divmod(total, 360_000)
    minutes, total = divmod(total, 6_000)
    secs, cs = divmod(total, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def make_ass() -> None:
    # B timings are shifted by A_DURATION - B_START = 10 seconds.
    captions = [
        (6.0, 13.0, "祠语智游已建立18种角色化讲解策略。\\N每种策略都受到统一事实与安全边界约束。"),
        (13.0, 21.0, "本次选取古风书生、儿童友好与中性清晰。\\N三种代表风格进行展示。"),
        (21.0, 29.0, "游客设置可用时间、兴趣和讲解节奏。\\N系统据此生成个性化文化导览路线。"),
        (29.0, 35.05, "路线生成后，游客确认前往第一站。\\N系统随后进入点位状态。"),
        (35.05, 49.72, "游客确认到达后，TourState 更新当前位置。\\N点位讲解由审核事实和当前路线共同约束。"),
        (49.72, 78.10, "古风书生改变的是表达方式，不改变文化事实。\\N点位、对象与下一步仍由确定性状态推进。"),
        (78.10, 87.73, "游客询问灰塑特点，系统结合当前点位。\\N回答材料、制作工艺与馆内关联实例。"),
        (87.73, 101.06, "“再讲详细一点”继承当前对象和证据范围。\\N无需重复说明问题背景。"),
        (101.06, 109.53, "闭馆时间属于动态服务信息。\\N系统给出已知时段，并提示以当日官方公告为准。"),
        (109.53, 123.60, "面对学术研究问题，系统提供可核验的研究视角。\\N同时说明个案材料的适用边界。"),
        (123.60, 137.17, "完成三个正式点位后，系统基于真实记录生成游览总结。\\N并统计本轮提问与讲解覆盖。"),
        (137.17, 149.0, "游客确认需要后，系统返回审核范围内的周边候选。\\N营业、价格与交通仍以商家和地图最新信息为准。"),
    ]
    header = """[Script Info]
Title: 祠语智游 A+B 连续审阅版
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,36,&H00FFFFFF,&H00FFFFFF,&H003A261F,&H00000000,-1,0,0,0,100,100,1,0,1,2,0,2,120,120,19,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = "".join(
        f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}\n"
        for start, end, text in captions
    )
    ASS_FILE.write_text(header + body, encoding="utf-8-sig")


def make_base() -> None:
    font_bold = r"C\:/Windows/Fonts/msyhbd.ttc"
    font_regular = r"C\:/Windows/Fonts/msyh.ttc"
    common_label = (
        "drawbox=x=0:y=0:w=28:h=968:color=0x743329:t=fill,"
        "drawbox=x=28:y=0:w=232:h=128:color=0xF6F1E7:t=fill,"
        f"drawtext=fontfile='{font_bold}':text='祠语智游':"
        "fontcolor=0x743329:fontsize=32:x=48:y=28,"
        f"drawtext=fontfile='{font_regular}':text='古风书生主线':"
        "fontcolor=0xA65A45:fontsize=22:x=48:y=76"
    )
    title = (
        "color=c=0x743329:s=1920x1080:d=6:r=30,"
        f"drawtext=fontfile='{font_bold}':text='祠语智游':"
        "fontcolor=white:fontsize=84:x=(w-text_w)/2:y=260,"
        f"drawtext=fontfile='{font_bold}':text='多角色沉浸式非遗智能导游':"
        "fontcolor=0xF5D8AE:fontsize=44:x=(w-text_w)/2:y=400,"
        f"drawtext=fontfile='{font_regular}':text='18种角色化讲解策略':"
        "fontcolor=white:fontsize=31:x=(w-text_w)/2:y=510,"
        f"drawtext=fontfile='{font_regular}':text='本次展示  ·  古风书生  ·  儿童友好  ·  中性清晰':"
        "fontcolor=0xF5D8AE:fontsize=28:x=(w-text_w)/2:y=570[title]"
    )
    filter_text = ";\n".join(
        [
            title,
            (
                f"[0:v]trim=start=0:end={A_SOURCE_END},"
                f"setpts=(PTS-STARTPTS)/{A_SOURCE_SPEED},fps=30,"
                "scale=1452:968:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:0:color=0xF6F1E7,setsar=1,"
                "drawbox=x=0:y=968:w=1920:h=112:color=0x3A261F:t=fill,"
                f"{common_label}[a_body]"
            ),
            f"[1:v]trim=start={B_START}:end={B_END},setpts=PTS-STARTPTS,fps=30,{common_label}[b_body]",
            "[title][a_body][b_body]concat=n=3:v=1:a=0[vout]",
        ]
    )
    FILTER_FILE.write_text(filter_text, encoding="utf-8")
    run(
        [
            str(FFMPEG),
            "-y",
            "-i",
            str(A_SOURCE),
            "-i",
            str(B_SOURCE),
            "-filter_complex_script",
            str(FILTER_FILE),
            "-map",
            "[vout]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-movflags",
            "+faststart",
            str(BASE),
        ]
    )


def burn_ass() -> None:
    ass_path = str(ASS_FILE).replace("\\", "/").replace(":", "\\:")
    run(
        [
            str(FFMPEG),
            "-y",
            "-i",
            str(BASE),
            "-vf",
            f"ass='{ass_path}'",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-movflags",
            "+faststart",
            str(CAPTIONED),
        ]
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    for path in (FFMPEG, A_SOURCE, B_SOURCE):
        if not path.exists():
            raise FileNotFoundError(path)
    make_ass()
    make_base()
    burn_ass()
    print(f"duration={FINAL_DURATION:.2f}")
    print(CAPTIONED)
    print(BASE)
    print(ASS_FILE)


if __name__ == "__main__":
    main()
