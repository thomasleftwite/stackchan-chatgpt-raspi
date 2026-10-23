# 検証計画

## 既存ベースライン（上流記録でありPiでの実測ではない）

上流 `docs/validation.md` にWindows版RC1のPython49件、Node37件、C++169項目、端末3構成ビルド、EXE自己診断15項目成功と記載。これらをRaspberry Pi版の合格結果として転記しない。

## テストマトリクス

| レベル | 試験 | 判定条件 |
| --- | --- | --- |
| L0 静的 | Python構文/型、TypeScript build、秘密値の追跡防止 | エラーなし、秘密値未含有 |
| L1 単体 | Node `npm test`、Python `unittest` | Pi上で成功 |
| L2 結合 | Node起動/停止、stdin JSON、WS fixture、PCMフレーム | 正しいイベント・フレーム境界 |
| L3 GUI | 設定・声採用・音声再生・中断 | UI応答、異常時にクラッシュしない |
| L4 ネットワーク | AP DHCP、gateway IP、AP側bind、上流から拒否 | 端末接続成功、意図しない公開なし |
| L5 実機 | 呼びかけ→質問→回答、半二重、200ms再生待機 | 端末で音声が途切れず再生 |
| L6 復旧 | AP/インターネット断、Pi再起動、Gemini認証/制限 | 安全な停止・再接続・適切な分類 |

## 実行順序

1. APIキーを使わないローカルテスト。
2. ダミー音声を使った模擬通信。
3. AP接続（インターネットなしでも可）。
4. 利用者の承認後にGemini実APIテスト（利用枠消費）。
5. 実機の反復・長時間試験。

## 記録様式

- 実施日時 / Pi OS・カーネル・Python・Node・npmのバージョン
- Git commit SHA / 実施コマンド / 成功・失敗 / 再現手順
- AP構成、端末ファーム版、端末・ホスト接続経路
- 音声・会話本文・APIキー・個人設定は記録しない

参考: https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/docs/validation.md

## 2026-10-23 環境診断

- 基準コミット: `c30d71d`（作業開始時、`origin/main` と一致）。
- Debian 13.6 (trixie)、aarch64、Python 3.13.5、Git 2.47.3。
- `python3 -m unittest discover -s tests -v`: 診断スクリプトの4件成功（欠落、Nodeバージョン境界、出力抑制、タイムアウト）。
- `python3 scripts/check_environment.py`: 終了コード1、Node/npm未導入を検出。前提未充足であり、ホストの合格判定ではない。
- 上流ソース未移管のため、Node/Windows回帰・GUI・AP・実機・外部API試験は未実施。

## 2026-10-23 作業再開・上流基準確認

- 作業開始HEAD: `cd4099c`、feature branch `feat/raspi-environment-preflight`、作業ツリーに未コミット変更なし。
- `python3 -m unittest discover -s tests -v`: 既存4件成功。
- `python3 scripts/check_environment.py`: 終了コード1、Node/npm未導入。Python 3.13.5、Git 2.47.3、aarch64を再確認。
- GitHub連携で上流mainのSHA、固定SHAのLICENSE（MIT）とserver/package.json（Node >=22.9.0）を確認。根拠と移管方針は `UPSTREAM_IMPORT.md` に記録。
- 通常のシェルからの `git ls-remote origin refs/heads/main refs/heads/feat/raspi-environment-preflight` はDNS解決失敗（github.com）。この時点ではリモート同期未確認。
- 上流の秘密設定・登録特徴・配布物に対するignoreパターンを追加。移管後の内容検査とWindows/Node回帰テストは未実施。
- ネットワーク利用を許可した `git ls-remote` 再実行は成功。origin/main=`c30d71d`、origin/feat/raspi-environment-preflight=`cd4099c`でローカル追跡SHAと一致。
- `git check-ignore -q` による12個の秘密設定/登録特徴/ビルドパスの除外、3個のソース/サンプルパスの非除外を確認。秘密値の内容検査を意味しない。
- `git diff --check`: 成功。変更差分を自己レビューし、ファーム・依存・OS/ネットワーク設定への変更がないことを確認。
- PR準備: feature branchへのローカルコミット成功。`git push origin feat/raspi-environment-preflight` はHTTPS認証情報を取得できず失敗。GitHub連携による代替のtree作成も403（Resource not accessible by integration）。リモート更新・今回の変更を含むPR作成は未実施。

## 2026-10-23 GitHub CLI認証の復旧

- 利用者が対処の実行を承認後に再確認すると、GitHub CLI 2.46.0-3が導入・認証済み。導入とログイン操作自体はエージェントでは実施していない。
- `gh api user --jq .login`: `thomasleftwite`を確認。秘密値は出力していない。
- `gh auth setup-git --hostname github.com`: 成功。
- `git push --dry-run origin feat/raspi-environment-preflight`: 成功（`cd4099c..d5a6188`）。Pi側のHTTPS認証不足は解消。dry-run時点ではリモート変更なし。
- GitHub連携アプリの書き込み403は未解消。GitHub CLI経路とは別の認証であり、この成功を連携アプリの修復とは扱わない。

## 2026-10-23 固定SHAからホストソース移管

