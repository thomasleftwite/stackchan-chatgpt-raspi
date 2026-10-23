# Raspberry Pi用の端末Wi-Fi設定アプリ

リポジトリ直下で起動する。

```bash
python3 -m raspi.provision --gui
```

端末をWiFiManagerの設定画面にし、端末設定用SSIDとパスワードをPiのアプリへ入力する。「端末の接続先をこのPiへ設定」で、現在のPi APの認証情報をWiFiManagerへ送信する。Pi側APのパスワードを端末へ手入力する必要はない。

実行条件はeth0の有線インターネット接続と、wlan0で起動済みのPi AP。Python/Tkinter・python-dbus・NetworkManager・iproute2・curl、および既存の非対話sudo権限を使う。依存やsudoersの変更は自動では行わない。

処理中はWi-Fiが一時的に端末設定APへ切り替わる。インターネットは有線を維持し、完了・失敗のいずれでもPi APへ戻す。画面を閉じる操作は処理完了まで待つ。補助処理が強制終了した場合も、180秒checkpointによるAP復旧を試みる。

接続パスワードは表示・保存せず、補助処理へのstdinと固定IPへのPOST本文だけで扱う。機械用 `--execute-stdin` はGUIの内部処理であり、パスワードを引数やチャットへ貼らない。

このアプリは端末の接続先設定専用。Gemini会話ホスト、音声再生、APIキー保存のLinux GUIは引き続き移植対象。ネットワーク構成と復旧は [NETWORK_AP_SETUP.md](../docs/NETWORK_AP_SETUP.md) を参照。
