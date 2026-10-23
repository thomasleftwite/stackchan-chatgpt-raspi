# ローカルPCのGemini Live中継

版: 0.2.0-dev / 更新日: 2026-10-16。

目的: AtomS3R + Atomic Voice Baseの16kHzマイク入力をPCで受け、Gemini Liveの24kHz回答音声を端末へ返す。クラウド公開はユーザー指定で保留し、現在はWindows PCで検証する。

保存済みGeminiキーで `gemini-3.8-live` の利用と24kHz音声応答を確認した。さらに、生成した試験音声を16kHzへ変換し、認証付きPC WebSocketサービス→Gemini Live音声入力→24kHz回答受信まで成功。最新の自動テストは26/26成功（5秒入力上限の全経路試験を追加）。初回の詳細は [PC検証記録](../docs/GEMINI_PC_VALIDATION_2026-10-16.md)。

その後、実機COM4もGemini端末版R01 / protocol v2へ更新し、**実マイク→PC→Gemini→24kHz回答の端末再生に成功、ユーザーが日本語回答を確認した。** [実機記録](../docs/GEMINI_DEVICE_VALIDATION_2026-10-16.md)を参照。現段階は1接続につき1質問・1回答で、会話履歴、連続録音、発話割込みは含まない。

実機向けの起動は案件ルートの `Start-Gemini-Device.cmd`。`local-gemini.ts` / `tools/run_gemini_device.py` が家庭内LANの空きポートとランダム端末トークンを用意しUSB経由で端末RAMへ設定する。R05はGemini PC readyを確認→長押し→Release to recordで離す→開始音後に約1秒静かに待つ→Speak now表示後に発話。約0.7秒無音で送信する可変長で、上限は前後の無音込み5秒。準備中に話すと環境音測定が影響を受けるので表示を待つ。[可変長の検証](../docs/VARIABLE_UTTERANCE_VALIDATION_2026-10-16.md)を参照。PC画面でstop、または最長約10分で停止。PC停止等でRelease表示に残る症状を修正し、可変長の実質問にも成功した。[録音開始の修正](../docs/RECORD_START_FIX_2026-10-16.md)。ツールは5秒ごとにGEM PING、正常停止時にGEM STOPを送る。端末は20秒で稼働通知が切れたことを表示する。前回の管理下の試験はstop済み。その後ユーザーが起動用ファイルの一度の終了と、再起動後の正常動作を報告した。終了原因は未解明で、約10分の期限終了との区別も未確認。[開発進捗](../docs/DEVELOPMENT_PROGRESS_2026-10-16.md)を参照。以下の `Start-Gemini-PC.cmd` はPC単独向けでUSB設定をしない。

現在の実機は顔表示Stage1 R01へ更新済み。起動直後はSleeping、短押しでReady、PC onlineを確認してから長押し・離す操作で質問する。Readyで短押しするとスリープへ戻る。まだウェイクワードを検出しない。新ファームウェアでの実機音声回帰は未実施、顔表示と短押し切替はユーザー確認済み。[段階開発](../docs/FACE_MODES_STAGE1.md)を参照。上記R05の会話成功は前段の結果。

## PC監視ツールの更新（2026-10-19）

現在の端末は呼びかけ統合Stage2 R01。PC監視レポートはversion 2で、固定分類の終了理由/段階/経過時間、子サーバ終了コード、端末停止応答の有無を記録する。USBの分割行を復元し、最大512 byteずつ読み込む。正常期限/stopとUSB失敗/停止未確認を区別し、例外本文やトークンは出さない。診断ホスト試験は `python -m unittest discover -s tests -p test_gemini_coordinator.py -v` を案件ルートで実行する。USB接触不良の可能性についての原因究明は利用者指示で保留。[検証と未確認範囲](../docs/USB_MONITOR_DIAGNOSTICS_2026-10-19.md)。

## 起動

Node.js 22.9.0以降（試験環境24.15.0、npm 11.14.0）を使用する。このフォルダで初回のみ依存を準備する。

```text
npm ci --ignore-scripts
npm test
```

案件ルートの `Start-Gemini-PC.cmd` を開くと、ビルド→非公開設定の初期作成→サービス起動を行う。終了はその画面でCtrl+C。自動起動やWindowsサービス登録は行わない。

同等の手動手順:

```text
npm run build
npm run gemini:init
npm run gemini:serve
```

既定は `http://127.0.0.1:8080/healthz` と `ws://127.0.0.1:8080/live`。ヘルスは `{"status":"ok","mode":"gemini-live","protocolVersion":2}` を返す。初期設定はPC内限定。実機対応時に `.env` のHOSTをこのPCの家庭内LANのIPv4へ変更し、端末側のURL/認証設定も用意する必要がある。LAN内は平文WSで、WSS/TLSは未対応。ファイアウォール設定は変更していない。

## キーと設定

