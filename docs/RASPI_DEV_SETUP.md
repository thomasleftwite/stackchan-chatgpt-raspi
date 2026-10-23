# Raspberry Pi 5 開発環境と引継ぎ

## 前提

- Raspberry Pi 5、Debian 13 (trixie)、aarch64。
- VS Code 1.134.0 ARM64、Codex拡張 `openai.chatgpt@26.1007.21434`、Codex CLI `0.163.0` は会話中の報告で確認済み。
- 2026-10-23: GitHub repoとorigin同期を確認。Debian 13.6 / aarch64、Python 3.13.5、Git 2.47.3。プロジェクト用Node 22.23.4 ARM64 / npm 10.9.9を導入済み（システムPATHは未変更）。

## 新規リポジトリが作成された後

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/thomasleftwite/stackchan-chatgpt-raspi.git
cd stackchan-chatgpt-raspi
code .
```

## 最初の確認

依存のインストールやOS設定の変更を行わない診断：

```bash
python3 scripts/check_environment.py
python3 -m unittest discover -s tests -v
```

診断はPython/Git/Node/npmを確認し、Node >=22.9.0を要求する。終了コード0はランタイムの前提充足、1は不足または確認失敗。ハードウェア・ホスト動作の検証は別途必要。


```bash
uname -m
cat /etc/os-release
python3 --version
node --version
npm --version
git status --short
```

## プロジェクト用Node ARM64環境

2026-10-23: 公式Node v22.23.4 ARM64 / npm 10.9.9を `.runtime/node-v22.23.4-linux-arm64/` に配置して検証した。システムのNodeやPATH設定は変更していない。Debianの標準候補Node 20.19.2は上流要件を満たさない。

別のcloneで同じ環境を用意する場合は、リポジトリ直下で以下を実施する。既存ランタイムがある場合は取得・展開を省略する。

```bash
mkdir -p .runtime
curl --fail --location https://nodejs.org/dist/v22.23.4/node-v22.23.4-linux-arm64.tar.xz -o .runtime/node-v22.23.4-linux-arm64.tar.xz
echo '6287aa46b6c375d816e63ae66d024fbbfd70404825aabdfdf898a970871d2f4b  .runtime/node-v22.23.4-linux-arm64.tar.xz' | sha256sum --check -
# 上の照合が成功した場合のみ展開する。
tar -xJf .runtime/node-v22.23.4-linux-arm64.tar.xz -C .runtime
export PATH="$PWD/.runtime/node-v22.23.4-linux-arm64/bin:$PATH"
node --version
npm --version
python3 scripts/check_environment.py
```

SHA256は取得時の公式 `https://nodejs.org/dist/v22.23.4/SHASUMS256.txt` と照合済み。`.runtime/` はGit除外で、依存キャッシュを含め配布物には含めない。上記exportは現在のシェルだけに適用する。

## Nodeテスト（ソース移管済み）

```bash
cd server
npm ci --ignore-scripts
npm test
node dist/host-self-check.js
```

Nodeテストと自己診断はループバック通信とfixtureを使用し、Gemini APIを呼ばない。`npm run gemini:check` 等の実APIコマンドは別途承認が必要。

起動・停止だけを再確認する場合は、build後に `node --test --test-timeout=10000 dist/test/wireless-host.test.js` を実行する。実際の子プロセスでHTTP/WS・PCM、stdin EOFによる終了、同一ポート再起動、二重起動失敗を検証する。LinuxではSIGTERM/SIGINTによる通信中の停止も確認し、Windowsではこのシグナル2件をスキップする。テスト後にホストは常駐しない。

## Pythonテスト（ソース移管済み）

```bash
cd ..
python3 -m unittest discover -s tests -p 'test_*.py'
```

Python依存を入れる場合はOS標準環境を汚さず、venvを使用する。Nodeバージョンは `server/package.json` の要件を確認する。

今回のPiではTkinterとpyserialが既存環境で利用可能だった。追加インストールは行っていない。GUIテストには表示先への接続が必要。Windows音声/DPAPI専用テストはLinuxでは計4件をスキップし、共通PCM検証と非Windows環境での安全な拒否を別途検証する。LinuxホストCLI/GUI追加後のPiで88件中84成功・4スキップ。表示先に接続できない隔離環境ではGUIテスト3件が別途エラーとなる。Windows版の実行結果やLinux用ホスト実装の完成とは区別する。

## AP構築時の注意

Pi Connectを使った遠隔接続が切れる恐れがあるため、無線インターフェースの設定をいきなり変更しない。接続経路・バックアップ・復旧手順・ローカル操作手段を先に確保する。現在は承認済みのeth0有線上流 + wlan0端末AP。端末接続失敗時もWi-Fi上流へ切り替えない。変更・復旧手順は [NETWORK_AP_SETUP.md](NETWORK_AP_SETUP.md) を参照。

## Codexへの初回指示

`AGENTS.md` と `docs/PROJECT_SPEC.md` を読んでください。最初に環境調査とテストを実施し、変更前に差分計画を提示してください。Windows版の互換性を維持し、ESP32-S3ファームウェア・ネットワーク設定・秘密情報は明示承認なしに変更しないでください。
