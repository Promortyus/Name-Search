# 姓名学取名遍历工具

这是一个 Streamlit 小工具，用来按单姓双名的康熙笔画遍历 `1-50` 的名字笔画组合。

## 运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

macOS 本地一键启动：双击 `姓名学取名工具.app`。应用会打开 Terminal 运行 `启动姓名学取名工具.command`；如果服务已经在 `8502` 端口运行，它会直接打开浏览器，否则会自动启动 Streamlit。

如果 `.app` 无法启动，也可以直接双击 `启动姓名学取名工具.command` 作为备用方式。

## 当前公式

- 天格 = 姓氏笔画 + 1
- 人格 = 姓氏笔画 + 名一笔画
- 地格 = 名一笔画 + 名二笔画
- 总格 = 姓氏笔画 + 名一笔画 + 名二笔画
- 夫妻关系 = 姓氏笔画 + 名二笔画
- 人际关系 = 名二笔画 + 1

天干五行阴阳按数字个位数映射：`1 甲木阳`、`2 乙木阴`、`3 丙火阳`、`4 丁火阴`、`5 戊土阳`、`6 己土阴`、`7 庚金阳`、`8 辛金阴`、`9 壬水阳`、`0 癸水阴`。

## AI 候选名字

页面下方的候选名字功能采用 workflow + harness：

1. 本机 `codex --search exec` 根据勾选的笔画组合，优先从康熙笔画索引页按笔画找候选字。
2. Agent 按名字偏好筛掉明显不适合取名的字，再组合成候选名字。
3. 本地 harness 只对候选字做美名腾小批量事实查询，补充 Google Sheets 云端字库；未配置云端时补充 `characters.csv`。
4. 本地代码读取云端字库或 `characters.csv`，用确定性字库校验每个候选字的姓名学笔画。

默认选字模型是 `gpt-5.5`。如果本机 Codex 升级后想切到更强模型，可在启动 Streamlit 前设置：

```bash
export NAME_SEARCH_CODEX_MODEL=gpt-5.6-sol
```

部署到 Streamlit Cloud 后，应用运行在云端容器里，不能复用你本机 Terminal 的 `codex login` 或 `codex` 命令。因此部署版默认只能使用笔画筛选和字库校验。

如果要在部署版生成候选，可在左侧栏临时输入 OpenAI API Key。这个 Key 只保存在当前 Streamlit 会话里，不写入文件或字库；请求会从部署的 Streamlit 后端发往 OpenAI API。默认 API 模型是 `gpt-5`，可通过环境变量覆盖：

```bash
export NAME_SEARCH_OPENAI_MODEL=gpt-5
```

### Google Sheets 字库

配置下面两个环境变量后，工具会优先使用 Google Sheets：

```bash
export NAME_SEARCH_GOOGLE_SHEET_ID=你的表格ID
export NAME_SEARCH_GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
```

把这张 Google Sheet 共享给 service account 的邮箱。工具会自动使用/创建两张 worksheet：

- `characters`：正式字库，一字一行，按 `char` 自动去重。
- `verification_log`：验证日志，每次外部验证都会追加记录。

自动去重规则：

- 同一个字、同一个姓名学笔画：更新验证次数、来源和最后验证时间。
- 同一个字、不同姓名学笔画：不覆盖原值，标记为 `conflict`。
- 外部验证失败：只写日志，不进正式字库。

未配置 Google Sheets 时，会回落到本地 `characters.csv`。本地字段：

```csv
char,name_strokes,wuxing,pinyin,source,verify_count,last_verified_at,status
宛,8,土,wan,manual,1,2026-08-14T00:00:00+00:00,verified
```

美名腾查询只用于当前候选字的小批量核验，不做全量抓取；如果外部站点拒绝命令行访问，工具会回落到当前字库，不绕过限制。