Geminiキーは既存の `../data/secrets.json` の `gemini_api_key` から読む。OpenAIキーは不要。`GEMINI_API_KEY` 環境変数があればそちらを優先する。モデルは `GEMINI_MODEL`、既定 `gemini-3.8-live`。

`gemini:init` は `.env` がなければランダムな64桁の `DEVICE_TOKEN`、HOST、PORTだけを作成し、既存ファイルを上書きしない。Geminiキーは複製しない。DEVICE_TOKENは端末認証専用。キーやトークンをチャット・URL・ログへ載せない。`.env.example` は空の見本。実設定、バックアップ、node_modules、dist、`.pio` はGit対象外。

## 検証コマンド

```text
npm test
npm run gemini:check
npm run gemini:local-check
```

- `npm test`: 実APIを呼ばず、型検査・PCM形式・認証・順序・上限・期限・切断・credit/drain・秘密設定読込みを試験する。
- `gemini:check`: モデルのHTTP確認と短いテキストからのLive音声応答。Live接続1回。
- `gemini:local-check`: 試験用の音声をLiveで生成し、16kHzへ診断用変換してPCサービス経由でLiveへ入力。24kHz回答を検査する。Live接続2回。再生完了通知は模擬で、スピーカーや人の聴取を確認するものではない。

実API試験はアカウントのAPI利用枠を消費する。利用残量・料金はこの試験では確認していない。課金設定の変更は行わない。音声・文字起こし・生のAPIエラーを保存せず、安全な数値と状態だけを出力する。

## Gemini用protocol v2

HTTPサーバの `/live` upgrade前に `Authorization: Bearer <DEVICE_TOKEN>` を検査する。クエリ付きURLや別パスを拒否。同時1接続、処理中の切断後も前のAPI処理が終わるまで新規接続を拒否する。

1. `ready`: mode=gemini-live、protocolVersion=2、入力16kHz/出力24kHzと上限を通知。
2. 入力binary: 12 byte little-endianヘッダ（generation:u32、sequence:u32、sampleCount:u16、flags:u16=0）+ signed16bit mono PCM。最大640 byte/フレーム、連番0開始。`input_ack` を受けて次を送る。最大250フレーム・80,000サンプル（5秒）。
3. JSON `input_end`（generation付き）で入力終了。`thinking` 後にGeminiへmanual VADのactivityStart→16kHz raw PCM→activityEndで送る。WAVヘッダは付けない。
4. `output_start` で24kHz回答のsamples/framesを通知。端末はgeneration/sequence付き `next` を1つ送り、最大960 byteの回答フレームを1つ取得する。世代・連番・総量を照合する。
5. 最終フレーム後の `output_end` を確認し、実際の再生キューが空になってから `played`（generation/samples付き）を送る。サーバは `complete` とclose1000。PC試験クライアントのplayedは模擬通知。

回答は最大240,000サンプル（10秒）をRAMに蓄積してから配信する。接続90秒、入力無通信10秒、API処理30秒+子プロセス終了猶予2秒、メッセージ1,024 byte、入力65,536 byte/秒、送信滞留32,768 byteの上限を設ける。Gemini SDK 2.30.0の接続待ちを確実に打ち切るため、API処理を子プロセスで分離し期限超過時にその子だけを終了する。自動再試行は行わない。

## 既存の診断機能

`npm start` は従来のecho用 `server.ts` を起動する別コマンド。入力16kHzをそのまま返すprotocol v1診断で、Gemini回答ではない。今回の起動には `gemini:serve` を使う。

`local-lan.ts` と `tools/run_lan_probe.py` は実機LAN診断専用。150フレーム限定で16→24kHz補間した自声を端末で自然に再生できた。[LAN検証記録](../docs/LAN_PCM_VALIDATION_2026-10-16.md)を参照。この成功と今回のPC/Gemini試験を合わせても、実機Gemini統合の合格には数えない。

Cloud Run用Dockerfileは従来echoだけの許可リストで、新しいGemini PC機能を含まない。Dockerビルド・公開は未検証。[クラウド検討](../docs/AI_STUDIO_CLOUD_FEASIBILITY_2026-10-16.md)と[構成案](../docs/GEMINI_LIVE_ARCHITECTURE_REVIEW.md)は履歴として保持する。


2026-10-19追記: 子サーバ終了/Ctrl+CでもUSBを閉じる前に端末へGEM STOPを送るよう修正。診断16件成功。強制終了/USB切断は端末側の20秒期限で検知する。利用者はPC単独用Start-Gemini-PC.cmdで20秒以上Onlineが残ったと報告し、追加監視せず次回問いかけ時の接続結果で表示更新する現状を許容。原因解明/停止復帰の合格とは区別する。実機の起動/再設定にはStart-Gemini-Device.cmdを使う。[確認記録](../docs/PC_SERVICE_STATUS_2026-10-19.md)。