- 開始HEAD: `2706623`（PR #1 merge済みmain）。作業branch: `feat/import-upstream-host`。
- 上流cloneのHEADを `dec249696e84f97b63eba122f33dbb624edfd484` に固定。許可リスト60ファイルの移管後バイト比較とSHA256照合は全件一致。`UPSTREAM_FILES.json` に一覧を記録。
- data、端末ファーム、登録特徴、音声、個人設定、配布物を移管していない。空の秘密設定サンプルと固定のテスト用値は保持。Google/GitHubの既知トークン形式・秘密鍵ヘッダーの検査は0件。依存定義・lockfileは上流と一致。
- Debian 13.6 / aarch64、Python 3.13.5。公式Node v22.23.4 / npm 10.9.9をGit除外の `.runtime/` に配置し、公式SHA256一致を確認（手順は `RASPI_DEV_SETUP.md`）。OSのNode・ネットワーク設定は変更していない。
- NodeのbinをPATHに加え、`npm ci --prefix server --ignore-scripts --no-audit --no-fund --cache "$PWD/.runtime/npm-cache"`: 成功、116パッケージ。依存更新は行っていない。
- `cd server; npm test`: TypeScript build成功。隔離環境ではソケット使用テスト7ファイルが失敗したが、制限外で同じコマンドを実行すると37件すべて成功。各サーバーの待受は127.0.0.1のみ。
- `cd server; node dist/host-self-check.js`: PASS、12001 PCM samples、worker=true、apiCalls=0。
- `python3 -m unittest discover -s tests -v`: 制限外で53件中49成功・2エラー・2スキップ、終了コード1。隔離環境ではGUI表示に接続できず追加3エラー（46成功・5エラー・2スキップ）。
- Pythonの残る2エラー: `test_preview_rejects_non_pcm_and_cancelled_playback_does_not_open_audio` は `ValueError: PC_AUDIO`、`test_pairing_is_persistent_encrypted_and_corruption_fails_closed` は `RuntimeError: WINDOWS_REQUIRED`。Windows専用コードを保持したためLinuxでは実行不可。上流cloneで `python3 -m unittest discover -s tests` を実行しても同じ2件がエラー（49件中45成功・2エラー・2スキップ）となり、移管による新規失敗ではない。
- PythonテストやWindows実装は変更せず、Linux向けテスト実行方針をTODOへ追加。Python全体が合格したとは扱わない。
- `PATH="$PWD/.runtime/node-v22.23.4-linux-arm64/bin:$PATH" python3 scripts/check_environment.py`: 終了コード0、ランタイム前提PASS。ホスト/実機動作の合格判定ではない。
- 移管したPythonファイルの構文確認、60ファイルのハッシュ再照合、既知秘密形式の再検査、ファーム/dataパス不在、ランタイムのGit除外を確認。`git diff --check` 成功。差分を自己レビューし、取り込んだコードとテストが固定SHAから未変更であることを確認。
- Windows実環境、wireless-hostの正常起動・停止、AP・実機・実音声・外部APIは未検証。公開待受・OS設定変更・端末書込み・Gemini API呼び出しは行っていない。

## 2026-10-23 Pythonエラー解析・テストOS条件修正

- 開始HEAD: `efc2078`、PR #2の `feat/import-upstream-host` branch。作業ツリーはクリーン。
- 再現: `PYTHONPATH=tests python3 -m unittest -v test_voice_features.VoiceFeatureTest.test_preview_rejects_non_pcm_and_cancelled_playback_does_not_open_audio test_wireless_host.WirelessHostTests.test_pairing_is_persistent_encrypted_and_corruption_fails_closed`。対象2件ともエラー（`PC_AUDIO` / `WINDOWS_REQUIRED`）。
- 仮説を切り分け: 実装と対象テストは上流ハッシュ一致。Linuxでは取消フラグの有無によらずWindows用再生を拒否。DPAPI保存も拒否しファイルを書き込まない。原因は移管の破損や再生取消の回帰ではなく、上流のWindows専用テストにOS条件が不足していたこと。
- 修正: PCMデコード検証を共通テストへ分離。Windows再生取消・DPAPI往復には `skipUnless(os.name=='nt', ...)` を付与。非WindowsではWindows DLLへ到達せず拒否することを確認し、ペアリング保存失敗で新規ファイル/一時ファイルを作らず、既存ファイルも変更しないことを追加検証。
- 修正した対象5テストの実行: 3成功・2スキップ、終了コード0。
- `python3 -m unittest discover -s tests -v`（GUI表示への接続が可能な制限外環境）: 56件中52成功・Windows専用4件スキップ、エラー/失敗0、終了コード0。
- アプリ/Node/依存/端末ファームに変更なし。58ファイルの上流ハッシュ一致を再確認し、変更したテスト2ファイルは `UPSTREAM_FILES.json` の `local_modifications` に記録。sha256は移管元の値を保持。
- `git diff --check` 成功。自己レビューで共通PCM検証が実行され、Windows専用テストの元の検証内容が維持されることを確認。Windows実環境のテストは未実施。GUI表示接続不可の隔離環境では既存GUIテスト3件の実行に引き続き制限がある。
- Nodeコード・依存が変わらないためNode 37件と自己診断は直前の実測を参照し、今回は再実行していない。実API・実機・実音声の試験も行っていない。

## 2026-10-23 wireless-host起動・停止検証

- 開始HEAD: `9649286`、PR #2の `feat/import-upstream-host` branch。利用者から端末起動済みの報告とホスト起動・停止検証の指示を受けた。
- 読み取り確認: `iw dev` のtypeはmanaged/P2P-device、APなし。`ip -j -4 address show up` の非loopbackはwlan0のみ。SSID/パスワード/IP値は出力していない。APや遠隔管理経路の設定は変更していない。
- 既存ホストはprivate IPv4のみを許可するため、AP未構築のまま端末向け待受を始めず、実APIを使わないfixtureをループバックで検証する方針とした。
- 先に追加した実プロセス試験を実行し、未変更ホストがready前に終了コード1となることを確認。fixture=true（boolean）かつ127.0.0.1/32の場合に限りループバック起動を許可する最小変更を行った。通常起動、曖昧なfixture指定、全インターフェース、公開IPは拒否する。
- `cd server; npm run build; node --test --test-timeout=10000 dist/test/wireless-host.test.js`: build成功、新規5件すべて成功。実際のNode子プロセスを起動し、以下を確認した。
  - health応答とprotocol v2、640 bytesの16kHz入力PCMからfixtureの24kHz無音PCM 1922 bytes/3フレームを受信。
  - stdin EOFで終了コード0、同一ポートでの起動・通信・停止を2回成功。
  - WS接続中のSIGTERM/SIGINTで終了コード0、WS切断、同一ポートで再起動成功。この2件はWindowsではスキップする。
  - ポート使用中の二重起動は終了コード1/failedイベントのみで失敗し、先行ホストはhealth応答を継続。
  - fixture未指定/false/文字列、広いloopback subnet、0.0.0.0/公開IP、特権ポート、null、不正JSONを拒否。標準エラーへ詳細を出していない。
- `cd server; npm test`: TypeScript buildとNode全42件成功（今回の5件を含む）。ソケットを使うため隔離制限外で実施。子プロセスにはAPIキー・NODE_OPTIONS・秘密設定パスを継承しない。
- テスト後にこのbuildを使うwireless-hostプロセスが0件であることを確認。57個の未変更上流ファイルのSHA256一致、`git diff --check`成功。変更したホストはマニフェストに記録し、差分を自己レビューした。
- Pythonは今回変更しておらず、直前の56件中52成功・4スキップを参照。Windows実測、端末/AP経由の接続、Linux GUI、実音声、Gemini実APIは未実施。端末からの入力は受け付けず、ネットワーク公開・OS設定変更・実API呼び出しは行っていない。

## 2026-10-23 有線上流固定・AP構築・Piアプリからの端末設定

