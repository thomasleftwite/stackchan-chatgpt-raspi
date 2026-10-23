# 有線上流と端末専用Wi-Fi AP

2026-10-23。利用者が有線経由のインターネット疎通成功を条件として恒久化とAP設定を承認し、その後、新APへ端末の接続先Wi-Fiを更新することも明示承認した。

## 構成と実施結果

| 用途 | 設定 |
| --- | --- |
| インターネット上流 | eth0、有線。自動接続、IPv4/IPv6の既定経路、route metric 100 |
| 端末専用ネットワーク | wlan0、NetworkManagerのAP、2.4GHz channel 6 / 20MHz |
| AP認証 | WPA2-PSK / RSN / CCMP。自動生成のパスワードは文書・Git・共有ログに含めない |
| AP側アドレス | 10.42.0.1/24（設定前の経路との競合なしを確認） |
| DHCP/DNS/NAT | NetworkManagerのipv4.method=sharedで管理 |
| APのIPv6 | disabled。APは上流の既定経路にしない |
| 旧Wi-Fiクライアント | プロファイルは保持。自動接続なし、IPv4/IPv6の既定経路にしない |
| ホスト待受 | 検証時は10.42.0.1:48443のみ、trusted subnet 10.42.0.0/24、fixture=true |

eth0を指定したHTTPSはHTTP 200。設定後もIPv4/IPv6の既定経路はeth0のみで、AP起動後も有線HTTPSに成功した。無線のAPモードと2437MHz/channel 6、wlan0用dnsmasqのDHCP範囲・APアドレス・lease file設定を確認した。

上流側の既存ルーターやSSH・Raspberry Pi Connectサービス自体の設定は変更していない。再起動後の自動接続と別クライアントからの遠隔管理接続は未検証。

## 端末の接続先設定

`Stackchan-Setup` は端末自身の設定用APであり、Piが提供する接続先ではない。今回はPi側に `Stackchan-Pi` を用意し、利用者が端末のWiFiManager画面から接続先を保存する。これは当初の保存Wi-Fi保持方針に対する利用者承認済みの例外で、ファーム書込み・保存領域初期化・呼びかけ登録の変更は行わない。

利用者の追加指示により、スマホによる手動入力からPiアプリ経由の設定へ変更した。リポジトリ直下で `python3 -m raspi.provision --gui` を実行し、端末設定用SSIDとパスワードをローカル画面に入力する。パスワード欄は非表示で、Pi側APの接続情報はNetworkManagerから取得するため転記不要。

アプリはwlan0を一時的に端末設定APへ接続し、`http://192.168.4.1/0wifi` のフォームを検証して `/wifisave` にPOSTする。設定用接続はメモリ内だけに作成し、上流の既定経路にもDNSにも使わない。成功・失敗のいずれでも元のPi APへ戻す。端末用の一時接続設定は削除し、有線経由HTTPSを再確認する。GUIの権限付き補助処理は既存の `sudo -n` 権限を使い、sudoersやサービス設定は変更しない。

パスワードをコマンド引数、URLクエリ、ログへ含めず、補助処理へのstdinとWiFiManagerへのPOST本文だけで渡す。プロキシとリダイレクトを無効にして送信先を固定する。設定用パスワードやWiFiManagerの応答HTMLは保存しない。

実機では設定送信・AP復帰が成功し、端末1台のAP参加、DHCPリース、端末からホストへのhealthアクセスを確認した。確認用fixtureは終了コード0で停止済み。実API会話と実音声は未検証。

## 安全な適用と復旧

1. 有線の設定変更前に、対象プロファイルのUUIDと変更対象プロパティのみをGit除外領域へ権限600で保存。有線変更には120秒のNetworkManager checkpointを使用し、eth0指定HTTPS成功後に確定した。
2. 最初のWi-Fi AP作成にはwlan0だけを対象とする180秒checkpointを使用。失敗・未確定時は新規プロファイルを削除してWi-Fi側だけを復旧する。有線設定は対象外。旧Wi-Fiが復元されても上流の既定経路にはしない。
3. APが動作し、有線HTTPSと既定経路が維持されることを確認後、APの自動接続を有効にしてcheckpointを確定した。
4. 端末設定アプリもwlan0限定180秒checkpointを使う。通常の失敗は明示的なAP復帰で処理し、復帰失敗時はcheckpoint rollbackを要求する。アプリ最終版は他者の接続設定を消さないようグローバルの新規接続削除フラグを使わず、自分の一時プロファイルだけを削除する。強制終了時はタイムアウトでAPへ戻り得るが、メモリ内の非自動接続プロファイルが残る可能性はある。

AP停止が必要になった場合は、作業中のホストをそのPIDに対してSIGTERMで終了・回収した後、以下を実行する。有線接続は変更しない。

```bash
sudo nmcli connection modify stackchan-device-ap connection.autoconnect no
sudo nmcli connection down stackchan-device-ap
```

APを再開する場合は以下を実行する。

```bash
sudo nmcli connection modify stackchan-device-ap connection.autoconnect yes
sudo nmcli connection up stackchan-device-ap ifname wlan0
```

端末接続エラーを理由にWi-Fiをインターネット上流へ戻さない。有線設定自体を取り消す必要が生じた場合は、利用者の新しい指示を確認してから非公開のバックアップを使う。

## 記録の保護

Pi APの秘密値は `.runtime/network/`（Git除外、ディレクトリ700、認証情報ファイル600）とNetworkManagerの保護された接続設定だけに保存する。端末設定アプリは端末設定用パスワードを恒久保存しない。公開文書には実パスワード、既存SSID、プロファイルUUID、端末MAC、会話音声を記録しない。今回の一度限りの適用・表示・検証スクリプトも `.runtime/` に置き、Gitへ含めない。

## 根拠

- [NetworkManager共有IPv4設定](https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nm-settings-nmcli.html)
- [NetworkManager checkpoint API](https://networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.html)
- [checkpointの新規接続削除フラグ](https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nm-dbus-types.html)
