# Demo Assets Package

Complete materials for creating a 45-second demo video or presenting the AI Playwright Test Generator to prospects.

## 📦 What's Included

### Scripts & Planning Docs
- **short_video_script.md** — Full 45s script with shot-by-shot breakdown and timings
- **short_video_shots.md** — Shot list (what to capture for each segment)
- **short_video_spoken.txt** — Voiceover lines (copy-paste into your teleprompter or recording notes)

### Demo Assets (to be recorded/captured)
- **demo_shots/** — Directory for your screen captures and GIFs matching the shot list
  - shot01_hook.png — Hook slide (Streamlit + CLI split-screen)
  - shot02_paste_story.png — User story entry
  - shot03_acceptance.png — Acceptance criteria close-up
  - shot04_generate_spinner.gif — Generation spinner (animated)
  - shot05_code_zoom.png — Generated code with real selectors
  - shot06_run_ui.gif — Test execution (animated)
  - shot07_results.png — Test results (both UI and CLI)
  - shot08_reports.png — Generated reports preview (HTML/JSON/screenshots)
  - shot09_export_cta.png — Export buttons + CTA

## 🎬 How to Use These Files

### Option 1: Record a Video Yourself
1. Open the app (Streamlit or CLI) on your laptop
2. Follow the shots in **short_video_shots.md** in order
3. Use **short_video_spoken.txt** as your script
4. Record using QuickTime (Mac), OBS Studio (free, any OS), or Camtasia
5. Add captions matching the script timings
6. Export as MP4 (or share as GIF set)

### Option 2: Outsource the Video
1. Send **short_video_script.md** + **short_video_shots.md** to a designer/video editor
2. They capture the shots from the running app
3. They edit with captions and voiceover (using **short_video_spoken.txt**)
4. You get back a polished 45s video

### Option 3: Use as Static Demo Pack
1. Screenshot each shot (shot01–shot09) from your app
2. Save as PNG in demo_shots/
3. Create a simple web/PDF slideshow or carousel
4. Use for LinkedIn, email demos, or in-meeting presentations

## 🎥 Recording Tips

**Software recommendations:**
- **Mac:** QuickTime (free, built-in)
- **Windows:** OBS Studio (free) or Camtasia (~$99)
- **Any OS:** ScreenFlow, Loom, or even phone screen recording

**Best practices:**
- Record at 1080p or higher
- Crop 16:9 aspect ratio for video platforms
- Capture only the app window (no taskbar/menu bar)
- Speed up the "generate" segment (shot04, shot06) 2x to keep video snappy
- Add captions in white text for readability on all devices
- Export as MP4 with H.264 codec for compatibility

## 📋 Checklist Before Recording

- [ ] App running and tested (generates tests successfully)
- [ ] Playwright browsers installed (`playwright install chromium`)
- [ ] LLM model loaded (Ollama/LM Studio active)
- [ ] Screen at 1080p+ resolution
- [ ] Quiet environment (or plan to add voiceover in post)
- [ ] All three UI pages working (Streamlit, CLI results, reports)

## 🎯 Demo Quick Reference

| Segment | Duration | Key Message |
|---------|----------|-------------||
| Hook | 5s | "From user story to test in under a minute" |
| Story Input | 10s | Non-technical, plain English |
| Generation | 15s | AI scrapes real DOM, no hallucination |
| Execution | 4s | Real browser, real results |
| Results | 2s | Fast, actionable feedback |
| Reports | 4s | Shareable (HTML/JSON) with screenshots |
| CTA | 5s | GitHub link + call to action |

**Total: 45 seconds**

## 📲 Sharing Options

Once you have the video/GIFs:

1. **YouTube Short** — Upload as unlisted, share link
2. **LinkedIn** — Excellent for reaching QA/QE professionals
3. **GitHub README** — Embed video link or GIF at top of docs
4. **Email** — Send as MP4 attachment or GIF (smaller file size)
5. **Slack/Teams** — Drop GIF directly in channel
6. **Loom/Wistia** — Host with interactive annotations

## 🔧 File Encoding for Video Platforms

- **LinkedIn, Twitter, TikTok:** MP4 (H.264), max 500MB, 16:9 or 9:16
- **YouTube:** MP4, any resolution, add captions as SRT file
- **Email/Slack:** GIF or low-bitrate MP4 (4–10MB)

## 📝 Next Steps

1. **Decide format:** Video (MP4) or animated GIF set
2. **Record the shots** using the script and shot list
3. **Add captions** and voiceover (use **short_video_spoken.txt** as script)
4. **Export** in your chosen format
5. **Test playback** on phone to verify clarity
6. **Share** on your preferred channels with this README for context

---

*Generated for: AI Playwright Test Generator demo package*
*Version: 1.0 — 2026-05-22*