- 開始HEAD: `b091908`。`feat/raspi-wired-ap` branchを作成。利用者は有線HTTPS疎通成功後の恒久上流化、AP設定、新しいPi APへ端末接続先を更新することを明示承認し、さらにPiアプリからWiFiManagerへ設定する方式への変更を指示した。
- `curl --interface eth0 ... https://github.com/`: HTTP 200。eth0はlink upで、設定前のIPv4 default metricはeth0=100 / wlan0=600だった。
- 有線profileの自動接続とIPv4/IPv6既定経路を恒久化。旧Wi-Fi client profileは自動接続を無効にし、IPv4/IPv6 never-defaultを有効化。変更後も有線HTTPS成功、IPv4/IPv6の既定経路はeth0だけ。Wi-Fi上流への自動切替は構成していない。
- wlan0のAP対応を確認し、競合しない10.42.0.1/24で2.4GHz channel 6 / 20MHz・WPA2/CCMP・NetworkManager sharedを設定。AP自動接続を有効化。実際のAPモード、wlan0のdnsmasq・DHCP範囲・APアドレス・lease fileを確認。有線HTTPSと既定経路維持も再確認した。
- 有線変更には120秒、AP作成にはwlan0限定180秒checkpointを使用し、検証成功後に確定。秘密値とバックアップはGit除外領域にのみ保存し、ディレクトリ700・認証情報ファイル600を確認。実パスワード・元の接続名・UUID・端末MACを共有記録へ出していない。
- AP上でfixtureホストを10.42.0.1:48443だけに起動。Piからのローカルhealthはprotocol v2でHTTP 200。同じPiのeth0アドレスではTCP 48443に接続できないことを確認。上流LAN上の別機器からの接続試験は未実施。
- 最初の手動設定待機では180秒間の端末参加0台で終了。その後、利用者の追加指示に合わせて手動情報表示を閉じ、`raspi/provision.py`、`provision_network.py`、`provision_ui.py` を追加した。アプリはNetworkManagerからPi AP認証情報を取得し、一時的なメモリ内クライアント接続からWiFiManagerへPOSTし、finallyでPi APを復旧する。
- 初回のアプリ実機試験は `PORTAL_FORM_MISMATCH` で送信前に停止し、AP復帰成功。実機の相対actionへの互換性を疑い、同じ相対フォームの回帰テストでエラーを再現した。許可するactionを `/wifisave` と `wifisave` だけに修正した後、実機再試験で `complete / saved=true / apRestored=true` を確認。任意のURLやリダイレクト先への送信は許可していない。
- アプリで接続先保存後の確認: AP参加1台、DHCPリース1件、端末からのhealthイベント1件。今回はPi自身からhealthを呼ばず、遠隔イベントをローカル疎通と区別した。監視用スクリプトの冒頭表示には前回の固定文言が残っていたが、この回のlocalHealthはfalse（未実施）であり、ローカルhealthの成功結果は先行試験だけを根拠とする。fixtureの実API呼び出し0、会話セッション0、終了コード0。
- 端末設定後にAPモード、IPv4/IPv6 defaultがeth0のみであること、一時接続profileが残っていないことを確認した。
- 最終レビューでアプリのcheckpointはflags=0へ変更し、無関係な新規profileを削除しない構成にした。自分の一時profileだけを削除する。最終版のprepare/checkpoint作成・破棄も実機で確認（Wi-Fi切替・端末保存はこの確認では再実行していない）。
- `python3 -m unittest discover -s tests -v`: 73件中69成功・Windows専用4件スキップ、エラー0。新規17件には失敗時AP復旧、誤経路時送信拒否、フォーム検証、相対パス、秘密値のstdin渡しとGUI欄消去、checkpoint対象限定を含む。GUI接続が可能な隔離制限外で実施した。
- Nodeコードは今回変更しておらず、直前の全42件成功を参照し再実行していない。端末ファーム書込み・保存領域初期化・呼びかけ登録変更・API課金試験は実施していない。
- 未検証: 再起動後の自動接続、別クライアントからの遠隔管理・上流LANからの拒否、Windows実行、Linux用Gemini会話GUI・秘密保存・実音声、長時間稼働。アプリからの端末Wi-Fi設定とHTTP到達の成功を、実会話の成功とは扱わない。
- コミット対象11ファイルを確認し、実APパスワードとの一致0件、既知秘密形式0件、runtime/data/端末ファームの混入0件。`git diff --cached --check`成功。自己レビュー後、今回限りの端末設定用認証ファイルは削除した。

## 2026-10-23 端末再起動後の接続復帰

- 利用者が端末を再起動し、画面に「Start PC Service」と表示されたと報告。Pi自体は再起動していない。
- 開始HEAD: `c8893ec`。読み取り確認でAP参加1台、DHCPリース1件、IPv4の既定経路はeth0のみ。
- `sudo -n env VERIFY_REMOTE_ONLY=1 python3 .runtime/network/verify-device.py`: AP側10.42.0.1:48443へfixtureホストを起動し、端末からのhealthイベント1件を確認。Pi自身からhealthを呼ばず、端末の到達と区別した。端末再起動後のAP再接続・DHCP取得・ホストへのHTTP到達が成功。
- 同じPiの有線側アドレスへのTCP 48443接続は拒否。実API呼び出し0、会話セッション0、確認後のホスト終了コード0。ホストは常駐していない。
- 「Start PC Service」はホスト停止中の待機表示と整合する。起動後の画面遷移は利用者からの確認を得ておらず、画面検証の成功とは記録しない。
- 変更はTODOと検証記録のみ。コード・OS設定・端末ファームは変更せず、Python/Nodeテストは再実行していない。Pi再起動、実API会話、実音声、会話後復帰は未検証。

## 2026-10-23 進捗整理と統合準備

- 利用者から、現状の整理・push・mergeと、その後の次工程への移行を明示指示された。
- `docs/PROGRESS.md` を追加し、TODO/READMEの古い状態表示を現在の実測に合わせた。合格結果は直前のNode42件、Python73件中69成功・4スキップ、端末/APの実測を参照し、文書変更だけのため再実行はしていない。
- PR #2/#3の先頭はそれぞれ `b091908` / `4aa7716`、競合なし、CI未設定であることを確認。統合前に文書差分・秘密値非混入を確認し、PRの依存順にmergeする。

## 2026-10-23 統合完了とLinuxホスト次工程

