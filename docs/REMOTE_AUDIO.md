# Connect経由の操作と音声の再生先

更新: 2026-10-23。

## 現在の推奨手順: 端末で試聴

利用者からPiでの音声再生を使えないと指定されたため、試聴先の既定を端末へ変更した。GUIで専用待受を準備し、Readyの端末で長押しし「Release to ask」で離した後、準備とビープ終了を待ち「Listening」で短い一言を話すと、固定の日本語サンプルが端末のスピーカーから再生される。録音は破棄しAPIへ送らない。Pi/Windowsの音声出力やConnectの音声転送は不要。操作と制約は [Piアプリ](../raspi/README.md#端末で声を試聴採用保存) を参照。

## Piローカル試聴の動作

WindowsからConnectのターミナルや画面共有を使っても、RasPi版ホストはPi上で動く。補助経路のPiローカル試聴は`raspi/voice_preview.py`のALSA/aplayでPiの音声出力へ送る。Windowsのサウンドデバイスを利用する処理はない。端末との会話回答は従来どおり端末のスピーカーへ送る。

Connectのターミナル接続は音声転送を提供しない。画面共有についても、[Raspberry Pi開発者の説明](https://forums.raspberrypi.com/viewtopic.php?t=389450)では音声のストリーミングに対応しておらず、[WayVNCの音声対応課題](https://github.com/any1/wayvnc/issues/209)も未完了。ConnectやWindowsの音量設定を変えるだけではPiの試聴音声をPCへ転送できない。

## 補助経路: Piの音声出力が使える場合の手順

1. Piに接続した音声対応HDMIモニター、または利用できるUSB等の音声出力を用意する。
2. Piのデスクトップの音声メニューで、その出力先とミュート/音量を確認する。PC側の音量ではなくPi側の出力を確認する。
3. RasPiホストを停止し、端末をSleepingにして、声の試聴画面を開く。
4. APIキーを非表示欄へ1度入力し、候補を選んで明示的にサンプルを生成・再生する。実API利用枠を消費する。
5. Pi側のスピーカーで日本語を最後まで確認してから採用する。処理の正常終了だけを聴感成功とはしない。

物理的な接続と出力先の確認が必要。今回の調査では音声設定は変更していない。

## 既存Windows版でWindowsのスピーカーを使う手順

Windows版ホストアプリが既に動く環境をお持ちの場合に使える。Pi版の音声を転送する方法ではなく、Windows版の試聴機能を直接動かす方法。

1. Windowsの「設定 → システム → サウンド → 出力」で使用するスピーカー/ヘッドホンを選ぶ。ミュートと音量も確認する。[Microsoftの手順](https://support.microsoft.com/en-us/windows/hardware/audio/fix-audio-issues-when-no-sound-plays-from-speakers-or-headphones-in-windows)
2. **Windows上で**既存Windows版ホストアプリを起動する。Connect内でRasPi版を起動する操作とは異なる。
3. Gemini APIキーとモデルを指定し、「声を確認・管理」を開く。ホストサービスを開始せず、端末はSleepingにする。
4. 候補を選びSleeping確認をチェックして、日本語サンプルを生成・試聴する。Windows版は`desktop/voice_preview.py`のWindows waveOutを使用する。
5. 日本語を確認して採用/除外する。Windows版の評価・選択はWindows側に保存され、RasPi版へは自動同期されない。

この手順は既存Windows実装の確認に基づく。利用者のWindows機での試聴・出力先は未検証。Windows版の新規配布やインストールは今回実施していない。

## PiホストのままWindowsで試聴する構成案

これは現時点で未実装。Connectの設定追加では実現しない。

1. Pi側に音声サンプルをメモリから返す、loopback限定の試聴Web UI/APIを追加する。
2. 既存SSHへ到達できるLAN/VPN環境で、WindowsからSSHのローカル転送を作る。Connectのリモートシェルと直接SSH接続は別の接続経路。
3. Windowsのブラウザーで転送先のlocalhostを開き、クリック操作で音声を再生する。再生はWindowsのブラウザー音声出力を使う。
4. 採用・除外の結果はPiへ反映し、音声・APIキーをディスクへ保存しない。

この案には追加実装と認証・中断・再生完了・Windows側の回帰検証が必要。既存のAP限定ホスト待受を上流LANへ公開する変更は行わない。SSH/ファイアウォール等の実機設定が必要となった場合は、AGENTS.mdに従って計画・復旧手順と承認を先に扱う。今回、待受追加・SSH設定・Connect設定・依存インストールは実施していない。

## APIキーの入力回数

RasPi GUIは**アプリを閉じるまで**非表示欄のキーをメモリで再利用する。連続試聴とホストの停止/再開始に再入力は不要。「キーを消去」またはアプリ終了で入力を削除する。処理中は消去ボタンを無効化し、終了時には処理を止め子プロセスも回収する。

Piやアプリの再起動後も使う永続保存は未実装。設定ファイル、ログ、Gitにはキーを書かない。
