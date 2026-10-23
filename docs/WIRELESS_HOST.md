# USBに依存しないホットスポット構成

2026-10-21更新: 利用者がホットスポット参加を信頼条件とする方式へ変更を指示。0.5.0-preview.1では4行コードとアプリPSKを廃止した。[現行方式と検証](HOTSPOT_TRUST.md)を参照。以下は0.4.0-preview.1の設計履歴。

2026-10-20 / 0.4.0-preview.1。ユーザー承認の構成: PCは共有Wi-Fi、端末はPCのモバイルホットスポット。既存のWiFiManager、顔表示、呼びかけ登録/検出、手動質問、音声再生、USB診断を維持する。

## 完成形へ向けた今回の実装

端末はWi-FiのDHCPゲートウェイをPCとしてTCP48443へWSS接続する。IP固定・起動ごとのUSB設定転送は不要。初回は端末固有の無作為128bitキーを画面4行×8桁で表示し、ユーザーがPCへ登録する。キーを設定APや平文ネットワーク経由では配らない。
標準のTLS1.2 DHE-PSK-AES128-GCM-SHA256を用い、双方の鍵所持をTLSハンドシェイクで認証する。証明書を使わない方式のため、証明書配布・端末時計依存・証明書検証の省略は発生しない。Node.js標準TLSとESP32 WiFiClientSecureのPSK APIを利用する。独自暗号プロトコルは作らない。
HTTPにもBearer認証を要求し、既存protocol v2の半二重音声通信を維持。セッションごとのトークン配布は不要。Gemini APIキーはPCにのみ保存し端末へは渡さない。

## 保存・失効・移行

PC: pairing.jsonをWindows DPAPIで保護し、同じWindowsユーザーで復元する。APIキーの任意保存は既存どおり。配布物にユーザーの認証情報は含めない。
端末: NVSの独立したstacklink領域へキーと初回接続確認を保存。SPIFFSの登録音声特徴・Wi-Fi用領域を消去しない。物理取得への対策としてのフラッシュ暗号化は未実装。
再起動後は同じキーで自動接続。Sleeping中に5秒で離す呼びかけ登録は維持し、10秒長押し→離す操作で端末認証だけを更新する。PCの「端末登録を解除」はPC側保存を削除する操作であり、キーを端末側でも更新することで以前のPCを失効させる。

## 接続確認

最初の認証済みHTTPSチェックでPC接続を確認する。常時のTLS再接続は待受マイクを途切れさせるため行わず、Wi-Fi断・実会話の通信失敗後に再試行する。PC停止後、次の質問までOnline表示が残る場合があるという既存の許容方針を維持する。
ホストはユーザーが停止するまで稼働。USB診断だけ約10分の旧経路を残す。USBモードは開発用の平文WSで、明示的なUSB設定コマンドで切り替える。通常の無線モードは平文へフォールバックしない。

## 配布とWindows受信許可

EXEの一時展開先の変化を避けるため、同梱Nodeをユーザー別のハッシュ付き固定ディレクトリへ配置する。起動ごとに同梱実行ファイルとのハッシュ一致を確認し、改変があれば復元する。
ホットスポット側IPへだけバインドし、tools/configure_wireless_firewall.ps1で中継実行ファイル/TCP48443/当該インターフェース/当該サブネットに受信を限定する。スクリプトは既定で計画表示のみ、-Applyで初めて変更する。ホストやスクリプトが上流共有Wi-Fi全体への受信を自動許可することはない。
固定IPは要求しない。ただしホットスポットのサブネット/インターフェースまたは同梱Node更新で実行ファイルのハッシュが変わる場合は受信規則の更新が必要。

## 検証範囲

Python設定/暗号化/実行パスの回帰34件成功。Node24.15.0でサーバー28件成功（誤PSK拒否、認証なし拒否、TLSでのPCM往復を含む）。端末版ビルド成功。Node22の旧テスト実行はファイル全体の10秒制限で2ファイルが時間切れとなり、配布版Node24で全件成功を確認。
追加C++ホスト回帰・EXE自己診断・実機のホットスポット接続とTLS会話・再起動後の認証保持は、結果を下に追記する。Windows設定変更はまだ行わない。

## 根拠

- Node.js TLS-PSK: https://nodejs.org/download/release/latest-v22.x/docs/api/tls.html#pre-shared-keys
- ESP32の固定版ライブラリ: framework-arduinoespressif32のWiFiClientSecure.h / ssl_client.cpp（setPreSharedKey）
- Windowsホットスポット: https://support.microsoft.com/en-gb/windows/experience/connectivity-networking/use-your-windows-device-as-a-mobile-hotspot

PSKはパスワード由来にせずesp_fill_randomの16bytesで生成する。設定APの12345678をPSKに流用しない。WebSockets2.7.3にはPSK設定の公開APIがないため、既存の版固定・ガード付きビルド補助でESP32のsetPreSharedKey呼出しだけを追加し、ソースが変わった場合はビルドを止める。

## 最終結果と次の承認

C++144項目（既存130、Wi-Fi4、無線認証10）、Python34、サーバー28、3構成ビルド、最終EXEの自己診断10項目が成功。C++テストはプロジェクト内のZig0.15.2でWindows SDK不足を回避して実行。Pythonのステージ退避テストが一度WinError5で失敗したが、同じコードで再試行して成功した（同期/スキャンによる一時ロックの可能性、原因確定ではない）。
配布EXE/ZIPはreleases/StackchanHost-0.4.0-preview.1-win-x64。配布物はGit除外。コードとランチャーソースハッシュ一致、キー非同梱、TLSを含む自己診断10項目成功を確認。
新端末版の導入は自動承認審査で拒否されたため未実施。理由は認証キーの永続化と通信方式を変える実機導入に明示確認が必要という判断。端末は既存の固定パスワードWiFiManager付きR07のまま。新イメージは.pio/firmware-snapshots/gemini-wireless-v1.binに保存し、明示的な導入承認を待つ。
ホットスポットとWindows受信規則は未変更。実機の新構成接続/会話/再起動後保持は未検証で、PC上のTLS往復と区別する。