- 進捗整理を `fcbebe7` へコミット・push。利用者の明示承認に従い、PR #2を `ed15d4b` でmerge後、PR #3をmainへretargetし、先頭 `fcbebe7`・MERGEABLE/CLEANを再確認して `d3f000d` でmergeした。mainはorigin/mainへfast-forward同期し、新しい `feat/raspi-host-cli` branchを作成した。
- Linux専用のAP読み取り、Node実行、CLI/基本GUIを `raspi/host_network.py`、`host.py`、`host_ui.py` に追加。AP/shared接続かつ一意なRFC1918 IPv4/16〜/30だけを選び、上流・公開IP・曖昧なアドレスを拒否する。OS/ネットワーク設定は今回変更していない。
- Node >=22.9.0を検証し、自身のNodeを専用プロセスグループで起動。EOF→SIGTERM→SIGKILLで自身の子だけを終了・回収し、GUIを閉じる際も処理の終了を待つ。Nodeのstderrやprovider本文を表示せず、固定イベントと許可された失敗分類だけを取り出す。
- GUIはAPI不要のfixtureを初期状態とし、実APIを使うモードではキーを今回のセッションだけで保持。入力欄は開始時に消去する。CLIは明示の `--live` と対話端末での非表示入力を要求し、非TTYでキー入力へフォールバックしない。継承済みキー・NODE_OPTIONS・秘密設定を子へ渡さない。
- `python3 -m raspi.host --fixture --duration 3`: 実APを自動検出してready→stopped、終了コード0。
- CLIを実AP上で別プロセスとしてfixture起動後、親CLIへSIGTERMを送信: stoppedイベント、終了コード0。検証後にこのbuildのwireless-hostプロセスが0件であることを確認した。
- 新規テストはAP境界、Nodeバージョン、継承キー排除、明示キー必須、固定エラー分類、秘密情報除去、キー入力取消、非TTY拒否、CLIのシグナル、子の強制回収、実Node再起動/同一ポート再利用、GUIの初期状態とキー欄消去を検証する。実APIの接続はモックであり、課金API呼び出しは行っていない。
- 非TTYガード追加時のテストでキー入力取消が期待130に対し1となる失敗を検出。sys import漏れを修正し、最終の `python3 -m unittest discover -s tests` は88件中84成功・Windows専用4件スキップ、失敗/エラー0。
- Node/Windows共通コードや依存は変更しておらず、Node全42件は前工程の結果を参照して再実行していない。`git diff --check`とPython構文確認は成功。
- 未検証: 実APIによる会話・音声とその中断、Linuxの声管理/PC試聴、設定永続化、Pi再起動と外部LAN/Windows実測。今回のGUIは基本起動・停止の段階であり、全受入条件の達成とは扱わない。

## 2026-10-23 承認済み実API試行・認証失敗の切り分け

- 開始HEAD: `ad4e767`、`feat/raspi-host-cli`。利用者の「ok、進めて」により実API会話試験が承認された。PiのGUI非表示欄に利用者がキーを入力し、開始時に欄を消去。キー・音声・質問内容を共有ログやGitへ保存していない。
- Git除外の監督用ハーネス `python3 .runtime/live-check.py` でGUIと実ホストを起動。固定イベントのみを収集し、`ready → session-busy → turn-failed(code=AUTH) → session-idle → stopped` を確認。セッション1件、音声生成/再生の完了イベント0件。エラー後にホストを停止し、自動再試行していない。
- 利用者は「ウェイクワード無反応、画面ボタン長押しで質問モードに入り、発話後にエラー」と報告。長押しの質問はホストへ到達したが、ウェイクワード検出と実音声応答の成功とは扱わない。
- 有線インターフェースを指定したキーなしHTTPSでGoogle APIホストからHTTP 404を受信。TLS/HTTPの到達だけを確認したもので、API認証の成功ではない。
- コード読み取り: ホスト子プロセスには明示入力のGEMINI_API_KEYだけを渡し、継承済みGOOGLE_API_KEYを渡さない。SDKにはapiKeyとvertexai=falseを明示。AUTH分類は401または認証を示す本文パターンであり、今回の固定イベントに詳細statusはないため、キーの無効化・種類・制限のどれかは確定できない。
- 上流固定SHAの端末実装を読み取り確認: 呼びかけ検出はWakeWait、マイク許可、Wi-Fi接続、ホスト稼働などが条件。ホスト停止中やSleeping時は検出しない。現在の実機ファームとの一致や試行時の画面状態は未確認。端末ファーム・登録特徴は変更していない。
- Google公式キー資料を参照: https://ai.google.dev/gemini-api/docs/api-key 。キーの種類・有効性・制限確認は候補であり、今回の原因と断定していない。キーをチャットへ送らず、発行元と端末画面表示の確認を依頼した。
- 今回のリポジトリ変更はTODOと進捗・検証文書のみ。コード/依存/OS設定の変更なし。コードテストは再実行せず、直前のPython88件中84成功・4スキップとNode42件を参照。実API会話、ウェイクワード、Pi再起動、Windows実測は引き続き未完了。

### 利用者からの追加確認と生成なしの認証診断

- 利用者は、呼びかけを試した時の表示が「Start PC Service」、入力キーがGoogle AI Studio発行のGemini APIキーだったと回答。ホスト未接続時に呼びかけを検出しない上流仕様と整合するが、ホスト接続後の検出は未確認。キーの発行元だけでは有効性やLive API利用可否は確定しない。
- Git除外の `python3 .runtime/auth-check.py` を用意し、Piで非表示入力する診断画面を表示。固定HTTPS先の `GET /v1beta/models?pageSize=1` をボタン操作1回につき1回だけ実行し、生成APIを呼ばない。キーはHTTPヘッダーだけに設定し、入力欄を即時消去。プロキシ・リダイレクト・自動再試行を無効化した。
- 診断の出力はHTTP番号、固定結果、許可したGoogleエラーstatus/reasonのみ。本文・メタデータ・キーを出力せず、結果だけをGit除外のモード600ファイルに保存する。成功してもLive API会話の成功とは扱わない。
- `python3 .runtime/auth-check.py --self-test`: 秘密文字列/任意reasonの除外、既知認証理由の保持、不正JSON、200応答、リダイレクト拒否のオフライン確認が成功。実キーによる診断でHTTP 400、status=INVALID_ARGUMENT、reason=API_KEY_INVALIDを確認。Googleが今回入力されたキーを無効として拒否していることを特定。発行元が異なるという仮説は利用者回答で退けたが、誤コピー・削除済み等の内訳は不明。Pi画面での再コピー/必要なら再発行を案内した。ホスト実装の不具合を示す証拠はなく、製品コードは変更していない。

### 認証GETの再確認

- 利用者がPiの非表示入力で再確認し、固定イベント `http=200, result=MODELS_ACCESS_OK` を受信。モデル一覧への認証成功を確認した。キーの値や、同じキーを再コピーしたか新規発行したかは取得していない。
- モデル一覧の成功とLive APIの利用可否を区別し、有効なキーでホストを再起動して端末画面の遷移・呼びかけ・短い会話を再検証するよう案内。実API試験の承認は継続している。今回のGETでは音声生成APIを呼んでいない。

