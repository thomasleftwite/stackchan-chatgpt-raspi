# Raspberry Pi用アプリ

## 会話ホストの起動・停止

リポジトリ直下からGUIを起動する。

```bash
python3 -m raspi.host --gui
```

初期状態は「APIを使わず接続だけ確認」で、固定の無音fixtureを返す。実会話用の経路も実装済みだが、実API・実音声の検証は未実施。利用者の承認後にチェックを外してAPIキーを入力すると、端末からの質問時にGemini APIを利用する。キーは保存せず、開始時に入力欄を消去し、子プロセスの環境にだけ渡す。会話終了後の永続保存や自動起動は行わない。

CLIでAPI不要の起動・停止だけを確認する場合:

```bash
python3 -m raspi.host --fixture --duration 5
```

実APIを使用するCLIは `python3 -m raspi.host --live`。対話端末でのみキーを非表示入力し、コマンド引数・ファイル・継承済み環境変数からキーを受け取らない。CLIはCtrl-C/SIGTERM、GUIは「停止」またはウィンドウを閉じる操作で自身のNodeと同じプロセスグループを終了・回収する。

待受先はNetworkManagerの実際のAP/shared接続とIPv4から決定し、上流インターフェース・公開IP・曖昧な複数アドレスを拒否する。既存のプロジェクト用Nodeを優先し、`--node` で明示パスも指定できる。Node >=22.9.0とserverのbuildが必要。Nodeの標準エラーは表示せず、標準出力からも固定イベントと安全な失敗分類だけを表示する。

## 端末Wi-Fi設定

リポジトリ直下で起動する。

```bash
python3 -m raspi.provision --gui
```

端末をWiFiManagerの設定画面にし、端末設定用SSIDとパスワードをPiのアプリへ入力する。「端末の接続先をこのPiへ設定」で、現在のPi APの認証情報をWiFiManagerへ送信する。Pi側APのパスワードを端末へ手入力する必要はない。

実行条件はeth0の有線インターネット接続と、wlan0で起動済みのPi AP。Python/Tkinter・python-dbus・NetworkManager・iproute2・curl、および既存の非対話sudo権限を使う。依存やsudoersの変更は自動では行わない。

処理中はWi-Fiが一時的に端末設定APへ切り替わる。インターネットは有線を維持し、完了・失敗のいずれでもPi APへ戻す。画面を閉じる操作は処理完了まで待つ。補助処理が強制終了した場合も、180秒checkpointによるAP復旧を試みる。

接続パスワードは表示・保存せず、補助処理へのstdinと固定IPへのPOST本文だけで扱う。機械用 `--execute-stdin` はGUIの内部処理であり、パスワードを引数やチャットへ貼らない。

`raspi.provision` は端末の接続先設定専用で、ホスト停止中に使用する。声のPC試聴・採用管理・PCM再生とAPIキーの永続保護は引き続き移植対象。ネットワーク構成と復旧は [NETWORK_AP_SETUP.md](../docs/NETWORK_AP_SETUP.md) を参照。
