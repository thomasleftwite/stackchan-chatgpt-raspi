# Raspberry Pi 5 開発環境と引継ぎ

## 前提

- Raspberry Pi 5、Debian 13 (trixie)、aarch64。
- VS Code 1.134.0 ARM64、Codex拡張 `openai.chatgpt@26.1007.21434`、Codex CLI `0.163.0` は会話中の報告で確認済み。
- Piのnode/npm、GitHub新規repoの存在、Pi上のテスト実行は未確認。

## 新規リポジトリが作成された後

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/thomasleftwite/stackchan-chatgpt-raspi.git
cd stackchan-chatgpt-raspi
code .
```

## 最初の確認

```bash
uname -m
cat /etc/os-release
python3 --version
node --version
npm --version
git status --short
```

## Nodeテスト（上流ソースが移管済みの場合のみ）

```bash
cd server
npm ci --ignore-scripts
npm test
```

## Pythonテスト（上流ソースが移管済みの場合のみ）

```bash
cd ..
python3 -m unittest discover -s tests -p 'test_*.py'
```

Python依存を入れる場合はOS標準環境を汚さず、venvを使用する。Nodeバージョンは `server/package.json` の要件を確認する。

## AP構築時の注意

Pi Connectを使った遠隔接続が切れる恐れがあるため、無線インターフェースの設定をいきなり変更しない。接続経路・バックアップ・復旧手順・ローカル操作手段を先に確保する。AP用のUSB Wi-Fiまたは有線LAN上流を優先候補として比較する。

## Codexへの初回指示

`AGENTS.md` と `docs/PROJECT_SPEC.md` を読んでください。最初に環境調査とテストを実施し、変更前に差分計画を提示してください。Windows版の互換性を維持し、ESP32-S3ファームウェア・ネットワーク設定・秘密情報は明示承認なしに変更しないでください。