### 有効なキーでの呼びかけ・音声回答成功

- 同じ監督用GUIで利用者がキーをローカル入力しホストを開始。`ready → device-online → session-busy → turn-complete → voice-played → session-idle → stopped` を受信。キー再入力後の実API試行で音声生成完了と端末再生完了を確認した。初回AUTHを除外せず、失敗と再試行を別の結果として記録。
- 利用者も「呼びかけに反応し、音声で回答した」と回答。今回の呼びかけ・録音・Gemini Live・端末音声再生の単発試験は成功。端末ファームや登録特徴の変更なし。音声/質問/キーを共有ログやGitへ保存していない。
- 試験ハーネスは再生完了後にホストを停止。session-idleイベントは確認したが、連続する次の質問、実API処理中断、端末/Pi再起動後の実会話復帰、長時間稼働、声のPC試聴/保存は未検証。
- 更新はTODO、進捗、検証記録、raspi README。コード/依存/OS設定の変更なし。コードテストは直前の合格結果を参照し再実行せず、文書の差分チェックを実施する。

- GitHubでPR #4は `ad4e767` を先頭として `c581b22` へmerge済みであることを確認。後続の実機検証文書4ファイルは `docs/live-hardware-validation` branchで別PRにまとめる。実装の追加差分はない。

## 2026-10-23 開発経緯の整理と継続準備

- 利用者からTODOほか資料更新、push/merge、その後のコンパクト化と開発継続を明示指示された。
- README、TODO、PROGRESS、ROADMAP、RASPI_DEV_SETUP、ARCHITECTUREの古い未着手/未導入表示を実測に合わせ、DEVELOPMENT_HISTORYを追加。成功・失敗・未検証と承認済み運用判断を分離して記録。
- PR #5の先頭 `e90e344` がMERGEABLE/CLEANであることを確認した。今回の文書追加後に再度先頭・差分を確認してmergeする。コード変更なしのためPython/Nodeテストは再実行しない。既存結果はPython88件中84成功・4スキップ、Node42件。
- コンパクト化の継続用要約はhandoffスキルに従い一時ディレクトリへ保存し、Gitへ含めない。チャットを圧縮する操作ツールはこの接続にはないため、実際のチャット圧縮が完了したとは扱わない。
- 文書差分を自己レビューし、更新資料のローカルリンク不在0件、`git diff --check`成功。秘密値、音声、個人設定、端末ファーム、runtimeの混入なしを変更対象で確認。

## 2026-10-23 fixtureホストの反復質問・接続断回復

- PR #5を先頭 `eae235f`・MERGEABLE/CLEAN・変更文書9ファイル・CI設定なしで最終確認し、利用者承認に従い `1483b29` へmerge。mainをfast-forward同期し、`test/host-reconnection` branchへ移動。
- 継続要約を `/tmp/stackchan-raspi-handoff.md`（モード600）へ保存。チャットを圧縮する操作ツールはなく、公式の入力欄 `/compact` 操作が必要と利用者へ説明済み。実際の圧縮は未確認のまま、引継ぎ記録に基づき次工程を実施した。
- `server/test/wireless-host.test.ts` に実プロセスの回帰試験5件を追加。本番コード・Windows desktop・依存・端末ファーム・実機OS/ネットワーク設定の変更なし。子ホストは既存のキーを継承せず、127.0.0.1/32のfixtureだけを使用する。
  - 同じホストで3回の質問を完了し、各回のsession-idle・voice-playedとプロセス継続を確認。
  - 入力PCMのack後にtransportを切断し、再生完了0件のままidleへ復帰。再接続した質問は最後まで成功。
  - 出力開始後に先頭PCMフレームだけを受け取り、transport切断またはstopを送信。不完全な応答はvoice-playedを報告せず、再接続後の質問は完了。
  - 先頭出力フレームの受信後に自身のfixture子プロセスへSIGKILL。同一ポートで新ホストを起動し、質問が完了。Windowsではこの1件をスキップする。
- `PATH="$PWD/.runtime/node-v22.23.4-linux-arm64/bin:$PATH" npm --prefix server run build`: TypeScript build成功。
- `.runtime/node-v22.23.4-linux-arm64/bin/node --test --test-timeout=10000 server/dist/test/*.test.js`: 47件すべて成功、失敗/スキップ0、終了コード0。実API呼び出し・音声生成・実機操作は行っていない。
- Pythonは変更しておらず、前工程の88件中84成功・4スキップを参照して再実行しない。合成peerによるplayed通知は実スピーカー再生の証拠とはしない。実機Wi-Fi断、実API処理中断、Pi再起動、長時間稼働、Windows実測は未検証。
- 最終差分を自己レビューし、`git diff --check`成功、更新文書のローカルリンク不在0件、禁止対象の変更0件、検証後のwireless-host残存0件を確認した。

## 2026-10-23 RasPi GUIの声選択・サービス制御・端末モニター

- `raspi/host.py`、`raspi/host_ui.py`、ホスト試験と関連資料を更新。Windows/端末ファーム/既存server/依存/ネットワーク実機設定に変更なし。
- GUI: 声カタログの選択、サービス開始/停止/再開・二重開始防止、キー欄消去、終了待機、通信未確認への30秒遷移と再受信時の復帰、生成/再生/待機状態、エラー保持、秘密値の履歴除外と履歴件数制限を試験。
- 声: 初期環境へのGEMINI_VOICEの限定継承、不正なモデル/声の拒否、stdinへのvoiceコマンド限定送信、確認応答のrequest IDだけの保持を試験。稼働中の回答の声の維持と次質問への反映は既存Node VoiceControl回帰も成功。
- 初回のsandbox内Python試験ではソケット作成がPermissionError、GUIは表示接続不可でスキップ。ローカル画面/ソケットを許可して再実行し、GUI終了時の予約コールバックの回収を修正した後の `python3 -m unittest discover -s tests -v` は全95件中91成功・Windows専用4件スキップ、終了コード0。追加回帰7件はすべて成功し、Tkの終了後コールバックエラーも出なくなった。
- `PATH="$PWD/.runtime/node-v22.23.4-linux-arm64/bin:$PATH" npm --prefix server run build` 成功。`.runtime/node-v22.23.4-linux-arm64/bin/node --test --test-timeout=10000 server/dist/test/*.test.js` は47件成功、失敗/スキップ0、終了コード0。
- `python3 -m py_compile raspi/host.py raspi/host_ui.py tests/test_raspi_host_controls.py`、`git diff --check` 成功。
- 未検証: 新GUIで実端末の声を変更した際の聴感、実API会話、Windows実環境、長時間/画面サイズ別の操作。試聴・採用評価・保存とキー永続保護は未実装。端末状態は通信イベントからの観測であり、Ready/Sleepingの直接取得やWi-Fi断の確定検知ではない。

