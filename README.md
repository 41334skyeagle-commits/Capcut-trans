# CapCut 字幕簡體轉繁體工具

這是一個 Python/Tkinter 桌面程式，可將 CapCut 專案中的字幕由簡體中文轉成繁體中文，並支援手動逐條編輯。

## 功能

- 匯入資料夾：選擇 CapCut 專案根目錄、CapCut 草稿資料夾，或一般字幕資料夾。
- 讀取現有字幕：支援讀取 CapCut `draft_content.json` 與 `.srt` 字幕檔。
- 重新整理：重新掃描匯入資料夾中的專案與字幕檔。
- 儲存：將修改後的字幕寫回原檔，第一次儲存會建立 `.bak` 備份。
- 左欄顯示專案列表：顯示找到的 CapCut 專案或 SRT 字幕檔。
- 右欄顯示字幕：顯示每一條字幕的開始時間、結束時間與字幕內容。
- 手動編輯：點擊或按 Enter 可開啟單條字幕編輯視窗。
- 批次轉換：可對目前專案的全部字幕執行簡體轉繁體。

## 安裝

建議使用 Python 3.10 或更新版本。

```bash
python -m pip install -r requirements.txt
```

`opencc-python-reimplemented` 會提供較完整的簡繁詞彙轉換。如果沒有安裝 OpenCC，程式仍可啟動，但只會使用內建的簡易字表，轉換品質較有限。

## 使用方式

```bash
python capcut_subtitle_converter.py
```

1. 按「匯入資料夾」選擇 CapCut 專案或字幕資料夾。
2. 在左欄選擇要處理的專案或字幕檔。
3. 確認右欄列出的開始時間、結束時間與字幕內容。
4. 按「全部簡轉繁」執行批次轉換，或點擊單條字幕開啟手動編輯。
5. 按「儲存」寫回檔案。

## CapCut 檔案支援說明

程式會掃描匯入資料夾底下所有名為 `draft_content.json` 的 CapCut 草稿檔，並嘗試從 `materials.texts` 讀取字幕文字，再從 `tracks[].segments[]` 對應字幕的開始與結束時間。

不同版本的 CapCut 草稿格式可能略有差異；儲存時程式會盡量只更新已辨識的文字欄位，不刪除未知欄位。