## 2026-10-23 新GUIの実AP起動停止・実音声/声変更の確認

- 開始HEAD: `2aae26c`、`feat/raspi-host-controls`（PR #7）。利用者の「ok、すすめて」により実機確認を継続。Git除外の一時GUIハーネスで製品HostWindow/HostServiceを使用し、入力キー/音声/質問本文/選択した声を記録せず固定イベントだけ観測した。
- APのfixture開始/16秒待機/停止を2回実施。どちらもreadyと停止/子プロセス回収を確認。1回目はdevice-onlineも受信。2回目は観測中のdevice-onlineなしであり、端末の再接続成功とは扱わない。
- 利用者が新GUIの非表示欄にキーを入力してホストを開始。2回ともsession-busy→turn-complete→voice-played→session-idleを受信し、最初の再生完了後のvoiceコマンドにvoice-selectedの確認応答を受信した。利用者も「2回とも回答し、声も変わった」と確認。2回目の再生後にホストを停止し、stoppedを受信。キーは保存せず、端末ファームと実機ネットワーク設定の変更なし。
- 状態表示の修正: 固定SHAの既存`src/WirelessLink.cpp`ではhealth成功後にonlineを記憶し、Wi-Fi断/会話失敗でofflineになるまで待機中のGETを再送しない。したがって30秒の未受信から切断を示唆する表示は不適切。固定時計のGUI回帰で旧表示が失敗することを確認後、「定期通知なし（現在の接続は判定できません）」へ変更。新たな通信・監視ポーリングやファーム変更は追加しない。
- 修正後の`python3 -m unittest discover -s tests -v`: 95件中91成功・Windows専用4件スキップ、終了コード0。`py_compile`と`git diff --check`成功。Node/serverは変更しておらず、直前のbuild/47件成功を参照し再実行しない。
- 未検証: 実Wi-Fi断や実API中断の復帰、Pi再起動、長時間稼働、Windows実環境。Pi自身の声試聴/採用/保存とキー永続保護は引き続き未実装。

## 2026-10-23 ホスト停止中の声試聴・採用・XDG保存

- 開始HEAD: `dee33b0`、作業branch: `feat/raspi-voice-preview`（GUIのPR #7を土台とする）。既存serverのvoice-previewを再利用し、Linux専用生成/ALSA再生、GUI試聴/採用/除外、声設定保存を`raspi/voice_*.py`に追加。Windows製品コード・server・依存・端末ファーム・実機ネットワーク設定の変更なし。
- 試聴はホスト停止中のみ。明示的な生成ボタン、Sleeping確認、非表示キー入力を必要とし、生成前にキー欄を消去。試聴中はホストの開始を禁止。PCMをファイルやGUIイベントへ渡さず、再生スレッド内で消去。生成出力650000 bytes/PCM480000 bytes/生成48秒を上限とし、自身の子プロセスグループを中断・回収する。
- 新規回帰22件: XDG保存8件（GUI/CLI共通の選択、権限700/600、未試聴/除外/revision違い、破損原本保全、シンボリックリンク/権限不備/過大データの拒否、原子的置換失敗）、生成/再生8件（PCM/ID/上限、失敗分類、時間切れ、中断、SIGTERM無視へのSIGKILL回収、音声デバイス不在）、実Tk GUI6件（完了/中断/採用/除外/復元/ホスト排他/終了回収）。合成子プロセスと一時設定だけを使用し、API・実スピーカーを使用しない。
- 最初の生成/再生試験で2件はテスト側のMock参照の誤りで失敗し、修正後すべて成功。既存のホストGUI試験22件も成功。
- 最終`python3 -m unittest discover -s tests -v`: 全117件中113成功・Windows専用4件スキップ、終了コード0。`py_compile`、`git diff --check`成功。声設定と破損バックアップのGit除外を確認。
- 実機ALSA: 既存`aplay --help`でraw/S16_LE/mono/24000Hzの指定を照合し、`play_pcm(bytearray(4800), Event())`の0.1秒無音再生がTrueで正常終了。実際の日本語サンプルの聴感の証拠とはしない。
- Node/serverは変更しておらず、直前のbuild/全47件成功を参照して再実行しない。Linux追加試験はWindowsでスキップし、Windows既存回帰は製品コード無変更のままPiで実行可能な部分だけ確認。
- 実APIの試聴・採用確認画面をPiへ表示し、利用者のローカルキー入力と明示クリックを待つ。キー/音声/個人の声選択をログに含めず、成功/保存/再読込み結果のbooleanだけ観測する。未実施時点で聴感成功とは扱わない。
- 未対応/未検証: 稼働中のホストからの試聴、キー永続保護、Windows実環境、電源断直後の実復旧。設定の破損/書込み失敗回帰と実機電源断は区別する。

## 2026-10-23 Connect上で試聴画面が見えない報告への対応

- 利用者がRaspberry Pi Connectの画面共有で画面を見られないと報告。アプリの生存、表示先、画面内座標だけを読み取り確認。Connect/アプリともwayland-0/:0、HDMI-A-1有効、画面ロックなしで、表示先の不一致は確認されなかった。非昇格sandbox内の/procではGUIを検出できず、実画面側で再確認して生存を確認した。
- 試聴の子画面は閉じていたため、同一アプリのボタンから開き直し、メイン/試聴を画面内へ配置・前面表示。Connectページの再読込み後、利用者が「ホスト画面と試聴画面が見える」と確認。Connectサービスや実機設定の変更は行っていない。再表示/再読込みで表示できた事実と、共有表示不全の根本原因の確定は区別する。
- `raspi/voice_ui.py`で試聴画面を親画面へtransientとして関連付け、画面寸法内に配置し、再操作では既存画面を再表示するよう修正。親子関係がない旧実装に対するGUI回帰の失敗を再現してから修正した。
- 修正後の`python3 -m unittest discover -s tests -v`: 118件中114成功・Windows専用4件スキップ、終了コード0。新規1件は親子関係、画面内配置、重複作成防止、閉じた後の再作成を実Tkで確認。`py_compile`、`git diff --check`成功。
- 既存の利用者画面は入力を消さずに維持。サンプル生成・聴感・採用保存は引き続き利用者の操作結果を待つ。表示確認を音声試聴の成功として扱わない。

## 2026-10-23 試聴できない報告とキー入力の改善

- 利用者から「聞こえない／エラーになった」と報告。既存の試聴ハーネスに生成/再生終了イベントがなく、固定文言の状態ラベルは「メイン画面の非表示欄へAPIキーを入力してください」。確認時点でキー未入力のguardにより生成前に止まっていた。キーそのもの・選択した声・プロバイダー本文は読んでいない。
- `raspi/voice_ui.py`の試聴画面へ、メイン画面と同じStringVarを使う非表示キー欄を追加し、未入力の案内をその画面へ変更。`raspi/host_ui.py`で試聴中/稼働中の入力欄を無効化。従来どおり生成開始時に両画面から消去し、保存しない。
- 新規GUI回帰で入力欄がない旧実装の失敗を再現後、欄の共有・非表示・生成開始時の消去・完了を確認。`python3 -m unittest discover -s tests -v`: 119件中115成功・Windows専用4件スキップ、終了コード0。`py_compile`と`git diff --check`成功。
- 利用者が開いている既存画面にも同じキー変数の非表示欄を追加。再起動や入力値の読み取りは行わず、明示操作での再試行を依頼。音声サンプルの聴感・採用保存は引き続き結果待ち。自動再試行は行っていない。

- その後、試聴ハーネスから生成/再生処理の成功1件と失敗1件を受信。利用者は「試聴完了と表示されたが聞こえない」と回答。再生プロセスの正常終了だけを聴感成功とは扱わず、採用保存も未確認のまま保持する。後続の失敗は固定ステータスが汎用案内であり、原因分類は未確定。
- Piの既定出力がダミーでないことと、ミュート/ゼロ音量でないことを分類だけ読み取り確認。ALSAのデバイス数は日本語ロケールでの文字列不一致を避け、LC_ALL=Cで再確認して出力機器の存在を確認した。設定値や機器識別名は記録せず、実機設定は変更していない。
- Connectの音声転送についてRaspberry Pi開発者の[一次回答](https://forums.raspberrypi.com/viewtopic.php?t=389450)を確認。Connectは音声を転送せず、[WayVNCの対応課題](https://github.com/any1/wayvnc/issues/209)も未完了。PC側での聴取を期待した場合にPi側の再生成功でも聞こえない経路を特定し、利用者が聞こうとした出力機器の確認を依頼。物理側の聴感は未確認。

## 2026-10-23 APIキーのセッション内再利用とWindows音声経路の調査

- 利用者が都度のキー入力を煩雑と指摘し、WindowsからConnectのターミナル接続でWindows音声資源を使うか、必要な設定手順の調査を依頼。
- GUIはアプリ終了まで非表示のキー欄をメモリ内で再利用するよう変更。連続試聴とホスト停止/再開始では再入力不要。「キーを消去」とアプリ終了で削除。処理中は明示消去を無効化する。キーのファイル/ログ保存は追加していない。
- 旧実装が2回目の試聴にキーを維持しない失敗を既存GUI試験へ組込み再現し、修正後に連続2回の試聴、ホスト再開始、非表示欄の共有、明示消去/終了消去を確認。`python3 -m unittest discover -s tests -v`: 119件中115成功・Windows専用4件スキップ、終了コード0。試験はダミー生成器・既存fixtureであり、実APIは呼び出していない。
- 現行RasPi版はPiのaplayを使用し、Windows版はWindows waveOutを使用することをコードから確認。Connectの一次資料を調査し、ターミナル/画面共有はWindowsへの音声転送経路でないと整理。Piの音声出力を使う手順、既存Windowsアプリを直接試聴に使う手順、未実装のloopback Web/SSH転送案を[REMOTE_AUDIO.md](REMOTE_AUDIO.md)へ記録した。
- APIキーのディスク永続保護、Pi版のWindowsブラウザー音声再生は未実装。Windows機での実測、物理側の聴感、採用保存は未確認。Windows/SSH/Connect/音声出力の実機設定変更は行っていない。

## 2026-10-23 端末スピーカーでの声試聴

- 開始HEAD: `c7f8f70`、作業branch: `feat/device-voice-preview`（声管理PR #8を土台とする）。利用者から「raspiでの音声再生は利用できません。端末側で試聴できるように」と指定され、PROJECT_SPEC FR-05と受入条件を更新。端末ファームの変更なしで実装した。
- `server/device-preview.ts`と`device-preview-host.ts`を追加。既存HTTP/WS v2の端末起点の録音操作を試聴開始の合図にする。録音PCMを直ちに消去し、既存VoiceControl.previewの固定テキストだけをAPIへ渡す。端末からのplayed通知とセッション終了後に専用ホストを停止・回収。サーバーから端末を起こす新命令は追加していない。
- AP側だけの待受を通常ホストと専用試聴で共通化するため、既存の境界検証をhost-boundary.tsへ抽出。localhostは明示fixture true/127.0.0.1/32だけ許可し、上流LANへの公開や実機設定変更を行わない。
- 生成中の切断を即座に扱うため、既存gemini-serverへ任意のonDisconnectを追加。通常会話のbusy/idle解除の挙動は維持し、専用試聴だけが切断時に生成ワーカーを中断する。録音をAPIへ渡さないこと、遅延PCMの消去、再生完了前の切断に成功を付けないことを試験。
- Pythonは専用Nodeエントリの選択、request IDと固定イベントだけの受信、GUI既定「端末」、状態案内、通常ホストとの排他、ユーザー中断、再生完了後だけ採用可能となる処理を追加。Piローカル試聴は任意の補助経路として保持。キーのアプリ起動中の再利用と明示消去は維持。
- `PATH="$PWD/.runtime/node-v22.23.4-linux-arm64/bin:$PATH" npm --prefix server run build`: 成功。`.runtime/node-v22.23.4-linux-arm64/bin/node --test --test-timeout=10000 server/dist/test/*.test.js`: 最終54件成功、失敗/スキップ0、終了コード0。新規7件は固定文/入力破棄、遅延PCM中断、失敗分類、実WS生成中切断、実fixture再生完了/単発、出力中断/ポート再利用、不正境界/IDを確認。
- `python3 -m unittest discover -s tests -v`: 最終124件中120成功・Windows専用4件スキップ、終了コード0。追加5件で公開イベントの秘密除外、実Node子/合成端末、Tkの端末既定/再生確認/中断/排他を確認。`py_compile`と`git diff --check`成功。API不要の試験では実端末と音声デバイスを使用しない。
- 実機: 利用者のローカルキー入力と明示的な準備・端末操作で、waiting→generating→output→preview_finished trueを2回観測。採用保存とファイル再読込のbooleanも2回成功。利用者が「端末から聞こえ、採用して保存できた」と確認した。実機の音声成功はonDisconnect追加前、追加後は実WS切断を含むAPI不要の全回帰で確認した。
- 実機試験後の専用device-preview-host残存0件を実画面側の/procで確認。キー・実音声・質問内容・選択された声はログ/PR/Gitへ含めず、試聴用録音をAPIへ送信しない。
- 未検証: 120秒の実時間待機による期限切れ、Windows実環境、実Wi-Fi断/電源断、アプリ実再起動での保存選択の利用者画面確認。保存後の再読込と一時設定でのGUI再起動回帰とは区別する。

## 2026-10-23 APIキーの暗号化保存・次回復元

- 開始HEAD: `3af804a`、branch: `feat/raspi-encrypted-api-key`。利用者から、一度設定したAPIキーを次回変更までPi内へ暗号化保管するよう指定。端末ファーム・Windows製品コード・server・依存・実機ネットワーク/OS設定への変更なし。
- `raspi/key_store.py`: 既存cryptography 43.0.0のAES-256-GCM、ランダムな256bit暗号鍵/12バイトnonce、バージョン識別子AAD。暗号文とローカル暗号鍵を別XDG領域へ保存。所有者、700/600、リンク、サイズ、dirfd固定、プロセス間ロック、原子的置換、fsyncを確認。平文一時ファイルや秘密バックアップなし。同一ユーザー/root・ディスク全体流出への保護ではない。
- GUIは起動時の復元、保存・更新・削除、開始/試聴準備の自動保存を追加。保存失敗時はホスト/生成を開始せず、固定メッセージだけを表示。終了はメモリ欄を消去し、暗号文は保持。CLIは保存キーを再利用し、未設定時だけ対話入力で保存。fixture CLIはストアを読まない。
- 新規8件: 別Pythonプロセスでの復元/更新/削除/権限/平文不在、改ざん/鍵紛失、権限/シンボリックリンク/ハードリンク、書込み失敗時の旧値保持/一時ファイル回収、不正値/過大ファイル、4プロセス同時更新、CLIの非対話復元/fixture秘密非参照、実Tkの再生成復元/マスク/削除/保存失敗時起動抑止。実API通信なし。
- 既存GUI試験のXDG保存先を一時領域へ隔離し、旧CLIの未設定/キャンセル試験は保存キーなしを明示して実ホストを開始しないよう修正。初回試験の既知ダミー保存だけを照合して除去。Tkの表示試験で一度停止したため中断し、単独試験成功後に全回帰を再実行した。
- 最終全Python回帰: `python3 -c "import unittest,faulthandler; faulthandler.dump_traceback_later(25,exit=True); result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests')); raise SystemExit(not result.wasSuccessful())"`: 132件中128成功・Windows専用4件スキップ、6.450秒、終了コード0。`git diff --check`成功。Node/server無変更のため、直前54件成功の結果を参照して再実行していない。
- 実画面: 開いていた旧GUIの入力済みキーをローカル標準入力で暗号化保存し、旧画面を正常終了。更新GUIを別プロセスで起動し、固定表示「保存済みキーを復元しました。」との一致で実キー復元を確認。キー値は読出し表示せず、引数・環境・ログ・Gitへ移していない。起動はAPI不要の接続確認状態、ホスト停止中。保存/復元だけではAPI通信なし。
- 未検証: PiのOS再起動・電源断、Windows実環境、実キーによる更新後の会話。削除はunlinkであり物理的な完全消去/外部バックアップ消去を保証しない。暗号化用ローカル鍵は削除後も保持する。

## 2026-10-23 声追加の操作案内と試聴ウィンドウの再表示

- 開始HEAD: `8656853`、branch: `fix/raspi-voice-review-retry`。候補を選んで採用保存すると未試聴の案内となり、試聴画面を閉じた後に再度開かなくなったという利用者報告。未試聴の声を採用しないルールは維持する。
- 実画面はToplevelが存在・normal・mapped、試聴状態には通常ホスト停止の案内が残っていた。ボタン再操作は受け付けた。利用者操作時に不可視となった直接原因は未確定。既存画面を画面外へ移した場合には再表示操作で戻らない欠陥を再現した。秘密欄・選択声名は出力せず、表示属性と固定状態分類だけを取得した。
- 修正前: `test_reopen_moves_existing_dialog_back_inside_screen`は画面幅1600に対し右端2400で失敗。`test_dialog_can_prepare_from_running_fixture_without_api_generation`は試聴画面内の停止・準備操作がないため失敗。未試聴での操作/閉じて再表示の試験も候補保持の入口がなく失敗。
- Pi専用GUIで「1. ホストを停止して試聴を準備（生成なし）」→「2. 選択した声を試聴」→「3. 採用して保存」を明示。準備は通常ホスト停止を待ってfixtureを解除し、生成しない。未試聴/試聴中は採用ボタンを無効にし、選択候補は試聴中ロック。同モデルの候補を閉じて開き直しても保持し、再表示ごとに画面内へ再配置する。
- 最終全Python回帰: 時間制限付きunittest discoverで137件中133成功・Windows専用4件スキップ、8.880秒、終了コード0。新規5件はListening/ビープ待ちの案内、画面外からの復帰、通常fixtureホスト稼働中から準備/試聴/保存、未試聴の採用無効化/閉じて候補保持/試聴後保存、10回連続で閉じて再表示/親子非表示からの復帰/主要ボタンの画面内配置を確認。全て一時設定とAPI不要の注入処理で実施。端末・Windows製品コード・server・依存・OS/ネットワーク設定に変更なし。
- 更新GUIへ正常終了・再起動して試聴画面を画面内に表示。キーは暗号化ストアから復元。初回の利用者再確認では画面表示に成功したが、Readyからの長押し後に無音。固定ステータスは端末開始待ち→TIMEOUTとなった。AP接続台数1、確認時のTCP接続0を読み取り取得。固定SHAの既存LocalGemini.cppではボタン解放後の環境音準備、ビープ、700ms待ち後にListeningへ進み、それ以前の入力を破棄する。Piの案内が待ちを省いていたため、Listening表示を待って発話する案内へ修正した。

- 再試行は利用者の明示ボタン操作と端末操作だけで実施し、「音声が聞こえ、採用して保存できた」と回答。固定画面表示でも保存完了を確認。自動のAPI再試行なし。その後GUIを正常終了・別プロセスで再起動し、固定文との一致でキー復元、声名を出さないboolean判定で採用声選択の復元を確認。実画面で試聴ダイアログの開く→閉じる→再表示を3回行い、3回ともmappedを確認。最新案内を反映した試聴画面を開いている。
- 未検証: 利用者操作時に画面が不可視となった直接原因、Windows実環境、画面サイズ全般、長時間運用。画面外からの復帰欠陥を修正したことと、初回の不可視原因の断定は区別する。
